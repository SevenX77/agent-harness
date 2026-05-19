"""Tests for provider metadata loaded from app/data/llm_providers."""

from __future__ import annotations

from pathlib import Path

import pytest
from services import llm_provider_meta
from services.llm_provider_meta import ProviderMeta, load_provider_meta


@pytest.fixture
def provider_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    docs_dir = tmp_path / "llm_providers"
    docs_dir.mkdir()
    monkeypatch.setattr(llm_provider_meta, "DOCS_DIR", docs_dir)

    fixtures = {
        "anthropic": (
            ["anthropic_compatible"],
            None,
            "x-api-key: ${key}\nanthropic-version: 2023-06-01\n",
        ),
        "openai": (["openai_compatible"], "/v1/models", "Authorization: Bearer ${key}\n"),
        "gemini": (["google_genai"], "/v1beta/models", "x-goog-api-key: ${key}\n"),
        "deepseek": (["openai_compatible"], "/v1/models", "Authorization: Bearer ${key}\n"),
        "ark": (["openai_compatible"], "/api/v3/models", "Authorization: Bearer ${key}\n"),
        "openrouter": (["openai_compatible"], "/api/v1/models", "Authorization: Bearer ${key}\n"),
    }
    for vendor, (sdks, models_path, auth_header) in fixtures.items():
        models_value = "null" if models_path is None else f'"{models_path}"'
        sdk_lines = "\n".join(f"  - {sdk}" for sdk in sdks)
        (docs_dir / f"{vendor}.md").write_text(
            f"""# {vendor}

## §1.4 Other content

Ignored.

## §1.5 Runtime metadata

```yaml
compatible_sdks:
{sdk_lines}

models_endpoint_path: {models_value}

auth_header_format: |
{_indent(auth_header)}
```

## §2 More content
""",
            encoding="utf-8",
        )
    return docs_dir


@pytest.mark.parametrize(
    ("vendor", "compatible_sdks", "models_endpoint_path", "auth_fragment"),
    [
        ("anthropic", ["anthropic_compatible"], None, "x-api-key"),
        ("openai", ["openai_compatible"], "/v1/models", "Bearer"),
        ("gemini", ["google_genai"], "/v1beta/models", "x-goog-api-key"),
        ("deepseek", ["openai_compatible"], "/v1/models", "Bearer"),
        ("ark", ["openai_compatible"], "/api/v3/models", "Bearer"),
        ("openrouter", ["openai_compatible"], "/api/v1/models", "Bearer"),
    ],
)
def test_load_provider_meta_from_section_15_yaml(
    provider_docs: Path,
    vendor: str,
    compatible_sdks: list[str],
    models_endpoint_path: str | None,
    auth_fragment: str,
) -> None:
    meta = load_provider_meta(vendor)

    assert meta == ProviderMeta(
        vendor=vendor,
        compatible_sdks=compatible_sdks,
        models_endpoint_path=models_endpoint_path,
        auth_header_format=meta.auth_header_format,
    )
    assert auth_fragment in meta.auth_header_format


def test_gemini_is_strictly_google_genai(provider_docs: Path) -> None:
    meta = load_provider_meta("gemini")

    assert meta.compatible_sdks == ["google_genai"]
    assert "openai_compatible" not in meta.compatible_sdks


def test_missing_vendor_doc_raises_file_not_found(provider_docs: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Provider doc not found"):
        load_provider_meta("nonexistent")


def test_missing_section_15_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs_dir = tmp_path / "llm_providers"
    docs_dir.mkdir()
    (docs_dir / "fake.md").write_text("# Just a heading, no metadata\n", encoding="utf-8")
    monkeypatch.setattr(llm_provider_meta, "DOCS_DIR", docs_dir)

    with pytest.raises(ValueError, match="§1.5 metadata section"):
        load_provider_meta("fake")


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
