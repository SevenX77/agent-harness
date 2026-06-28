# N6 前端实施手册 · 操作 / 切片 Schema / 维护生命周期规范

> 配套文档。`frontend-page-authoring-methodology.md` 管**内容与设计**（每页写什么、
> 怎么组织、配色一色一义）；**本文管机械与运维**——怎么看、怎么改、什么时候改、
> 测试截图怎么截、切片字段 schema、状态点配色锁定。两份一起构成手册的完整规范。
>
> 适用对象：`docs/studio/mvp1/_impl/frontend-handbook/`（由 `build_template_slice.py`
> 从 `tpl-*.json` 切片生成 `index.html` 的 N6 前端实施手册）。

## 0. 心智模型（先读这条）

**手册 = 「数据（切片 JSON） → 生成器（build 脚本） → 自包含 HTML」的单向流水线。**

- **真相在切片**：所有文字、状态、截图引用都写在 `tpl-*.json` 里。
- **观感在生成器**：布局、配色、导航、交互都在 `build_template_slice.py` 里。
- **`index.html` 是产物，不是源**：永远不手改，永远重新生成。

铁律：**改内容只动 JSON，改观感只动生成器，`index.html` 只由生成器写。**

---

## 1. 怎么看手册（读者指南）

### 1.1 读者是谁
两类：① 人（PM / 前端 / 审计）；② **Studio Copilot LLM**（手册是它的知识库，
故文字要机器可消费、字段级精确，不能只给人看的比喻）。

### 1.2 物理结构
- 单个**自包含** `index.html`（截图已 base64 内联，无外链依赖，可直接发/可本地起 http）。
- 是 SPA：所有页面是 `.doc-section`，靠 JS `showPage(i)` 切换；全局 `PAGES` 数组
  + `showPage` 挂在 window 上（可被 Playwright `p.evaluate(()=>showPage(PAGES.indexOf('n1_tests'),false))` 驱动）。
- 左侧 `#toc` 导航 = S0 总览 + 7 个节点组，每组 = 节点主页（parent）+ 子页列表。
- hash 路由：`#<page_id>` 直达某页；`#<anchor>` 跳页内锚点（chip/xlink 用）。

### 1.3 每个节点的页（固定 6 类）
| 页 | 看什么 | 状态点语义 |
|---|---|---|
| 节点主页 | 该节点的旅程/边界总览 | **全部子页里最差的那个**（绿仅当所有子页全绿，见 §5.3） |
| 设计页（可多个 surface） | 每个操作原子「应该长啥样」+ 前后端契约 | 该 surface 全原子 **fe_status + be_status**（两轴都符合才绿） |
| 后端接口契约 | 该节点全部后端机制/接口契约 | 全功能 **be_status** + 全机制卡 **backend_status**（机制 partial/bad 也算） |
| 前端复用模块 | 被多操作共用的前端组件登记 | 全节点 **fe_status**（前端模块实现状态） |
| 实施 | 逐功能现状/差距 | 全节点 **fe_status + be_status** |
| 测试 | 每个功能的两层测试 + 真机截图 | **真机实测完整性**（见 §5.3，不是只看代码符合） |

> 通则：任一页面只要有没做完的部分，圆点就不会是绿；圆点 = 该页所有状态徽章取最差。见 §5.3。

### 1.4 跳转规则
- **chip**（设计页「前端模块」小标签）→ 链到「前端复用模块」登记页对应卡。
- **xlink**（蓝色文字链）→ 跨页跳：设计↔实施↔测试↔契约互链（如测试卡「对应设计」、
  实施卡「→ 看契约」）。
- 状态点本身不可点；要看明细点页标题进页。

---

## 2. 怎么改手册（切片 schema + 生成）

### 2.1 四类切片 + 注册
节点在 `build_template_slice.py` 的 `NODES` 里注册；每个节点的 `PAGES_Nx` 列出它的
surface，每个 surface 是一个 6 元组：

```
(ns, label, design文件, [机制文件...], 实施文件, 复用模块文件)
```

例（`PAGES_N1` 的 home surface）：
```
("home", "Home/Welcome 屏",
 "tpl-n1-home-design.json", ["tpl-n1-mech-skills.json","tpl-n1-mech-nativefs.json"],
 "tpl-n1-home-impl.json", "tpl-n1-home-femods.json")
```

所以一个 surface 最多 4 类切片：**design / mech(可 0..n) / impl / femods**。

### 2.2 切片字段 Schema（权威字段表，依生成器 `.get()` 抽取）

**① design 切片（`tpl-*-design.json`）**
顶层：`page_id`, `title`, `intro`, `atoms[]`。
每个 atom：
| 字段 | 含义 |
|---|---|
| `n` | 原子编号（节点内唯一，跨 surface 连续） |
| `cap` | 操作名（卡标题） |
| `track` | 可选，子轨道标注 |
| `func` / `action` / `fe_design` | 功能 / 用户动作 / 前端逻辑 |
| `fe_modules` | `[{name}]`，复用模块 chip（链到 femods 登记页） |
| `be_contract` | `[{endpoint, purpose}]`，后端契约端点 |
| `fe_status` | 前端是否符合设计：`符合` / `偏差` / `未实施` |
| `be_status` | 后端实现状态：`已实现` / `未实现` / `契约问题` / `n/a` |
| `gap_brief` / `impl_ref` | 现状偏差 / 链到实施详情 |

**② mech 切片（`tpl-*-mech-*.json`）** — 后端机制/接口契约
机制项 + 接口 `i`：`id`, `endpoint`, `provider`, `purpose`, `req`, `resp`；机制有 `title` / `state`。

**③ impl 切片（`tpl-*-impl.json`）**
顶层：`id`, `title`, `design_ref`, `intro`, `functions[]`, `plan`, `tests[]`。
- **function**：`n`, `cap`, `design_ref`, `current`, `gap`, `fe_status`, `be_status`, `be_dep`（后端依赖说明）, `fe_status_prev` / `fe_resync`（状态变更留痕，可选）。
- **test**：见 §4.3。

**④ femods 切片（`tpl-*-femods.json`）** — 复用模块登记，是一个 list，每项：
`name`, `what`, `duties[]`, `api`, `reuse_note`, `used_by`, `where`（**定义在哪 = 源码文件路径**）, `boundary`, `design_note`, `kind`。

### 2.3 状态值枚举（不许自创别的字符串）
- `fe_status`：`符合`(绿) / `偏差`(琥珀) / `未实施`(红)
- `be_status`：`已实现`(绿) / `契约问题`(琥珀) / `未实现`(红) / `n/a`(灰)
- 测试真机实测：测试项加 `shot_na`（字符串理由）= 无法真机验证 → 该测试在测试页算「部分实测」（琥珀）。
  测试项绿线 = `fe_status=符合` **且** `screenshots[]` 非空（有真机截图）；`符合` 但没截图、又非 `shot_na`
  = 琥珀「待真机实测」，**不许只凭代码符合就涂绿**（见 §5.3）。

### 2.4 生成命令
```bash
cd docs/studio/mvp1/_impl/frontend-handbook
python3 build_template_slice.py        # 无参数；读 tpl-*.json + screenshots/ + 模板 → 写 index.html
```
- **幂等**：同样输入 → 字节一致输出。改完必须重新生成并把 `index.html` 一起提交。
- **绝不手改 `index.html`**；手改会在下次生成时被覆盖，且制造 diff 噪声。
- 验证生成成功：`grep -c 'status-dot review'`（应为 0，无蓝点）、死链自检（`href="#x"` 的 x 都要有对应 `id="x"`）、`shot-img` 计数对得上截图数。

---

## 3. 什么时候改（维护生命周期 / reconcile）—— 最关键、最容易漏

> 这一节是为了根治「手册状态滞后代码」：切片里的 `fe_status` / `be_status` / `be_dep`
> 是**手维护的元数据**，代码改了它不会自动跟着变，会漂移在代码后面好几个 PR。

### 3.1 每个前端 PR 收尾，必须回写对应切片
做完一个前端功能（或修一个 bug），在同一个/紧随的改动里回写它所属 surface 的切片：
- 实现了什么 → 更新 function 的 `fe_status` / `current` / `gap`。
- 后端那一半状态变了 → 更新 `be_status` / `be_dep`（**据代码，不据旧文案**）。
- 写了/补了测试 → 更新 `tests[]`（层级、断言、`fe_status`）。
- 截了真机图 → 挂进 `screenshots`（§4）。
- 然后重新生成 `index.html` 一起提交。

### 3.2 状态字段必须跟「代码真相」对齐，不跟旧文案
报任何状态 / 改任何状态字段前，去**源码**核对（参见根记忆
`feedback_no_overclaim_verify_status_against_code`）：
- 后端能力到底建没建 → grep Rust/后端：函数是否实现、是否注册、前端是否在调、是否带测试。
- 前端动作到底接没接 → grep 前端：是否真调了那个命令 / 渲了那个状态。
- **切片自带的 `be_dep`「等后端/未实现」这类文案可能是几个 PR 前写的，默认当它过时，验过再信。**

### 3.3 自相矛盾 = 漂移信号
**design 切片说「已实现」但 impl 切片还说「契约问题」** —— 这种同一节点内两份切片
打架，几乎一定是其中一份没跟上代码。发现立刻拿代码裁决、对齐两边。

### 3.4 reconcile 触发点（任一发生就查一遍切片是否还准）
1. 改了某动作的前端/后端代码。
2. 后端契约/机制状态有变更。
3. **自己要向人或在报告里陈述某页状态/完成度之前**（先核对再说）。

### 3.5 收尾自检清单
- [ ] 我改的功能对应的 function `fe_status` / `current` / `gap` 更新了？
- [ ] `be_status` / `be_dep` 是据当前代码、不是抄旧文案？
- [ ] design 切片与 impl 切片的状态一致、不打架？
- [ ] 新增/变更的测试回写进 `tests[]`、截图挂进 `screenshots`？
- [ ] 重新跑了 `build_template_slice.py`、`index.html` 一起提交？
- [ ] 无蓝点、无死链、截图计数对？

---

## 4. 测试截图怎么截 + 怎么挂进切片

### 4.1 方法（headless VPS）
真机截图法见 `docs/development/RUN_AND_SCREENSHOT.md §2`（Xvfb 虚拟显示器 + 截图 + 合成点击）。
截手册自身页面（验证状态点/徽章渲染）可用 Playwright + `file://` 直接加载 `index.html`：
- 脚本必须放在 `apps/studio/frontend/`（有 `node_modules/playwright-core`，ESM 才解析得到）。
- 用 `xvfb-run` 起虚拟显示器，宽视口（如 1500px）截 `#toc` 或整页。
- 切页用 `p.evaluate(()=>showPage(PAGES.indexOf('n1_tests'),false))`（hash goto 同文件不会重切页）。
- 懒加载图点击用 `el.click()` via `p.evaluate`（actionability wait 会在懒加载图上超时）。

### 4.2 放哪 + 命名
- 真机图一律放 `docs/studio/mvp1/_impl/frontend-handbook/screenshots/`。
- 命名：`n<节点>-<序号>-<语义>.png`（如 `n1-12-newskill-error.png`）；
  **特写**用 `-closeup` 后缀（如 `n1-12b-error-closeup.png`），由 Pillow 从全图裁框 + 放大生成。
- 生成器构建时把图 base64 内联进 `index.html`（`embed_shot`），所以图必须先在 `screenshots/` 落盘。

### 4.3 怎么挂进切片（test 字段）
test 项字段：
| 字段 | 含义 |
|---|---|
| `covers` | 这条测试覆盖的功能名（卡标题） |
| `atoms` | `[原子编号...]`，驱动「对应设计」跳链 |
| `layer1` | ① 静态测试（RED→GREEN，mock）的要点列表 |
| `layer2` | ② e2e 真实测试的要点列表 |
| `shots` | 预期截图的 TODO 文字（还没截时占位） |
| `screenshots` | `[{file, caption}]`，**已截的真机图**；`file` = `screenshots/` 下文件名 |
| `shot_na` | 字符串：**截不到/无法真机验证的原因**（见 §4.4） |
| `fe_status` | 该测试对应前端是否符合设计 |

**多张截图 = 前/中/后状态变化**：`screenshots` 数组按顺序渲染成多张图，用来展示
「点之前→点之后→结果」的状态迁移；需要时配特写图证实细节（错误文案、toast 等）。

### 4.4 什么算 `shot_na`（不可截图 / 无法真机验证）
当一个动作的**真实效果是系统级 / 瞬态的、headless 物理上截不到稳定帧也跑不了真机**时，
标 `shot_na` 并写清原因 + 替代验证。典型：
- 弹**系统**原生对话框（目录选择器、文件选择器）——虚拟显示器驱动不了系统对话框。
- 跳**系统**文件管理器（reveal in folder）——headless 里没有文件管理器。
- 亚百毫秒一闪的加载骨架——截不到稳定帧。
- 需注入故障才出现的 fallback——headless 造不出故障态。
- 冷启动横幅——需后端起不来 + 全新 webview，headless 无窗口管理器。

`shot_na` 的理由里要注明**替代验证**（哪个单测/组件测断言了它、读了哪段码确认逻辑）。

**注意验证子等级（别一刀切）**：`shot_na` 里其实有两档——
(a) 组件测已**完整断言**该状态（如骨架/故障 fallback，只是截不了图）；
(b) **只断言了「调用发对了」**、真实 OS 效果无人验（如系统对话框/文件管理器）。
两者真机端到端都没证据（故测试页都计「部分实测」琥珀），但写理由时要如实区分到哪一档，
不要把 (a) 说成 (b) 或反之。

---

## 5. 状态点配色（锁定）

### 5.1 状态点 = 交通灯三色，无蓝
导航/页头的**状态点**（`.status-dot`）只用：**绿 ok / 琥珀 partial / 红 bad**。
- **不用蓝**：蓝（原 review）不属于红黄绿语义，没图例读不懂；图例又太占地已删。
  登记/无量化数据的页，要么给派生状态（如复用模块用前端 rollup），要么不显示点。
- 自检：生成后 `grep -c 'status-dot review'` 必须为 0。

### 5.2 状态点 ≠ 徽章，别混
`badge`（卡右上小标签）仍可用蓝（`.badge.b` = info/归属/链接），那是中性信息色，
和「状态点交通灯」是两套东西。配色「一色一义」的总规则见
`frontend-page-authoring-methodology.md §3.4`；这里只约束**状态点**子集为三色。

### 5.3 每页状态点怎么算（总规则：圆点 = 本页所有状态徽章里最差的那个，绿仅当全绿）

**铁律：一个页面只要露出任何没做完的部分，圆点就不能是绿。** 圆点不是「数某一个字段」，
而是把这一页上**渲染出来的全部状态信号**收齐取最差。各页面具体收哪些信号：

- **设计页** = 该 surface 全原子的 `fe_status` **与** `be_status`（前端那一半符不符合设计 + 后端契约
  那一半实现了没，两轴都要绿圆点才绿）。
- **实施页** = 全节点功能的 `fe_status` 与 `be_status`。
- **后端接口契约页** = 全节点功能 `be_status` **加上**全部机制卡 `backend_status[].status`
  （机制卡的 `partial`/`bad`/`review` 都算进来；`review`=待证据，按琥珀计）。
  —— 这是过去最大的漏洞：契约页满屏机制卡 `partial` 却仍显示绿，就是因为旧算法只数功能级
  `be_status`、从不读机制卡自己的状态。现已收进来。
- **前端复用模块页** = 全节点 `fe_status`（前端模块建好没）。
- **测试页 = 真机实测完整性**：`偏差`/`未实施` 测试=红；标 `shot_na`（无法真机实测）=琥珀；
  `符合` **且挂了真机截图（`screenshots[]` 非空）为证** =绿；`符合` 但**未贴真机截图、又非
  `shot_na`** = 琥珀「待真机实测」；混合→琥珀。**「代码符合」≠「真机验证过」——绿线 = 有真机
  截图,没截图一律不许涂绿（无论它代码上多么符合）。** 这是过去最大的测试页漏洞:旧算法只要
  `fe_status=符合` 就涂绿、从不看有没有截图,导致一大片「写了测试但没真机截图」的卡被假绿。
  现已堵上:绿强制要求 `screenshots[]` 非空。
  - 每个 `shot_na` 测试卡挂「⚠ 无真机实测」琥珀徽章;每个「符合但未贴截图」卡挂「⚠ 待真机实测
    （截图未贴）」琥珀徽章,并在测试页提示框分别说明缺口。补上真机截图后该卡方可转绿。
- **节点主页（父节点圆点）** = 其全部子页里**最差**的那个（不再用写死的人工状态表；
  只有该节点所有子页都无量化数据时，才退回人工表兜底）。

> rollup 规则：全绿→绿；全红→红；**只要有任何非绿（含 `partial`/`review`/机制 `bad`）→琥珀**；
> 无数据→不显示点。`review`（待证据）按非绿计入琥珀，因为状态点是三色交通灯、没有蓝（见 §5.1）。
>
> 注意：圆点只忠实 rollup 切片里**已登记**的 `fe_status`/`be_status`/机制 `status` 标签——
> 标签若比真实代码乐观（滞后），圆点也会跟着乐观。标签准不准是另一件事（逐页对代码核对，
> 见 §3「跟代码 reconcile」），不归状态点算法管。

---

## 附：与其它文档的边界
- 本文 = 手册的**机械/运维/schema/生命周期**。
- `frontend-page-authoring-methodology.md` = 手册的**内容/页面骨架/写作规则/一色一义**。
- `docs/development/RUN_AND_SCREENSHOT.md` = 起应用 + headless 真机截图的**底层命令**。
- `apps/studio/frontend/CLAUDE.md` = 前端任务的**单 agent 工作流 SOP**。
- 根记忆 `feedback_no_overclaim_verify_status_against_code` = 报状态前先用代码核对的铁律
  （本文 §3 的行为根因）。
