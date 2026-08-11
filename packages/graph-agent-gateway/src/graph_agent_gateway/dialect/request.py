"""The vocabulary every dialect shares: what is asked, and what comes out.

The input side (:class:`Prompt`, :class:`Reasoning`) is written in the caller's
words — one turn of text, optionally a picture, and how hard the model should
think. The output side (:class:`WireRequest`) is a rendered HTTP request that
nobody has sent yet, which is what makes a dialect testable without a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class Image:
    """One picture, carried as base64 because every provider accepts it that way."""

    media_type: str
    base64_data: str

    @property
    def data_uri(self) -> str:
        return f"data:{self.media_type};base64,{self.base64_data}"


@dataclass(frozen=True)
class Prompt:
    """One user turn: the words, and the picture if there is one."""

    text: str
    image: Image | None = None


@dataclass(frozen=True)
class WireRequest:
    """A request rendered but not sent."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: dict[str, object] | None = None


class AuthScheme(Enum):
    """Where a provider wants the secret."""

    API_KEY_HEADER = "api_key_header"
    BEARER_HEADER = "bearer_header"
    QUERY_KEY = "query_key"

    def headers(self, secret: str) -> dict[str, str]:
        if self is AuthScheme.API_KEY_HEADER:
            return {"x-api-key": secret}
        if self is AuthScheme.BEARER_HEADER:
            return {"Authorization": f"Bearer {secret}"}
        return {}

    def params(self, secret: str) -> dict[str, str]:
        return {"key": secret} if self is AuthScheme.QUERY_KEY else {}


@dataclass(frozen=True)
class AbsolutePath:
    """The provider publishes this one path under the host, version included."""

    path: str

    def url(self, base_url: str) -> str:
        return join_base_url_and_path(base_url, self.path)


@dataclass(frozen=True)
class VersionedPath:
    """A path under the OpenAI-compatible ``/v1`` root.

    A base url may or may not already end at that root, so the version prefix
    comes from the base url when it has one and from us when it does not.
    """

    suffix: str

    def url(self, base_url: str) -> str:
        normalized_suffix = self.suffix if self.suffix.startswith("/") else f"/{self.suffix}"
        base_path = urlsplit(base_url.rstrip("/")).path.rstrip("/")
        if any(base_path.endswith(version_root) for version_root in ("/v1", "/api/v3")):
            return join_base_url_and_path(base_url, normalized_suffix)
        return join_base_url_and_path(base_url, f"/v1{normalized_suffix}")


WirePath = AbsolutePath | VersionedPath


def join_base_url_and_path(base_url: str, path: str) -> str:
    """Append a path to a base url without repeating a version segment.

    A base url configured as ``https://host/v1`` and a published path of
    ``/v1/messages`` mean the same endpoint as ``https://host`` and
    ``/v1/messages``; joining them naively would ask for ``/v1/v1/messages``.
    """

    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    parts = urlsplit(normalized_base)
    base_path = parts.path.rstrip("/")
    for version_root in ("/v1", "/v1beta", "/api/v3"):
        if base_path.endswith(version_root) and normalized_path.startswith(f"{version_root}/"):
            normalized_path = normalized_path[len(version_root) :]
            break
    return urlunsplit((parts.scheme, parts.netloc, f"{base_path}{normalized_path}", "", ""))
