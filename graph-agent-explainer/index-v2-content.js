Object.assign(SLIDES, {
  intro: {
    tag: '序 · 起点',
    title: '0.1 专业流程缺什么',
    text: `
      <p><b>专业 AI 产品最慢的地方，不是模型执行，而是真懂领域的人改不动生产流程。</b>故事、影视、内容资产、企业知识处理这些场景里，真正有价值的判断往往在领域专家脑子里；但一旦要变成稳定产品，就会落到工程排期、需求翻译、测试返工和运行环境上。</p>
      <p>coding agent 带火了一个重要引子：模型进入生产以后，需要被一个 harness 包住。代码领域的 harness 是 repo、终端、测试、文件系统、权限和 review；它让 agent loop 可以探索、修改、验证。但专业领域的问题不一样，很多步骤不应该让 agent 每次重新规划。</p>
      <p>graph-agent 的切入点，是把专业领域的<b>确定性工作流</b>变成可编写、可编译、可预演、可运行的工程对象。阶段顺序、依赖关系、输入输出、质量门槛和返工路径固定下来；语义判断、生成和审查这些最后一公里交给 Agent。</p>
      <div class="big-quote">强逻辑进图，最后一公里交给 Agent。
        <span class="src">这不是把所有规则塞进更长的 prompt，而是把流程控制从上下文里拿出来。</span></div>
      <figure class="diagram">
        <figcaption>同样是把模型放进系统，目标完全不同</figcaption>
        <svg viewBox="0 0 860 340" role="img" aria-label="agent loop harness vs deterministic workflow harness">
          <defs>
            <marker id="arr0" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#8bd5ff"/></marker>
          </defs>
          <rect width="860" height="340" fill="#09090b"/>
          <rect x="40" y="62" width="350" height="208" rx="16" fill="#15151a" stroke="#52525b"/>
          <text x="70" y="104" fill="#f4f4f5" font-size="20" font-weight="700">Agent-loop harness</text>
          <circle cx="156" cy="174" r="34" fill="#172554" stroke="#3266e8" stroke-width="2"/>
          <text x="133" y="180" fill="#dbeafe" font-size="15" font-weight="700">Agent</text>
          <path d="M156 130 C 260 110, 305 185, 228 236" fill="none" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr0)"/>
          <path d="M125 215 C 74 180, 83 116, 140 105" fill="none" stroke="#f59e0b" stroke-width="3" marker-end="url(#arr0)"/>
          <text x="70" y="292" fill="#cbd5e1" font-size="14">适合开放探索：路径由 agent 边做边判断。</text>

          <rect x="470" y="62" width="350" height="208" rx="16" fill="#052e2b" stroke="#2dd4bf"/>
          <text x="500" y="104" fill="#ccfbf1" font-size="20" font-weight="700">Workflow harness</text>
          <g fill="#111827" stroke="#3266e8" stroke-width="2">
            <rect x="502" y="142" width="82" height="52" rx="10"/>
            <rect x="622" y="142" width="82" height="52" rx="10"/>
            <rect x="742" y="142" width="82" height="52" rx="10"/>
          </g>
          <text x="525" y="174" fill="#dbeafe" font-size="13" font-weight="700">Phase</text>
          <text x="640" y="174" fill="#dbeafe" font-size="13" font-weight="700">Agent</text>
          <text x="765" y="174" fill="#dbeafe" font-size="13" font-weight="700">Gate</text>
          <line x1="588" y1="168" x2="616" y2="168" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr0)"/>
          <line x1="708" y1="168" x2="736" y2="168" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr0)"/>
          <text x="500" y="292" fill="#cbd5e1" font-size="14">适合专业生产：路径确定，局部节点使用智能。</text>
        </svg>
      </figure>
    `
  },

  handoff: {
    tag: '序 · 起点',
    title: '0.2 领域知识到产品代码的磨损',
    text: `
      <p>复杂专业流程最痛的地方，是懂领域的人和能交付产品级代码的人往往不是同一个人。领域专家能说清楚“这个事件该不该拆”“这个镜头是否破坏连续性”“这个设定能不能进入下游”，甚至能 vibe coding 出 demo；但 demo 离稳定、可批量、可观测、可恢复的产品流程还差一层工程底座。</p>
      <p>如果全交给工程师，工程师可以写出更可维护的系统，却很难凭空补齐领域判断。于是协作链条变成：领域专家讲流程，工程师翻译成代码，再拿结果回去确认“是不是这个意思”。每一轮沟通都在消耗上下文，每一次返工都拉长反馈周期。</p>
      <div class="big-quote">领域专家 → 工程师翻译 → 回头验证，是复杂专业 workflow 最常见、也最昂贵的隐形成本。
        <span class="src">graph-agent 要缩短的，正是这条链。</span></div>
      <p>更好的方式，是让流程本身成为双方共享的源码。领域专家直接修改阶段、规则和验收标准；工程师维护运行时、工具、安全边界和集成接口；AI 也可以参与生成和修正流程，但必须经过 compile 和 predict 的检查。</p>
      <figure class="diagram">
        <figcaption>从跨职能翻译链，变成本地短反馈环</figcaption>
        <svg viewBox="0 0 860 330" role="img" aria-label="domain expert workflow feedback loop">
          <defs><marker id="arr1" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#2dd4bf"/></marker></defs>
          <rect width="860" height="330" fill="#09090b"/>
          <text x="50" y="48" fill="#f4f4f5" font-size="18" font-weight="700">旧链路：慢在翻译和验证</text>
          <rect x="58" y="80" width="146" height="58" rx="10" fill="#27272a" stroke="#52525b"/><text x="84" y="116" fill="#e4e4e7" font-size="14">领域专家</text>
          <line x1="212" y1="109" x2="276" y2="109" stroke="#f59e0b" stroke-width="3" marker-end="url(#arr1)"/>
          <rect x="288" y="80" width="146" height="58" rx="10" fill="#3b2f12" stroke="#f59e0b"/><text x="314" y="116" fill="#fde68a" font-size="14">需求翻译</text>
          <line x1="442" y1="109" x2="506" y2="109" stroke="#f59e0b" stroke-width="3" marker-end="url(#arr1)"/>
          <rect x="518" y="80" width="146" height="58" rx="10" fill="#27272a" stroke="#52525b"/><text x="544" y="116" fill="#e4e4e7" font-size="14">工程实现</text>
          <path d="M590 148 C 500 212, 250 212, 130 148" fill="none" stroke="#ef4444" stroke-width="3" marker-end="url(#arr1)"/>
          <text x="260" y="238" fill="#fca5a5" font-size="14">回头验证领域判断是否被正确表达</text>
          <text x="50" y="286" fill="#f4f4f5" font-size="18" font-weight="700">新循环：写流程 → 编译 → 预演 → 观察 → 修正 → 运行</text>
        </svg>
      </figure>
    `
  },

  thesis: {
    tag: '序 · 起点',
    title: '0.3 两条价值主线',
    text: `
      <p>所以这页要讲的不是“我们也能搭 agent loop”。agent loop 已经有很多成熟产品和开源框架，单独把图里的某个 LLM 调用换成 agent loop，也不是 graph-agent 最大的亮点。</p>
      <p>graph-agent 的核心价值有两条。第一，<b>专业领域的人开发更快</b>：workflow 变成 source code 后，懂领域的人可以用本地短循环直接改流程，而不是等待漫长的需求翻译。第二，<b>领域知识让结果更好</b>：知识不只放进 prompt，而是进入 gate、validator、schema 和 review phase，成为执行控制的一部分。</p>
      <div class="big-quote">Graph-Agent = 专业 workflow 的 <b>Compiler + Runtime</b>。
        <span class="src">用文档表达流程，用编译器检查结构，用运行时执行图，用 trace 和 lineage 留下证据链。</span></div>
      <p>后面的章节都围绕这两件事展开：为什么 workflow 应该像源码，compile / predict / run 如何压短反馈，Local Edit == Cloud Run 为什么重要，bounded agent loop 如何服务关键节点，以及 Knowledge as Control 如何把领域知识变成质量系统。</p>
    `
  },

  source: {
    tag: '第 1 部分 · Workflow as Source Code',
    title: '1.1 流程源码',
    text: `
      <p><b>Workflow as Source Code</b> 的意思不是把配置文件写得更复杂，而是把一条专业生产链写成可检查、可运行、可追踪的工程对象。<code>GRAPH.md</code> 描述阶段和依赖，<code>SKILL.md</code> 描述阶段目标、输入输出、工具、参考资料和验收标准。</p>
      <p>以故事事件抽取为例，一条流程可能是 <code>setup → aggregate → review → settings</code>。这不是模型自由发挥的聊天顺序，而是领域生产的工序：先准备段落，再聚合事件，再审查时序和地点，最后提炼设定给下游使用。</p>
      <p>当流程成为源码，它就能被版本管理、review、diff、lint、compile、predict 和 run。更关键的是，它让领域专家、工程师和 AI 共享同一个表达对象。</p>
      <div class="pcards cols-3">
        <div class="pcard"><div class="pc-ico">AUTHOR</div><div class="pc-h">领域作者能读</div><div class="pc-t">阶段目标、依赖和验收标准显式写在文档里，不藏在 Python 控制流。</div></div>
        <div class="pcard"><div class="pc-ico">CHECK</div><div class="pc-h">系统能检查</div><div class="pc-t">拓扑、契约、引用、工具和输出形状可以在运行前被校验。</div></div>
        <div class="pcard"><div class="pc-ico">ITERATE</div><div class="pc-h">AI 能迭代</div><div class="pc-t">模型可以生成或修改 workflow，再通过编译和预演暴露问题。</div></div>
      </div>
    `
  },

  authoring: {
    tag: '第 1 部分 · Workflow as Source Code',
    title: '1.2 作者与机器的共同语言',
    text: `
      <p>专业 workflow 的作者不应该只剩工程师。影视策划、小说编辑、知识库负责人、研究员、PM、标注团队负责人，都可能比工程师更清楚某一步应该如何判断。</p>
      <p>graph-agent 给这些人的是一种工程化表达方式：不是让他们从头学习框架 API，而是把阶段、依赖、输入输出、工具、参考资料和验收标准写成结构化文档。文档可以被人读，也可以被机器编译。</p>
      <p>工程师仍然负责系统边界：运行时、模型网关、权限、持久化、部署和 SDK。领域逻辑留在 skill 目录里，框架层保持稳定。这样“懂领域”和“能运行”之间不再隔着一条长翻译链。</p>
      <div class="lesson-alert"><b>关键变化:</b>领域知识不再只通过会议和需求文档传递，而是直接进入可执行 workflow source。</div>
    `
  },

  compilerMental: {
    tag: '第 1 部分 · Workflow as Source Code',
    title: '1.3 不是配置，是可编译对象',
    text: `
      <p>如果只把 <code>GRAPH.md</code> / <code>SKILL.md</code> 看成配置，就会低估它。配置通常只是给程序填参数；workflow source 描述的是一套会被解析、校验、装配和执行的结构。</p>
      <p>编译器心智带来的第一件事，是错误提前暴露。依赖成环、输出字段不匹配、引用的工具不存在、子图目标找不到，这些问题不应该等长流程跑到一半才发现。</p>
      <p>第二件事，是文档、画布和运行记录可以同源。Studio 不是额外画一张图，而是把同一份 workflow source 展示成可读的图、属性面板和 trace。</p>
      <figure class="diagram">
        <figcaption>同一份 workflow 的三种视图</figcaption>
        <svg viewBox="0 0 860 300" role="img" aria-label="workflow source graph trace">
          <defs><marker id="arr2" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#8bd5ff"/></marker></defs>
          <rect width="860" height="300" fill="#09090b"/>
          <rect x="58" y="82" width="190" height="120" rx="14" fill="#111827" stroke="#3266e8"/><text x="98" y="130" fill="#dbeafe" font-size="18" font-weight="700">文档视图</text><text x="93" y="162" fill="#bfdbfe" font-size="14">GRAPH / SKILL</text>
          <line x1="260" y1="142" x2="344" y2="142" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr2)"/>
          <rect x="360" y="82" width="190" height="120" rx="14" fill="#052e2b" stroke="#2dd4bf"/><text x="408" y="130" fill="#ccfbf1" font-size="18" font-weight="700">图视图</text><text x="398" y="162" fill="#99f6e4" font-size="14">节点 / 边 / 契约</text>
          <line x1="562" y1="142" x2="646" y2="142" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr2)"/>
          <rect x="662" y="82" width="190" height="120" rx="14" fill="#27272a" stroke="#52525b"/><text x="708" y="130" fill="#e4e4e7" font-size="18" font-weight="700">运行视图</text><text x="706" y="162" fill="#cbd5e1" font-size="14">trace / lineage</text>
          <text x="58" y="250" fill="#cbd5e1" font-size="16">三种视图对应同一份源码，所以调试、审查和运行不会各说各话。</text>
        </svg>
      </figure>
    `
  },

  compile: {
    tag: '第 2 部分 · Compiler + Runtime',
    title: '2.1 compile / assemble',
    text: `
      <p><b>Compiler + Runtime</b> 的第一步是 compile。<code>compile_skill</code> 不调用模型，它做的是静态检查：语法是否正确，字段是否符合契约，依赖是否能成立，引用的 phase、tool、reference、subgraph 是否存在。</p>
      <p>第二步是 assemble。<code>assemble_graph</code> 把 phase 装配成确定性的状态图。文档里的 <code>depends_on</code> 变成边，Agent / Logic / Subgraph 变成不同类型的节点。</p>
      <p>下面保留原来的 Studio 演示：左侧是 workflow 文档，右侧是编译出来的图。它要表达的重点不是画布效果，而是画布上的节点和边都有源码依据。</p>
      <div class="studio-host" data-demo="demo-compile"></div>
      <div class="lesson-alert"><b>编译器的价值:</b>把结构错误挡在运行前，让专业 workflow 可以被稳定迭代。</div>
    `
  },

  predict: {
    tag: '第 2 部分 · Compiler + Runtime',
    title: '2.2 predict 预演',
    text: `
      <p><code>predict_skill</code> 是开发速度的关键。它不是随便 mock 一个结果，而是沿同一张编译图预演路径：哪些节点会跑，输入输出是什么形状，依赖如何传播，哪里可能断。</p>
      <p>这件事的重点不是节省一次调用，而是缩短反馈周期。复杂 workflow 最怕的是改完流程后要等整条链跑完，才知道结构写错、字段不匹配或下游路径不成立。</p>
      <p>当 predict 和真实 run 面对同一张图，作者就可以用很短的循环工作：写流程 → 编译 → 预演 → 观察 → 修正 → 运行。反馈越短，领域专家越敢去表达复杂分支、嵌套子图和批量迭代。</p>
      <figure class="diagram">
        <figcaption>predict 把结构反馈提前到本地</figcaption>
        <svg viewBox="0 0 860 270" role="img" aria-label="predict feedback loop">
          <defs><marker id="arr3" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#2dd4bf"/></marker></defs>
          <rect width="860" height="270" fill="#09090b"/>
          <g fill="#111827" stroke="#3266e8">
            <rect x="50" y="96" width="112" height="58" rx="12"/><rect x="208" y="96" width="112" height="58" rx="12"/><rect x="366" y="96" width="112" height="58" rx="12"/><rect x="524" y="96" width="112" height="58" rx="12"/><rect x="682" y="96" width="112" height="58" rx="12"/>
          </g>
          <g fill="#dbeafe" font-size="14" font-weight="700"><text x="80" y="132">写流程</text><text x="240" y="132">编译</text><text x="398" y="132">预演</text><text x="556" y="132">观察</text><text x="714" y="132">修正</text></g>
          <g stroke="#2dd4bf" stroke-width="3" marker-end="url(#arr3)"><line x1="170" y1="125" x2="200" y2="125"/><line x1="328" y1="125" x2="358" y2="125"/><line x1="486" y1="125" x2="516" y2="125"/><line x1="644" y1="125" x2="674" y2="125"/></g>
          <path d="M740 166 C 658 226, 160 226, 106 166" fill="none" stroke="#f59e0b" stroke-width="3" marker-end="url(#arr3)"/>
          <text x="50" y="224" fill="#cbd5e1" font-size="15">这条短循环，是专业领域的人开发更快的直接原因。</text>
        </svg>
      </figure>
    `
  },

  run: {
    tag: '第 2 部分 · Compiler + Runtime',
    title: '2.3 run 与 trace',
    text: `
      <p><code>run_skill</code> 是真实运行入口。它沿同一张编译图推进，根据依赖关系计算执行顺序；没有依赖冲突的节点可以并行，有依赖的节点必须等待上游完成。</p>
      <p>运行时不是黑盒。每个阶段开始、工具调用、节点完成、输出写入、图完成，都会成为结构化 trace 事件。trace 让作者能回看过程：哪一步用了什么输入，为什么下游结果变成这样。</p>
      <p>下面保留原来的线性图和 fanout 图演示。它要说明：编排不是藏在脚本里的执行顺序，而是由图的依赖结构推导出来。</p>
      <div class="studio-host" data-demo="demo-run"></div>
      <div class="lesson-alert"><b>运行时的价值:</b>让 workflow 不只是跑出结果，而是留下可解释、可追踪、可恢复的执行证据。</div>
    `
  },

  localLoop: {
    tag: '第 3 部分 · Local Edit == Cloud Run',
    title: '3.1 本地短循环',
    text: `
      <p><b>Local Edit == Cloud Run</b> 的第一层价值，是让领域作者可以在本地快速修改确定性工作流。改一个阶段、加一个 gate、调整一个输出字段，不需要先进入长沟通链，而是可以直接 compile、predict、观察路径。</p>
      <p>这不是让所有领域专家都变成工程师。它真正提供的是一种能表达复杂流程的工程界面：领域经验仍然来自人，但表达结果可以被系统检查、被 AI 读取、被云端运行。</p>
      <p>这也是“专业领域的人开发更快”的核心机制。速度提升来自反馈变短、沟通磨损变少、错误定位更清楚，而不是跳过工程质量。</p>
      <div class="big-quote">开发速度的提升，不是来自少做工程，而是减少“领域知识 → 需求 → 代码 → 再验证”的翻译损耗。
        <span class="src">懂领域的人能直接塑造 workflow，工程师维护可运行的底座。</span></div>
    `
  },

  cloudSameGraph: {
    tag: '第 3 部分 · Local Edit == Cloud Run',
    title: '3.2 云端同图运行',
    text: `
      <p>第二层价值，是本地预演和云端运行面对同一张图。同一份 <code>GRAPH.md</code> / <code>SKILL.md</code>，本地用于编译和预演，云端用于真实运行和批量处理，中间没有另一套临时逻辑。</p>
      <p>很多 AI demo 在本地能跑，一到生产就要重新接模型、存储、并发、日志和错误处理。graph-agent 把这些通用运行时职责收口，让 workflow source 成为本地和云端共同依赖的资产。</p>
      <p>对领域作者来说，这意味着本地看到的路径、节点和契约不是玩具版本。今天在本地改动并通过预演的结构，明天可以进入云端批量运行和追踪。</p>
      <figure class="diagram">
        <figcaption>同一张图：本地预演，云端运行</figcaption>
        <svg viewBox="0 0 860 330" role="img" aria-label="local edit cloud run same graph">
          <defs><marker id="arr4" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#8bd5ff"/></marker></defs>
          <rect width="860" height="330" fill="#09090b"/>
          <rect x="56" y="78" width="210" height="150" rx="16" fill="#111827" stroke="#3266e8"/><text x="104" y="120" fill="#dbeafe" font-size="18" font-weight="700">本地编辑</text><text x="86" y="158" fill="#bfdbfe" font-size="14">compile / predict</text><text x="86" y="190" fill="#bfdbfe" font-size="14">快速观察结构</text>
          <line x1="280" y1="153" x2="372" y2="153" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr4)"/>
          <rect x="388" y="64" width="196" height="178" rx="18" fill="#052e2b" stroke="#2dd4bf"/><text x="432" y="112" fill="#ccfbf1" font-size="18" font-weight="700">同一张编译图</text><circle cx="448" cy="168" r="20" fill="#3266e8"/><circle cx="510" cy="168" r="20" fill="#2dd4bf"/><circle cx="486" cy="210" r="20" fill="#f59e0b"/><line x1="468" y1="168" x2="490" y2="168" stroke="#fff" stroke-width="2"/><line x1="498" y1="185" x2="492" y2="194" stroke="#fff" stroke-width="2"/>
          <line x1="600" y1="153" x2="692" y2="153" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr4)"/>
          <rect x="708" y="78" width="154" height="150" rx="16" fill="#3b2f12" stroke="#f59e0b"/><text x="750" y="120" fill="#fef3c7" font-size="18" font-weight="700">云端运行</text><text x="734" y="158" fill="#fde68a" font-size="14">run / trace</text><text x="734" y="190" fill="#fde68a" font-size="14">批量与存档</text>
          <text x="56" y="284" fill="#cbd5e1" font-size="16">本地打磨的是生产会运行的同一个结构，不是另一个临时替身。</text>
        </svg>
      </figure>
    `
  },

  aiWorkflowDev: {
    tag: '第 3 部分 · Local Edit == Cloud Run',
    title: '3.3 AI 参与开发 workflow',
    text: `
      <p>当 workflow 是机器可读、可写、可编译的源码，AI 就不只能写胶水脚本。它可以生成 <code>GRAPH.md</code> / <code>SKILL.md</code>，调用 compile 检查结构，再用 predict 预演路径。</p>
      <p>这件事的价值仍然落在开发效率上。AI 生成的 workflow 不必一次就正确，但它必须进入一个能自检、能定位、能迭代的环境。错误可以被归类为拓扑问题、契约问题、引用问题、输出形状问题或阶段逻辑问题。</p>
      <p>领域专家也因此能和 AI 一起工作：专家给判断，AI 起草结构，系统给编译反馈，再一起修正。流程开发从“写完一坨脚本再试”变成可控的迭代。</p>
      <div class="lesson-alert alert-green"><b>关键不是让 AI 替代作者，</b>而是让作者和 AI 都围绕同一份可检查的 workflow source 工作。</div>
    `
  },

  bounded: {
    tag: '第 4 部分 · Bounded Autonomy',
    title: '4.1 固定强逻辑，放开关键节点',
    text: `
      <p><b>Bounded Autonomy</b> 在这里不是主卖点，而是执行机制。全局流程应该确定：哪些阶段必须跑，谁依赖谁，失败后走哪里，产物如何验收。局部节点可以智能：需要语义判断、工具调用、审查或生成时，再让 agent loop 处理。</p>
      <p>换句话说，graph 里的 LLM 节点升级成 bounded agent loop，可以比单次 LLM 调用拿到更高质量的结果。原因不是 agent 神秘地更聪明，而是它可以在一个清晰目标内读取资料、调用工具、修正中间结果，最后通过 <code>finish_task</code> 提交。</p>
      <p>同时，loop 被图节点包住，不会把整条流程的不确定性放大。全局路径、输入输出、重试边界和验收标准仍然由 workflow 控制。</p>
      <figure class="diagram">
        <figcaption>单次 LLM 调用 vs bounded agent loop</figcaption>
        <svg viewBox="0 0 860 330" role="img" aria-label="single llm call versus bounded agent loop">
          <defs><marker id="arr5" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#8bd5ff"/></marker></defs>
          <rect width="860" height="330" fill="#09090b"/>
          <rect x="52" y="74" width="300" height="168" rx="16" fill="#181114" stroke="#7f2d16"/>
          <text x="82" y="114" fill="#fed7aa" font-size="19" font-weight="700">单次 LLM 调用</text>
          <rect x="92" y="148" width="180" height="56" rx="12" fill="#27272a" stroke="#52525b"/><text x="126" y="183" fill="#e4e4e7" font-size="14">prompt → output</text>
          <text x="82" y="270" fill="#fecaca" font-size="14">适合简单问题，不适合反复核查和修正。</text>
          <rect x="440" y="50" width="360" height="220" rx="18" fill="#111827" stroke="#3266e8"/>
          <text x="470" y="92" fill="#dbeafe" font-size="19" font-weight="700">bounded agent loop</text>
          <rect x="486" y="124" width="82" height="44" rx="10" fill="#052e2b" stroke="#2dd4bf"/><text x="508" y="152" fill="#ccfbf1" font-size="13">Plan</text>
          <line x1="572" y1="146" x2="612" y2="146" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr5)"/>
          <rect x="620" y="124" width="82" height="44" rx="10" fill="#172554" stroke="#3266e8"/><text x="642" y="152" fill="#dbeafe" font-size="13">Act</text>
          <line x1="662" y1="170" x2="662" y2="198" stroke="#8bd5ff" stroke-width="3" marker-end="url(#arr5)"/>
          <rect x="620" y="206" width="82" height="44" rx="10" fill="#3b2f12" stroke="#f59e0b"/><text x="638" y="234" fill="#fef3c7" font-size="13">Review</text>
          <path d="M620 228 C 540 228, 522 190, 522 172" fill="none" stroke="#f59e0b" stroke-width="3" marker-end="url(#arr5)"/>
          <text x="470" y="294" fill="#cbd5e1" font-size="14">目标窄、上下文干净、结果可验收，质量才会稳定提高。</text>
        </svg>
      </figure>
    `
  },

  nodes: {
    tag: '第 4 部分 · Bounded Autonomy',
    title: '4.2 三类节点',
    text: `
      <p>bounded 的关键，是把不同性质的工作拆开。不是所有阶段都需要模型，也不是所有阶段都应该交给 agent 自己判断。</p>
      <ul>
        <li><b>Agent 节点</b>:需要语义判断、工具调用、资料读取、生成或审查的阶段。它有 role、goal、tools、references、max_iterations 和 validator。</li>
        <li><b>Logic 节点</b>:确定性计算。字段转换、分数聚合、格式组装、路由判断，能不用模型就不用模型。</li>
        <li><b>Subgraph 节点</b>:把一个完整 workflow 当成一步嵌进来，让复杂流程分层复用。</li>
      </ul>
      <p>这种拆分让系统保持一个清楚原则：强逻辑进图，语义工作进 agent 节点。下面保留原来的节点演示，点节点可以看右侧真实属性。</p>
      <div class="studio-host" data-demo="demo-nodes"></div>
    `
  },

  subgraph: {
    tag: '第 4 部分 · Bounded Autonomy',
    title: '4.3 子图与迭代',
    text: `
      <p>复杂专业流程一定会长大。故事生产会从事件抽取进入角色状态、空间连续性、镜头拆解、资产生成和审查；企业流程会从资料读取进入分类、核查、审批、回写和归档。如果所有东西都摊在一张图上，作者会看不懂，系统也难复用。</p>
      <p>Subgraph 的作用，是让一个节点指向另一个完整 skill。这样上层作者看到的是“事件抽取”或“镜头生成”，下层仍然保留可编译、可预演、可追踪的内部结构。</p>
      <p>批量迭代也是同理。对每个片段、每个镜头、每个资产跑类似流程，应该用声明式 batch / parallel map 表达，而不是把并发控制和业务判断混在一起。</p>
      <div class="studio-host" data-demo="demo-subgraph"></div>
      <div class="lesson-alert"><b>子图 + 迭代的意义:</b> workflow 可以分层、复用、批量、并行，但作者面对的仍然是文档和图。</div>
    `
  },

  knowledge: {
    tag: '第 5 部分 · Knowledge as Control',
    title: '5.1 领域知识不是背景材料',
    text: `
      <p><b>Knowledge as Control</b> 要讲清楚一件事：领域知识不是给模型“参考一下”的背景材料，而是决定结果质量的控制面。</p>
      <p>在专业流程里，知识包括硬规则、分类体系、审查标准、案例、风格偏好和专家修正。只把它们塞进上下文，会遇到两个问题：上下文变长后注意力被稀释；规则之间没有执行位置，模型可以遵守，也可能忽略。</p>
      <p>graph-agent 更适合的做法，是先声明每个节点需要什么知识，再把知识接入计划审查、产物验收和返工路径。知识不只参与生成，更参与控制。</p>
      <div class="lesson-alert"><b>一句话:</b>领域知识让结果更好，不是因为 prompt 更长，而是因为知识进入了 workflow 的决策点。</div>
    `
  },

  gates: {
    tag: '第 5 部分 · Knowledge as Control',
    title: '5.2 知识变门禁',
    text: `
      <p>如果知识只是 prompt 上下文，它没有强制力。graph-agent 的方向，是把知识变成 gate / validator / schema / review phase：计划要被审，输出要过契约，产物要按领域标准验收，不达标就带诊断返回局部节点。</p>
      <p>这就是用领域知识提升质量的核心。比如事件抽取的 review phase 不只是让模型再看一遍，而是明确要求它核查时间、地点、事件边界和歧义说明。输出 schema 规定必须提交哪些字段，validator 再检查结构是否能交给下游。</p>
      <p>下面保留原站的 agent loop 演示。它展示知识如何从规则推导出本步协议，再用协议审计划和产出。</p>
      <div class="studio-host" data-demo="demo-loop"></div>
      <div class="lesson-alert alert-green"><b>质量不是一次生成出来的，</b>而是在生成、审查、诊断、返工的闭环里逐步收敛。</div>
    `
  },

  quality: {
    tag: '第 5 部分 · Knowledge as Control',
    title: '5.3 从硬标准到审美标准',
    text: `
      <p>领域知识可以分两层。第一层是硬标准：格式、分类、镜头语法、结构完整性、输入输出契约。这些可以写成 schema、validator 或强规则，目的是挡住明显不合格的产物。</p>
      <p>第二层是审美和风格：节奏、构图偏好、叙事取舍、某个创作者的品味。这些很难完全写成代码谓词，但可以通过 rubric、examples、专家修正和评分回路进入 gate。</p>
      <table class="cmp">
        <thead><tr><th>层级</th><th class="them">解决的问题</th><th class="us">在 graph-agent 中的位置</th></tr></thead>
        <tbody>
          <tr><td>硬标准</td><td class="them">对不对、齐不齐、能不能交给下游</td><td class="us">schema、validator、review phase</td></tr>
          <tr><td>审美标准</td><td class="them">好不好、像不像、是否符合某种风格</td><td class="us">rubric、examples、专家反馈、gate 回灌</td></tr>
        </tbody>
      </table>
      <p>这也是 graph-agent 能服务高要求创作系统的原因。它不只编排步骤，还给质量判断留下进入流程的位置。</p>
    `
  },

  lineage: {
    tag: '第 6 部分 · Lineage 与系统位置',
    title: '6.1 Lineage / 局部重算',
    text: `
      <p>生产级专业 workflow 必须回答一个问题：这个产物从哪来？依赖了哪些输入？改动发生后，哪些结果需要重算？</p>
      <p><b>Lineage / 局部重算</b> 不是缓存技巧，而是持续迭代的生产语义。如果每个产物都只是孤立文件，修改就只能靠经验判断；如果每个产物都挂在依赖链上，系统就能知道谁受影响、谁仍然可信。</p>
      <p>比如改了 <code>score</code> 的输出契约，下游扩写和审查需要重新检查；上游 <code>segment</code> 不必推倒重来。复杂流程越长，这种局部重算越重要。</p>
      <div class="studio-host" data-demo="demo-invalid"></div>
    `
  },

  observability: {
    tag: '第 6 部分 · Lineage 与系统位置',
    title: '6.2 可观测性是信任基础',
    text: `
      <p>多步骤 AI 系统想进入生产，必须能回答：哪一步、哪个输入、哪个模型角色、哪个工具调用、哪个判断导致了这个结果。没有这些证据，结果再好也很难被组织稳定采用。</p>
      <p>graph-agent 的 trace 事件把过程变成证据链。它不只服务调试，也服务复盘、验收、审计和后续优化。尤其当 workflow 由人类和 AI 共同开发时，trace 是双方共同定位问题的位置。</p>
      <p>checkpoint 和状态记录则让长流程有恢复和分段处理的基础。长流程不应该因为一次中断完全重来，也不应该因为下游出错丢掉上游所有可信产物。</p>
      <div class="big-quote">可观测性让 workflow 从“跑出了一个结果”，升级成“留下了一条可以追问的过程”。</div>
    `
  },

  position: {
    tag: '第 6 部分 · Lineage 与系统位置',
    title: '6.3 引擎 / 网关 / 工作台',
    text: `
      <p>最后把系统位置收束清楚。graph-agent 是编排引擎，graph-agent-gateway 是模型接入层，Studio 是作者工作台。三者分开，系统才不会互相污染。</p>
      <div class="flywheel">
        <div class="fw-stage"><div class="fw-k">graph-agent · 引擎</div><div class="fw-h">Compiler + Runtime</div><div class="fw-t">把 workflow source 编译成图，负责调度、状态、trace、gate、lineage 和局部重算。</div></div>
        <div class="fw-arrow">▼ 通过模型接口调用 ▼</div>
        <div class="fw-stage"><div class="fw-k">gateway · 网关</div><div class="fw-h">模型接入层</div><div class="fw-t">把角色解析到 provider，收口协议差异、能力探测和错误分类，让 workflow 资产不绑死某一家模型。</div></div>
        <div class="fw-arrow">▲ 被它驱动 / 编辑 ▼</div>
        <div class="fw-stage bottom"><div class="fw-k">Studio · 工作台</div><div class="fw-h">人类与 AI 的作者界面</div><div class="fw-t">文档、画布、属性面板、trace 是同一份 workflow 的不同视图。作者在这里写流程、看图、预演、运行、修正。</div></div>
      </div>
      <p>在 SFM 这样的上层产品里，graph-agent 承担的是专业 workflow 底座：把故事、世界设定、角色、分镜、资产、审查和返工这些长链条变成可管理的流程。</p>
      <div class="lesson-alert"><b>最终价值:</b>不是炫耀一个更复杂的 agent，而是让懂领域的人更快开发确定性 workflow，并把领域知识变成能持续提升质量的控制系统。</div>
    `
  }
});
