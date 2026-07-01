---
module: 02-mechanism/02-resolver
doc: mvp1-alignment
status: audited-ready（**U1 单元锁定 2026-06-05**;子图 path 解析（相对 skill root 优先，绝对也须落在边界内）+ DI 协议形状(契约)已定、删 registry;默认实现 LocalWorkspaceResolver 函数体归 kiro;文件未 FROZEN）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·编译）
---

# 02-resolver — 机制 B · 子图引用解析(path · DI 接缝)

> **Tier**: 机制层 B · 编译期 | **Owns**: 把子图引用的 **path**（相对 skill root 或绝对）解析成子图本地 root + skill-root 边界校验(**无 registry**)+ 定义 `SkillResolverProtocol` DI 接缝**形状**(契约,非 kiro) | **现状**: ⏳ | **Related**: `01-compile`(用它递归解析 SUBGRAPH)· `01-contract/02-skill-syntax`(path 语法)· `05-run-inner/07-subagent`(运行期子代理,另一回事)

## 1. 定义
resolver = 把子图引用(`SUBGRAPH.md` / agent `subgraphs[]` 的 **`path`**,相对 skill root 或绝对)解析成**子图本地 root** 的接缝。mvp1 **无 registry、无逻辑 id 寻址**——path 直接解析;resolver 只做两件事:**边界校验**(解析后的 root 是否落在引用方 skill 根内)+ **合法性校验**(是目录、含 `GRAPH.md`)。

> 反转说明:早期模型用逻辑 id + `resolve_skill(id)` 查注册表,**已废弃**。mvp1 子图直接写 path(见 `skill-syntax` §2.1),不再有注册表寻址、id→路径 映射、dotted-id、多命中歧义(path 是确定地址、无歧义)。

## 2. 数据流 / 机制
1. loader 编译 SUBGRAPH 节点 / agent `subgraphs[]` 时,读到 `path`(相对 skill root 或绝对)。
2. **边界校验**:path 解析后的子图 root 必须落在引用方 **skill root** 内——防引用工作区外的任意目录;越界 → 解析失败(报警;studio 标红 → 可触发 reconnect)。
3. **合法性校验**:path 是目录、且含 `GRAPH.md` → 否则失败。
4. 把该目录当子图 root,按完整 graph skill **递归编译**;递归防环(`[F-v3-compile-recursion-cycle]`)。

## 3. 接口契约
- 输入:`path`(相对 skill root 或绝对) + host 提供的 skill root 边界;输出:子图 root(`Path`)。
- 接缝**保留**(host 注入边界),但语义从"id→registry→root"变为"**path → 边界/合法性校验 → root**"。
- **DI 显式、不全局化**:中间件消费 `_build_skill_node` 已备好的 runtime map,不自己找 resolver(见 `07-subagent`)。
- **DI 接缝协议形状 = 契约,归本域(非 kiro)**:上面「输入(path + skill root 边界)→ 输出(子图 root)+ 失败(越界 / 非目录 / 缺 `GRAPH.md` → raise)」就是 `SkillResolverProtocol` 的 mvp1 协议形状(mvp0 曾是 FROZEN 专文 `10-skill-resolver-protocol-spec`,path 版承接它)——**这是 engine↔studio 的 DI 契约,不是 kiro 实现细节**。`run_skill`/`compile_skill` 带可选 `skill_resolver` 覆盖参数这件事归 [`03-api-contract`](../../03-api-contract/mvp1-alignment.md)(只引用、不复制);省略时 engine 用默认 `LocalWorkspaceResolver`,Studio 等宿主拥有 registry/边界真相时仍显式注入。**默认实现的内部函数体**(具体怎么查边界 / 合法性)归 kiro。

## 4. 设计决策基础(用户原话)
> 子图 path(PM 2026-06-02):"subgraph.md里面写path, 直接解析就好了, 随便放哪里。唯一要注意的是copilot 的工作目录范围要把subgraph的子图path 加进去。"
> path 放宽为相对(skill 根内)/绝对(2026-06-21):默认子图随引用方 skill 自包含迁移,推荐写相对 skill root；绝对路径也接受,但解析后仍须落在 skill root 内。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RS1 | 子图按 **path**（相对 skill root 或绝对）直接解析,删 registry / id 寻址 / dotted-id / 多命中歧义 | path 直接打开,无需注册表；相对路径保证随 skill 迁移 |
| RS2 | resolver 只剩**边界校验 + 合法性校验**(接缝保留、大幅简化) | host 决定工作目录边界;防引用工作区外任意目录 |
| RS3 | **SUBGRAPH(编译期 path 解析)≠ subagent(运行期委派)** | 不同生命周期(断层#7);子代理与 agent phase 捆绑、不走 path |
| RS4 | DI 显式、不被 middleware 全局化 | 防隐式全局依赖 |

## 6. 测试关键点
1. 相对或绝对 path → 子图 root;含 `GRAPH.md` 校验通过。
2. path 在工作目录边界外 → 解析失败、报警。
3. 递归子图防环。
4. 写旧的 registry 逻辑 id → 应失败(已无 registry 寻址)。

## 7. 涉及 region / platform
engine 定义解析机制 + 校验;host(studio)注入工作目录边界。

## 8. gaps / 待设计
1. **协议形状已不是 gap(2026-06-05 纠正)**:DI 接缝**形状**是契约、已在 §3 定义(本域 owns 形状,`03-api-contract` owns `skill_resolver` 参数面)。残留只剩默认实现 `LocalWorkspaceResolver` 的**内部函数体**(旧 registry/search_paths 寻址 → 边界+合法性校验的实现),归 kiro。
2. **工作目录边界的具体表示**(copilot cwd / workspace 根集合怎么传进来)与 host 约定待定。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-compile`(递归解析 SUBGRAPH)· `01-contract/02-skill-syntax`(path 语法)· `05-run-inner/07-subagent`(运行期子代理,另一回事)
