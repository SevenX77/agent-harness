import logging
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from deerflow.config import get_app_config
from deerflow.reflection import resolve_class

logger = logging.getLogger(__name__)

# MODIFIED: Model Resolver hook for dependency injection.
# External code sets this to intercept all model creation calls.
# Signature: (name: str | None, thinking_enabled: bool, **kwargs) -> BaseChatModel
_model_resolver_hook: Callable[..., BaseChatModel] | None = None


def set_model_resolver_hook(hook: Callable[..., BaseChatModel] | None) -> None:
    """Register an external Model Resolver to intercept create_chat_model calls.

    This allows the outer GraphAgent layer to inject its own model selection
    logic (role-based routing, provider failover, circuit breaking) without
    deerflow/ importing any graph_agent/ modules.
    """
    global _model_resolver_hook
    _model_resolver_hook = hook
    logger.info("Model resolver hook %s", "registered" if hook else "cleared")


def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    *,
    _bypass_hook: bool = False,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance from the config.

    Args:
        name: The name of the model to create. If None, the first model in the config will be used.
              When a model_resolver_hook is set, `name` is treated as a role/tier name
              and delegated to the external resolver.
        _bypass_hook: If True, skip the model_resolver_hook and use DeerFlow native
              model creation directly. Used by ModelResolver's fallback path to avoid
              global hook mutation and associated thread-safety issues.

    Returns:
        A chat model instance.
    """
    # MODIFIED: delegate to external Model Resolver if registered
    if _model_resolver_hook is not None and not _bypass_hook:
        return _model_resolver_hook(name, thinking_enabled=thinking_enabled, **kwargs)

    config = get_app_config()
    if name is None:
        name = config.models[0].name
    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "thinking",
            "supports_vision",
        },
    )
    # Compute effective when_thinking_enabled by merging in the `thinking` shortcut field.
    # The `thinking` shortcut is equivalent to setting when_thinking_enabled["thinking"].
    has_thinking_settings = (model_config.when_thinking_enabled is not None) or (model_config.thinking is not None)
    effective_wte: dict = dict(model_config.when_thinking_enabled) if model_config.when_thinking_enabled else {}
    if model_config.thinking is not None:
        merged_thinking = {**(effective_wte.get("thinking") or {}), **model_config.thinking}
        effective_wte = {**effective_wte, "thinking": merged_thinking}
    if thinking_enabled and has_thinking_settings:
        if not model_config.supports_thinking:
            raise ValueError(f"Model {name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
        if effective_wte:
            model_settings_from_config.update(effective_wte)
    if not thinking_enabled and has_thinking_settings:
        if effective_wte.get("extra_body", {}).get("thinking", {}).get("type"):
            # OpenAI-compatible gateway: thinking is nested under extra_body
            kwargs.update({"extra_body": {"thinking": {"type": "disabled"}}})
            kwargs.update({"reasoning_effort": "minimal"})
        elif effective_wte.get("thinking", {}).get("type"):
            # Native langchain_anthropic: thinking is a direct constructor parameter
            kwargs.update({"thinking": {"type": "disabled"}})
    if not model_config.supports_reasoning_effort and "reasoning_effort" in kwargs:
        del kwargs["reasoning_effort"]

    # For Codex Responses API models: map thinking mode to reasoning_effort
    from deerflow.models.openai_codex_provider import CodexChatModel

    if issubclass(model_class, CodexChatModel):
        # The ChatGPT Codex endpoint currently rejects max_tokens/max_output_tokens.
        model_settings_from_config.pop("max_tokens", None)

        # Use explicit reasoning_effort from frontend if provided (low/medium/high)
        explicit_effort = kwargs.pop("reasoning_effort", None)
        if not thinking_enabled:
            model_settings_from_config["reasoning_effort"] = "none"
        elif explicit_effort and explicit_effort in ("low", "medium", "high", "xhigh"):
            model_settings_from_config["reasoning_effort"] = explicit_effort
        elif "reasoning_effort" not in model_settings_from_config:
            model_settings_from_config["reasoning_effort"] = "medium"

    model_instance = model_class(**kwargs, **model_settings_from_config)
    return model_instance
