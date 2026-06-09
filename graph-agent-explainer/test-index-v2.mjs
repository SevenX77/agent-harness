import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = await readFile(join(here, "index-v2.html"), "utf8");
const content = await readFile(join(here, "index-v2-content.js"), "utf8");
const combined = html + "\n" + content;

const requiredCopy = [
  "Workflow as Source Code",
  "Compiler + Runtime",
  "Local Edit == Cloud Run",
  "Bounded Autonomy",
  "Knowledge as Control",
  "Lineage / 局部重算",
  "专业领域的人开发更快",
  "确定性工作流",
  "领域知识让结果更好",
  "graph 里的 LLM 节点升级成 bounded agent loop",
  "强逻辑进图",
  "最后一公里交给 Agent",
  "gate / validator / schema / review phase",
  "不是模型执行，而是真懂领域的人改不动生产流程",
  "懂领域的人",
  "沟通磨损",
  "领域专家 → 工程师翻译 → 回头验证",
  "写流程 → 编译 → 预演 → 观察 → 修正 → 运行",
];

for (const text of requiredCopy) {
  assert.ok(combined.includes(text), `missing required copy: ${text}`);
}

const forbiddenCopy = [
  "未实现",
  "待实现",
  "实现中",
  "live",
  "设计蓝图",
  "停留在概念",
  "诚实标注",
  "不吹牛",
  "部分仍在",
  "第 7 部分",
  "7.1",
  "0.1 一条 LLM 流程为何会失控",
  "流程为何会失控",
  "失控",
  "Agent 需要 harness",
  "harness 是最大亮点",
  "再做一个 coding agent",
];

for (const text of forbiddenCopy) {
  assert.ok(!combined.includes(text), `forbidden copy found: ${text}`);
}

const navMatch = html.match(/<aside[^>]*class="[^"]*\bsidebar\b[^"]*"[\s\S]*?<\/aside>/);
assert.ok(navMatch, "sidebar aside should exist");
assert.ok(/position:\s*sticky/.test(html), "sidebar should use sticky positioning");
assert.ok(/overflow-y:\s*auto/.test(html), "sidebar should be its own scroll area");
assert.ok(html.includes("hashchange"), "page should react when URL hash changes after load");
assert.ok(html.includes("showPage(idx, false)"), "hash navigation should reuse the page switcher");

const svgCount = (html.match(/<svg\b/g) || []).length;
assert.ok(svgCount >= 4, `expected at least 4 explanatory SVG diagrams, saw ${svgCount}`);

const frameworkMarkers = [
  "const TOC",
  "const SLIDES",
  "className = 'doc-section'",
  "class=\"reading-column\"",
  "class=\"paginator\"",
  "src=\"./index-v2-content.js\"",
];

for (const marker of frameworkMarkers) {
  assert.ok(html.includes(marker), `missing original framework marker: ${marker}`);
}

assert.ok(!html.includes("{ ch: '7."), "chapter 7 should be removed");

const chapterCount = (html.match(/\{ ch: '/g) || []).length;
assert.ok(chapterCount >= 6, `expected at least 6 chapters, saw ${chapterCount}`);

assert.ok(content.includes("Object.assign(SLIDES"), "content script should populate SLIDES");
assert.ok(content.includes("class=\"studio-host\""), "content should reuse studio-host slots");
assert.ok(content.includes("data-demo=\"demo-compile\""), "content should keep compile demo");

const slideCount = (combined.match(/title: '/g) || []).length;
assert.ok(slideCount >= 18, `expected dense slide content, saw ${slideCount}`);

const paragraphCount = (combined.match(/<p>/g) || []).length;
assert.ok(paragraphCount >= 45, `expected explanatory paragraph density, saw ${paragraphCount}`);

const harnessMentions = (combined.match(/\bharness\b/gi) || []).length;
assert.ok(harnessMentions <= 8, `harness should be an intro, not a chapter; saw ${harnessMentions} mentions`);

console.log("index-v2 explainer checks passed");
