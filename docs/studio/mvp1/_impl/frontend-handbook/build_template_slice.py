#!/usr/bin/env python3
"""Template-slice generator (unified-card edition).

One universal component `card(title, fields, tag)` renders every "object + attributes"
block; a small set of helpers (card_grid / rule / flow / be-ref / schema tags / diagram /
callout / list / badge / shot) covers everything that is NOT a card.

Pages: tpl_overview / apikeys_design / mech_cred / fe_modules / apikeys_impl / apikeys_tests.
"""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "module-review-handbook-template.html"
OUT = HERE / "index.html"  # 服务于 http://<lan>:8902/ 根路径，固定一个 URL，不再新建文件
SHOTS = HERE / "screenshots"  # 真机测试截图，构建时 base64 内联进 index.html（自包含）
D12 = "studio-mvp1-12d-repair-framework-2026-06-15.html"

FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@300;400;500;600;700;800&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">'
)

CSS = """
<style>
  :root { --font-sans:'Outfit','Noto Sans SC',sans-serif; --font-mono:'JetBrains Mono',monospace;
          --accent-blue-hover:#517def; --good:#1f7a4d; --bad:#b23a3a; --warn:#9a6a12; --info:#2a4aa0; }
  .callout { font-size:13.5px; }
  code { font-family:var(--font-mono); font-size:12px; background:#eef1f6; border:1px solid var(--border-color); border-radius:4px; padding:1px 5px; color:#0d7288; }
  .lesson-title { letter-spacing:-.5px; } .sec-label { letter-spacing:-.2px; }
  .card-header-tag { color:var(--accent-blue-hover); }
  .node-card .nid { color:var(--accent-blue-hover); }
  .xlink { color:var(--accent-blue); text-decoration:none; border-bottom:1px dotted var(--accent-blue); cursor:pointer; }
  .xlink:hover { color:var(--accent-blue-hover); }
  .mod-count { font-weight:600; color:var(--text-muted); font-size:12px; margin-left:4px; }
  /* ── badge: one component, one semantic per color ── */
  .badge { font-size:10px; font-weight:700; border-radius:99px; padding:2px 9px; white-space:nowrap; display:inline-block; }
  .badge.g { color:var(--good); background:rgba(31,160,90,.13); }   /* 好/通过 */
  .badge.a { color:var(--warn); background:rgba(214,158,46,.16); }  /* 未决/警示 */
  .badge.r { color:var(--bad);  background:rgba(200,60,60,.12); }   /* 坏/否 */
  .badge.b { color:var(--info); background:rgba(50,102,232,.12); }  /* 中性信息/归属 */
  .badge.x { color:#555;        background:#ececec; }               /* 中立/停用 */
  /* ── card: THE universal component (标题 + ≤1 标签 + 字段) ── */
  .card { border:1px solid var(--border-color); border-radius:12px; overflow:hidden; margin:10px 0 14px; background:#fff; scroll-margin-top:14px; }
  .card-hd { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 14px; background:#f7f8fa; border-bottom:1px solid var(--border-color); flex-wrap:wrap; }
  .card-title { font-size:13.5px; font-weight:800; color:var(--text-title); }
  .card-title.mono { font-family:var(--font-mono); font-size:12.5px; }
  .card-tags { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
  .card-row { display:grid; grid-template-columns:104px 1fr; gap:14px; padding:9px 14px; border-bottom:1px solid #eef0f3; align-items:start; }
  .card-row:last-child { border-bottom:0; }
  .card-row.solo { grid-template-columns:1fr; }
  .card-k { font-size:12px; font-weight:700; color:var(--text-muted); }
  .card-v { font-size:13px; line-height:1.7; color:#3b414a; }
  .card.acc-do { border-left:3px solid #2faa6a; } .card.acc-do .card-title { color:var(--good); }
  .card.acc-dont { border-left:3px solid #d36a6a; } .card.acc-dont .card-title { color:var(--bad); }
  /* ── card-grid: lay out N cards ── */
  .card-grid { display:grid; gap:10px; margin:6px 0 14px; }
  .card-grid.c2 { grid-template-columns:1fr 1fr; }
  .card-grid.c3 { grid-template-columns:repeat(3,1fr); }
  .card-grid > .card { margin:0; }
  /* ── ig-title: subsection heading ── */
  .ig-title { font-size:13px; font-weight:800; color:var(--text-title); margin:14px 0 8px; padding-left:9px; border-left:3px solid var(--accent-blue-hover); }
  .iface-group { margin:0 0 16px; }
  /* ── be-ref: lightweight "reference to an interface" (not a full card) ── */
  .be-ref { border:1px solid var(--border-color); border-radius:8px; padding:7px 10px; margin-bottom:6px; background:#fafbfc; }
  .be-ref:last-child { margin-bottom:0; }
  .be-ref .ep { font-family:var(--font-mono); font-size:11.5px; color:#0d7288; }
  .be-ref .pp { font-size:12.3px; color:#505864; line-height:1.5; margin-top:3px; }
  /* ── rule: 条件 → 结果 ── */
  .rule-list { display:flex; flex-direction:column; gap:5px; margin:4px 0; }
  .rule { display:grid; grid-template-columns:1fr max-content 1fr; align-items:center; gap:9px; border:1px solid var(--border-color); border-radius:8px; padding:6px 11px; background:#fafbfc; }
  .rcond { font-size:12px; color:#3b414a; } .rarrow { color:var(--text-muted); font-weight:700; }
  .rres { font-size:12px; color:var(--text-title); font-weight:600; }
  /* ── flow: numbered sequence ── */
  .flow-list { display:flex; flex-direction:column; margin:4px 0; }
  .flow-step { display:grid; grid-template-columns:max-content 1fr; gap:10px; align-items:start; padding:7px 0; }
  .flow-step .fs-n { width:21px; height:21px; border-radius:50%; background:var(--accent-blue-hover); color:#fff; font-size:12px; font-weight:800; display:flex; align-items:center; justify-content:center; }
  .flow-step .fs-t { font-size:12.8px; color:#3b414a; line-height:1.55; padding-top:1px; }
  .flow-step:not(:last-child) .fs-n { position:relative; }
  .flow-step:not(:last-child) .fs-n::after { content:""; position:absolute; top:23px; left:50%; width:2px; height:calc(100% + 2px); background:rgba(81,125,239,.28); }
  /* ── lists used as a field value ── */
  .duty-list { margin:2px 0; padding-left:20px; } .duty-list li { font-size:12.8px; color:#3b414a; line-height:1.62; margin-bottom:5px; }
  .v-ul { margin:0; padding-left:18px; } .v-ul li { font-size:12.8px; color:#3b414a; line-height:1.6; margin-bottom:4px; }
  /* ── chips / coverage ── */
  .chip { display:inline-block; font-size:11.5px; color:var(--accent-blue); text-decoration:none; background:rgba(50,102,232,.07); border:1px solid rgba(50,102,232,.22); border-radius:6px; padding:1px 8px; margin:0 5px 4px 0; }
  .chip:hover { background:rgba(50,102,232,.13); }
  .cov-chip { display:inline-block; font-family:var(--font-mono); font-size:11px; color:var(--info); background:rgba(50,102,232,.09); border:1px solid rgba(50,102,232,.26); border-radius:5px; padding:1px 6px; margin:3px 4px 0 0; }
  .part-div { font-size:16px; font-weight:800; color:#fff; background:var(--accent-blue-hover); border-radius:9px; margin:26px 0 14px; padding:9px 14px; scroll-margin-top:14px; }
  .part-div:first-of-type { margin-top:4px; }
  .status-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; margin-left:auto; margin-top:6px; }
  .status-dot.ok { background:#2faa6a; } .status-dot.partial { background:#e0a92e; }
  .status-dot.bad { background:#d35555; } .status-dot.review { background:#5b8def; }
  .progress-item .status-dot { margin-top:3px; }
  /* ── shot placeholder ── */
  .shot-ph { display:flex; align-items:center; justify-content:space-between; gap:10px; border:1px dashed var(--border-hover); border-radius:8px; background:#fbfcfe; padding:8px 11px; margin-bottom:6px; }
  .shot-cap { font-size:12.3px; color:#49515d; } .shot-todo { font-size:10.5px; font-weight:700; color:var(--text-muted); background:#eef1f6; border-radius:5px; padding:1px 7px; flex:none; }
  /* ── real test screenshot (base64-inlined) ── */
  .shot-fig { margin:0 0 10px; border:1px solid var(--border-hover); border-radius:10px; overflow:hidden; background:#fff; box-shadow:0 1px 3px rgba(20,30,50,.06); }
  .shot-img { display:block; width:100%; height:auto; cursor:zoom-in; }
  .shot-figcap { font-size:12px; color:#1f7a3d; background:#f0faf3; border-top:1px solid var(--border-hover); padding:6px 11px; }
  /* ── screenshot not capturable in headless (reason in place of shot) ── */
  .shot-na { display:flex; align-items:flex-start; gap:9px; border:1px solid #e6c9c9; border-left:3px solid #d35555; border-radius:8px; background:#fdf5f5; padding:9px 12px; margin-bottom:6px; }
  .shot-na-tag { font-size:11px; font-weight:800; color:#b23b3b; background:#f7e3e3; border-radius:5px; padding:2px 8px; flex:none; white-space:nowrap; }
  .shot-na-why { font-size:12.3px; color:#5a4a4a; line-height:1.5; }
  /* ── lightbox：点击截图放大 + 缩放 ── */
  .lightbox { display:none; position:fixed; inset:0; z-index:9999; background:rgba(12,16,24,.93); touch-action:none; -webkit-user-select:none; user-select:none; }
  .lightbox.open { display:block; }
  .lb-stage { position:absolute; inset:0; overflow:hidden; cursor:grab; }
  .lightbox.dragging .lb-stage { cursor:grabbing; }
  .lb-img { position:absolute; top:50%; left:50%; max-width:none; transform-origin:center center; will-change:transform; box-shadow:0 10px 40px rgba(0,0,0,.5); }
  .lb-bar { position:absolute; top:14px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:6px; background:rgba(28,34,46,.92); border:1px solid rgba(255,255,255,.14); border-radius:10px; padding:6px 8px; z-index:2; }
  .lb-bar button { width:34px; height:30px; border:none; border-radius:7px; background:rgba(255,255,255,.1); color:#eef2f8; font-size:17px; font-weight:700; cursor:pointer; line-height:1; }
  .lb-bar button:hover { background:rgba(255,255,255,.22); }
  .lb-pct { min-width:50px; text-align:center; font-size:12.5px; color:#cdd6e4; font-variant-numeric:tabular-nums; }
  .lb-close { position:absolute; top:14px; right:18px; width:38px; height:34px; border:none; border-radius:8px; background:rgba(28,34,46,.92); color:#eef2f8; font-size:20px; cursor:pointer; z-index:2; }
  .lb-close:hover { background:rgba(210,85,85,.85); }
  .lb-hint { position:absolute; bottom:16px; left:50%; transform:translateX(-50%); font-size:11.5px; color:#8b97a8; background:rgba(28,34,46,.8); padding:4px 12px; border-radius:8px; z-index:2; }
  /* ── transformation diagram ── */
  .diagram { border:1px solid var(--border-color); border-radius:10px; background:#fafbfe; padding:12px 14px; margin:4px 0; }
  .transform { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
  .t-box { border:1px solid var(--border-color); border-radius:10px; padding:10px; background:#fff; flex:1; min-width:150px; }
  .t-title { font-size:11px; font-weight:800; color:var(--text-muted); margin-bottom:7px; }
  .t-item { font-family:var(--font-mono); font-size:12px; background:#f2f4f8; border:1px solid var(--border-color); border-radius:6px; padding:3px 8px; margin-bottom:5px; display:block; width:fit-content; }
  .t-arrow { font-size:11.5px; font-weight:700; color:var(--accent-blue); text-align:center; min-width:78px; line-height:1.5; }
  .t-ep { font-family:var(--font-mono); font-size:12px; color:#0d7288; background:rgba(13,114,136,.07); border:1px solid rgba(13,114,136,.26); border-radius:6px; padding:4px 8px; margin-bottom:5px; }
  .t-note { font-family:var(--font-sans); font-size:10px; color:var(--text-muted); margin-left:4px; }
  /* ── data-file schema (field tags) ── */
  .schema-ver { font-size:11.5px; color:var(--text-muted); margin-bottom:7px; font-family:var(--font-mono); }
  .struct { border:1px solid var(--border-color); border-radius:10px; background:#fafbfe; padding:9px 11px; margin-bottom:9px; }
  .struct-name { font-family:var(--font-mono); font-size:11px; font-weight:800; color:var(--accent-blue-hover); margin-bottom:8px; }
  .fields { display:flex; flex-wrap:wrap; gap:7px; }
  .field { border:1px solid var(--border-color); border-radius:8px; background:#fff; padding:6px 9px; width:fit-content; max-width:250px; }
  .field.sensitive { border-color:rgba(231,76,60,.5); background:rgba(231,76,60,.05); }
  .f-name { font-family:var(--font-mono); font-size:11.5px; font-weight:700; color:var(--text-title); }
  .field.sensitive .f-name::after { content:" 🔒"; }
  .f-type { font-family:var(--font-mono); font-size:10px; color:var(--accent-blue); margin-left:6px; background:rgba(50,102,232,.08); border-radius:4px; padding:0 5px; }
  .f-mean { font-size:11px; color:#505864; line-height:1.45; margin-top:4px; }
  .flashx { outline:2px solid var(--accent-orange); outline-offset:2px; border-radius:6px; }
  /* ── S0: 实施 routine 编号步骤卡 ── */
  .routine-list { counter-reset:routine; }
  .routine-step { border:1px solid var(--border-color); border-radius:10px; background:#fff; padding:12px 14px 12px 44px; position:relative; }
  .routine-step::before { counter-increment:routine; content:counter(routine); position:absolute; left:13px; top:13px; width:22px; height:22px; border-radius:6px; background:#15171d; color:#fff; display:flex; align-items:center; justify-content:center; font-family:var(--font-mono); font-size:11px; font-weight:800; }
  .routine-step b { color:var(--text-title); font-size:13.5px; }
  .routine-step p { color:#505864; font-size:13px; line-height:1.65; margin-top:3px; }
  /* ── S0: 实施环境 键值表（窄键列，值列吃满） ── */
  .kv-table { width:100%; border-collapse:collapse; table-layout:auto; border:1px solid var(--border-color); border-radius:12px; overflow:hidden; margin:12px 0 22px; }
  .kv-table td { vertical-align:top; font-size:12.8px; line-height:1.6; padding:11px 14px; border-bottom:1px solid var(--border-color); }
  .kv-table tr:last-child td { border-bottom:0; }
  .kv-table td:first-child { white-space:nowrap; width:1%; font-weight:700; color:var(--text-title); background:#f7f8fa; border-right:1px solid var(--border-color); }
  .kv-table td:last-child { color:#505864; word-break:break-word; }
  /* ── 实施 todo 列表（套用 12D wave-todo 展示） ── */
  .todo-box { margin:12px 0 22px; }
  .todo-box > summary { list-style:none; cursor:pointer; display:flex; align-items:center; justify-content:space-between; gap:10px; min-height:38px; padding:8px 12px 8px 34px; border:1px solid var(--border-color); border-radius:9px; background:#fafbfc; color:var(--text-title); font-size:13px; font-weight:800; position:relative; }
  .todo-box > summary::-webkit-details-marker { display:none; }
  .todo-box > summary::before { content:"+"; position:absolute; left:11px; top:50%; transform:translateY(-50%); width:15px; height:15px; border-radius:4px; background:#15171d; color:#fff; display:flex; align-items:center; justify-content:center; font-family:var(--font-mono); font-size:11px; font-weight:800; line-height:1; }
  .todo-box[open] > summary::before { content:"\2212"; }
  .todo-count { color:var(--text-muted); font-family:var(--font-mono); font-size:11px; font-weight:700; white-space:nowrap; }
  .todo-rows { display:grid; gap:7px; margin-top:10px; }
  .todo-row { display:grid; grid-template-columns:18px minmax(0,1fr) auto; gap:10px; align-items:center; padding:9px 11px; border:1px solid #eef0f3; border-radius:9px; background:#fff; }
  .todo-row input { width:14px; height:14px; accent-color:var(--accent-green); }
  .todo-row.done .todo-title { color:#596170; text-decoration:line-through; text-decoration-color:rgba(46,204,113,.55); }
  .todo-title { min-width:0; color:var(--text-title); font-size:12.8px; font-weight:700; line-height:1.45; }
  .todo-title code { font-size:11px; }
  .todo-row .state-badge { justify-self:end; white-space:nowrap; }
  /* ── mobile ── */
  @media(max-width:600px){
    .card-row { grid-template-columns:1fr; gap:3px; } .card-row .card-k { color:var(--text-title); }
    .card-grid.c2,.card-grid.c3 { grid-template-columns:1fr; }
    .rule { grid-template-columns:1fr; gap:3px; } .rarrow { display:none; }
    .transform { flex-direction:column; align-items:stretch; }
  }
</style>
"""

DIAGRAMS = {
    "endpoint_transform": (
        '<div class="diagram">'
        '<div class="transform">'
        '<div class="t-box"><div class="t-title">provider（一把 key + 多个 URL）</div>'
        '<span class="t-item">🔑 一把 key</span><span class="t-item">URL-A</span><span class="t-item">URL-B</span></div>'
        '<div class="t-arrow">拆分 +<br>逐协议探通<br>→</div>'
        '<div class="t-box"><div class="t-title">平铺的标准 endpoint 列表</div>'
        '<div class="t-ep">URL-A × openai</div>'
        '<div class="t-ep">URL-A × anthropic <span class="t-note">一 URL 通两协议 → 两 endpoint</span></div>'
        '<div class="t-ep">URL-B × ark</div></div>'
        '</div></div>'
    ),
}

ESC = lambda s: html.escape(str(s if s is not None else ""), quote=False)


def code(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", ESC(s))


def embed_shot(filename, caption=""):
    """Inline a real test screenshot as a base64 data URI (self-contained HTML).

    Missing file → empty string (graceful; the test card still renders its text
    shots). Used by render_tests when a test declares a ``screenshots`` list.
    """
    path = SHOTS / filename
    if not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    figcap = f'<figcaption class="shot-figcap">✅ 真机实测 · {code(caption)}</figcaption>' if caption else ""
    return (
        '<figure class="shot-fig">'
        f'<img class="shot-img" loading="lazy" alt="{ESC(caption)}" src="data:image/png;base64,{b64}"/>'
        f'{figcap}</figure>'
    )


def listify(text):
    """A free-text field value: if it's >1 sentence/clause, break into a scannable list;
    a single sentence stays plain prose. Splits only on full-width 。；(never inside code/ASCII)."""
    s = str(text or "")
    if not s:
        return ""
    items = [x.strip() for x in re.split(r"[。；]", s) if x.strip()]
    if len(items) <= 1:
        return code(s)
    return '<ul class="v-ul">' + "".join(f"<li>{code(x)}</li>" for x in items) + "</ul>"


# ───────────────────────── primitives ─────────────────────────
def badge(text: str, kind: str = "x") -> str:
    return f'<span class="badge {kind}">{ESC(text)}</span>'


FE_KIND = {"符合": "g", "偏差": "a", "未实施": "r"}
BE_KIND = {"已实现": "g", "未实现": "r", "契约问题": "a", "n/a": "x"}
D12_KIND = {"ok": "g", "partial": "a", "bad": "r", "review": "b"}
METHOD_KIND = {"GET": "b", "POST": "g", "PUT": "a", "DELETE": "r", "PATCH": "a"}
STATE_KIND = {"ready": "g", "historical_ready": "b", "untested": "x", "failed": "r", "cooling_down": "a", "off": "x"}


def fe_badge(s: str) -> str:
    s = (s or "").strip()
    label = {"符合": "符合设计", "偏差": "有偏差", "未实施": "未实施"}.get(s, s)
    return badge("前端·" + label, FE_KIND.get(s, "x"))


def be_badge(s: str) -> str:
    s = (s or "").strip()
    return badge("后端·" + s, BE_KIND.get(s, "x"))


def d12_badge(s: str) -> str:
    s = (s or "").strip()
    return badge(s, D12_KIND.get(s, "x"))


def method_badge(mth: str) -> str:
    return badge(mth, METHOD_KIND.get(mth, "x"))


def card(title, fields=None, *, tag="", anchor="", mono=True, accent=""):
    """The one universal card: title (left) + optional single tag-slot (top-right) + N fields."""
    aid = f' id="{anchor}"' if anchor else ""
    acc = f' acc-{accent}' if accent else ""
    tcls = " mono" if mono else ""
    tag_html = f'<span class="card-tags">{tag}</span>' if tag else ""
    hd = f'<div class="card-hd"><span class="card-title{tcls}">{title}</span>{tag_html}</div>'
    body = ""
    for k, v in (fields or []):
        if not v:
            continue
        if k:
            body += f'<div class="card-row"><div class="card-k">{ESC(k)}</div><div class="card-v">{v}</div></div>'
        else:
            body += f'<div class="card-row solo"><div class="card-v">{v}</div></div>'
    return f'<div class="card{acc}"{aid}>{hd}{body}</div>'


def card_grid(cards, cols=2):
    return f'<div class="card-grid c{cols}">{"".join(cards)}</div>'


def v_ul(items):
    return f'<ul class="v-ul">' + "".join(f"<li>{code(x)}</li>" for x in items) + "</ul>" if items else ""


def duty_ol(items):
    return '<ol class="duty-list">' + "".join(f"<li>{code(x)}</li>" for x in items) + "</ol>" if items else ""


def _kv_table(rows):
    """窄键列键值表（实施环境用）。rows = [(key, value_html), ...]。"""
    body = "".join(f'<tr><td>{ESC(k)}</td><td>{v}</td></tr>' for k, v in rows)
    return f'<table class="kv-table"><tbody>{body}</tbody></table>'


def _wave_cards(items):
    """标题 + 描述的白卡网格（波次 / 方法论用，套用 12D wave-card 展示）。items = [(title, desc), ...]。"""
    cards = "".join(f'<div class="wave-card"><h4>{code(t)}</h4><p>{code(d)}</p></div>' for t, d in items)
    return f'<div class="wave-grid">{cards}</div>'


def _routine_steps(items):
    """编号步骤卡（实施 routine 用，套用 12D routine-step 展示）。items = [(title, desc), ...]。"""
    steps = "".join(f'<div class="routine-step"><b>{code(t)}</b><p>{code(d)}</p></div>' for t, d in items)
    return f'<div class="routine-list">{steps}</div>'


def _todo_list(title, items):
    """可折叠 todo 列表（实施顺序用，套用 12D wave-todo 展示）。
    items = [(code, title, status_cls, badge_label, done_bool), ...]。"""
    rows = ""
    for code_, ttl, cls, label, done in items:
        dc = " done" if done else ""
        ck = " checked" if done else ""
        rows += (f'<label class="todo-row{dc}"><input type="checkbox" disabled{ck}>'
                 f'<span class="todo-title"><code>{ESC(code_)}</code> · {code(ttl)}</span>'
                 f'<span class="state-badge {cls}">{ESC(label)}</span></label>')
    ndone = sum(1 for it in items if it[4])
    return (f'<details class="todo-box" open><summary><span>{ESC(title)}</span>'
            f'<span class="todo-count">{ndone}/{len(items)} done</span></summary>'
            f'<div class="todo-rows">{rows}</div></details>')


def rule_list(pairs):
    return '<div class="rule-list">' + "".join(
        f'<div class="rule"><div class="rcond">{code(c)}</div><div class="rarrow">→</div><div class="rres">{code(r)}</div></div>'
        for c, r in pairs
    ) + "</div>"


def group_by_module(atoms):
    order = []
    by = {}
    for a in atoms:
        if a["module"] not in by:
            by[a["module"]] = []
            order.append(a["module"])
        by[a["module"]].append(a)
    return order, by


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "x"


# ───────────────────────── reusable-modules page ─────────────────────────
def _module_card(g, anchor, kind_label):
    duties = g.get("duties", [])
    fields = [
        ("它是什么", listify(g.get("what", ""))),
        (f"功能（{len(duties)} 条）" if duties else "", duty_ol(duties)),
        ("API / 后端", listify(g.get("api", ""))),
        ("复用范围", listify(g.get("reuse_note", ""))),
        ("被哪些操作用", listify(g.get("used_by", ""))),
        ("定义在哪", listify(g.get("where", ""))),
        ("边界", listify(g.get("boundary", ""))),
        ("设计提醒", listify(g.get("design_note", ""))),
    ]
    return card(ESC(g["name"]), fields, tag=badge(kind_label, "b"), anchor=anchor, mono=False)


def render_fe_modules(reg, nctx):
    """reg = list of (anchor, femod-dict) aggregated+deduped across this node's stages."""
    code_, name = nctx["code"], nctx["name"]
    cards = "".join(_module_card(g, anchor, g.get("kind", "前端模块")) for anchor, g in reg)
    content = (
        f'<div class="callout">这一页登记 <b>{ESC(code_)} · {ESC(name)} 里能被多个操作 / 多个页面共用的前端模块</b>，各操作卡用 chip 链进来复用（同一组件只登记一次）。它们是<b>真实的功能代码</b>，不是只挂名的目录——每张卡的「定义在哪」字段直接指向源码文件，缺了对应模块界面就渲染不出来。导航上这一页的状态点 = 这些模块<b>是否都已实现并符合设计</b>（和「后端接口契约」页对称：那页看后端那一半建好没，这页看前端模块建好没）；每个模块自己干啥看卡内「功能」字段。复用模块是<b>本节点自己的</b>，不和别的节点共享通用组件。</div>'
        + cards
    )
    return section(nctx["pages"]["fe_modules"], "可复用前端模块 · 登记处", f"可复用前端模块（{code_} 登记处）",
                   f"整个 {name} 节点里能被多操作 / 多页面引用的前端共享模块都登记在这一页。", content)


# ───────────────────────── design page ─────────────────────────
def _be_href(c, nctx):
    mref, iref = c.get("mechanism_ref"), c.get("iface_ref")
    if mref and iref:
        return f"#{mref}-{iref}"
    return "#" + (mref or iref or nctx["pages"]["overview"])


def render_design(d, femhome, label, nctx):
    apfx = nctx["apfx"]
    femhome_id = nctx["pages"]["fe_modules"]
    order, by = group_by_module(d["atoms"])
    body = ""
    for m in order:
        body += f'<div class="sec-label">{ESC(m)} <span class="mod-count">{len(by[m])} 个</span></div>'
        for a in by[m]:
            be_refs = "".join(
                f'<div class="be-ref"><a class="ep xlink" href="{_be_href(c, nctx)}">{ESC(c["endpoint"])}</a>'
                f'<div class="pp">{code(c.get("purpose",""))}</div></div>'
                for c in a.get("be_contract", [])
            )
            chips = "".join(
                f'<a class="chip" href="{femhome.get(x.get("name",""), "#" + femhome_id)}">{ESC(x.get("name",""))}</a>'
                for x in a.get("fe_modules", [])
            )
            gap = listify(a.get("gap_brief", "")) + (
                f' <a class="xlink" href="#{apfx}fn-{a["n"]}">→ 看实施详情</a>' if a.get("impl_ref") else ""
            )
            title = f'#{a["n"]} · {ESC(a["cap"])}' + (f' · {ESC(a["track"])}' if a.get("track") else "")
            tag = fe_badge(a.get("fe_status", "")) + be_badge(a.get("be_status", ""))
            fields = [
                ("功能", listify(a.get("func", ""))),
                ("用户动作", listify(a.get("action", ""))),
                ("前端逻辑", listify(a.get("fe_design", ""))),
                ("前端模块", chips),
                ("后端契约", be_refs),
                ("现状偏差", gap),
            ]
            body += card(title, fields, tag=tag, anchor=f"{apfx}atom-{a['n']}", mono=False)
    return section(
        d["page_id"], f"操作设计页 · {label}", d["title"], d.get("intro", ""),
        '<div class="callout">本页是 <b>设计</b>（MVP1 应该长啥样）。每张卡右上两轴状态：前端徽章=前端是否符合设计（我们的活）；后端徽章=后端契约<b>实现状态</b>（据「后端实施手册」）。「后端契约」点端点链到机制页那条接口；「前端模块」chip 链到 <a class="xlink" href="#' + femhome_id + '">可复用前端模块登记页</a>；「现状偏差」链到实施详情。</div>'
        + body,
    )


# ───────────────────────── mechanism page ─────────────────────────
def _iface_card(i, prefix=""):
    ep = i["endpoint"]
    parts = ep.split(" ", 1)
    method = parts[0] if parts[0] in METHOD_KIND else ""
    path = parts[1] if (method and len(parts) > 1) else ep
    fields = [
        ("用途", listify(i.get("purpose", ""))),
        ("请求", code(i.get("req", ""))),
        ("响应", listify(i.get("resp", ""))),
        ("实现", code(i.get("provider", ""))),
    ]
    anchor = f'{prefix}-{i.get("id","")}' if prefix else i.get("id", "")
    return card(ESC(path), fields, tag=method_badge(method) if method else "", anchor=anchor, mono=True)


def render_mech(m, label=""):
    mid = m["id"]
    # submodules
    subs = ""
    for i, s in enumerate(m.get("submodules", [])):
        fields = [
            ("代码", code(s.get("code", ""))),
            ("一句话", listify(s.get("summary", ""))),
            ("核心定义", code(s.get("formula", ""))),
            ("图示", DIAGRAMS.get(s.get("diagram") or "", "")),
            ("关键规则", v_ul(s.get("rules", []))),
            ("做什么", v_ul(s.get("do", []))),
            ("不做什么", v_ul(s.get("dont", []))),
            ("⚠ 现码偏差", listify(s.get("deviation", ""))),
        ]
        owner = s.get("owner") or m.get("owner_tag", "")
        subs += card(ESC(s["name"]), fields, tag=badge(owner, "b") if owner else "", anchor=f"{mid}-submod-{i}", mono=False)
    # data files
    files = ""
    for f in m.get("files", []):
        if f.get("structs"):
            schema_html = '<div class="schema-ver">' + code(f.get("version", "")) + "</div>"
            for st in f["structs"]:
                fl = "".join(
                    f'<div class="field{" sensitive" if x.get("sensitive") else ""}">'
                    f'<span class="f-name">{ESC(x["name"])}</span><span class="f-type">{ESC(x.get("type",""))}</span>'
                    f'<div class="f-mean">{code(x.get("meaning",""))}</div></div>'
                    for x in st.get("fields", [])
                )
                schema_html += f'<div class="struct"><div class="struct-name">{ESC(st["name"])}</div><div class="fields">{fl}</div></div>'
            storage = listify(f.get("storage_note", "")) + f'<a class="xlink" href="{D12}#s0_overview">→ 后端实施手册</a>'
            fields = [
                ("存什么", listify(f.get("what", ""))),
                ("结构 schema", schema_html),
                ("谁拥有", listify(f.get("owns", ""))),
                ("前端怎么读写", listify(f.get("crud_pointer", ""))),
                ("落盘（不归前端）", storage),
                ("安全（前端侧）", listify(f.get("security_fe", ""))),
            ]
            files += card(ESC(f["name"]), fields, tag=badge("数据文件", "x"), mono=True)
    # interfaces (grouped) -> iface cards
    groups = m.get("interface_groups")
    if groups:
        ifaces = ""
        for g in groups:
            members = [i for i in m.get("interfaces", []) if i.get("group") == g["key"]]
            ifaces += (f'<div class="iface-group"><div class="ig-title">{ESC(g["title"])}（{len(members)}）</div>'
                       f'<div class="callout {"blue" if g["key"] in ("crud", "query") else "amber"}" style="margin:0 0 10px">{code(g.get("note",""))}</div>'
                       + "".join(_iface_card(i, mid) for i in members) + "</div>")
    else:
        ifaces = "".join(_iface_card(i, mid) for i in m.get("interfaces", []))
    # boundaries -> 2 cards in a grid
    b = m.get("boundaries", {})
    if isinstance(b, dict):
        bounds = card_grid([
            card("✓ 明确做", [("", v_ul(b.get("do", [])))], accent="do", mono=False),
            card("✕ 明确不做", [("", v_ul(b.get("dont", [])))], accent="dont", mono=False),
        ], 2)
    else:
        bounds = v_ul(b)
    # states & errors
    se = m.get("states_errors", "")
    if isinstance(se, dict):
        st_cards = [
            card(f'{s["dot"]} {ESC(s["name"])}', [("含义", code(s["mean"]))],
                 tag=badge(s["code"], STATE_KIND.get(s["code"], "x")), mono=False)
            for s in se.get("states", [])
        ]
        proj = se.get("projection", {})
        pe = se.get("probe_errors", {})
        probe_cards = card_grid([
            card("结构性错配 → 短路停", [("", v_ul(pe.get("short_circuit", [])))], mono=False),
            card("瞬时类 → 不短路", [("", v_ul(pe.get("no_short_circuit", [])))], mono=False),
        ], 2)
        states_html = (
            f'<p class="body-copy">{code(se.get("intro", ""))}</p>'
            f'<div class="ig-title">6 态定义</div>{card_grid(st_cards, 3)}'
            f'<div class="ig-title">合成逻辑（怎么从事实源算出一个态）</div>'
            f'<div class="callout blue" style="margin:0 0 10px"><b>由谁</b>　{code(proj.get("owner",""))}<br><b>优先级</b>　{code(proj.get("priority",""))}</div>'
            f'{rule_list(proj.get("rules", []))}'
            f'<div class="ig-title">failed 的 reason_code（3 种）</div>{rule_list(se.get("reason_codes", []))}'
            f'<div class="ig-title">探测 / 测试错误码</div>{probe_cards}'
            f'<div class="callout"><b>终态资源错误</b>　{code(se.get("terminal",""))}</div>'
        )
    else:
        states_html = f'<p class="body-copy">{code(se)}</p>'
    # backend status -> cards
    bs = "".join(
        card(code(b["item"]),
             [("说明", listify(b.get("note", ""))),
              ("对应后端实施手册", f'<a class="xlink" href="{D12}#{b.get("ref","")}_overview">{ESC(b.get("d12",""))}</a>')],
             tag=d12_badge(b.get("status", "")), mono=False)
        for b in m.get("backend_status", [])
    )
    # overview card + data flow
    ov = m.get("overview", {})
    flow_html = "".join(
        f'<div class="flow-step"><span class="fs-n">{idx+1}</span><div class="fs-t">{code(s)}</div></div>'
        for idx, s in enumerate(ov.get("dataflow", []))
    )
    summary_card = card("本页速览", [
        ("管什么", listify(ov.get("manages", ""))),
        ("为什么单列一页", listify(ov.get("why_single", ""))),
        ("设计归属", listify(ov.get("design_owner", ""))),
        ("现码落点", listify(ov.get("code_location", ""))),
    ], mono=False) if ov else ""
    parts = ['<div class="callout amber">本页是<b>后端机制的设计</b>。实现不归我们（归后端，追踪在「后端实施手册」）；我们把设计拆清楚，并在最后一节<b>引用后端实施手册标注后端实现状态</b>。</div>']
    if summary_card:
        parts.append(summary_card)
    if flow_html:
        parts.append(f'<div class="ig-title">核心数据流</div><div class="flow-list">{flow_html}</div>')
    if subs:
        parts.append(f'<div class="sec-label">子模块（{len(m.get("submodules", []))}）</div>{subs}')
    if files:
        parts.append(f'<div class="sec-label">数据文件</div>{files}')
    if ifaces:
        parts.append(f'<div class="sec-label">接口（契约）</div>{ifaces}')
    if isinstance(m.get("boundaries"), dict) or m.get("boundaries"):
        parts.append(f'<div class="sec-label">边界（做什么 / 不做什么）</div>{bounds}')
    if isinstance(se, dict):
        parts.append(f'<div class="sec-label">状态与错误</div>{states_html}')
    # rule_sections: 通用「条件 → 结果」映射段（错误码映射、判定 reason 等），用统一 rule 组件
    for rs in m.get("rule_sections", []):
        parts.append(f'<div class="ig-title">{ESC(rs.get("title", ""))}</div>')
        if rs.get("note"):
            parts.append(f'<div class="callout blue" style="margin:0 0 10px">{code(rs["note"])}</div>')
        parts.append(rule_list(rs.get("rules", [])))
    if bs:
        parts.append('<div class="sec-label">后端实现状态（据后端实施手册）</div>'
                     '<div class="callout">这节只回答前端关心的三件事：<b>这条后端能力就绪没</b>（徽章）、<b>缺口在哪、卡住哪个前端功能</b>（说明）、<b>详情去哪看</b>（链到后端实施手册）。后端内部怎么实现的不在这里堆。</div>' + bs)
    return "".join(parts)


# ───────────────────────── implementation page ─────────────────────────
def render_impl(im, ns, label, nctx):
    apfx = nctx["apfx"]
    # atom → 覆盖它的 test 卡主锚点（test 卡按首 atom 命名；多 atom test 时其余 atom 也映射到同一锚点，避免死链）。
    tested_map = {}
    for t in im.get("tests", []):
        ats = t.get("atoms", [])
        if ats:
            primary = f'{apfx}test-{ats[0]}'
            for a in ats:
                tested_map.setdefault(a, primary)
    funcs = ""
    for f in im["functions"]:
        rows = [
            ("现状", listify(f.get("current", ""))),
            ("差距 / 要改", listify(f.get("gap", ""))),
            ("后端依赖", listify(f.get("be_dep", ""))),
            ("对应设计", f'<a class="xlink" href="#{apfx}atom-{f["n"]}">设计页 #{f["n"]} · {ESC(f["cap"])} →</a>'),
        ]
        if f["n"] in tested_map:
            rows.append(("对应实测", f'<a class="xlink" href="#{tested_map[f["n"]]}">实测页 #{f["n"]}（真机截图 / 截不到的附原因）→</a>'))
        funcs += card(f'#{f["n"]} · {ESC(f["cap"])}', rows,
                      tag=fe_badge(f.get("fe_status", "")), anchor=f"{apfx}fn-{f['n']}", mono=False)
    plan = ""
    for s in im["plan"]:
        blk = s.get("block", "")
        plan += card(f'Step {s.get("step","")}', [
            ("改什么", listify(s.get("what", ""))),
            ("依赖", listify(s.get("depends_on", ""))),
            ("为什么排这个顺序", listify(s.get("why", ""))),
        ], tag=badge(blk, "a" if "后端" in blk else "g"), mono=False)
    content = (
        f'<p class="body-copy">{code(im.get("intro",""))}</p>'
        + f'<div class="ig-title">逐功能 现状 / 差距（{len(im["functions"])}）</div>{funcs}'
        + ('<div class="ig-title">实施计划（按依赖排序）</div>'
           '<div class="callout">排序轴 = <b>后端先于前端</b>铁律：能<b>前端独立</b>做的（绿标）先做；<b>等后端</b>契约的（琥珀标）排在「后端先行」项之后。</div>' + plan if plan else "")
    )
    return content


# ───────────────────────── testing page ─────────────────────────
def render_tests(im, ns, label, n_atoms, apfx=""):
    tests = im.get("tests", [])
    covered = sorted({a for t in tests for a in t.get("atoms", [])})
    items = ""
    for t in tests:
        figs = "".join(embed_shot(s["file"], s.get("caption", "")) for s in t.get("screenshots", []))
        captured = bool(t.get("screenshots"))
        na = (t.get("shot_na") or "").strip()
        todo = "已实测" if captured else "截图待贴"
        # headless 截不到的功能：把原因写在截图位置（替代占位），不再显示「截图待贴」
        na_box = (f'<div class="shot-na"><span class="shot-na-tag">🚫 headless 截不到</span>'
                  f'<span class="shot-na-why">{code(na)}</span></div>') if na else ""
        phs = "" if na else "".join(
            f'<div class="shot-ph"><span class="shot-cap">📷 {code(s)}</span><span class="shot-todo">{todo}</span></div>'
            for s in t.get("shots", [])
        )
        shots = figs + na_box + phs
        if captured:
            label_row = "预期截图（真机实测）"
        elif na:
            label_row = "真机截图（headless 不可截 · 附原因 + 替代验证）"
        else:
            label_row = "预期截图"
        atoms = t.get("atoms") or []
        anchor = f"{apfx}test-{atoms[0]}" if atoms else ""
        design_link = (
            f'<a class="xlink" href="#{apfx}atom-{atoms[0]}">设计页 #{atoms[0]} · 看这条的设计意图 →</a>'
            if atoms else ""
        )
        verify_tag = badge("⚠ 无真机实测", "a") if na else ""
        items += card(code(t.get("covers", "")), [
            ("对应设计", design_link),
            ("① 静态测试 (RED→GREEN)", duty_ol(t.get("layer1", []))),
            ("② e2e 真实测试", duty_ol(t.get("layer2", []))),
            (label_row, shots),
        ], tag=fe_badge(t.get("fe_status", "")) + verify_tag, anchor=anchor, mono=False)
    cov = "".join(f'<span class="cov-chip">#{a}</span>' for a in covered)
    na_n = sum(1 for t in tests if (t.get("shot_na") or "").strip())
    na_note = (
        f'<div class="callout amber">其中 <b>{na_n} 项</b>标 <b>⚠ 无真机实测</b>：'
        f'它们是<b>系统级 / 瞬态行为</b>（弹系统目录选择器、跳系统文件管理器、亚百毫秒一闪的加载骨架、'
        f'需注入故障的 fallback、冷启动横幅）——headless 虚拟显示器驱动不了、截不到稳定帧，'
        f'只能由<b>自动化单测 / 组件测试 + 读码</b>覆盖（卡内已注明替代验证），<b>没有真机端到端截图为证</b>。'
        f'故本页状态点标<b>琥珀（部分实测）</b>，不是全绿。</div>'
    ) if na_n else ""
    content = (
        f'<div class="callout"><b>覆盖 {len(covered)} / {n_atoms}</b>：本页的设计原子里有 {len(covered)} 个配了两层测试（每张卡标题 = 它覆盖的原子）。「有测试」≠「已通过」，通过以真跑结果为准。{cov}</div>'
        + na_note
        + items
    )
    return content


def two_layer_explainer():
    tl = card_grid([
        card("① 业务逻辑静态测试（红 → 绿）", [("", v_ul([
            "先写能复现缺口的失败测试（RED），实现后变绿（GREEN）。",
            "<b>什么叫 mock</b>：用一个<b>假替身</b>替掉真后端 / 真文件系统 / 真点击，这样能<b>单独</b>验前端这一步的接线对不对——点了按钮有没有调对函数、状态有没有刷新、错误文案对不对——不用等后端、不依赖磁盘，跑得快又稳。真连通留给 ② 去真跑。",
            "纯展示 / 状态改动则列出要断言的 DOM / 文本 / 状态证据。",
            "组件测覆盖 success / empty / error；契约测断言打对端点、收对 DTO。",
        ]))], mono=False),
        card("② e2e 真实测试（点界面 + 截图）", [("", v_ul([
            "鼠标真点界面、跑到预期状态，截图为证：页面状态、标签 / 徽章颜色、toast 红或绿。",
            "涉及真连通的（如 endpoint test）必须用真 key 真模型调用真跑一次——『测试通过 ⟺ 真能用』，不只 mock。",
        ]))], mono=False),
    ], 2)
    return (
        '<div class="callout green">前端测试分<b>两层</b>，每个功能两层都要覆盖：</div>' + tl
        + f'<div class="callout">方法论参照<b>后端实施手册</b>的「证据闭环 / RED→GREEN / 真 App 点击 + 截图」一节 → <a class="xlink" href="{D12}#s0_overview">后端实施手册 · 方法论</a>。</div>'
    )


def _part_div(label, anchor=""):
    aid = f' id="{anchor}"' if anchor else ""
    return f'<div class="part-div"{aid}>{ESC(label)}</div>'


# ───────────────────────── consolidated pages (1 each, sectioned by 页面) ─────────────────────────
def render_contract(stages, nctx):
    code_ = nctx["code"]
    npages = len([s for s in stages if s.get("mechs")])
    body = "".join(
        _part_div(f'{s["label"]} · {m["title"]}', anchor=m["id"]) + render_mech(m, s["label"])
        for s in stages for m in s["mechs"]
    )
    intro = f'<div class="callout amber">本页是 {ESC(code_)} 全部<b>后端机制 / 接口契约的设计</b>（按页面分节）。实现不归我们（归后端，追踪在「后端实施手册」）；我们把契约拆清楚、并在各节末标后端实现状态。</div>'
    return section(nctx["pages"]["contract"], f"后端接口契约 · {code_}", f"后端接口契约（{code_} 汇总）",
                   f"{code_} 各页面依赖的后端机制设计 + 接口契约 + 后端实现状态，按页面分节。", intro + body)


def render_impl_all(stages, nctx):
    code_ = nctx["code"]
    tests_id = nctx["pages"]["tests"]
    body = "".join(
        _part_div(s["label"]) + render_impl(s["impl"], s["ns"], s["label"], nctx)
        for s in stages if s["impl"]
    )
    intro = f'<div class="callout green">本页是 {ESC(code_)} 全部页面的<b>前端实施</b>（我们的活，按页面分节）：逐功能现状 / 差距（点「→ 设计」回看）+ 按依赖排序的实施计划。测试在 <a class="xlink" href="#{tests_id}">测试页</a>。</div>'
    return section(nctx["pages"]["impl"], f"实施 · {code_}", f"前端实施（{code_} 汇总）",
                   "每个功能的现状 / 差距 / 依赖排序的实施计划，按页面分节。", intro + body)


def render_tests_all(stages, nctx):
    code_ = nctx["code"]
    body = "".join(
        _part_div(s["label"]) + render_tests(s["impl"], s["ns"], s["label"], len(s["design"]["atoms"]), nctx["apfx"])
        for s in stages if s["impl"]
    )
    return section(nctx["pages"]["tests"], f"测试 · {code_}", f"前端测试（{code_} 汇总）",
                   "业务逻辑静态测试（红→绿）+ e2e 真实测试，按页面分节。", two_layer_explainer() + body)


# ───────────────────────── legacy node (N1–N6, 旧格式占位，待深化) ─────────────────────────
def _legacy_table(tbl):
    if not isinstance(tbl, dict) or not tbl.get("rows"):
        return ""
    heads = tbl.get("headers", [])
    return ('<table class="info-table"><thead><tr>' + "".join(f"<th>{ESC(h)}</th>" for h in heads) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{code(c)}</td>" for c in row) + "</tr>" for row in tbl["rows"]) + "</tbody></table>")


def render_node_legacy(nd):
    nid = nd.get("code", "")
    parts = [
        f'<div class="callout amber"><b>⚠ 待深化</b>：本节点（{ESC(nid)}）内容仍是<b>旧格式审计稿</b>（节点总览 + 子节点验收页），尚未按新结构（设计 / 后端接口契约 / 前端复用模块 / 实施 / 测试）拆开深化。先迁入、保留 7 节点全貌，后续逐节点像 N0 那样深化。</div>'
    ]
    if nd.get("intent_oneliner"):
        parts.append(f'<div class="callout"><b>这个节点干什么</b>　{code(nd["intent_oneliner"])}</div>')
    for key, label in [("role_table", "界面单元 → 作用"), ("surfaces_table", "界面 surface"),
                       ("actions_table", "用户动作"), ("issues_table", "问题"), ("gates_table", "验证门禁")]:
        t = nd.get(key)
        if isinstance(t, dict) and t.get("rows"):
            parts.append(f'<div class="ig-title">{label}（{len(t["rows"])}）</div>' + _legacy_table(t))
    if nd.get("current_risk"):
        parts.append(f'<div class="callout amber"><b>当前风险</b>　{code(nd["current_risk"])}</div>')
    for ch in nd.get("children", []):
        cid = ch.get("code", "")
        parts.append(card(f'{ESC(cid)} · {ESC(ch.get("title",""))}', [
            ("问题", listify(ch.get("problem", ""))),
            ("正确设计", listify(ch.get("design", ""))),
            ("现状", listify(ch.get("current", ""))),
            ("修复", listify(ch.get("fix", ""))),
            ("自动验证", v_ul(ch.get("auto", []))),
            ("手工验收", v_ul(ch.get("manual", []))),
            ("放行判据", v_ul(ch.get("pass", []))),
        ], tag=d12_badge(ch.get("status", "")), anchor=cid, mono=False))
    return section(nid, f"{nid} · 节点（待深化）", nd.get("title", nid), nd.get("intent_oneliner", ""), "".join(parts))


# ───────────────────────── handbook overview (7 nodes) ─────────────────────────
def render_node_overview(stages, nctx):
    """节点主页：该节点的总入口（每个 surface 操作设计 + 契约/复用模块/实施/测试）。"""
    code_, name = nctx["code"], nctx["name"]
    n_surfaces = len(stages)
    total_pages = n_surfaces + 4
    items = []
    for i, s in enumerate(stages):
        d = s["design"]
        link = f'<a class="xlink" href="#{d["page_id"]}">{code_}.{i+1} · {ESC(d["title"])}</a>'
        desc = (f'本页讲 <b>{ESC(s["label"])}</b> 这一页上的全部操作设计：每个操作的目标长啥样、'
                f'用户怎么触发、前端怎么做、依赖后端哪条契约。')
        items.append(card(link, [("讲什么", desc)], mono=False))
    fixed = [
        (nctx["pages"]["contract"], n_surfaces + 1, "后端接口契约", f"{code_} 各页面依赖的后端机制 + 接口契约 + 后端实现进度（按页面分节）。实现归后端，我们只把契约定清楚。"),
        (nctx["pages"]["fe_modules"], n_surfaces + 2, "前端复用模块", f"{code_} 内被多个操作 / 页面复用的前端共享组件登记处（同一组件只登记一次）。"),
        (nctx["pages"]["impl"], n_surfaces + 3, "实施", "每个功能的现状 / 差距 + 按依赖排序的前端实施计划。"),
        (nctx["pages"]["tests"], n_surfaces + 4, "测试", "业务逻辑静态测试（红→绿）+ e2e 真实测试（点界面、出预期状态截图）。"),
    ]
    for pid, n, nm, desc in fixed:
        link = f'<a class="xlink" href="#{pid}">{code_}.{n} · {nm}</a>'
        items.append(card(link, [("讲什么", ESC(desc))], mono=False))
    intro = (f'<div class="callout"><b>{ESC(code_)} · {ESC(name)} 节点主页</b>：{code(nctx.get("intent", ""))}'
             f'本节点拆成下面 {total_pages} 页：<b>{n_surfaces} 个页面的操作设计</b>'
             f'（并列、非递进）+ <b>后端接口契约 / 前端复用模块 / 实施 / 测试</b> 各一页。点任意一页进入。</div>')
    impl_block = ""
    if code_ == "N0":
        norms = _wave_cards([
            ("另开分支", "在 `feat/n0-settings-frontend` 上做，别和后端线 `codex/studio-mvp1-12d-strict-tdd` 的未提交活混；做完按文件名逐个 commit，绝不 `git add .`。"),
            ("Worktree / 地基", "`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased`；N0 settings 前端 `apps/studio/frontend/src/components/studio/settings/` + 后端契约 router（`llm.py` / `copilot.py` / `settings.py`）均已提交、无未提交改动；codex 未提交活在别的区（runs / skills / loopback），不冲突。"),
            ("后端先于前端", "每页动手前确认它依赖的后端契约是已提交那版；前端只投影后端 DTO、不自存第二份真相。"),
            ("逐页走 routine", "每页按 S0 的 5 步：读设计 → 写两层测试（先红）→ 按契约实现 → 跑 focused gate → 真机验收。"),
        ])
        track = ('<div class="callout amber"><b>3 件后端依赖（边建边等后端，不挡开工）</b>：'
                 '① <b>API Keys 蓝态</b>——后端 <code>probe_import_draft</code>（探测导入草稿的函数）是桩，UI 先建、后端 worker 落地才点亮历史可用态；'
                 '② <b>Roles required_minimum</b>——gateway <code>_apply_output_token_intent</code>（落 token 意图判 fit 的函数）缺该分支，控件先建、后端补分支才生效 not_fit；'
                 '③ <b>Roles schema 清理</b>——后端 <code>llm_config.py</code>（角色配置模型）还留 <code>inherit</code> / 组级 intent / <code>cost_priority</code>（都是可选字段），前端按 role-only 建、不发它们即可，后端并行清。</div>')
        todo = _todo_list("实施顺序 · Todo（满分先行、最复杂压后）", [
            ("N0.2", "General 设置页 · 操作设计", "ok", "✅ 前端完成 · 仅 #15.1 语言持久化等后端", True),
            ("N0.5", "Copilot 设置页 · 操作设计", "ok", "✅ 全做完 #55/#56/#57/#61/#62/#63/#64/#65（Wave A 后端 + Wave B 前端 12 项）", True),
            ("N0.3", "API Keys 设置页 · 操作设计", "partial", "✅ 前端可做的 #19/#22 已做 · #20/#24/#25/#27/#30+蓝态 等后端", True),
            ("N0.1", "Settings 壳层 · 操作设计", "ok", "✅ 全做完 #2/#4/#5/#6/#9", True),
            ("N0.4", "LLM 角色设置页 · 操作设计", "partial", "✅ 前端完成 #35/#36/#46/#47/#50a · #51/#50b 等后端", True),
        ])
        impl_block = (
            '<div class="sec-label">开工实施 · 规范（开工前必读）</div>'
            '<p class="body-copy">设计已审计可 100% 落地；下面是怎么开工的硬规范——分支 / worktree、地基、后端先于前端、逐页 routine。</p>'
            + norms + track
            + '<div class="sec-label">实施顺序 · Todo</div>'
            '<p class="body-copy">按「满分先行、最复杂压后」排；勾掉一页 = 该页<b>前端可做</b>的设计原子全部实现 + 两层测试过 + 真机验收过。<b>等后端</b>的原子（后端契约/字段未就绪，前端建了也无数据可接）在右侧标签里单列、不算未完成——五页前端可做的都已落地（6 commit，见进度文档）。</p>'
            + todo)
    elif code_ == "N6":
        norms = _wave_cards([
            ("另开分支", "N6 前端在 `feat/n6-publish-frontend` 上做，别和后端线 `codex/studio-mvp1-12d-strict-tdd` 的未提交活混；做完按文件名逐个 commit，绝不 `git add .`。"),
            ("Worktree / 地基", "`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased`；N6 前端 = `components/studio/Workspace.tsx`（成功 run 后存档反馈）、`components/history/HistoryPanel.tsx`（本地历史面板）、`components/studio/Header.tsx`（Release + Package release 入口 / 回执徽章）、`hooks/usePublishSkill.ts`（发布 hook）、`hooks/useRunHistory.ts`（本地历史 + run 详情 hook）、`lib/tauri.ts`（native-fs 命令）；后端契约 history / revert / publish（`routers/skills.py`）、`runs.get_run`（#1 读 git_status 的读模型）、native-fs `publish_package_writer`（`native_fs.rs`）均已实现、可接。"),
            ("后端先于前端", "每页动手前确认它依赖的后端契约是已提交那版；前端只投影后端 DTO（`PublishResult` / `GitHistoryItem` / `RunDetail.metadata.git_status`）、不自存第二份真相。"),
            ("逐页走 routine", "每页按 S0 的 5 步：读设计 → 写两层测试（先红）→ 按契约实现 → 跑 focused gate → 真机验收（发布 / native-fs 写盘要用真路径真跑一次）。"),
        ])
        track = ('<div class="callout amber"><b>3 件后端 code↔design drift（边建边等后端，不挡开工）</b>：'
                 '① <b>发布 zip 上传未接</b>——publish 远端只同步 release manifest（`sync_release_manifest` → `POST /releases`），未上传 zip package（`upload_artifact` 无 publish 生产调用）；前端 Release / 回执按设计先建，zip 上传收口归后端（D12 Rust 写者）。'
                 '② <b>registry 前置校验未实现</b>——registry host/token 缺时后端降级本地发布、<b>不报错</b>（`REGISTRY_NOT_CONFIGURED` 从不抛），前端「Open Settings」指引逻辑先建，registry 指引分支等后端补抛 typed error 才点亮（user_id 缺的指引已可用）。'
                 '③ <b>git_status 边界</b>——`auto_commit_run` 在无 `.git` 时返回 None 但仍被标 committed；前端 #1 用「已自动存档（如有 git 仓）」保留口径，后端区分 skipped/no_repo 后再收紧。</div>')
        todo = _todo_list("实施顺序 · Todo（满分先行、最复杂压后）", [
            ("N6.2", "发布(Release) · 操作设计", "partial", "前端独立为主 · #7 等后端 drift", False),
            ("N6.1", "本地存档与历史 · 操作设计", "partial", "前端独立 · 读模型已就绪", False),
        ])
        impl_block = (
            '<div class="sec-label">开工实施 · 规范（开工前必读）</div>'
            '<p class="body-copy">设计已审计可落地（发布契约的 zip 上传 / registry 前置 / git_status 三处 code↔design drift 已标清、不挡前端开工）；下面是怎么开工的硬规范——分支 / worktree、地基、后端先于前端、逐页 routine。</p>'
            + norms + track
            + '<div class="sec-label">实施顺序 · Todo</div>'
            '<p class="body-copy">N6 只 2 张设计页，按「满分先行、最复杂压后」排；每勾掉一页 = 该页设计原子全部实现 + 两层测试过 + 真机验收过。前端独立项（#9 删 confetti orphan、#5 入口文案消歧、#1/#2 接 run 完成、#3/#4/#6/#8/#10 补回归）不被后端挡；唯 #7 的 registry 指引分支待后端补抛码。</p>'
            + todo)
    elif code_ == "N5":
        norms = _wave_cards([
            ("另开分支（⚠ 基线非干净）", "N5 前端在 `feat/n5-debug-resume-frontend` 上做。⚠ 与 N0/N6 不同：N5 的续跑/HitL/篡改前端脚手架**当前是未提交 WIP**（8 个改动 + 3 个未跟踪新文件，和后端线 `codex/studio-mvp1-12d-strict-tdd` 的活混在同一脏工作树）。开工第一步：**先把这批 N5 前端改动 commit 到专属分支、或 stash 隔离**，从已知 committed 状态起步，别直接在当前脏工作树上接着改；做完按文件名逐个 commit，绝不 `git add .`。"),
            ("Worktree / 地基", "`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased`（当前在 `feat/n0-settings-frontend`，工作树 55 个未提交文件、29 个在 `frontend/src`）。**已提交干净层**（图节点 + 画布 + 边 + 事件流，last commit `c11d56f0`「harden mvp1 wave1 contracts」）：`components/nodes/SkillNode.tsx`、`components/GraphCanvas/GraphCanvas.tsx`、`components/edges/ContextEdge.tsx`、`hooks/useRunStream.ts`、`lib/websocket.ts`。**未提交脏层**（N5 续跑脚手架，已存在但未 commit）：改动 8 个——`api/client.ts`（resumeRun/getResumeValidity）、`api/types.ts`（ResumeValidityResponse）、`TracePanel.tsx`（latestHitlPrompt + VirtualTraceList + 全局 Resume）、`Workspace.tsx`（4 个 handler 都在）、`node-status.ts`（deriveNodeStatuses）、`panels/EdgeContextView.tsx`、`panels/PropertiesPanel.tsx`（NodeResumeDebugBar）、`lib/edge-context.ts`；未跟踪新文件 3 个——`node-resume.ts`（nodeResumeCheckpointFromEvents）、`panels/edge-tamper.ts`、`resume-options.ts`（hitlResumeOptionsFromRequest）。"),
            ("后端先于前端", "N5 的续跑 / checkpoint / 事件契约归 engine，Studio 前端只投影 DTO（`RunMetadata` / `ResumeValidityResponse` / `EventEnvelope`）+ 触发，不自存第二份真相；下面 4 处后端 gap **边建边等、不挡开工**。"),
            ("逐页走 routine + 调试前置", "每页按 S0 的 5 步：读设计 → 写两层测试（先红）→ 按契约实现 → 跑 focused gate → 真机验收。⚠ N5 真机验收**必须先有一次真实失败 / 暂停 Run**（产 trace + checkpoint）才能验节点级续跑 / HitL / 篡改；HitL 与续跑真跑要用真 key 真模型，不接受 mock 充数。"),
        ])
        track = ('<div class="callout amber"><b>4 处后端依赖（边建边等后端，不挡开工）</b>：'
                 '① <b>HitL 暂停事件未发射</b>——引擎 <code>InterruptedEvent</code> / <code>ResumedEvent</code> 仅类定义、从不发射，真实续跑事件是 <code>resume_applied</code>；前端 HitL 悬浮框（<code>NodeToolbar</code> 锚 paused 节点）先建、mock interrupted 测，后端补发即点亮（卡 N5.2#5）。'
                 '② <b>事件不带 checkpoint_id/ns</b>——<code>events.py</code> 各事件类无该字段、sidecar 不 enrich；节点 / 边续跑先建，真跑缺 checkpoint 时退化为「最近 checkpoint」，后端 enrich 后转精准定位（卡 N5.1#2 / N5.3#9）。'
                 '③ <b>validity 全局 artifact 级</b>——<code>resume_validity</code> 只比 content_hash / execution_fingerprint、<code>resume_from_node_id</code> 仅回显、无 per-node 判定；前端置灰先建，真跑会见无关旁支也判 dirty（F3 未满足），据实记、后端补 per-node 后收敛（卡 N5.1#3）。'
                 '④ <b>节点级 1..X-1 不重跑 编排 partial</b>——<code>resume_skill</code> 收并校验起止节点但无显式跳跑编排（D10.2）；前端带 <code>resume_from_node_id</code> 先建，真跑核对上游是否重跑、若重跑据实记（卡 N5.1#2 / F2）。</div>')
        todo = _todo_list("实施顺序 · Todo（满分先行、最复杂/最依赖后端压后）", [
            ("N5.4", "Trace 时间线 · 操作设计", "ok", "底座 · 已符合 · 回归保护", False),
            ("N5.3", "边 dot Context 篡改 · 操作设计", "partial", "纯前端 · Textarea→可写 Monaco", False),
            ("N5.1", "失败节点 · 操作设计", "partial", "前端下沉 + 等后端 validity / 跳跑", False),
            ("N5.2", "HitL 悬浮输入 · 操作设计", "bad", "等后端 · 暂停事件源未发射", False),
        ])
        impl_block = (
            '<div class="sec-label">开工实施 · 规范（开工前必读）</div>'
            '<p class="body-copy">设计已审计可落地（续跑 / checkpoint / 事件 4 处后端 gap 已标清、均边建边等不挡前端开工）。⚠ 与 N0/N6 不同：N5 续跑 / HitL / 篡改前端脚手架**已是未提交 WIP**（混在 codex 后端线脏工作树里），开工第一步是先把它 commit 到专属分支或 stash 隔离、从干净基线起步，别在脏树上接着改。下面是开工硬规范——分支 / worktree、地基、后端先于前端、逐页 routine + 调试前置。</p>'
            + norms + track
            + '<div class="sec-label">实施顺序 · Todo</div>'
            '<p class="body-copy">按「满分先行、最复杂 / 最依赖后端压后」排：N5.4 trace 已全符合（做底座 + 回归保护）→ N5.3 边篡改唯一实质活是换可写 Monaco（纯前端快赢）→ N5.1 失败节点（错误就地纯前端，但节点级 Resume / 脏态置灰卡后端 validity + 跳跑，且脏态置灰依赖节点 Resume 先落位）→ N5.2 HitL（旗舰悬浮框卡在暂停事件源未发射，最依赖后端）。每勾掉一页 = 该页设计原子全部实现 + 两层测试过 + 真机验收过（受后端 gap 制约的项据实记、不谎报解锁）。</p>'
            + todo)
    return section(nctx["pages"]["overview"], f"节点主页 · {code_}", f"{code_} · {ESC(name)}",
                   f"{name} 节点的 {total_pages} 页总入口：{n_surfaces} 个页面操作设计 + 契约 / 复用模块 / 实施 / 测试。",
                   intro + "".join(items) + impl_block)


def _full_node_card(full):
    """A 7-node-overview card for a deepened (full) node."""
    from collections import Counter
    nctx, stages = full["nctx"], full["stages"]
    code_, name = nctx["code"], nctx["name"]
    cnt = Counter()
    for s in stages:
        cnt.update(Counter(a.get("fe_status", "") for a in s["design"]["atoms"]))
    n_atoms = sum(len(s["design"]["atoms"]) for s in stages)
    roll = "偏差" if cnt.get("偏差") else ("未实施" if cnt.get("未实施") else "符合")
    p = nctx["pages"]
    return card(
        f'{ESC(code_)} · {ESC(name)}', [
            ("状态", f'已铺开（{len(stages)} 个页面：{"、".join(s["label"] for s in stages)}）· {n_atoms} 操作 = {cnt.get("符合",0)} 符合 / {cnt.get("偏差",0)} 偏差 / {cnt.get("未实施",0)} 未实施'),
            ("页面", f'<a class="xlink" href="#{p["overview"]}">节点主页</a> · <a class="xlink" href="#{stages[0]["design"]["page_id"]}">设计（{len(stages)}）</a> · <a class="xlink" href="#{p["contract"]}">后端接口契约</a> · <a class="xlink" href="#{p["fe_modules"]}">前端复用模块</a> · <a class="xlink" href="#{p["impl"]}">实施</a> · <a class="xlink" href="#{p["tests"]}">测试</a>'),
        ], tag=fe_badge(roll), mono=False)


def _legacy_node_card(nd):
    return card(
        f'{ESC(nd.get("code",""))} · {ESC(nd.get("title",""))}', [
            ("状态", "旧格式占位，待深化为「设计 / 后端接口契约 / 前端复用模块 / 实施 / 测试」"),
            ("页面", f'<a class="xlink" href="#{nd.get("code","")}">节点（待深化）</a>'),
        ], tag=badge("待深化", "a"), mono=False)


def render_handbook_overview(node_specs):
    """node_specs = ordered list of ('full', full_dict) | ('legacy', nd) for N0..N6."""
    def t(headers, rowdata):
        return ('<table class="info-table"><thead><tr>' + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{code(x)}</td>" for x in r) + "</tr>" for r in rowdata) + "</tbody></table>")

    be = t(["前端要对接的后端", "= 什么", "管什么"], [
        ("gateway 后端", "gateway SDK + Python sidecar 暴露的 gateway API（如 `/api/llm/*`）", "凭证、协议探测、路由、6 态、materialize。"),
        ("engine 后端", "engine SDK + Python sidecar 暴露的 engine API", "执行原语：compile / run / predict / resume / serialize。搭图节点（N2）主要对接它。"),
        ("Studio Rust 后端", "`apps/studio/tauri`（与 Python sidecar 无关的原生部分）", "native-fs（本地文件读写）+ sidecar 生命周期 + IPC。搭图写盘走它。"),
    ])
    arch = (
        '<p class="body-copy">底层是 MVP1 三模块（Engine `packages/graph-agent` / Gateway `packages/graph-agent-gateway` / Studio `apps/studio`）。但<b>从前端对接的视角</b>，你只需认下面三块后端 —— 因为前端对接的全是 <b>Python sidecar</b>（`apps/studio/backend`）暴露的 HTTP API；这个 sidecar 是 engine/gateway 的 <b>adapter</b>。「sidecar API ↔ gateway/engine SDK」内部怎么拆是后端实现的事，<b>前端不区分</b>。</p>'
        + be
        + '<p class="body-copy"><b>前端</b> = `apps/studio/frontend`（React），只投影后端、不自存第二份真相。（General 页的 `app_settings.json` 是 Studio 自己的应用配置，由 sidecar 暴露但不属 gateway/engine；搭图节点的所有写盘走 Studio Rust 后端的 native-fs。）</p>')
    node_cards = "".join(
        _full_node_card(spec) if kind == "full" else _legacy_node_card(spec)
        for kind, spec in node_specs
    )
    env_tbl = _kv_table([
        ("基准分支", "`main`（<b>唯一权威基准</b>，`origin/main` CI 全绿）。新工作一律从 main 切分支：`git switch -c <type>/<desc> origin/main`。旧的 `feat/n0-settings-frontend` 等集成分支已并入 main 并清理，<b>别再基于旧分支/旧 worktree 开工</b>。"),
        ("怎么开工（从 main 切）", "`git worktree add ../<名字> origin/main`（或 `git switch -c <分支> origin/main`）切出自己的工作区。<b>不要复用旧集成 worktree</b>（已清理）。`main` 检出在 `.worktrees/main-gateway-integration`（永远 = `origin/main`）。"),
        ("跑应用", "`cd apps/studio/tauri && cargo tauri dev`（一条命令同时拉起 Vite + FastAPI sidecar）"),
        ("前端门禁（改完必跑、绿了再推 main）", "`apps/studio/frontend` 下：`npm run lint` · `npm run typecheck` · `npm test` · `npm run build`（缺一不可——lint/typecheck 是独立门禁，光过 test 不够）"),
        ("重建本手册", "`python3 docs/studio/mvp1/_impl/frontend-handbook/build_template_slice.py` → 同目录 `index.html`（本地 `:8902` 服务指向此目录）"),
        ("权威 spec", "`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`"),
        ("后端进度", "见下方「后端实施手册」D1–D12（对应 12D HTML，已同步到 main 基线）"),
    ])
    content = (
        '<div class="callout"><b>边界</b>：这本是 <b>Studio MVP1 前端</b>说明书，按工作流 <b>7 个节点（N0 Settings → N6 Publish）</b>组织。后端（gateway 后端 / engine 后端 / Studio Rust 后端）的实现不归我们；我们只把后端<b>契约</b>写清楚、按契约先建。每个节点内部一套页型：<b>设计 / 后端接口契约 / 前端复用模块 / 实施 / 测试</b>（复用模块是<b>各节点自己的</b>，节点间不共享通用组件）。<b>读法</b>：先看下面的实施环境 / 顺序 / routine / 方法论，再进具体节点页。</div>'
        '<div class="callout amber"><b>「后端实施手册」是什么</b>（后文都指它）：全名 <a class="xlink" href="' + D12 + '#s0_overview">Studio MVP1 后端 12 维度修复框架</a>，按 12 维度（D1–D12）记录后端三模块的进度。本手册引用它标注每条后端契约<b>实现到哪了</b>。</div>'
        + f'<div class="sec-label">架构基础 · 前端要对接的后端（全局 · 所有节点通用）</div>{arch}'
        + '<div class="callout green">一句话流程：前端画界面 → 调 Python sidecar 暴露的 API（即 gateway 后端 / engine 后端）→ sidecar 把活转给 gateway/engine SDK。前端只认 sidecar 的 API，不碰 SDK。</div>'
        + '<div class="sec-label">实施环境</div>'
        + '<p class="body-copy">这些信息决定后续所有测试和状态判断的坐标——先确认自己看的就是这条 worktree / branch，改完手册怎么重建、设计以哪份 spec 为准，都在这。</p>'
        + env_tbl
        + '<div class="sec-label">实施顺序（波次）</div>'
        + '<p class="body-copy">波次不是时间墙，是依赖关系 + 当前进度：先认清现在做到哪、按什么顺序往下推、为什么后端要先于前端。</p>'
        + _wave_cards([
            ("当前进度", "节点逐个从旧占位深化成完整页型；各节点当前是「已铺开」还是「待深化」以下方「7 个工作流节点」里每张节点卡的状态徽章为准（已铺开=完整页型、待深化=旧格式占位）。"),
            ("推进顺序", "按工作流 N0 → N6 逐节点深化，每节点产出一套页型（每个 surface 一张设计页 + 契约 + 复用模块 + 实施 + 测试）。"),
            ("后端先于前端（铁律）", "每节点先把后端契约（对接 gateway / engine sidecar API）定下来，再做前端适配，最后真机验收——契约没定就改前端 = 返工。"),
        ])
        + '<div class="sec-label">N1–N6 实施 Wave 计划（参照 12D wave todo）</div>'
        + '<p class="body-copy">全节点实施波次 + todo,按依赖排:Wave 0 纯前端、无后端依赖、现可做;Wave 1 后端/契约层(engine 服务 / gateway 服务 拥内核、Rust/Tauri 原生层唯一写盘+sidecar 生命周期+OS 桌面、Studio 后端壳只做 HTTP/DTO/编排),后端先于前端;Wave 2 前端接线,各自等对应 Wave 1 契约落地。engine 与 gateway 项归对应后端团队、12D 同步实施(逐项见后端实施手册 D 各域)。</p>'
        + _wave_cards([
            ("Wave 0 · 纯前端 / 无后端依赖", "现可做:N3/N1 部分已提交;剩 N4 trace 可读化、N3 lint hook 骨架、N5 边篡改可写 Monaco、N0 language。"),
            ("Wave 1 · 后端 / 契约层（后端先于前端）", "四块:engine 服务(G1/HitL/golden-stale/续跑/lint 内核/per-node golden 模型)+ gateway 服务(test 内核/6态 route/materialize/schema/P8)拥内核。Rust/Tauri 原生层是唯一写者(golden、publish 写包),还管 sidecar 生命周期/OS 桌面/MRU/checkpoint——native-fs 只是其文件 I/O 切面。`apps/studio/backend` 不是第三个 sidecar,是 Studio 后端壳(只 HTTP 端点+DTO 投影+编排,如 ⑧a wall_time DTO 透传、⑥-be 去 MetadataStore)。"),
            ("Wave 2 · 前端接线（依赖 Wave 1）", "skill-create via Rust、golden 三态、耗时显示、lint 字段投影、HitL 悬浮框、LLM 设置消费 Gateway DTO、P8 对比 UI。"),
        ])
        + _todo_list("Wave 0 · 纯前端（已全部整合 feat/n0 · 914 前端测试绿）", [
            ("N3.gating", "动作条锁态 tooltip + rounded-md", "ok", "Studio 前端 · 已提交", True),
            ("N3.drawer", "画布作用域 Compile drawer + 删旧浮层", "ok", "Studio 前端 · 已提交", True),
            ("N1.shell", "删孤儿 WelcomeScreen", "ok", "Studio 前端 · 已提交", True),
            ("N1.home", "Recent MRU 化 + shadcn Skeleton", "ok", "Studio 前端 · 已提交", True),
            ("N4.trace", "Trace 可读化（折叠 / 重试徽章 / Prompt 回溯接 findPromptEvent）", "ok", "Studio 前端 · ✅ 已整合", True),
            ("N3.lint", "实时 lint hook 接线骨架", "ok", "Studio 前端 · ✅ 已整合", True),
            ("N5.edge", "边 dot Context 篡改（Textarea → 可写 Monaco）", "ok", "Studio 前端 · ✅ 已整合", True),
            ("N0.i18n", "language 字段 + 设置页语言开关", "ok", "Studio settings · ✅ 已整合", True),
        ])
        + _todo_list("Wave 1 · 后端 / 契约层（✅ 已全部整合 feat/n0 · engine 1364 / gateway 240 / studio 958 全绿 · gatekeeper 抓修 5 处 agent 藏的回归）", [
            ("①C/D/G", "test/probe 内核归 Gateway + 删官方门禁 + 统一 test 入口 + 束 test 端点（Copilot SDK test 留 Studio）", "ok", "Gateway · ✅ 7f9bacd5", True),
            ("⑦B", "6 态投到裸 route DTO（ProviderRoute.ui_state）", "ok", "Gateway · ✅ 7f9bacd5", True),
            ("⑦F", "束 = 引用 + delta materialize（RoleEntry.bundle_id）", "ok", "Gateway · ✅ 7f9bacd5", True),
            ("⑦H", "role/intent schema 清理（删 inherit / ModelGroupIntent / cost_priority）", "ok", "Gateway · ✅ 7f9bacd5", True),
            ("⑩", "P8 临时 role 解析路径（materialize 延伸,依赖 ⑦F）", "ok", "Gateway · ✅ 7f9bacd5", True),
            ("④", "G1 定位轴 field_path/source_path 填满 + 不降级过边界", "ok", "引擎 · ✅ 6f2e8118", True),
            ("⑧b", "HitL InterruptedEvent/ResumedEvent 发射 + checkpoint_id/ns", "ok", "引擎 · ✅ 6f2e8118", True),
            ("⑨", "golden-stale-fields（eval 期）错误码注册 + 发射", "ok", "引擎 · ✅ 6f2e8118", True),
            ("⑪⑫⑬", "续跑细化:事件带 checkpoint_id · per-node validity · 1..X-1 不重跑", "ok", "引擎 · ✅ 6f2e8118", True),
            ("③", "/lint changed-markdown：lint 是 engine 服务的能力（F1 compile/lint authority）；Studio 后端壳把未落盘的编辑内容转发给 engine lint，不另造编译器", "ok", "engine 服务 · Studio 壳转发 · ✅ 已整合", True),
            ("⑤", "per-node golden：per-node 模型/cases/失效归 engine 服务（F5/ENGINE-3）；写 .workspace/golden 走 Rust 原生层；Studio 后端壳投影 SetGoldenReq.node_id + GoldenBaseline.cases DTO", "ok", "engine · Rust 写 · Studio 壳 · ✅ 已整合", True),
            ("⑥-be", "去注册表：Home 列表真相改 Rust 原生层工作区（打开文件夹/MRU/list_workspace_dir）；Studio 后端壳去掉自己的 MetadataStore，import 放宽（不卡缺根文档）", "ok", "Rust 原生层真相 · Studio 壳 · ✅ 已整合", True),
            ("⑧a", "wall_time：metric 是 engine 服务产出的；Studio 后端壳的 TokensMetrics DTO 停 forbid 剥字段、忠实透传", "ok", "engine 产出 · Studio 壳 DTO · ✅ 已整合", True),
            ("N6.pub", "写包走 Rust 原生层 publish_package_writer；Studio 后端壳做 registry precheck/编排、跳 Settings、git_status 无 git 良性边界", "ok", "Rust 写包 · Studio 壳编排 · ✅ 已整合", True),
        ])
        + '<div class="callout green" style="margin:14px 0 6px"><b>Wave 2 已实施 → 独立复核 → 整合 feat/n0</b>(实施前审计修订后的 4 项)。组合态定论门禁:<b>前端 122 文件 / 960 测试 + studio 后端 960 + typecheck 全绿</b>。集成 5 个 merge(llm/golden-wall 干净;field/hitl 解了 <code>Workspace.tsx</code>/<code>PropertiesPanel.tsx</code>/<code>GraphCanvas.tsx</code> 共享 hub 的 import/props 冲突——均"双方各加不同语义")。<b>skill 仍后端先行延期</b>;P8 已删(非设计原子)。下方「后端先行 follow-on」据实记前端已投影到位、等后端补的契约。</div>'
        + _todo_list("Wave 2 · 前端接线（4 项已整合 feat/n0 · skill 后端先行 · follow-on 见下）", [
            ("N4.golden", "golden 三态徽标(ShieldCheck) + per-node promote(SetGoldenReq.node_id);has-golden 两态已落,🟡 logic-OK / #33 模板待后端 follow-on", "ok", "✅ a875bd20", True),
            ("N4.wall", "运行耗时 TokensMetrics.wall_time_sec 投影 + 替换 TimelinePanel 旧 unknown 强转", "ok", "✅ a875bd20", True),
            ("N5.hitl", "HitL 节点锚定悬浮框(React Flow NodeToolbar 锚暂停节点);核实真 InterruptedEvent 无 tool_call_id 已降级", "ok", "✅ 1ded990a", True),
            ("N0.llm", "消费 6 态 / role_fit / materialize DTO + 补测锁定;#50b 束 test / #51 bundle_id 待后端 follow-on", "ok", "✅ fb931036", True),
            ("N3.field", "lint 字段就近投影:壳 LintError 补 field_path passthrough(skills.py:1484)+ Properties 字段旁标 + Monaco marker", "ok", "✅ 54632b7e", True),
            ("⑥-fe skill", "skill 新建/打开走 Rust native-fs(create/open/exists 已落;详见下方 follow-on)", "ok", "✅ 5389234e", True),
        ])
        + '<div class="sec-label">Wave 3 · follow-on（已实施 + 整合 feat/n0）</div>'
        + '<div class="callout green" style="margin:6px 0"><b>Wave 3 follow-on 已全部实施 → 独立复核 → 整合 feat/n0</b>。先用 workflow 规划 + 对抗式实施前审计(审计纠正了多处:golden-🟡 复用 <code>PredictDiagnosticExport</code> 不新建模型、bundle-test 复用现成 <code>materialize_model_bundle</code> 不碰 gateway、bundle-ref 只把 <code>bundle_id</code> 透传到 gateway 不在壳重造合并),再后端先行实施。组合全量门禁:<b>前端 988 / studio 后端 979 / Rust 90 / typecheck 全绿,engine/gateway 包零改动</b>。</div>'
        + _todo_list("Wave 3 follow-on · 已整合 feat/n0（后端先行,组合全量绿）", [
            ("skill", "Rust create/open_skill_workspace + workspace_path_exists,前端切走 Python POST;skill_index 与 Python 字节对齐", "ok", "✅ 5389234e · Rust 原生层", True),
            ("golden-🟡", "logic-OK 中间态:复用 PredictDiagnosticExport(不新建模型)+ 按 phases 出现驱动 + 仅 agent 节点", "ok", "✅ c9808701 · 壳投影", True),
            ("golden-#33", "手填模板:engine generate_heuristic_stub 重导 + run-less manual write(node_id keyed,不挂 run);写盘走 Rust 唯一写者(8ce187cd)", "ok", "✅ c9808701 · 壳", True),
            ("llm-#50b", "束级 test 端点 /model-bundles/{id}/test-jobs:复用 materialize_model_bundle 临时角色、不污染 roles 库", "ok", "✅ 7633708f · 壳", True),
            ("llm-#51", "束=引用:bundle_id 一路透传到 gateway materialize_role_entry(壳不重造合并)+ 删束级联 + 引用非快照", "ok", "✅ 7633708f · 壳 plumb", True),
        ])
        + '<div class="callout green" style="margin:8px 0"><b>设计待钉项已收尾(Wave-3b)</b>:① <b>agent 相位空模板已落地</b>——新建脚手架从 logic 三件套(LOGIC.md+actions/initialize.py)换成<b>空 agent 相位</b>(单文件 <code>phases/init/SKILL.md</code>,role/goal 占位满足引擎 min_length,引擎真编译验证为 agent 模式),Python/Rust 字节一致;② <b>手填 golden 改走 Rust 唯一写者</b>(删 Python 落盘端点,非桌面降级 Desktop-only,不走浏览器 HTTP——经核 MVP1 设计本就无"浏览器退回 HTTP"一说);③ 删死代码 <code>SkillCreatorWizard</code> 及连带孤儿 <code>creator/steps</code>(零引用核实)。组合门禁:前端 989 / 后端 982 / Rust 90 全绿。</div>'
        + '<div class="sec-label">实施 routine · 每页怎么落地</div>'
        + '<p class="body-copy">每个页面都按同一套节奏落地，让红灯、实现、验收、状态之间有可追踪的因果链——不是仪式，是因果。</p>'
        + _routine_steps([
            ("读页面设计", "从 MVP1 第一性原理确认每个操作的目标、用户怎么触发、前端职责、依赖哪条后端契约——别从旧实现 / 组件名出发。"),
            ("写两层测试（先红）", "业务逻辑静态测试（红 → 绿）+ e2e 真机测试（鼠标点界面、拿预期状态截图）；实现前先让测试失败。"),
            ("按契约实现前端", "只投影后端、不自存第二份真相；沿用现有 shadcn 组件与风格，不自造组件。"),
            ("跑 focused gate", "先跑该页 focused 测试，再按影响面扩到组合 gate；UI 改动必须补真机 / Tauri 手工路径。"),
            ("真机验收 + 收口", "截图对齐预期状态，记录真实结果与剩余风险，回填实施页 / 测试页；做不完的功能记进延期、继续下一个，不停在半路。"),
        ])
        + '<div class="sec-label">实施落地方法论</div>'
        + '<p class="body-copy">这套方法管的是<b>前端怎么正确落地</b>（不是怎么写这本手册）。核心：先把后端契约和正确设计认清，再用证据把「实现 == 设计」钉死，别从旧实现倒推、别拿降级凑数。</p>'
        + _wave_cards([
            ("先认契约与设计本体", "落地前先从第一性原理认清：这个操作的正确设计长啥样、依赖后端哪条契约、契约实现到哪了——不从旧实现倒推 UI。"),
            ("前端只投影、不自存真相", "前端只投影后端返回的 DTO，绝不在前端自存第二份真相；后端契约没定就不动前端（后端先于前端）。"),
            ("证据闭环验收", "每个功能都落到证据：业务逻辑静态测试（红 → 绿）+ 真机点击出预期状态截图。「有测试 / 能开机」≠「真能用」，以真跑为准。"),
            ("复用不自造、撞墙不空转", "沿用现有 shadcn 组件与设计风格，不自造；撞上做不了的功能记进延期、继续下一个，不停在半路。"),
        ])
        + '<div class="sec-label">7 个工作流节点</div>'
        + '<div class="callout">下面每张节点卡的状态徽章标明它是<b>已铺开</b>（完整页型：设计 / 后端接口契约 / 前端复用模块 / 实施 / 测试）还是<b>待深化</b>（旧格式占位，保留全貌待逐节点深化）。</div>'
        + node_cards
    )
    return section("handbook_overview", "Studio MVP1 · 前端实施手册 · 总览", "Studio MVP1 前端实施手册（N0–N6）",
                   "按 7 个工作流节点组织（N0 Settings → N6 Publish）；每节点一套页型：设计 / 后端接口契约 / 前端复用模块 / 实施 / 测试。", content)


def section(pid, tag, title, subtitle, content):
    return (f'<section class="doc-section" id="{pid}"><div class="card-header-tag">{ESC(tag)}</div>'
            f'<h2 class="lesson-title">{ESC(title)}</h2><div class="lesson-subtitle">{code(subtitle)}</div>{content}</section>')


# 每个 surface 一个元组：(ns, label, design_file, [mech_files], impl_file, femods_file)。
# N0：1 个壳层 + 4 个设置页（非递进、并列）。
PAGES_N0 = [
    ("shell", "Settings 壳层", "tpl-shell-design.json", ["tpl-shell-mech-overlay.json"], "tpl-shell-impl.json", "tpl-shell-femods.json"),
    ("general", "General 设置页", "tpl-general-design.json", ["tpl-general-mech-appsettings.json"], "tpl-general-impl.json", "tpl-general-femods.json"),
    ("apikeys", "API Keys 设置页", "tpl-apikeys-design.json", ["tpl-mech-cred.json"], "tpl-apikeys-impl.json", "tpl-apikeys-femods.json"),
    ("roles", "LLM 角色设置页", "tpl-roles-design.json", ["tpl-roles-mech-materialize.json"], "tpl-roles-impl.json", "tpl-roles-femods.json"),
    ("copilot", "Copilot 设置页", "tpl-copilot-design.json", ["tpl-copilot-mech-route.json"], "tpl-copilot-impl.json", "tpl-copilot-femods.json"),
]
# N1 · Init：3 个 surface（Home/Welcome 屏 / 新建 Skill 对话框 / Workspace 外壳）。
# skill 发现/读写契约（mech_skills）+ native-fs 本地文件契约（mech_nativefs）都挂 home 面，渲一次；
# femods 分布在 home（3 个 N1 自有模块）与 shell（外壳容器），newskill 复用 home 的（去重聚合进 n1_fe_modules）。
PAGES_N1 = [
    ("home", "Home/Welcome 屏", "tpl-n1-home-design.json", ["tpl-n1-mech-skills.json", "tpl-n1-mech-nativefs.json"], "tpl-n1-home-impl.json", "tpl-n1-home-femods.json"),
    ("newskill", "新建 Skill 对话框", "tpl-n1-newskill-design.json", [], "tpl-n1-newskill-impl.json", "tpl-n1-newskill-femods.json"),
    ("shell", "Workspace 外壳", "tpl-n1-shell-design.json", [], "tpl-n1-shell-impl.json", "tpl-n1-shell-femods.json"),
]

# N2 · Authoring：4 个 surface（画布 / Properties / GRAPH.md 宏观 / i/o 面板）。
# 机制 mech_graph 挂画布、mech_io 挂 i/o 面板；femods 单文件被所有 surface 复用（去重）。
PAGES_N2 = [
    ("canvas", "画布搭建", "tpl-n2-canvas-design.json", ["tpl-n2-mech-graph.json"], "tpl-n2-canvas-impl.json", "tpl-n2-femods.json"),
    ("properties", "Properties 节点属性", "tpl-n2-properties-design.json", [], "tpl-n2-properties-impl.json", "tpl-n2-femods.json"),
    ("graphmd", "GRAPH.md 宏观契约", "tpl-n2-graphmd-design.json", [], "tpl-n2-graphmd-impl.json", "tpl-n2-femods.json"),
    ("iopanel", "i/o 面板", "tpl-n2-iopanel-design.json", ["tpl-n2-mech-io.json"], "tpl-n2-iopanel-impl.json", "tpl-n2-femods.json"),
]

# N4 · Run & Verify：4 个 surface（Predict 试飞 / Run 控制 / Trace 去黑盒 / Golden 验收）。
# 每 surface 一张设计页 + 一张机制页；femods 分布在 predict/run/golden（trace 复用前两者，无单独 femods 文件）。
PAGES_N4 = [
    ("predict", "Predict 试飞", "tpl-n4-predict-design.json", ["tpl-n4-predict-mech.json"], "tpl-n4-predict-impl.json", "tpl-n4-predict-femods.json"),
    ("run", "Run 控制", "tpl-n4-run-design.json", ["tpl-n4-run-mech.json"], "tpl-n4-run-impl.json", "tpl-n4-run-femods.json"),
    ("trace", "Trace 去黑盒", "tpl-n4-trace-design.json", ["tpl-n4-trace-mech.json"], "tpl-n4-trace-impl.json", None),
    ("golden", "Golden 验收", "tpl-n4-golden-design.json", ["tpl-n4-golden-mech.json"], "tpl-n4-golden-impl.json", "tpl-n4-golden-femods.json"),
]

# N6 · Save & Publish：2 个 surface（本地存档与历史 / 发布 Release）。
# 每 surface 一张设计页 + 一张机制页 + 一份 femods；机制 id 唯一（n6_history_mech / n6_publish_mech）。
PAGES_N6 = [
    ("n6history", "本地存档与历史", "tpl-n6-history-design.json", ["tpl-n6-history-mech.json"], "tpl-n6-history-impl.json", "tpl-n6-history-femods.json"),
    ("n6publish", "发布(Release)", "tpl-n6-publish-design.json", ["tpl-n6-publish-mech.json"], "tpl-n6-publish-impl.json", "tpl-n6-publish-femods.json"),
]

# N3 · Compile：3 个 surface（实时 lint 三处投影 / Compile drawer / 动作条门控）。
# 共用一张编译/lint 错误契约机制页（挂在第一个 surface 上,只渲一次）；femods 单文件被所有 surface 复用（去重）。
PAGES_N3 = [
    ("lint", "实时 lint 与就近投影", "tpl-n3-lint-design.json", ["tpl-n3-mech-compile.json"], "tpl-n3-lint-impl.json", "tpl-n3-femods.json"),
    ("drawer", "Compile drawer", "tpl-n3-drawer-design.json", [], "tpl-n3-drawer-impl.json", "tpl-n3-femods.json"),
    ("gating", "动作条编译门控", "tpl-n3-gating-design.json", [], "tpl-n3-gating-impl.json", "tpl-n3-femods.json"),
]

# N5 · Debug & Resume：4 个 surface（失败节点调试 / HitL 悬浮输入 / 边 dot 篡改 / Trace 时间线）。
# resume+checkpoint 机制挂节点面、events 机制挂 trace 面；每 surface 一份 design/impl/femods（femods 聚合去重进 n5_fe_modules）。
PAGES_N5 = [
    ("n5node", "失败节点调试", "tpl-n5-node-design.json", ["tpl-n5-mech-resume.json", "tpl-n5-mech-checkpoint.json"], "tpl-n5-node-impl.json", "tpl-n5-node-femods.json"),
    ("n5hitl", "HitL 悬浮输入", "tpl-n5-hitl-design.json", [], "tpl-n5-hitl-impl.json", "tpl-n5-hitl-femods.json"),
    ("n5edge", "边 dot Context 篡改", "tpl-n5-edge-design.json", [], "tpl-n5-edge-impl.json", "tpl-n5-edge-femods.json"),
    ("n5trace", "Trace 时间线", "tpl-n5-trace-design.json", ["tpl-n5-mech-events.json"], "tpl-n5-trace-impl.json", "tpl-n5-trace-femods.json"),
]

# 节点注册表（N0–N6 顺序）。full = 已深化（自带页型）；legacy = 旧格式占位。
# bare=True 让 N0 沿用裸页面 id（contract/fe_modules/impl/tests）与裸 anchor，保持输出字节不变。
NODES = [
    {"code": "N0", "kind": "full", "name": "Settings · 设置与配置", "bare": True, "pages": PAGES_N0,
     "intent": "Settings 是工作流第 0 个节点 —— 进应用后在这里配置环境（一层壳 + 4 个设置页）。"},
    {"code": "N1", "kind": "full", "name": "Init · 发现与初始化", "pages": PAGES_N1,
     "file": "ui-review-N1.json",
     "intent": "Init 是工作流第 1 个节点 —— 进入 Studio 的完整旅程 + Home↔skill-workspace 强隔离切换：Home=打开文件夹+Recent（MRU 最近列表）的 IDE 起点（无聚合注册表，抄 Cursor/VS Code），新建走极简对话框（名+父目录，脚手架走 logic→agent 模板），进入后是沉浸式 Workspace 外壳（强隔离、copilot 退出恢复、非全屏启动）。skill 发现/读写归 gateway 后端 sidecar，本地落盘归 Studio Rust 后端 native-fs（D12）。"},
    {"code": "N2", "kind": "full", "name": "Authoring · 搭图与编辑", "pages": PAGES_N2,
     "intent": "Authoring 是工作流第 2 个节点 —— 把业务逻辑装配成严谨可编译的 graph_skill（画布搭建 + 三类节点属性 + GRAPH.md 宏观契约 + i/o 面板）；编译/lint 门控归 N3 Compile。"},
    {"code": "N3", "kind": "full", "name": "Compile · 编译门控", "pages": PAGES_N3,
     "file": "ui-review-N3.json",
     "intent": "Compile 是工作流第 3 个节点 —— 搭好图后编译校验 + 错误呈现 + 绿灯门控解锁下一步：编辑期实时 lint 把错误就近标在节点/属性/编辑器三处 → 点 Compile 弹 drawer 看完整错误（可复制） → compile-pass 才解锁 Predict。编译规则与错误码归 engine,Studio 只触发 + 呈现。"},
    {"code": "N4", "kind": "full", "name": "Run & Verify · 运行与验收", "pages": PAGES_N4,
     "intent": "Run & Verify 是工作流第 4 个节点 —— 把搭好编译过的 skill 真正跑起来并验收：predict 试飞跑通逻辑（硬前提）→ run 真跑消耗 token → trace 去黑盒 → golden 字段级对比验收。"},
    {"code": "N5", "kind": "full", "name": "Debug & Resume · 调试续跑", "pages": PAGES_N5,
     "file": "ui-review-N5.json",
     "intent": "Debug & Resume 是工作流第 5 个节点 —— 一次真实 Run 失败/暂停后，在出问题的那个节点/那条边上就地干预、从该点精准续跑（上游走 checkpoint 不重跑）：失败节点红灯+就地错误、节点级 Resume、脏态置灰（B）+ HitL 人工注入续跑（A）+ 边 dot 黑板篡改续跑（C），叠加在 Trace 运行流之上。续跑/checkpoint/事件契约归 engine，Studio 只投影 + 触发。"},
    {"code": "N6", "kind": "full", "name": "Save & Publish · 保存与发布", "pages": PAGES_N6,
     "file": "ui-review-N6.json",
     "intent": "Save & Publish 是工作流第 6 个节点 —— 验收通过后把成果留存与上线：成功 run 本地 git autocommit 存档（本地够用、可回滚）+（占坑低优先）发布打包上传 Artifact Registry（非 git push）→ 回主页闭环。"},
]


def _load(name):
    if not name:
        return None
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _make_nctx(node):
    """Build a node context: page-id map + anchor prefix. bare nodes keep N0's original ids."""
    code_, low = node["code"], node["code"].lower()
    if node.get("bare"):
        pages = {"overview": f"{low}_overview", "contract": "contract",
                 "fe_modules": "fe_modules", "impl": "impl", "tests": "tests"}
        apfx = ""
    else:
        pages = {k: f"{low}_{k}" for k in ("overview", "contract", "fe_modules", "impl", "tests")}
        apfx = f"{low}-"
    return {"code": code_, "name": node["name"], "intent": node.get("intent", ""), "pages": pages, "apfx": apfx}


def _build_full(node):
    """Load a full node's stages + per-node reusable-module registry (anchors prefixed per node)."""
    nctx = _make_nctx(node)
    stages = []
    for ns, label, dfile, mfiles, ifile, ffile in node["pages"]:
        d = _load(dfile)
        if not d:
            continue
        stages.append({
            "ns": ns, "label": label, "design": d,
            "mechs": [x for x in (_load(f) for f in mfiles) if x],
            "impl": _load(ifile),
            "femods": _load(ffile) or [],
        })
    reg, seen = [], {}
    for s in stages:
        for g in s["femods"]:
            nm = g.get("name", "")
            if nm and nm not in seen:
                anchor = f'{nctx["apfx"]}mod-{len(reg)}'
                seen[nm] = "#" + anchor
                reg.append((anchor, g))
    return {"nctx": nctx, "stages": stages, "reg": reg, "femhome": dict(seen)}


def _render_full_node(full):
    """Render a full node's sections; return (sections_html, pages_list, design_pages)."""
    nctx, stages, reg, femhome = full["nctx"], full["stages"], full["reg"], full["femhome"]
    p, code_, name = nctx["pages"], nctx["code"], nctx["name"]
    secs = render_node_overview(stages, nctx)
    pages = [(p["overview"], f"{code_} · {name} 主页")]
    design_pages = []
    for s in stages:
        secs += render_design(s["design"], femhome, s["label"], nctx)
        pages.append((s["design"]["page_id"], s["label"]))
        design_pages.append((s["design"]["page_id"], s["design"]["title"]))
    secs += render_contract(stages, nctx); pages.append((p["contract"], "后端接口契约"))
    secs += render_fe_modules(reg, nctx); pages.append((p["fe_modules"], "前端复用模块"))
    secs += render_impl_all(stages, nctx); pages.append((p["impl"], "实施"))
    secs += render_tests_all(stages, nctx); pages.append((p["tests"], "测试"))
    return secs, pages, design_pages


def main():
    style = re.search(r"<style>.*?</style>", TEMPLATE.read_text(encoding="utf-8"), re.S).group(0)

    # build ordered node specs (full = deepened, legacy = placeholder)
    node_specs = []
    for node in NODES:
        if node["kind"] == "full":
            full = _build_full(node)
            if not full["stages"]:
                # Full node registered but its stage JSON is not authored yet
                # (parallel deepening WIP). Fall back to the legacy placeholder so one
                # unfinished node never breaks the shared build for the others.
                nd = _load(node.get("file") or f'ui-review-{node["code"]}.json')
                if nd:
                    node_specs.append(("legacy", nd))
                continue
            secs, pgs, dpages = _render_full_node(full)
            full["_secs"], full["_pages"], full["design_pages"] = secs, pgs, dpages
            node_specs.append(("full", full))
        else:
            nd = _load(node["file"])
            if nd:
                node_specs.append(("legacy", nd))

    # assemble: S0 总览 + 每个节点的块（full 渲页型 / legacy 渲占位），按 N0..N6 顺序
    sections = render_handbook_overview(node_specs)
    pages = [("handbook_overview", "总览")]
    for kind, payload in node_specs:
        if kind == "full":
            sections += payload["_secs"]
            pages += payload["_pages"]
        else:
            sections += render_node_legacy(payload)
            pages.append((payload.get("code", ""), payload.get("code", "")))

    # ---- 导航：与原手册 buildTOC 完全同构（S0 总览 + 7 节点组，每组 parent + child-list + 状态点） ----
    def _stext(st):
        return {"ok": "符合用户逻辑", "partial": "部分符合", "bad": "违反用户逻辑"}.get(st, "需补证据")

    def _scls(st):
        return {"ok": "ok", "partial": "partial", "bad": "bad"}.get(st, "review")

    # 节点级前端实施状态（逻辑：rollup 该节点的前端 wave 项——全已提交=ok，有提交也有待办=partial，零提交=bad/未开始）。
    # 依据：git 已提交前端 commit + S0 wave todo 的待办项。随节点完成度更新这张表即可。
    node_impl_status = {
        "n0": "partial",  # Settings/APIKeys/Roles/Copilot/General 已提交；Copilot conformance Wave A(gateway snapshot+roles_changed)+Wave B(CopilotTab 12 项) 已落；Wave C(共享状态灯/WS reconnect/i18n toast/a11y/键盘/quit flush/cooling/shell-role) 待做
        "n1": "partial",  # shell/home 已提交；⑥-fe skill-create via Rust 待做
        "n2": "ok",       # canvas/authoring/topology 全部已提交，无待办前端项
        "n3": "partial",  # gating/drawer 已提交；lint 骨架 + 字段投影 待做
        "n4": "partial",  # trace 可读化已提交(Wave0)；golden/wall/p8(Wave2)待后端
        "n5": "partial",  # 边 Context 可写 Monaco + resume 骨架已提交(Wave0)；hitl + 引擎 resume(Wave2)待
        "n6": "bad",      # history/publish 前端未开始（history 读模型就绪但 UI 未接）
    }

    def _node_st(code_):
        return node_impl_status.get(code_.lower(), "partial")

    def _node_stext(st):
        # 圆点 = 本节点全部子页（前端/后端/测试各轴）里最差的那个，故措辞用整体口径，不再只说「前端」。
        return {"ok": "全部子页已达标", "partial": "尚有子页未完成", "bad": "整体未开始"}.get(st, "尚有子页未完成")

    # ---- per-page 状态规则（导航旁状态点 = 本页状态，不再全节点共用一个 rollup） ----
    # rollup：有效项全 ok→ok；全 bad→bad；混合→partial；无量化数据→none（不显示点）。
    def _rollup(vals, ok_set, bad_set):
        norm = []
        for v in vals:
            v = (v or "").strip()
            if v in ok_set:
                norm.append("ok")
            elif v in bad_set:
                norm.append("bad")
        if not norm:
            return "none"
        if all(x == "ok" for x in norm):
            return "ok"
        if all(x == "bad" for x in norm):
            return "bad"
        return "partial"

    def _test_roll(tests):
        # 测试页 = 「真机实测完整性」：偏差/未实施=红；标 shot_na（系统级/瞬态，无法真机端到端、
        # 只有自动化单测+读码覆盖）=黄（部分实测）；符合且可真机实测=绿。混合→黄，全黄/全绿各取其色。
        lv = []
        for t in tests:
            fs = (t.get("fe_status") or "").strip()
            if fs in ("偏差", "未实施"):
                lv.append("bad")
            elif (t.get("shot_na") or "").strip():
                lv.append("partial")
            elif fs == "符合":
                lv.append("ok")
        if not lv:
            return "none"
        if all(x == "ok" for x in lv):
            return "ok"
        if all(x == "bad" for x in lv):
            return "bad"
        return "partial"

    # ── 状态点 = 该页面上「所有状态徽章里最差的那个」，全绿才绿（覆盖前端+后端两轴 + 机制卡） ──
    def _kfe(v):  # fe_status → ok/partial/bad/none
        return {"符合": "ok", "偏差": "partial", "未实施": "bad"}.get((v or "").strip(), "none")

    def _kbe(v):  # be_status → ok/partial/bad/none（n/a / 空 = none，不参与）
        return {"已实现": "ok", "符合": "ok", "契约问题": "partial", "未实现": "bad"}.get((v or "").strip(), "none")

    def _kmech(mechs):  # 机制卡 backend_status[].status → 状态项（review=待证据，按琥珀计）
        out = []
        for mm in mechs or []:
            for b in mm.get("backend_status", []):
                out.append({"ok": "ok", "partial": "partial", "bad": "bad", "review": "partial"}.get(
                    (b.get("status") or "").strip(), "none"))
        return out

    def _roll3(items):  # 全 ok→ok；全 bad→bad；有任何非 ok（含 partial）→partial；无数据→none
        xs = [x for x in items if x in ("ok", "partial", "bad")]
        if not xs:
            return "none"
        if all(x == "ok" for x in xs):
            return "ok"
        if all(x == "bad" for x in xs):
            return "bad"
        return "partial"

    def _worst3(sts):  # 取最差：ok < partial < bad；无数据→none
        rank = {"ok": 0, "partial": 1, "bad": 2}
        xs = [s for s in sts if s in rank]
        return max(xs, key=lambda s: rank[s]) if xs else "none"

    def _page_status_map(full):
        # 每页状态点 = 本页面上「全部状态徽章里最差的那个」，绿仅当全绿：
        #   设计页 = 该 surface 全原子 fe_status + be_status（两轴都要符合才绿）；
        #   实施页 = 全节点功能 fe_status + be_status；
        #   后端接口契约页 = 全节点功能 be_status + 全机制 backend_status（机制 partial/bad 也算进来）；
        #   测试页 = 真机实测完整性（_test_roll）；复用模块页 = 全节点前端 fe_status。
        nc = full["nctx"]; p = nc["pages"]; stages = full["stages"]
        m = {}; all_fe = []; all_be = []; all_ts = []; all_mech = []
        for s in stages:
            im = s.get("impl") or {}
            fns = im.get("functions", []); tss = im.get("tests", [])
            atoms = (s.get("design") or {}).get("atoms", [])
            di = [_kfe(a.get("fe_status", "")) for a in atoms] + [_kbe(a.get("be_status", "")) for a in atoms]
            m[s["design"]["page_id"]] = _roll3(di)
            all_fe += [_kfe(f.get("fe_status", "")) for f in fns]
            all_be += [_kbe(f.get("be_status", "")) for f in fns]
            all_ts += tss
            all_mech += _kmech(s.get("mechs", []))
        m[p["impl"]] = _roll3(all_fe + all_be)
        m[p["tests"]] = _test_roll(all_ts)
        m[p["contract"]] = _roll3(all_be + all_mech)
        m[p["fe_modules"]] = _roll3(all_fe)
        return m

    def _pitem(pid, label, st):
        # 登记/目录页或无可量化数据 → 不显示状态点（只剩红/黄/绿交通灯，含义自明）。
        dot = "" if st in (None, "", "none") else '<span class="status-dot %s"></span>' % _scls(st)
        return ('<a class="progress-item" href="#%s" id="nav-%s">'
                '<span class="dot-indicator"></span>'
                '<span class="item-label">%s</span>'
                '%s</a>'
                % (pid, pid, ESC(label), dot))

    def _grp(parent, children):
        return '<div class="toc-group">%s<div class="child-list">%s</div></div>' % (parent, children)

    def _full_nav_group(full):
        nctx = full["nctx"]; code_ = nctx["code"]; p = nctx["pages"]
        items = [(pid, "%s.%d" % (code_, i + 1), title) for i, (pid, title) in enumerate(full["design_pages"])]
        base = len(full["design_pages"])
        items += [(p["contract"], "%s.%d" % (code_, base + 1), "后端接口契约"),
                  (p["fe_modules"], "%s.%d" % (code_, base + 2), "前端复用模块"),
                  (p["impl"], "%s.%d" % (code_, base + 3), "实施"),
                  (p["tests"], "%s.%d" % (code_, base + 4), "测试")]
        psmap = _page_status_map(full)
        # 父节点状态点 = 子页里最差的那个（子页本身已据页面内容算）。无任何子页数据才退回旧表。
        st = _worst3([psmap.get(pid, "none") for pid, _c, _lbl in items])
        if st == "none":
            st = _node_st(code_)
        children = "".join(_pitem(pid, "%s %s" % (c, lbl), psmap.get(pid, "none")) for pid, c, lbl in items)
        parent = ('<a class="toc-parent" href="#%s" id="nav-%s">'
                  '<span class="parent-node">%s</span><span class="parent-title">'
                  '<b>%s</b>'
                  '<span>%d 页 · %s</span></span>'
                  '<span class="status-dot %s"></span></a>'
                  % (p["overview"], p["overview"], ESC(code_), ESC(nctx["name"]), len(items), _node_stext(st), _scls(st)))
        return _grp(parent, children)

    def _legacy_nav_group(nd):
        nc = nd.get("code", "")
        kids = nd.get("children", [])
        chs = "".join(_pitem(ch.get("code", ""), "%s %s" % (ch.get("code", ""), ch.get("title", "")),
                             ch.get("status", "")) for ch in kids)
        title = nd.get("title", "").replace(nc + " · ", "")
        st = nd.get("status", "")
        parent = ('<a class="toc-parent" href="#%s" id="nav-%s"><span class="parent-node">%s</span>'
                  '<span class="parent-title"><b>%s</b>'
                  '<span>设计意图 · 当前差距 · %d 个模块 · %s</span></span>'
                  '<span class="status-dot %s"></span></a>'
                  % (nc, nc, ESC(nc), ESC(title), len(kids), _stext(st), _scls(st)))
        return _grp(parent, chs)

    # S0 · 总览
    toc = ('<div class="toc-group"><a class="toc-parent" href="#handbook_overview" id="nav-handbook_overview">'
           '<span class="parent-node">S0</span><span class="parent-title"><b>总览</b>'
           '<span>7 节点 · 架构 / 状态 / 方法论</span></span>'
           '<span class="status-dot ok"></span></a></div>')
    for kind, payload in node_specs:
        toc += _full_nav_group(payload) if kind == "full" else _legacy_nav_group(payload)
    pages_js = json.dumps([p[0] for p in pages])
    labels_js = json.dumps([p[1] for p in pages])

    js = """
const PAGES = %s, LABELS = %s; let cur = 0;
function showPage(i, smooth){ cur=Math.max(0,Math.min(PAGES.length-1,i)); const id=PAGES[cur];
  document.querySelectorAll('.doc-section').forEach(s=>s.classList.toggle('active', s.id===id));
  PAGES.forEach((p,idx)=>{const n=document.getElementById('nav-'+p); if(n){n.classList.toggle('active',idx===cur);}});
  var _pct=Math.round((cur+1)/PAGES.length*100);
  var _pf=document.getElementById('progress-fill'); if(_pf) _pf.style.width=_pct+'%%';
  var _pp=document.getElementById('progress-pct'); if(_pp) _pp.textContent=_pct+'%%';
  document.getElementById('prev-btn').style.visibility = cur===0?'hidden':'visible';
  document.getElementById('next-btn').style.visibility = cur===PAGES.length-1?'hidden':'visible';
  document.getElementById('prev-label').textContent = cur>0?LABELS[cur-1]:'';
  document.getElementById('next-label').textContent = cur<PAGES.length-1?LABELS[cur+1]:'';
  window.scrollTo({top:0,behavior:smooth?'smooth':'auto'}); if(history.replaceState) history.replaceState(null,'','#'+id); }
function nextPage(){ if(cur<PAGES.length-1) showPage(cur+1,true); }
function prevPage(){ if(cur>0) showPage(cur-1,true); }
function flash(el){ el.classList.add('flashx'); setTimeout(()=>el.classList.remove('flashx'),1200); }
window.addEventListener('load', ()=>{
  document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click', e=>{
    e.preventDefault(); const id=a.getAttribute('href').slice(1);
    let idx=PAGES.indexOf(id);
    if(idx>=0){ showPage(idx,false); return; }
    const el=document.getElementById(id); if(!el) return;
    const sec=el.closest('.doc-section'); if(sec){ const pi=PAGES.indexOf(sec.id); if(pi>=0&&pi!==cur) showPage(pi,false); }
    const dt=el.closest('details'); if(dt) dt.open=true;
    setTimeout(function(){ el.scrollIntoView({behavior:'smooth',block:'center'}); flash(el); }, 30);
  }));
  const h=location.hash?location.hash.slice(1):PAGES[0]; const s=PAGES.indexOf(h); showPage(s>=0?s:0,false);
});
// ── lightbox：点击 .shot-img 放大，滚轮/按钮缩放 + 拖动平移（iPad 友好）──
(function(){
  var lb=document.getElementById('lightbox'); if(!lb) return;
  var img=document.getElementById('lb-img'), stage=document.getElementById('lb-stage'), pct=document.getElementById('lb-pct');
  var scale=1, tx=0, ty=0, baseW=0, baseH=0;
  function apply(){ img.style.transform='translate(-50%%,-50%%) translate('+tx+'px,'+ty+'px) scale('+scale+')'; pct.textContent=Math.round(scale*100)+'%%'; }
  function fit(){ var vw=window.innerWidth*0.92, vh=window.innerHeight*0.84; var s=Math.min(vw/(baseW||1), vh/(baseH||1), 1); scale=s>0?s:1; tx=0; ty=0; apply(); }
  function open(src,alt){ img.src=src; img.alt=alt||''; lb.classList.add('open');
    if(img.complete && img.naturalWidth){ baseW=img.naturalWidth; baseH=img.naturalHeight; fit(); }
    else { img.onload=function(){ baseW=img.naturalWidth; baseH=img.naturalHeight; fit(); }; } }
  function close(){ lb.classList.remove('open'); img.src=''; }
  function zoom(f){ scale=Math.min(8, Math.max(0.2, scale*f)); apply(); }
  document.addEventListener('click', function(e){ var t=e.target;
    if(t && t.classList && t.classList.contains('shot-img')){ e.preventDefault(); open(t.getAttribute('src'), t.getAttribute('alt')); } });
  document.getElementById('lb-in').onclick=function(){ zoom(1.25); };
  document.getElementById('lb-out').onclick=function(){ zoom(0.8); };
  document.getElementById('lb-reset').onclick=function(){ fit(); };
  document.getElementById('lb-close').onclick=close;
  stage.addEventListener('click', function(e){ if(e.target===stage) close(); });
  lb.addEventListener('wheel', function(e){ e.preventDefault(); zoom(e.deltaY<0?1.12:0.89); }, {passive:false});
  document.addEventListener('keydown', function(e){ if(!lb.classList.contains('open')) return;
    if(e.key==='Escape') close(); else if(e.key==='+'||e.key==='=') zoom(1.25); else if(e.key==='-') zoom(0.8); });
  var drag=false, sx=0, sy=0;
  stage.addEventListener('pointerdown', function(e){ if(e.target!==img && e.target!==stage) return; drag=true; sx=e.clientX-tx; sy=e.clientY-ty; lb.classList.add('dragging'); try{ stage.setPointerCapture(e.pointerId); }catch(_){} });
  stage.addEventListener('pointermove', function(e){ if(!drag) return; tx=e.clientX-sx; ty=e.clientY-sy; apply(); });
  stage.addEventListener('pointerup', function(){ drag=false; lb.classList.remove('dragging'); });
  window.addEventListener('resize', function(){ if(lb.classList.contains('open') && baseW) fit(); });
})();
""" % (pages_js, labels_js)

    out = (
        '<!DOCTYPE html>\n<html lang="zh"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>Studio MVP1 · 前端实施说明书</title>'
        + FONT_LINKS + style + CSS + "</head><body>"
        '<div class="main-layout"><aside class="sidebar">'
        '<div class="sb-card"><div class="sb-title">Studio MVP1 · 前端实施说明书</div>'
        '<div class="sb-sub">按 7 个用户工作流节点（N0–N6）记录每个用户动作的前端实现详情与是否符合 MVP1。先读总览，再逐节点 / 页面看。</div></div>'
        '<div class="sb-card sb-progress">'
        '<div class="sb-progress-row"><span>阅读进度</span><b id="progress-pct">0%</b></div>'
        '<div class="sb-progress-track"><div class="sb-progress-fill" id="progress-fill"></div></div></div>'
        '<nav class="sb-card toc" id="toc">' + toc + '</nav></aside>'
        '<main class="viewport"><article class="reading-column"><div id="docInner">' + sections + '</div>'
        '<nav class="paginator">'
        '<button class="nav-btn" id="prev-btn" onclick="prevPage()"><span>&larr;</span><span class="nb-label" id="prev-label"></span></button>'
        '<button class="nav-btn" id="next-btn" onclick="nextPage()"><span class="nb-label" id="next-label"></span><span>&rarr;</span></button>'
        '</nav></article></main></div>'
        '<div class="lightbox" id="lightbox">'
        '<div class="lb-stage" id="lb-stage"><img class="lb-img" id="lb-img" alt=""/></div>'
        '<div class="lb-bar"><button id="lb-out" title="缩小">−</button>'
        '<span class="lb-pct" id="lb-pct">100%</span>'
        '<button id="lb-in" title="放大">+</button>'
        '<button id="lb-reset" title="适配窗口">⤢</button></div>'
        '<button class="lb-close" id="lb-close" title="关闭 (Esc)">×</button>'
        '<div class="lb-hint">滚轮 / ± 缩放 · 拖动平移 · 点背景或 Esc 关闭</div>'
        '</div>'
        "<script>" + js + "</script></body></html>"
    )
    OUT.write_text(out, encoding="utf-8")
    print("OK ->", OUT)
    print("pages:", [p[0] for p in pages])


if __name__ == "__main__":
    main()
