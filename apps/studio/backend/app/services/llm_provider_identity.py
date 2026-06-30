"""Provider identity derived from a base URL's registrable domain (eTLD+1).

A provider is classified by its **registrable domain** so any new provider is
auto-attributed without a hardcoded list (W3-B / R-B4 + R-B7):
``https://api.qnaigc.com/v1`` -> ``"qnaigc"``, ``*.wavespeed.ai`` -> ``"wavespeed"``.
Both ``api.wavespeed.ai`` and ``llm.wavespeed.ai`` collapse to the SAME provider
``"wavespeed"`` (we use the registrable domain, never the full host). The label is
a stable machine name; a human display alias (Qiniu / WaveSpeed / ARK) is layered
on top elsewhere.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Two-label public suffixes where the registrable label sits third-from-last
# (e.g. ``foo.com.cn`` -> ``foo``). Not a full PSL — covers the common ccTLD SLDs;
# everything else falls back to the last two labels (eTLD+1).
_MULTI_LABEL_SUFFIXES = frozenset(
    {
        "com.cn",
        "net.cn",
        "org.cn",
        "gov.cn",
        "edu.cn",
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "co.jp",
        "co.kr",
        "com.au",
        "com.br",
        "com.hk",
        "com.tw",
        "com.sg",
    }
)


def registrable_provider_name(base_url: str) -> str | None:
    """Return the provider's canonical name = the registrable-domain label of the
    base URL's host (eTLD+1), or ``None`` for an empty / single-label / raw-IP host.

    Examples: ``api.qnaigc.com`` -> ``"qnaigc"``; ``llm.wavespeed.ai`` -> ``"wavespeed"``;
    ``foo.com.cn`` -> ``"foo"``; ``10.1.2.3`` -> ``None``; ``localhost`` -> ``None``.
    """
    host = (urlsplit(base_url.strip()).hostname or "").lower().rstrip(".")
    if not host:
        return None
    labels = host.split(".")
    if len(labels) < 2 or all(label.isdigit() for label in labels):
        return None
    if ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return labels[-3]
    return labels[-2]


__all__ = ["registrable_provider_name"]
