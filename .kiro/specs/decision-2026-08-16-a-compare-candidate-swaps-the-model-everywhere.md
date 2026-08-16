# 决议:一个 compare 候选,要把模型换在这个节点跑到的每一处

- 日期:2026-08-16
- 范围:Studio backend `apps/studio/backend/app/services/model_compare.py`
- 相关 PR:本决议随同一 PR 落地
- 台账行:W2-21

---

## 1. 决策

节点级 Compare LLMs 的**候选 roles 文件**,从今以后是**当前 roles 真相的完整副本,
其中每一个角色的模型都被换成候选模型**;而不是从前那样只绑两个角色名。

三句话说清这次改的是什么:

1. **原来**:候选 roles 文件里只有两个角色——该节点的 effective role,和保底的
   `graph_agent`。别的角色在这份文件里根本不存在。
2. **现在**:先把当前生效的 `llm_roles.yaml` 整份读进来,把**每一个**角色的模型来源
   换成候选模型(其余属性——生成参数 `intent`、系统提示词前缀、lint 要求——原样保留),
   再物化成引擎能直接执行的 `fallback_chain`。真相里没有的两个角色(节点 effective
   role 与 `graph_agent`)照旧合成一个裸角色补上。
3. **代价**:一个作者有意挂了便宜模型的相位,在对比里也会被换成候选模型。

**术语**(首次出现即解释):

- **role(角色)**:一个有名字的模型配置(用哪些模型、什么温度、什么系统提示词前缀)。
  skill 的相位用 `llm_role: analyst` 这样的写法点名要哪个角色。
- **roles 真相**:`llm_roles.yaml` 这一份文件,是所有角色定义的唯一权威来源。
- **effective role(节点的生效角色)**:某个节点最终会用哪个角色的名字。AGENT 节点看
  它自己声明的 `llm_role`,没声明就用根图的默认;SUBGRAPH / LOGIC 节点自己不声明角色,
  退到约定名 `graph_agent`。
- **旁路单节点侧跑(side-run)**:对比不在主图里插节点,而是把被比的那个节点单独物化成
  一个只有一相的临时 skill,喂上主跑时它拿到的那份输入,单独跑一次。

---

## 2. 论据

### 2.1 缺陷本身(因果证据,operator 与本任务各跑一次)

被测对象 `D:/coding/skills/story-deconstruction-v3-lab`(实验副本),根图四个 phase
**全是 SUBGRAPH 节点**。照抄 `RunManager.start_node_compare_run` 对单个候选做的三件事
跑一遍 `global_synthesis`,原样输出:

```
node: global_synthesis
effective role bound in candidate roles file: graph_agent
roles defined in candidate file: ['graph_agent']
input keys from base run: ['accumulated_context', 'batch_outputs', 'entity_registry']
success: False
error: code='[F-v3-runtime-state-mapping-failed]' level='FATAL' stage=('运行期',)
  message="ResourceTerminalError: resource.no_available_route - {'role': 'analyst'}"
```

同一现象在本次的 pytest RED 里逐字复现:

```
E    graph_agent_gateway.resolve.resolver.RegistryResolutionError: role is not configured: analyst
E    graph_agent_gateway.call.resolver.ResourceTerminalError: resource.no_available_route - {'role': 'analyst'}
```

### 2.2 机制(逐环都有代码坐标)

1. `app/services/model_compare.py:155-160`(修复前)只往 `RolesData` 里放两个键:

   ```python
   effective = node_effective_role(skill_dir, node_id)
   roles = {effective: role_entry.model_copy(deep=True)}
   roles.setdefault("graph_agent", role_entry.model_copy(deep=True))
   ```

2. 同文件 `:119-122`(修复前)对 SUBGRAPH / LOGIC 节点的分支:

   ```python
   if isinstance(doc.ast, AgentNodeAST):
       return effective_llm_role(doc.ast, compiled.manifest.llm_role)
   # logic/subgraph nodes have no llm_role; fall back to the conventional role.
   return compiled.manifest.llm_role or "graph_agent"
   ```

   lab skill 根 `GRAPH.md` 没有 `llm_role`,所以它返回 `graph_agent`。

3. 而子图内层的相位各自声明角色。实测 `grep -rn "^llm_role:" --include=SKILL.md`:
   **16 个相位写 `analyst`、1 个写 `fast`**,`graph_agent` 一个都没有。

4. 侧跑用 `roles_path_override` 交给 worker(`app/services/run_manager.py:793,802,858`),
   worker 在**子进程里**把它写成环境变量(`run_manager.py:209-210`):

   ```python
   if roles_path_override:
       os.environ["STUDIO_LLM_ROLES_PATH"] = roles_path_override
   ```

5. 引擎侧的解析器 `_private_build_gateway_model_resolver`
   (`app/core/adapters/engine.py:271-274`)读这个环境变量,并把这份文件当作
   **整份 roles 真相**塞进一次性的 config store(`:310-315`)。于是内层相位要的
   `analyst` / `fast` 在这份文件里**根本不存在**,解析当场死。

**结论要说准确**:这不是「子图不支持 compare」。**只要执行路径上出现一个不等于该节点
effective role、也不等于 `graph_agent` 的角色名,侧跑就在解析处死掉。** 子图节点必然命中;
一个 AGENT 节点如果挂了用别的角色的 subagent,同样命中。

### 2.3 设计源怎么说(为什么修法是"换模型"而不是"换角色")

- `apps/studio/backend/app/models/model_compare.py:18-20`,`CompareCandidate` 的 docstring
  原文:

  > ``model_group_id`` names a model group from Settings; ``route`` is either the
  > sentinel ``"auto"`` (let the group's fallback order decide) or a specific
  > endpoint route id. No role/bundle — comparison means "same node, same input,
  > only the underlying model differs".

- MVP1 设计源 `docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:58`(F5 机制段)
  原文:

  > 每个候选 = 一个 model group + 一条 endpoint route("auto" 或具体 route)。
  > **候选只选模型,不做 role / bundle**(有意简化:对比 = 同节点同输入、只换底层模型)。

- 同文件 `:63`,PM 2026-07-01 原话:

  > 跑对比是在整图真的 run 的时候跑的……直接在这个节点加一个平行的 node,
  > **同样的输入和其他配置,除了 llm 不同**

三处口径一致:候选换的是**模型**,不是角色。所以候选 roles 文件里每个角色都必须
**还是它自己**(自己的参数、自己的提示词前缀),只是背后的模型换了。

### 2.4 为什么不能靠"把要用的角色列出来"

代码上做不到,而且这是结构性的、不是实现没写好:

- 子图是**装配期**另起一次 `compile_skill` 编出来的,根图的 `compiled.nodes` 里从来
  没有子图内层相位(这条已由 W2-5 的决议
  `.kiro/specs/decision-2026-08-15-predict-nested-phase-schema.md` 用同一事实立过案)。
- subagent 的角色是**运行期**才定的。

既然"这个节点会用到哪些角色"在写候选文件的时刻不可知,那么唯一可靠的答案就是
**覆盖整份真相**——不去猜要哪几个,而是保证要哪个都在。

---

## 3. 修在哪一层,为什么不是另一层

**修在 Studio backend `app/services/model_compare.py` 的 `build_candidate_roles`。**

判据是:坏掉的是"**这份候选 roles 文件该装什么**"这个判断,而这个判断的唯一 owner
就是这个函数。三个候选落点各自被排除的理由:

- **不修引擎(`packages/graph-agent`)**:引擎没有做错任何事。它拿到一个角色名,去
  roles 真相里找,找不到就报 `resource.no_available_route` —— 这正是 fail-fast 的正确
  行为。让引擎在找不到角色时"回退到某个别的角色"才是真缺陷(会把一次跑错模型的运行
  伪装成成功)。
- **不修 gateway(`packages/graph-agent-gateway`)**:gateway owns 角色物化与路由解析,
  它对着给它的那份 roles 数据算得完全正确。数据本身少了角色,不是 gateway 的问题。
- **不修 `_private_build_gateway_model_resolver`(`app/core/adapters/engine.py`)让它
  "在候选文件之外再兜一层活跃真相"**:那等于让一次侧跑同时看见两份 roles 真相,直接
  违反「底座一:config truth lives in exactly ONE place」。而且会造出最坏的一种结果——
  没被绑定的角色**静默用回原模型**,对比结果一半是候选一半是基准,而界面上看不出来。

---

## 4. 借了什么、拒了什么、为什么

参照对象(指名道姓,不写"业界一般"):

- **借:Kubernetes 的 `kubectl set image`。** 它改一个 Deployment 的镜像时,只替换
  `spec.template.spec.containers[*].image` 这一个字段,资源上其余所有东西——环境变量、
  资源配额、探针、标签——原样留在原地。取舍很清楚:**"换镜像"必须是一次窄替换**,
  因为你要比较的是新镜像的行为,任何被顺手改掉的第二个变量都会污染结论。本次照抄这条:
  只换 `model_groups` / `fallback_chain`(以及会把老模型带回来的 `bundle_id` /
  `source_profile_*` 引用),`intent`、`system_prompt_prefix`、`lint_requirements` 一律不动。

- **借:Nix / Bazel 的"整份环境替换"。** 它们不做"部分覆盖、其余继承宿主"的环境,而是
  一次性给出**完整**的依赖闭包,因为部分覆盖会让"没被覆盖的那部分从哪来"变成一个不可
  回答的问题。本次的候选 roles 文件正是这样一份闭包:worker 那个进程看到的 roles 真相
  就只有它,不存在"这个角色没定义所以去别处找"的第二条路。

- **拒:Kubernetes `kubectl set image` 的"只改被点名的那个容器"这一半。** 它能只点名
  一个容器,是因为**容器清单是显式的、可枚举的**。本仓这里的前提不成立——见 §2.4,
  一次执行会问哪些角色在写文件的时刻不可枚举。所以取它"窄替换字段"的那一半,不取它
  "窄选择对象"的那一半。

- **拒:给 `role_kind == "copilot"` 的角色开一个不换模型的口子。** 理由不是省事:
  `_filter_gateway_roles`(`app/core/adapters/gateway.py:900-914`)交给解析器的角色字段里
  **没有 `role_kind`**,解析器只按名字找角色。也就是说一个 skill 完全可以写
  `llm_role: copilot_deepseek_v4_flash`,那它就在执行路径上。按 kind 开口子会造出一类
  "看起来在真相里、实际会用回原模型"的角色,正是上面拒绝的那种静默半换。

- **拒:把 `load_roles_file(path) if path.exists() else RolesData()` 这个读法抽成公共
  helper。** 仓规是「相似逻辑第三次出现、且确认是同一业务含义时再抽」。目前同形状的读法
  有三处,但**其中一处业务含义不同**:`app/core/adapters/engine.py:275-291` 用
  `try/except Exception` 把**解析失败**也吞成空 `RolesData`,而
  `app/services/gateway_resolver.py:55` 与本次新增的这处都让格式错误保持致命。把三处
  合并会顺手改掉引擎适配器的错误行为——那是另一个议题,不夹带进这个 PR。

---

## 5. 验收判据

| # | 判据 | 落点 |
|---|---|---|
| a | 根图节点是 SUBGRAPH、内层相位声明另一个角色时:修复前 `build_candidate_roles` 产出的 RolesData 缺该角色、解析抛 `resource.no_available_route`;修复后该角色存在且解析成功 | `test_build_candidate_roles_swaps_the_model_for_every_role_in_the_truth`、`test_candidate_roles_file_resolves_the_inner_role_to_the_candidate` |
| b | AGENT 节点既有行为不回归:节点自己声明的角色(哪怕真相里没有)照样被绑上候选 | `test_build_candidate_roles_still_binds_an_agent_nodes_own_role` |
| c | 候选模型确实被用上——断言 `fallback_chain` 是候选那条 route,不是原角色的 | 上表 a / b 列出的四个测试**每一个**都断言解析结果 `== ["ark-lab:seed-lite"]`;fixture 里 `analyst` 自己的 route 是 `openai-direct:gpt-5`,两条 route 指向不同 endpoint,所以断言分得开「换了」与「没换」 |
| d | `node_effective_role` 与 `graph_agent` 两个键在修复后仍然存在 | `test_build_candidate_roles_materializes_an_executable_chain`(LOGIC 节点 → `graph_agent`)、`test_build_candidate_roles_still_binds_an_agent_nodes_own_role`(断言 `reviewer` 与 `graph_agent` 同时在) |
| e | 「只有模型不同」名副其实:角色自己的生成参数与系统提示词前缀不被候选覆盖 | `test_build_candidate_roles_keeps_each_role_params_and_prompt`(temperature 1.9 与 prefix 原样保留) |
| f | 真机因果闭环:用真实 lab skill + 真实 roles 真相,`analyst` / `fast` / `graph_agent` 三个角色全部解析到候选 route | 见 §6 |
| g | 全门禁绿 | ruff / mypy / 三套 pytest / pip-audit,见 PR 描述 |

## 6. 真机因果证据

用**本 worktree 的代码**、**真实的 lab skill**、**真实的 `llm_roles.yaml`**
(`C:\Users\test\AppData\Roaming\AgentStudio\llm\llm_roles.yaml`,内含 `fast` /
`analyst` / 两个 copilot 角色,**没有** `graph_agent`)走一遍写文件 + 解析:

```
code under test: ...\.worktrees\fix-compare-candidate-roles-cover-every-role\apps\studio\backend\app\services\model_compare.py
node: global_synthesis
effective role: graph_agent
roles defined in candidate file: ['analyst', 'copilot_claude_opus_4_8', 'copilot_deepseek_v4_flash', 'fast', 'graph_agent']
  analyst: OK -> ['ark-official:doubao-seed-2-0-lite-260428']
  fast: OK -> ['ark-official:doubao-seed-2-0-lite-260428']
  graph_agent: OK -> ['ark-official:doubao-seed-2-0-lite-260428']
```

修复前同一问法下 `analyst` 与 `fast` 都抛 `resource.no_available_route`(§2.1)。
探针停在解析这一步,不发 LLM 调用——**解析正是侧跑死掉的那一步**。

## 7. 顺带订正一句已经变假的注释

`app/services/model_compare.py` 的模块 docstring 开头,本次改动前写着「引擎无法在同一超步执行两个
图内节点(`WorkflowState.data` 是无 reducer 的 LastValue 通道),所以对比不注入并联节点」。
**前半句今天已经不成立**:`packages/graph-agent/src/graph_agent/core/state.py:323` 现在是
`data: Annotated[BusinessData, merge_business_channel]`,同文件 `:268` 的 reducer docstring
原文写着「the reason this channel stopped being a LastValue channel」(台账 W2-2 / #804)。

**但机制本身不改**:旁路单节点侧跑是设计源记录的 PM 批准形状
(`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:61`),理由是「不改 engine 执行、
永不写主黑板、per-candidate artifacts 各自分目录」——这三条与并联能不能跑无关。所以只订正
那句已经变假的依据,把 docstring 的立论换成设计源本身,并注明旧理由已失效及其出处。

## 8. 已知遗留(本 PR 不做,各记一句)

1. **这个失败戴着错误码 `[F-v3-runtime-state-mapping-failed]`,而它其实是角色解析失败;
   同一条错误还 `phase_id=None`,操作者看不出是哪个相位挂的。** 与台账 W2-9 / W2-12
   同一族(致命错误戴错码 / 丢分类信息),另立任务。
2. **压缩机制的 profile 缺口**:跑起来时 stderr 有两行
   `compaction: summarization model lacks profile.max_input_tokens; using fallback
   max_input_tokens=32000`。与本议题无关,记录在此以免被当成本次改动引入。
3. **代价本身没有被消掉,只是被明确接受**:一个作者有意挂便宜 `fast` 角色的相位,在对比
   里也会烧候选模型的 token。这是「只换模型」这条语义的直接后果(否则对比只比了一半),
   但它是真实取舍,不假装不存在。若将来要给某些角色开"不参与对比"的口子,那需要一个
   新的、显式的作者意图字段,不能靠 `role_kind` 这种为别的目的存在的分类去猜。
