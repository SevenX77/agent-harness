"""固定角色(fixed roles):被引擎 builtin skill 硬依赖、不可删除的 LLM 角色。

真相源在 engine —— builtin skill 用 frontmatter/`<phase_config>` 的 `llm_role:`
声明它需要哪个角色(例:`md-patch` 声明 `llm_role: fast`,它是 md2json 校验失败项
的外科式修补 agent)。studio **经 EngineAdapter 边界**读取这个引擎事实
(`app.core.adapters.engine.required_builtin_roles`),业务层不直接 import SDK
(模块边界:见 test_productization_import_boundary_red);加一个带新 `llm_role`
的 builtin skill,它自动成为固定角色,不漂移。

固定角色不可删除:删了引擎的 md2json 修补 / builtin subagent 就跑不起来。缺失时由
`runtime_truth_init` 自动补一个空槽(用户在设置页填模型)。
"""

from __future__ import annotations

from functools import lru_cache

from app.core.adapters.engine import required_builtin_roles as _engine_required_builtin_roles


@lru_cache(maxsize=1)
def required_builtin_roles() -> frozenset[str]:
    """引擎 builtin skill 硬依赖、不可删除的角色名集合(经 EngineAdapter 从引擎读取)。"""

    return _engine_required_builtin_roles()


def is_fixed_role(role_name: str) -> bool:
    return role_name in required_builtin_roles()
