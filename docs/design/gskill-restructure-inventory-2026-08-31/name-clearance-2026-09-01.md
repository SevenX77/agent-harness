# `gskill` 命名占名 / 混淆 / 商标复核报告

> **性质**:批C 前置调研的**只读事实清单**。本次作业**零注册、零购买、零提交、零仓库改动**——
> 全部动作是 HTTP GET/POST 查询(registry JSON endpoint、GitHub REST、RDAP、DNS-over-HTTPS、
> TMview 检索 API)与本仓文档只读检索。**没有**注册任何包名、域名、组织名或商标。
>
> **执笔者不是律师。**第 5 节(商标)给出的是**公开检索层面的事实**与**风险提示**,不是法律意见。

---

## 0. 复核判据(原文)与执行边界

### 0.1 判据原文

`D:\coding\agent-harness\docs\design\gskill-restructure-decision-2026-08-31.md:571`(§11.5 执行第 4 点):

> **保留发布前工序——裁名不免检**:该文档 §2.2 要求的 **PyPI / GitHub 占名、包名混淆检查、域名与商标复核**全部保留为批C 与发布前的工序。本裁决定的是**用哪个名字**,不是**这个名字可用**;复核失败仍按 §2.2 原文在发布前**一次性重裁新名**,**不留 alias**。

同文件 `:572`(§11.5 执行第 5 点):

> **对 §4.4-2 的影响**:该步「包名裁决」的**选名部分由本条完成**,**发布前复核部分仍未完成**;批C 的前置条件**不因本条自动满足**。

被引用的 §2.2 原文,`D:\coding\agent-harness\docs\engine\graph-skill-runtime\v1-alignment.md:57`:

> 相邻名称已经拥挤:npm 有直接竞品 [gwaghmar/graph 的 `graph-skill`](https://github.com/gwaghmar/graph),GitHub 另有 [`ouyangyipeng/Graph-Skill`](https://github.com/ouyangyipeng/Graph-Skill);`gskill` 还会让人联想到 G.SKILL 硬件品牌、GEPA 的 `gskill` 和 Go 生态同名工具。因此,发布前必须完成 PyPI/GitHub 占名、包名混淆检查、域名与商标复核。**任何一项失败都应在发布前重新裁决名称**,而不是为兼容 drafted 名称留下别名。

同文件 `:46-47` 记录:**Console command = `gskill`**、**MCP server/tool namespace = `gskill`**——这两项在 §11.5-3 中被**明确保留**(与裁决同向)。因此第 7 节(CLI 命令冲突)不是边缘项,而是直接命中已定设计。

### 0.2 时间点

全部查询执行于 **2026-09-01 14:57–15:06 UTC**(北京时间 2026-09-01 22:57–23:06)。
Registry / RDAP / DNS 结果均为该时刻快照,**不构成占名,也不保证此后仍然可用**。

### 0.3 判据映射(先给结论,证据在后)

| # | 判据项 | 结论 | 风险 |
|---|---|---|---|
| 1 | PyPI 占名 | **通过**——四个目标名全部空闲 | 低 |
| 2 | npm 占名 | **失败**——裸名 `gskill` 已被同领域活体竞品占用 | 高 |
| 3 | GitHub 占名 | **部分失败**——`SevenX77/gskill` 空闲,但组织命名空间 `github.com/gskill` 已被占 | 中 |
| 4 | 包名混淆检查 | **失败**——同领域存在 3 个精确同名项目 + 2 个精确同名 npm 分发 | 高 |
| 5 | 商标复核 | **失败(公开检索层面)**——G.SKILL 持有**在册美国 Class 9 文字商标**,其商品清单**明文包含"用于应用程序开发的可下载软件平台"** | 高 |
| 6 | 域名复核 | **有条件通过**——`.dev` / `.io` 空闲;`.ai` 标价 2 万美元;`.org` / `.com` 已被占 | 中 |
| 7 | CLI 命令冲突 | **失败**——`gskill` 命令已被两个活体发行工具同时声明 | 高 |

**七项中五项失败。**按 §11.5-4 与 §2.2 的原文("任何一项失败都应在发布前重新裁决名称"),
本报告的判定是 **建议重裁**。第 8 节给出理由排序;第 9 节给出「若仍坚持 gskill」时的
最小条件清单与占位动作清单(**只列,不执行**)。

---

## 1. PyPI 占名

### 1.1 查询方式(原文)

```bash
for n in gskill gskill-gateway gskill-studio gskill-runtime \
         graph-agent graph-skill graphskill gskil g-skill gskills \
         gskill-cli gskill-sdk gskill-engine; do
  curl -s -o /dev/null -w "%{http_code}" "https://pypi.org/pypi/$n/json"
done
# TestPyPI
curl -s -o /dev/null -w "%{http_code}" "https://test.pypi.org/pypi/<name>/json"
# PEP 503 规范化变体(下划线/大小写)
for n in gskill g_skill G-Skill GSKILL gskill_gateway gskill_studio gskill_runtime getskill; do ... done
```

时间:2026-09-01 14:57 UTC / 15:04 UTC(变体批)。

### 1.2 结果(原文)

**pypi.org**(HTTP 404 = 该项目不存在 = 名字空闲):

```
pypi/gskill          -> 404      pypi/graph-agent  -> 404      pypi/gskil      -> 404
pypi/gskill-gateway  -> 404      pypi/graph-skill  -> 404      pypi/g-skill    -> 404
pypi/gskill-studio   -> 404      pypi/graphskill   -> 404      pypi/gskills    -> 404
pypi/gskill-runtime  -> 404      pypi/gskill-cli   -> 404      pypi/gskill-sdk -> 404
pypi/gskill-engine   -> 404
```

**规范化变体**(PEP 503 把 `-`/`_`/大小写归一,故这些等价于同一个名字,一并验证无残留):

```
pypi/gskill -> 404   pypi/g_skill -> 404   pypi/G-Skill -> 404   pypi/GSKILL -> 404
pypi/gskill_gateway -> 404   pypi/gskill_studio -> 404   pypi/gskill_runtime -> 404
pypi/getskill -> 404
```

**test.pypi.org**:

```
testpypi/gskill -> 404   testpypi/gskill-gateway -> 404
testpypi/gskill-studio -> 404   testpypi/gskill-runtime -> 404
```

来源 URL:`https://pypi.org/pypi/<name>/json`、`https://test.pypi.org/pypi/<name>/json`

### 1.3 定级:**低**

四个目标分发名(`gskill`、`gskill-gateway`、`gskill-studio`、`gskill-runtime`)在正式 PyPI
与 TestPyPI 上**全部空闲**,规范化变体亦无残留(排除"曾注册后删除仍占位"的情形)。
这是七项里唯一一项**干净通过**的。

**注意事项(非风险,但影响动作顺序)**:PyPI 名字**先注册先得**,且本报告发布后随时可能
被他人占用;`gskill` 是当前热度很高的词根(见第 4 节),被抢注的概率不可忽略。

---

## 2. npm 占名

### 2.1 查询方式(原文)

```bash
for n in gskill gskill-gateway gskill-studio gskill-runtime graph-skill \
         graphskill gskil g-skill gskills gskill-cli gskill-sdk graph-agent; do
  curl -s -o /dev/null -w "%{http_code}" "https://registry.npmjs.org/$n"
done
curl -s "https://registry.npmjs.org/gskill"                 # 全量元数据
curl -s "https://registry.npmjs.org/gskill/0.3.1"           # bin 声明
curl -s "https://api.npmjs.org/downloads/point/last-month/gskill"
curl -s "https://registry.npmjs.org/-/v1/search?text=gskill&size=20"
```

时间:2026-09-01 14:57 UTC(存在性)/ 14:58 UTC(元数据)/ 15:05 UTC(bin 与搜索)。

### 2.2 结果(原文)

存在性(200 = 已被占用):

```
npm/gskill          -> 200   ← 已被占用
npm/graph-skill     -> 200   ← 已被占用(§2.2 已记录)
npm/gskill-gateway  -> 404   npm/gskill-runtime -> 404   npm/gskills   -> 404
npm/gskill-studio   -> 404   npm/graphskill     -> 404   npm/gskill-cli -> 404
npm/graph-agent     -> 404   npm/gskil          -> 404   npm/gskill-sdk -> 404
npm/g-skill         -> 404
npm/@gskill%2Fcore  -> 404
```

**`npm/gskill` 元数据原文**(`https://registry.npmjs.org/gskill`):

```
name: gskill
description: CLI for GetSkill - discover, install, and manage agent skills (gskill)
dist-tags: {'latest': '0.3.1'}
time.created: 2026-04-08T15:14:37.843Z
time.modified: 2026-04-12T10:15:05.434Z
versions: ['0.1.0', '0.2.0', '0.3.0', '0.3.1']
maintainers: [{'name': 'chris_lin_95', 'email': 'chris_lin_95@foxmail.com'}]
license: MIT
repository: {'type': 'git', 'url': 'git+https://github.com/chrislin95/marvel.git'}
homepage: https://getskill.net
keywords: ['gskill', 'getskill', 'agent', 'skills', 'cli', 'anthropic', 'claude-code', 'cursor']
deprecated: None
```

README 首段原文:

> # GetSkill CLI (gskill)
> Command-line tool for discovering, installing, and publishing skills for AI coding agents.
> **[getskill.net](https://getskill.net)**
> ## Installation
> ```bash
> npm install -g gskill
> ```

`bin` 声明原文(`https://registry.npmjs.org/gskill/0.3.1`):

```
bin: {'gskill': 'dist/index.js', 'getskill': 'dist/index.js'}
```

下载量:`{"downloads":8,"start":"2026-07-31","end":"2026-08-29","package":"gskill"}`(上月 8 次)

npm 检索 `text=gskill` 全量结果(6 条,原文):

```
gskill                        v0.3.1   CLI for GetSkill - discover, install, and manage agent skills (gskill)
@glapsfun/gskill              v0.7.0   Reproducible package manager for agentic AI skills (native binary launcher)
@glapsfun/gskill-linux-arm64  v0.7.0   gskill native binary for linux/arm64
@glapsfun/gskill-darwin-arm64 v0.7.0   gskill native binary for darwin/arm64
@glapsfun/gskill-linux-x64    v0.7.0   gskill native binary for linux/x64
@glapsfun/gskill-darwin-x64   v0.7.0   gskill native binary for darwin/x64
```

`@glapsfun/gskill` 元数据原文:

```
latest: 0.7.0   created: 2026-07-27T18:06:46.008Z   modified: 2026-08-26T18:49:22.618Z
bin: {'gskill': 'bin/gskill.js'}
desc: Reproducible package manager for agentic AI skills (native binary launcher)
repo: git+https://github.com/glapsfun/gskill.git
downloads(last month): 373
```

### 2.3 定级:**高**

三条独立事实叠加:

1. **裸名 `gskill` 在 npm 上不可得。**它已被 `chris_lin_95` 于 2026-04-08 注册,
   至今未 deprecate。npm 的 unpublish 政策(24 小时后不可无条件撤回)意味着这个名字
   **不会自然释放**;唯一路径是向持有者协商转让或走 npm dispute 流程,两者都不是
   我们可以单方面完成的动作。
2. **占用者与我们同域,不是无关项目。**它的自我描述是「discover, install, and manage
   **agent skills**」、关键词含 `anthropic` / `claude-code` / `cursor`,主站
   `getskill.net` 标题为「GetSkill — AI Agent Skills Registry」。我们做的是 agent skill
   的编译/运行/编排平台。两者在同一句话里说得清区别,但在 `npm i -g gskill` 这一行里
   分不开。
3. **第二个精确同名 npm 分发也在同域且更活跃。**`@glapsfun/gskill` v0.7.0,
   2026-08-26 仍在更新,上月 373 次下载(约为 `gskill` 的 47 倍),自述
   「Reproducible package manager for **agentic AI skills**」。

**带 `gskill-` 词缀的名字全部空闲**(`gskill-gateway`、`gskill-studio`、`gskill-runtime`),
所以 §11.5-2 的词缀规则在 npm 上可以落地;失败的**只有裸词根**。

**未能核实的一项(诚实边界)**:npm **scope `@gskill` 的归属无法匿名查证**。
`registry.npmjs.org/@gskill%2Fcore` 返回 404 说明该 scope 下没有名为 `core` 的包,
检索也未见任何 `@gskill/*` 包;但 `https://www.npmjs.com/org/gskill` 与
`https://www.npmjs.com/~gskill` 对 curl 与 WebFetch 均返回 **403**(npmjs.com 的反爬拦截,
不是"不存在"的证据)。**scope 是否已被注册,必须登录 npm 后台用 `npm org ls gskill`
或注册流程本身来判定**——本报告不下结论。

---

## 3. GitHub 占名

### 3.1 查询方式(原文)

```bash
curl -s "https://api.github.com/users/gskill"
curl -s "https://api.github.com/users/gskill/repos"
curl -s "https://api.github.com/users/gskill/events/public"
for r in SevenX77/gskill chrislin95/marvel gwaghmar/graph gskill/gskill; do
  curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/repos/$r"
done
curl -s "https://api.github.com/search/repositories?q=gskill+in:name&sort=stars&order=desc&per_page=15"
curl -s "https://api.github.com/search/repositories?q=gskill+in:name&sort=updated&order=desc&per_page=100"
for o in gskill gskill-dev gskillhq gskill-io getgskill gskill-ai gskilldev; do
  curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/users/$o"
done
```

时间:2026-09-01 14:58 UTC(账号与搜索)/ 15:06 UTC(候选组织名)。

### 3.2 结果(原文)

**`github.com/gskill` 账号已存在**:

```json
{"login": "gskill", "type": "User", "name": null, "company": null, "blog": "",
 "bio": null, "public_repos": 0, "created_at": "2013-10-10T17:51:09Z",
 "html_url": "https://github.com/gskill"}
```

补充:`public repos: 0`、`recent public events: 0` ——**休眠账号**,2013 年注册,无公开产出。

**目标仓库位置空闲**:

```
repos/SevenX77/gskill -> 404   ← 空闲(SevenX77 账号本身 200,public_repos=9,故 404 = 未创建)
repos/gskill/gskill   -> 404   ← 但 owner 命名空间被上面那个休眠 User 占着,无法创建
repos/gwaghmar/graph  -> 200   ← npm graph-skill 的上游(§2.2 已记录)
repos/chrislin95/marvel -> 404 ← npm gskill 声明的仓库地址,实际不可访问(私有或已删)
```

**候选组织命名空间**(404 = 可注册):

```
github.com/gskill     -> 200 (TAKEN)
github.com/gskill-dev -> 404 (FREE)     github.com/gskill-io  -> 404 (FREE)
github.com/gskillhq   -> 404 (FREE)     github.com/gskill-ai  -> 404 (FREE)
github.com/getgskill  -> 404 (FREE)     github.com/gskilldev  -> 404 (FREE)
```

**精确名搜索** `gskill in:name`:**total_count = 71**。其中名字精确等于
`gskill` / `gskills`(忽略大小写)且**与 AI agent skill 同领域**的:

| 仓库 | stars | 语言 | created | pushed | 自述 |
|---|---|---|---|---|---|
| `glapsfun/gskill` | 4 | Go | 2026-06-20 | **2026-08-28** | Gskill is a reproducible package manager for agentic AI skills |
| `itsmostafa/gskill` | **33** | Python | 2026-02-21 | 2026-04-12 | (无 description;topics = `agent-skills`,`ai-agents`,`claude-code`,`codex-cli`) |
| `rohitsandadi/gskill` | 18 | Python | 2026-01-14 | 2026-02-25 | An automated pipeline for learning repository-specific skills for coding agents |
| `civilgoody/gskills` | 0 | JS | 2026-08-26 | 2026-08-26 | Personal collection of Claude Code skills |
| `nickgu18/GSkills` | 0 | — | 2026-07-06 | 2026-07-06 | Publicly shareable agent skills — reusable, model-agnostic instructions for cloudcode/Claude Code/etc. |

同名但**不同领域**的(不构成混淆,列出以免遗漏):`ericwq/gskills`(13★,gRPC-go 实现细节)、
`MtnMurrDog/GSkills2`(体操动作库)、`OZXC/GSkills1`(Google Skills)、以及十余个
0★ 个人仓。

**§2.2 提到的 `ouyangyipeng/Graph-Skill`,核实存在**:

```
full_name: ouyangyipeng/Graph-Skill | stars: 2 | lang: Python
created: 2026-04-17 | pushed: 2026-05-05
```

### 3.3 定级:**中**

- **通过的部分**:`SevenX77/gskill` 可以创建,`gskill-gateway` / `gskill-studio` 作为
  同账号下的仓库名也不受阻。裁决要求的「主仓名 = gskill」在**个人账号命名空间下可以实现**。
- **失败的部分**:**组织命名空间 `github.com/gskill` 不可得**——被 2013 年的休眠 User
  占着。GitHub 不因休眠而释放用户名(其 name-squatting 政策只处理**商标持有人**的
  申诉,而我们不是 `gskill` 商标持有人——见第 5 节,商标在别人手里)。因此
  `github.com/gskill/gskill` 这种"组织名 = 产品名"的规范形状**做不到**;要么留在
  `SevenX77/` 下,要么用 `gskill-dev` / `gskillhq` 之类的**变形组织名**。
- **混淆的部分**:71 个同名/近名仓库中至少 5 个与我们同域,其中 `glapsfun/gskill`
  四天前(2026-08-28)还在更新。搜索 `gskill` 时我们不会是唯一结果,甚至不是最显眼的
  (`itsmostafa/gskill` 33★ 高于我们目前任何 gskill 相关公开产出)。

---

## 4. 包名混淆 / typosquatting 评估

### 4.1 查询方式(原文)

除第 1–3 节已列的 registry 探测外,补充:

```bash
# 编辑距离近名 / 视觉混淆名
for n in gskil gsklll gskiIl g5kill qskill getskill; do
  curl -s -o /dev/null -w "%{http_code}" "https://registry.npmjs.org/$n"
done
# 下载量级
curl -s "https://api.npmjs.org/downloads/point/last-month/<pkg>"
# 上游项目性质
curl -s "https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md"
curl -s "https://api.github.com/repos/gepa-ai/gepa"
```

时间:2026-09-01 14:59–15:05 UTC。

### 4.2 结果(原文)

**同名(精确)分发与工具,按领域重合度排序**:

| 载体 | 标识符 | 性质 | 活跃度 | 与我们的重合 |
|---|---|---|---|---|
| npm | `gskill` | GetSkill CLI,agent skill 的发现/安装/发布 | 上月 8 次下载,2026-04 后未更新 | **同域**,且**同 CLI 名** |
| npm | `@glapsfun/gskill` + 4 个平台二进制包 | agentic AI skills 的可复现包管理器 | 上月 373 次,2026-08-26 更新 | **同域**,且**同 CLI 名** |
| Go module | `github.com/glapsfun/gskill` | 同上(Go 本体) | 已发 v0.0.1→v0.7.0 | **同域**,`go install` 产出同名二进制 |
| GitHub | `itsmostafa/gskill` | 用演化搜索为仓库自动学习 skill,产出 `.claude/skills/{repo}/SKILL.md` | 33★,2026-04 后停更 | **同域** |
| GitHub | `rohitsandadi/gskill` | 同上思路;README 声明**已迁入 GEPA 主仓** `gepa-ai/gepa` 的 `src/gepa/gskill/` | 18★ | **同域** |
| GitHub | `gepa-ai/gepa` | 上条的上游,**6331★**,2026-08-30 仍在更新 | 极活跃 | `gskill` 是其子模块名 |

**GEPA 关联的原文证据**(`rohitsandadi/gskill` README):

> **gskill now lives in the main GEPA repo at [`src/gepa/gskill/`](https://github.com/gepa-ai/gepa/tree/main/src/gepa/gskill).**

`gepa-ai/gepa` 仓库元数据:`stars: 6331`,`pushed: 2026-08-30`,
desc = `Optimize prompts, code, and more with AI-powered Reflective Optimization`。

**近名 / 视觉混淆名(全部空闲,即 typosquatting 空间敞开)**:

```
npm/gskil -> 404   npm/gsklll -> 404   npm/gskiIl -> 404   npm/g5kill -> 404   npm/qskill -> 404
pypi/gskil -> 404  pypi/g-skill -> 404  pypi/gskills -> 404
npm/getskill -> 200  ← 已被占用(与 npm gskill 同一产品的别名 bin)
```

`gskiIl` 注意:第 4 个字符是**大写 I**而非小写 l——在多数等宽字体里与 `gskill` 视觉难辨,
是经典的 homoglyph 抢注位。它当前空闲。

### 4.3 定级:**高**

理由分三层:

1. **不是"联想",是"同名同域同命令"。**§2.2 当初的措辞是 `gskill` 会"让人**联想**到
   G.SKILL 硬件品牌、GEPA 的 gskill 和 Go 生态同名工具"——这个描述**低估了实际情况**。
   实测结果是:GEPA 的 gskill 与 Go 生态的 gskill **不是遥远的联想对象,而是与我们
   争夺同一批用户、同一条安装命令、同一个搜索词的活体项目**;此外还多出一个 §2.2 未
   记录的 npm 占用者(GetSkill CLI)。
2. **搜索与安装两条入口都会串。**用户搜 "gskill claude skill" 会同时命中至少四个项目;
   用户敲 `npm i -g gskill` 装到的是别人的东西;用户敲 `go install .../gskill@latest`
   装到的是第三方。我们无法通过文档消除这三条歧义,因为它们发生在我们的文档之外。
3. **typosquatting 风险是次要项,但不为零。**同名空间已经拥挤到"用户本来就分不清哪个是
   哪个"的程度时,恶意抢注近名的收益反而更高——受害者难以判断自己装错了。近名槽位
   (`gskil`、`gskiIl` 等)当前全部空闲,发布后需要防御性占位(见第 9 节)。

**反向证据(该记的都记)**:三个 GitHub 同名项目与两个 npm 同名分发**已经彼此共存**,
说明这个名字在开源社区层面**不是不能用**,只是**不能独占**。若"独占"不是产品要求,
则本项风险可以按"接受歧义 + 靠词缀区分"的方式降级——代价见第 8 节。

---

## 5. 商标复核

### 5.1 查询方式(原文)

Justia / uspto.report / USPTO TSDR API 全部不可用(见 5.4「未能到达的层面」),
因此改用 **TMview**——由 EUIPO 与各国知识产权局共建的**官方多局商标检索服务**,
覆盖 USPTO、EUIPO、UKIPO、CNIPA、KIPO 等 30 个局:

```bash
# 检索(POST)
curl -s -X POST "https://www.tmdn.org/tmview/api/search/results" \
 -H "Content-Type: application/json" -H "Accept: application/json" \
 -H "Origin: https://www.tmdn.org" -H "Referer: https://www.tmdn.org/tmview/" \
 -d '{"page":"1","pageSize":"100","criteria":"C","basicSearch":"gskill",
      "territories":[],"offices":[],"niceClasses":[],"applicants":[],
      "tmStatus":[],"tmTypes":[],"sortBy":"relevance"}'
# 同上,basicSearch 改 "g.skill";另做 offices:["US"] 定向查询
# 对照组(验证 US 覆盖有效):basicSearch "anthropic", offices ["US"] → 返回 12 条 Anthropic, PBC 在册记录
# 明细(含商品清单)
curl -s "https://www.tmdn.org/tmview/api/trademark/detail/<ST13>"
```

时间:2026-09-01 15:01–15:03 UTC。
**覆盖有效性已验证**:对照组查询 `anthropic` + `offices:["US"]` 返回 12 条 Anthropic, PBC
在册美国商标(含 Class 9 / 35 / 41 / 42),证明 TMview 的 USPTO 数据通路正常,
下列"未见"结论不是数据缺失造成的。

### 5.2 结果:精确字符串 `GSKILL`(无点)的在册商标

检索 `gskill`,`totalResults = 38`;其中 mark 名归一化后**精确等于 `gskill`** 的 4 条,
**全部落在 Nice Class 9**:

| 局 | 商标 | 状态 | 类别 | 申请人 | 申请号/注册号 | 申请日 / 注册日 / 到期 |
|---|---|---|---|---|---|---|
| RU | GSKILL | Registered | 9 | Джи Скилл Интернешнл Энтерпрайз(= G.Skill International Enterprise) | 2013706992 / 521228 | 2013-03-05 / 2014-08-27 / 2023-03-05 |
| AR | GSKILL | Registered | 9 | SAFTEL INC. 100,00% | 3035007 / 2469692 | 2010-09-30 / 2011-10-06 / — |
| AR | GSKILL | Registered | 9 | SAFTEL INC. 100,00% | 4064096 / 3258626 | 2021-10-20 / 2022-01-24 / 2031-10-21 |
| CN | GSKILL | **Expired** | 9 | 姜恒*** | 10308672 / 10308672 | 2011-12-15 / 2013-03-21 / 2023-03-20 |

即:**去掉点的 `GSKILL` 本身就是 G.Skill 集团在部分辖区注册的文字商标形态**(RU 一条直接
以 G.Skill 集团俄文名义持有),类别同样是 Class 9。

`offices:["US"]` + `basicSearch "gskill"` 返回 7 条,其中**精确匹配 0 条**——
即 USPTO 没有以无点 `GSKILL` 为 mark 文本的在册记录。

### 5.3 结果:`G.SKILL` 的美国在册记录(关键项)

检索 `g.skill`,`totalResults = 5076`(含大量 `...GSKILL...` 的组合词);
其中 **office = US 且 mark 精确为 G.SKILL** 的 6 条:

| 状态 | 类别 | 形态 | 申请人 | 申请号 / 注册号 | 申请日 / 注册日 |
|---|---|---|---|---|---|
| Registered | **9** | **Word** | GSKILL USA, INC. | 77038116 / **3282000** | 2006-11-07 / 2007-08-21 |
| Registered | 9 | Combined | GSKILL USA, INC. | 77040093 / 3282061 | 2006-11-08 / 2007-08-21 |
| Registered | 9 | Combined | GSKILL USA, INC. | 87115758 / **5160134** | 2016-07-26 / 2017-03-14 |
| Registered | **9** | **Word** | GSKILL USA, INC. | 97688567 / **7127358** | 2022-11-22 / **2023-08-01** |
| Registered | 41 | Combined | G.SKILL International Enterprise | 86372845 / 4856562 | 2014-08-20 / 2015-11-17 |
| Ended | 41 | Combined | G.SKILL International Enterprise | 86371545 / 4882523 | 2014-08-20 / 2016-01-05 |

**权利人明细**(TMview detail,ST13 `US500000097688567`):

```
markFeature            = "Word"
markCurrentStatusCode  = "Registered"
markCurrentStatusDate  = "2023-08-01T00:00:00.000Z"
applicationNumber      = "97688567"      registrationNumber = "7127358"
applicants = [{"fullName": "GSKILL USA, INC.", "legalEntity": "Corporation",
               "nationalityCode": "US",
               "fullAddress": "20259 PASEO DEL PRADO\n91789\nWALNUT\nCA"}]
oppositions = []   cancellations = []   renewals = []
```

**Class 9 商品清单原文(US Reg. 7127358,2023 年在册的文字商标)** —— 逐字摘录与我们
相关的条目:

> Dynamic random access memory (dram); blank usb flash drives; computer game software
> downloadable from a global computer network; computer hardware; computer memory hardware;
> **downloadable computer software for the collection, editing, organizing, modifying,
> book marking, transmission, storage and sharing of data and information**; downloadable
> computer software for controlling the operation of audio and video devices; computer
> peripheral apparatus; **downloadable computer software platforms, recorded, for
> application development, web hosting, database management**; computer software platforms
> for development of interactive audio applications for use with mobile audio platforms;
> **computer software platforms, recorded or downloadable for music production, television,
> film and motion picture production and gaming**; downloadable computer e-commerce
> software to allows users to perform electronic business transactions via a global computer
> network; downloadable universal peripheral interface (upi) software for controlling the
> operation of computer peripherals and audio devices, namely, speakers; ...
> recorded computer operating system software; ...

对照:**2007 年那条文字商标(US Reg. 3282000)的 Class 9 清单只有一句**——

> Computer hardware; computer memory hardware

即 G.SKILL 在 **2016 与 2022 两次扩张**中,把商品清单从"硬件"扩到了**明文的可下载软件平台,
且点名 "for application development"**。

**EUIPO 平行记录**(ST13 `EM500000018797746`):

```
tmName = G.SKILL   markFeature = "Word"   markCurrentStatusCode = "Registered"
applicationNumber = 018797746   applicationDate = 2022-11-21
markCurrentStatusDate = 2023-06-06   expiryDate = 2032-11-21
niceClass = [9, 41]
applicants = [{"organizationName": "G. SKILL International Enterprise Co., Ltd.",
               "nationalityCode": "TW", "incorporationCountryCode": "TW",
               "fullAddress": "6F., No. 69, Dongxing Rd., Xinyi Dist.\n11070\nTaipei City"}]
```

其 Class 9 清单同样含 `Computer software for the collection, editing, organizing,
modifying, book marking, transmission, storage and sharing of data and information`、
`Computer software platforms for controlling the operation of computer peripherals and
audio devices`、`Downloadable computer software ...`、`Recorded computer operating system
software`。

**G.SKILL 正在进行的 2026 年新申请(Class 9 文字商标,全部 status = Filed)**:

| 局 | 申请号 | 申请日 | 形态 | 类别 |
|---|---|---|---|---|
| GB(英国) | UK00004370806 | **2026-04-09** | Word | 9 |
| EM(EUIPO) | 019373730 | **2026-06-01** | Word | 9 |
| CA(加拿大) | 2481690-00 | **2026-06-12** | Word | 9 |
| AU(澳大利亚) | 2664445 | **2026-06-19** | Word | 9 |

此外在册的 Class 9 `G.SKILL`(部分):CN 4749728(2008 起,2028 到期)、CN 18824550、
CN 68426337(2033 到期)、EM 004611241(**2035 到期**)、EM 005488341(2036)、
EM 015327489(2036,Class 9+41)、GB UK00904611241(2035)、AU 1129881(2036)、
AU 1756443(2036)、KR 4010166600000(2034)、IL 253622(2033)、EG 285702(2033)、
NZ 1190561(2031)、PH 4-2022-504424(2032)。

### 5.4 未能到达的层面(如实记录,不臆测)

- **Justia Trademarks**:`https://trademarks.justia.com/...` 对 WebFetch 与带浏览器
  User-Agent 的 curl 均返回 **403**;`uspto.report` 返回 **403 + Cloudflare 挑战页**。
  故本节的 USPTO 事实**不来自** Justia,而来自 TMview 的 USPTO 数据通路。
- **USPTO TSDR API**:`https://tsdrapi.uspto.gov/ts/cd/casestatus/sn77038116/info.json`
  返回 **401**(现需 API key)。未申请 key。
- **台湾 TIPO** 未覆盖:TMview 返回的 office 列表为
  `['AR','AU','BR','BX','CA','CL','CN','DE','DO','EG','EM','ES','FR','GB','IL','IN','IT','JP','KR','MX','MY','NZ','PE','PH','RU','TH','UA','US','VN','WO']`——**不含 TW**。
  G.SKILL 是台湾公司(EUIPO 记录地址:Taipei City),其**本土注册未纳入本次检索**。
- **未做正式律师检索**。本节没有做 clearance search 意义上的近似检索
  (音近/形近/义近全谱、共存协议调查、实际使用范围与市场分割分析),也没有查
  USPTO TTAB 的异议/撤销案件史(TMview 的 `oppositions` / `cancellations` 字段为空,
  但该字段对 USPTO 记录**未必完整**)。
- **无点 `gskill` 在软件类的注册**:公开网页与 TMview 层面,**未见任何人以无点
  `gskill` 为 mark 在 Class 42(SaaS)注册**;Class 9 的无点 `GSKILL` 注册见 5.2,
  持有人指向 G.Skill 集团及其关联方(RU/AR),不是第三方软件公司。

### 5.5 定级:**高**

风险不在"硬件品牌联想",而在四条可核实的事实叠加:

1. **同类别。**我们的产品(可下载的开发者软件平台 + CLI)标准落在 **Nice Class 9**
   (可下载软件)与 **Class 42**(SaaS/软件即服务)。G.SKILL 在 Class 9 有**多件在册,
   含文字商标**。
2. **商品重合,且是明文重合。**US Reg. 7127358 的清单里有
   `downloadable computer software platforms, recorded, for application development`——
   "用于**应用程序开发**的可下载软件平台"。这不是需要推论的邻接,这就是我们在做的事的
   官方分类语言。
3. **标识近似度极高。**`gskill` 与 `G.SKILL` 的差别只有一个句点。商标近似判断通常
   **忽略标点**;`GSKILL`(无点)本身还是 G.Skill 集团在 RU 的注册形态(5.2)。
   在 Class 9 内,这基本等同于同一标识。
4. **权利人处于主动扩张与维权姿态。**2016 与 2022 两次把商品清单扩进软件;2026 年
   4–6 月连发四国 Class 9 **文字**商标新申请。一个刚刚花钱在全球加固同类别文字商标的
   权利人,遇到同类别、近乎同名的新软件产品,发函的概率不低。

**反向证据(必须一并记)**:
- 三个 GitHub `gskill` 项目与两个 npm `gskill` 分发**已长期共存,未见被清理的迹象**——
  说明 G.SKILL 对小型开源项目的实际执法密度不高(或尚未注意到)。
- 商标保护是**类别 + 混淆可能性**双重限定的。G.SKILL 的实际使用集中在内存/散热/外设
  及其配套控制软件(如 WigiDash),销售渠道是 DIY 硬件零售;我们的渠道是开发者
  registry 与 CLI。市场分割论在争议中是可主张的抗辩。
- 但**这两条都是"可能不被追究"的论据,不是"不侵权"的论据**。项目从开源仓库走向
  **发布身份**(注册 PyPI 分发、买域名、做安装包、可能商业化)的那一刻,风险曲线
  与"一个 4 星 GitHub 仓"不在同一档。§11.5-4 要求的正是**发布前**判定。

---

## 6. 域名复核

### 6.1 查询方式(原文)

```bash
# HTTP 可达性
for d in gskill.dev gskill.io gskill.ai gskill.com gskill.net getskill.net gskill.org; do
  curl -s -o /dev/null -w "%{http_code} %{url_effective}" -L --max-time 15 "https://$d"
done
# RDAP(先经 IANA bootstrap 取权威端点,再直连)
curl -s https://data.iana.org/rdap/dns.json
curl -s -L "https://rdap.verisign.com/com/v1/domain/gskill.com"
curl -s -L "https://rdap.publicinterestregistry.org/rdap/domain/gskill.org"
curl -s -L "https://pubapi.registry.google/rdap/domain/gskill.dev"          # 对照组: claude.dev
curl -s -L "https://rdap.identitydigital.services/rdap/domain/gskill.io"    # 对照组: github.io
curl -s -L "https://rdap.identitydigital.services/rdap/domain/gskill.ai"
# DNS 第二信号(Google DoH,读权威 NS / NXDOMAIN)
curl -s "https://dns.google/resolve?name=<domain>&type=NS"
# 页面内容
curl -s -L "https://<domain>"   # 取 <title> / meta description / 正文
```

IANA bootstrap 原文(证明用的是**权威**端点,不是第三方镜像):

```
dev -> ['https://pubapi.registry.google/rdap/']
ai  -> ['https://rdap.identitydigital.services/rdap/']
org -> ['https://rdap.publicinterestregistry.org/rdap/']
com -> ['https://rdap.verisign.com/com/v1/']
```

时间:2026-09-01 14:59 UTC(HTTP)/ 15:00 UTC(RDAP)/ 15:06 UTC(DoH)。

### 6.2 结果(原文)

| 域名 | HTTP | RDAP | DoH NS 查询 | 判定 |
|---|---|---|---|---|
| **gskill.dev** | `000`(连接失败) | `errorCode 404 Not Found`(对照组 `claude.dev` → 200 REGISTERED) | `Status=3 NXDOMAIN`,AUTH = `ns-tld1.charlestonroadregistry.com`(.dev 权威) | **未注册 = 可注册** |
| **gskill.io** | `000` | `errorCode 404 Object not found`(对照组 `github.io` → 200 REGISTERED) | `Status=3 NXDOMAIN`,AUTH = `a0.nic.io`(.io 权威) | **未注册 = 可注册** |
| gskill.ai | `200` | **REGISTERED**,registration `2026-03-22`,expiration `2028-03-22`,last changed `2026-08-12`,status `client transfer prohibited` | `NS=['launch1.spaceship.net','launch2.spaceship.net']` | **已注册,挂牌出售** |
| gskill.org | `200`(114 字节空页) | **REGISTERED**,registration `2025-12-01`,expiration `2026-12-01`,registrar `Dynadot Inc` | `NS=['ns1.afternic.com','ns2.afternic.com']`(Afternic = 域名交易平台) | **已注册,疑似投资持有** |
| gskill.com | `403 Forbidden`(重定向到 `www.gskill.com`) | **REGISTERED**,registration **`2004-08-12`**,expiration `2030-08-12`,registrar `eNom, LLC`,status `client transfer prohibited` | — | **长期持有**(2004 年起,与 G.SKILL 品牌同期) |
| gskill.net | `200` → 重定向至 `https://www.hugedomains.com/domain_profile.cfm?d=gskill.net` | — | — | **已注册,HugeDomains 挂牌** |
| getskill.net | `200` | — | — | **npm `gskill` 占用者的主站**,标题 `GetSkill — AI Agent Skills Registry` |

**gskill.ai 页面原文**(`<title>` 与正文摘录):

> gskill.ai for sale | Spaceship.com
> Domain for sale · gskill.ai · Listed with spaceship.com · get this domain ·
> **Buy now $20,000** · Make offer

**gskill.com 页面原文**:

> 403 Forbidden — You don't have permission to access this resource.
> Additionally, a 403 Forbidden error was encountered while trying to use an
> ErrorDocument to handle the request.

(注:`gskill.com` 返回 403 而非 G.SKILL 官网内容;G.SKILL 官方站点是 `www.gskill.com`
在其它路径上可用,以及 `gskill.us` 论坛。403 说明该主机存在但拒绝根路径匿名访问,
**不能据此断定持有人身份**——只能说该域名 2004 年起被持续持有、锁定转移。)

### 6.3 定级:**中**

- **开发者品牌最常用的两个 TLD 都空闲**:`gskill.dev` 与 `gskill.io` 均为 NXDOMAIN +
  RDAP 未找到,两条独立信号一致。这是本节的**通过面**。
- **失败面**:`.com` 自 2004 年被锁定持有且到期日排到 2030;`.ai` 要 2 万美元;
  `.org` 挂在 Afternic;`.net` 挂在 HugeDomains。也就是说 `gskill` 这个词根在
  域名市场上**早就被系统性持有并定价**,我们只能拿到 `.dev`/`.io`。
- **实务影响**:选 `gskill.dev` 或 `gskill.io` 可用,但**输入 `gskill.com` 的用户到不了
  我们**,而 `.com` 与 G.SKILL 品牌同期(2004)持有——这条与第 5 节的商标风险**叠加**:
  用户在 `.com` 上找到的不是我们,而在商标层面 `.com` 的长期持有正是"该标识与 G.SKILL
  长期关联"的旁证。

---

## 7. CLI 命令冲突

### 7.1 查询方式(原文)

```bash
# npm 声明的可执行名
curl -s "https://registry.npmjs.org/gskill/0.3.1"          | jq .bin
curl -s "https://registry.npmjs.org/@glapsfun%2Fgskill"    # → versions[latest].bin
# Go module proxy(权威版本列表)
curl -s "https://proxy.golang.org/github.com/glapsfun/gskill/@v/list"
curl -s "https://proxy.golang.org/github.com/itsmostafa/gskill/@v/list"
# GitHub release 资产名
curl -s "https://api.github.com/repos/glapsfun/gskill/releases/latest"
# Homebrew
curl -s -o /dev/null -w "%{http_code}" "https://formulae.brew.sh/api/formula/gskill.json"
curl -s -o /dev/null -w "%{http_code}" "https://formulae.brew.sh/api/cask/gskill.json"
# Scoop / winget / AUR / Debian / Ubuntu / crates.io
curl -s -o /dev/null -w "%{http_code}" "https://raw.githubusercontent.com/ScoopInstaller/Main/master/bucket/gskill.json"
curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/g/gskill"
curl -s "https://aur.archlinux.org/rpc/v5/search/gskill"
curl -s "https://sources.debian.org/api/search/gskill/"
curl -s -L "https://packages.ubuntu.com/search?keywords=gskill&searchon=names&exact=1"
curl -s -A "<browser UA>" -o /dev/null -w "%{http_code}" "https://crates.io/api/v1/crates/gskill"
```

时间:2026-09-01 14:59–15:05 UTC。

### 7.2 结果(原文)

**已被声明的 `gskill` 可执行名(冲突项)**:

```
npm gskill@0.3.1        bin: {'gskill': 'dist/index.js', 'getskill': 'dist/index.js'}
npm @glapsfun/gskill@0.7.0  bin: {'gskill': 'bin/gskill.js'}
Go  proxy.golang.org/github.com/glapsfun/gskill/@v/list -> v0.0.1 v0.3.0 v0.5.2 v0.6.0 v0.7.0
GitHub release glapsfun/gskill v0.7.0 (2026-08-26) 资产:
    gskill_0.7.0_darwin_amd64.tar.gz / darwin_arm64 / linux_amd64 / linux_arm64
    (+ checksums.txt.sigstore.json、SBOM —— 即已做签名与 SBOM 的正式发行)
```

**未见冲突的分发渠道**:

```
brew formula gskill        -> 404      winget manifests/g/gskill -> 404
brew cask    gskill        -> 404      AUR search gskill         -> {"resultcount":0,"results":[]}
Scoop Main/gskill.json     -> 404      Debian sources search     -> {"exact":null,"other":[]}
crates.io gskill           -> 404      crates.io gskill-gateway/-studio -> 404
```

(Ubuntu `packages.ubuntu.com` 精确搜索返回 HTTP 200 的是**搜索页本身**,不是命中;
Debian 的 JSON API 明确给出 `"exact": null`,故判定为无同名 apt 包。)

### 7.3 定级:**高**

- **`gskill` 这个命令名已被两个活体项目同时声明**,且两者都在我们要做的事的
  邻接位置(agent skill 的安装/包管理)。`npm i -g gskill` 与
  `npm i -g @glapsfun/gskill` **彼此之间就已经互相覆盖** `gskill` 这个 bin;
  我们再进去是第三个。
- **`go install github.com/glapsfun/gskill@latest` 产出的二进制就叫 `gskill`**,
  且已发到 v0.7.0、带 sigstore 签名与 SBOM——这是一个在正经维护的发行,不是弃置实验。
- **这一项直接命中已定设计。**`v1-alignment.md:46-47` 把 **Console command** 与
  **MCP namespace** 都定为 `gskill`,§11.5-3 又明确"与本裁决同向,保留"。
  也就是说冲突落在**裁决保留的那一半**上,不是可以改词缀绕开的那一半
  (`gskill-gateway` 这类词缀名在所有包管理器上都空闲)。
- **通过面**:系统级包管理器(brew / scoop / winget / apt / AUR / crates.io)**全部无冲突**。
  真正的战场只在 npm 全局 bin 与 `go install` 的 `$GOBIN`,以及用户 `$PATH` 里
  谁先出现。

---

## 8. 总评

### 8.1 判定:**建议重裁**

按 §11.5-4 与 §2.2 的原文判据——「PyPI / GitHub 占名、包名混淆检查、域名与商标复核」,
「**任何一项失败**都应在发布前重新裁决名称」——本次复核结果是:

- **通过 1 项**:PyPI 占名(四个名字全空闲,含规范化变体)。
- **部分通过 1 项**:域名(`.dev` / `.io` 可得;`.com` / `.ai` / `.org` / `.net` 不可得)。
- **部分失败 1 项**:GitHub 占名(仓库位置可得;**组织命名空间 `github.com/gskill` 不可得**)。
- **失败 4 项**:npm 占名(裸词根不可得)、包名混淆(同域三个同名 GitHub 项目 +
  两个同名 npm 分发)、商标(**在册美国 Class 9 文字商标,商品清单明文含
  "用于应用程序开发的可下载软件平台",标识仅差一个句点,权利人 2026 年仍在扩张申请**)、
  CLI 命令冲突(`gskill` 命令已被两个活体发行占用,且正落在裁决保留的 console command 上)。

**按判据的字面,已经触发"发布前一次性重裁新名"。**

### 8.2 风险按严重度排序(给决策用)

1. **商标(第 5 节)——不可自行消解,且随发布而升级。**这是唯一一项**不由先来后到
   决定、也不能靠改词缀规避**的风险。US Reg. 7127358 是 2023 年新在册的**文字**商标,
   Class 9,商品清单里有 `downloadable computer software platforms, recorded, for
   application development`;我们做的正是可下载的应用开发软件平台。`gskill` 与
   `G.SKILL` 在商标近似判断中基本等同(标点通常被忽略,且无点 `GSKILL` 本身就是
   G.Skill 在 RU 的注册形态)。权利人 2026 年 4–6 月还在 GB/EU/CA/AU 连发四国 Class 9
   文字商标新申请——这是加固与维权姿态,不是休眠权利。
2. **CLI 命令冲突(第 7 节)——命中裁决明确保留的那一项。**`gskill` 命令被
   GetSkill CLI 与 glapsfun/gskill(Go,v0.7.0,带签名与 SBOM)同时占用。词缀规则
   (§11.5-2)能救 `gskill-gateway`、`gskill-studio`,**救不了 console command 与
   MCP namespace**,而后两者是 §11.5-3 点名保留的。
3. **npm 裸名不可得(第 2 节)——事实性关闭,非我方可解。**npm 的 unpublish 政策
   使该名字不会自然释放;要么协商转让,要么永远用 scope 或词缀替代。
4. **混淆密度(第 4 节)——已经拥挤到"搜索与安装两条入口都会串"。**§2.2 当年写的是
   "会让人**联想**到 GEPA 的 gskill 和 Go 生态同名工具";实测这两个不是遥远联想,
   而是与我们抢同一批用户、同一条安装命令、同一个搜索词的活体项目,并且还多出一个
   §2.2 未记录的 npm 占用者。**本项的实际严重度高于设计文档当时的记载**。
5. **GitHub 组织名不可得(第 3 节)——形状受损,不阻塞。**`github.com/gskill` 被
   2013 年休眠 User 占着;GitHub 的用户名释放政策只对**商标持有人**开放,而 `gskill`
   在 Class 9 的商标在别人手里(第 5 节),这条路对我们关闭。
6. **域名(第 6 节)——可接受的次优。**`.dev` / `.io` 空闲够用;代价是 `.com` 到不了
   我们,且 `.com` 自 2004 年被持有这件事本身还是第 1 项风险的旁证。

### 8.3 若不接受"重裁"结论,唯一诚实的表述是什么

本报告**不替用户改裁决**。但按「论据先行」纪律必须说清:如果保留 `gskill`,
那么保留的**不是"复核通过的名字"**,而是**"复核不通过、但接受其风险的名字"**。
这两者在台账上必须写成不同的话——因为第 5 节的风险不随时间衰减,只随发布规模增长。

第 9 节按这个前提给出条件清单。

---

## 9. 若保留 `gskill`:条件清单与发布前最小占位动作清单

> **以下全部为"待执行清单",本次作业未执行任何一条。**

### 9.1 必须先完成的条件(缺一不可)

| # | 条件 | 为什么是硬条件 |
|---|---|---|
| C1 | **取得执业商标律师对 US Class 9 / Class 42 的正式 clearance 意见**,范围至少覆盖 US Reg. 7127358、5160134、3282000、3282061 与 EUIPO 018797746 / 004611241,并明确回答:我们的商品描述与其 `downloadable computer software platforms ... for application development` 是否构成 likelihood of confusion | 第 5 节是公开检索层面的事实,不是法律结论;这一项是本报告**唯一无法自行完成**的复核项(§2.2 要求"商标复核",而不是"商标检索") |
| C2 | **补做台湾 TIPO 检索**(TMview 不覆盖 TW,而 G.SKILL 是台湾公司) | 权利人本土注册未纳入本次检索,是已知的证据缺口 |
| C3 | **裁定 console command 的最终形态**:是接受与两个活体工具共用 `gskill` 这个 bin,还是把 CLI 改成不冲突的名字 | §11.5-3 保留了 `gskill` 作为 console command,但第 7 节证明该位置已被占;这是设计与事实的直接冲突,必须显式裁决,不能默认 |
| C4 | **裁定 npm 发布身份**:用 scope(`@<org>/gskill`)、还是全部走词缀名(`gskill-cli` 等)、还是不上 npm | 裸名不可得是事实性关闭,必须选一条替代路径 |
| C5 | **裁定 GitHub 归属**:留在 `SevenX77/gskill`,还是建变形组织名(`gskill-dev` / `gskillhq` / `gskill-ai` 等,均已实测空闲) | `github.com/gskill` 不可得,组织名 = 产品名的形状做不到 |

### 9.2 发布前最小占位动作清单(按"越晚越贵"排序;只列,不执行)

**第一优先——先来先得且随时可能被抢的**

1. 注册 PyPI 分发名 `gskill`(占位 sdist,版本 `0.0.0`);同时注册 `gskill-gateway`、
   `gskill-studio`(若 runtime 独立分发则加 `gskill-runtime`)。
2. 在 TestPyPI 上同样占位(四个名),避免发布演练时被他人抢先。
3. 注册域名 `gskill.dev`(首选,开发者工具惯例)与 `gskill.io`(防御位);
   两者均已实测未注册。
4. 创建 GitHub 仓库 `SevenX77/gskill`,并按 C5 的裁决结果同时注册所选组织名
   (`gskill-dev` / `gskillhq` / `gskill-ai` / `gskilldev` 中之一,均已实测空闲)。
5. 按 C4 的裁决结果,注册 npm scope 或词缀名:
   - 若走 scope:先用登录态确认 `@gskill` scope 是否可注册(本报告**未能**匿名查证),
     不可用则改用已实测空闲的组织向 scope;
   - 若走词缀:占位 `gskill-cli`、`gskill-gateway`、`gskill-studio`、`gskill-runtime`
     (全部实测 404 空闲)。
6. 占位 crates.io `gskill` / `gskill-gateway` / `gskill-studio`(全部实测空闲)——
   即使当前不发 Rust crate,Tauri 壳未来可能需要,且占位成本极低。

**第二优先——防御性反抢注**

7. 占位 npm/PyPI 近名槽位:`gskil`、`gskills`、`g-skill`、`graphskill`,以及
   homoglyph 位 `gskiIl`(第 4 个字符为大写 I)。全部实测空闲。
8. 在 Homebrew / Scoop / winget / AUR **暂不占位**——这些渠道当前无冲突(第 7 节),
   且它们要求真实可安装的发行物,提前占位反而制造死配置。等有正式安装包再提交。

**第三优先——发布身份对齐**

9. 在 README / 站点首屏放**显式免责与区分声明**:说明本项目与 G.SKILL
   International Enterprise(内存/外设品牌)无关联,并说明与 npm `gskill`(GetSkill CLI)、
   `glapsfun/gskill`、GEPA `gskill` 的区别。这不消除商标风险,但是善意使用
   (good-faith)的证据,且直接减轻第 4 节的用户混淆。
10. 若 C1 的律师意见判定风险可接受,考虑在 **Class 9 + Class 42** 提交我方商标申请——
    但注意:在已有近乎同名的 Class 9 在册文字商标的情况下,申请本身可能被驳回或引发异议,
    这一步应由 C1 的意见决定做不做,不要先做。

### 9.3 若走"重裁"

候选新名必须在**决定之前**跑完与本报告相同的七项检查(本次机械执行耗时约 10 分钟,
脚本化后可复用)。判据:七项**全部通过**,或失败项能被证明为"不可自行消解者以外的项"。
**本报告不代为提出候选名**——那属于命名裁决,不属于复核。

---

## 10. 证据文件清单(本次作业落盘的原始数据)

全部位于本报告同目录
(`...\e47fa48b-1904-4f62-aa53-1a12ca33cff7\scratchpad\`):

| 文件 | 内容 |
|---|---|
| `tmview_p1.json` | TMview 检索 `gskill` 全量结果(38 条) |
| `tmv_dotted.json` | TMview 检索 `g.skill`(返回前 100 条,totalResults 5076) |
| `tmv_us_gskill.json` | TMview 检索 `gskill` 限定 office=US(7 条,精确匹配 0) |
| `tmv_us_control.json` | 对照组:检索 `anthropic` 限定 office=US(12 条,证明 US 通路有效) |
| `det_US500000097688567.json` | US Reg. 7127358 明细,含 Class 9 商品清单全文 |
| `det_US500000087115758.json` | US Reg. 5160134 明细,含 Class 9 商品清单全文 |
| `det_US500000077038116.json` | US Reg. 3282000 明细(2007 年清单仅"hardware; memory hardware") |
| `det_EM500000018797746.json` | EUIPO 018797746 明细,含 Class 9 商品清单全文 |
| `tm_analyze.py` / `tm_report.txt` | 上述 JSON 的解析脚本与其输出 |

---

*报告生成:2026-09-01 UTC。全部结论为该时间点的公开可核实事实;registry / 域名 / 商标状态
随时间变化,发布前应重跑第 1、2、3、6、7 节的机械检查。第 5 节的商标结论**不是法律意见**,
须按 C1 补正式检索。*
