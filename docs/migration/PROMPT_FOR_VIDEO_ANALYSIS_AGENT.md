# PROMPT — 把新 graph_agent 替换进 video_analysis 项目

> 全文复制给 video_analysis 项目的 AI 即可。

---

## 你要做的事

video_analysis 项目里 `src/core/graph_agent/` 是旧版 graph_agent 1.0.0
(2026-04-05,vendored,5.5 MB)。把它替换成上游 agent-harness 仓库
v1-reset 之后的新版。

新版 wheel:

```
路径:   /Users/sevenx/Documents/coding/agent-harness/dist/graph_agent_engine-0.1.0-py3-none-any.whl
SHA256: 9175a55cbc2e92293557e371ba5fd08c319e2ebd85915842eb8749df3a8f7b40
大小:   248 KB,105 个文件
```

业务代码用 `from src.core.graph_agent.xxx` 路径式 import,**保持 vendored
形式**(不要装 wheel 不要改 import),只把目录里的内容换成新版。

---

## 关键事实(不要忽略)

新版相对旧版有几处必须处理的差异:

1. **新版砍掉了 4 个文件**(项目实际依赖,**必须从旧版保留**):
   - `tools/understand_video.py` — `shot_tools.py` / `scene_tools.py`
     直接 import
   - `tools/generate_image.py`
   - `tools/generate_video.py`
   - `config/multimodal_config.py` — 上面 3 个文件依赖它
2. **新版 `tools/__init__.py` 只导 `synthesize_speech_tool`**——
   旧版的 `generate_image_tool` / `generate_video_tool` 不再 export,
   所以旧版的 `tools/__init__.py` 也必须保留
3. **新版 `config/__init__.py` 不再导 `*multimodal*` 系列符号**——
   旧版的 `config/__init__.py` 也必须保留
4. **新版完全删除了 `deerflow/` 子目录**(2.3 MB)——业务代码 0 处
   `import deerflow`,删除无影响,正好瘦身
5. **新版 loader 不识别 `<node id="...">` 包裹语法**——
   `src/skills/visual_gt_analysis/SKILL.md` 必须改写成新版 `phases:`
   列表语法

把这 5 件事处理好,替换就能成功。下面给具体步骤。

---

## 替换步骤

### Step 1:备份 + 创建工作分支

```bash
cd /Users/sevenx/Documents/coding/video_analysis
git checkout -b feat/upgrade-graph-agent

# 整目录备份(rollback 用,不进 git)
cp -R src/core/graph_agent src/core/graph_agent_bak_v1
echo "src/core/graph_agent_bak_v1/" >> .gitignore
```

### Step 2:把要保留的旧文件存到旁边

```bash
mkdir -p /tmp/preserve_legacy/tools /tmp/preserve_legacy/config

# 4 个新版砍掉的实现文件
cp src/core/graph_agent/tools/understand_video.py     /tmp/preserve_legacy/tools/
cp src/core/graph_agent/tools/generate_image.py       /tmp/preserve_legacy/tools/
cp src/core/graph_agent/tools/generate_video.py       /tmp/preserve_legacy/tools/
cp src/core/graph_agent/config/multimodal_config.py   /tmp/preserve_legacy/config/

# 2 个 __init__.py(导出多模态符号)
cp src/core/graph_agent/tools/__init__.py             /tmp/preserve_legacy/tools/
cp src/core/graph_agent/config/__init__.py            /tmp/preserve_legacy/config/

# providers.py 旧版(被多模态工具依赖,保留旧版接口)
cp src/core/graph_agent/tools/providers.py            /tmp/preserve_legacy/tools/
```

### Step 3:解压新 wheel

```bash
mkdir -p /tmp/new_engine
cd /tmp/new_engine
unzip /Users/sevenx/Documents/coding/agent-harness/dist/graph_agent_engine-0.1.0-py3-none-any.whl
ls graph_agent/   # 应该看到新版结构
cd /Users/sevenx/Documents/coding/video_analysis
```

### Step 4:用新版覆盖旧目录(rsync 模式)

```bash
# 先把旧目录里的 deerflow 和 tools/__pycache__ 清掉,避免残留
rm -rf src/core/graph_agent/deerflow
rm -rf src/core/graph_agent/__pycache__
find src/core/graph_agent -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 用新 wheel 完整替换 src/core/graph_agent 内容
rsync -a --delete \
      /tmp/new_engine/graph_agent/ \
      src/core/graph_agent/

# 项目不需要 wheel 自带的 examples 和 builtin skills,删掉
rm -rf src/core/graph_agent/examples
rm -rf src/core/graph_agent/skills/builtin
```

### Step 5:把保留的 6 个文件放回(覆盖新版的同名文件)

```bash
# 4 个文件:新版根本没有的,直接放进去
cp /tmp/preserve_legacy/tools/understand_video.py    src/core/graph_agent/tools/
cp /tmp/preserve_legacy/tools/generate_image.py      src/core/graph_agent/tools/
cp /tmp/preserve_legacy/tools/generate_video.py      src/core/graph_agent/tools/
cp /tmp/preserve_legacy/config/multimodal_config.py  src/core/graph_agent/config/

# 2 个文件:新版有同名但 export 缩水,用旧版覆盖以保留多模态导出
cp /tmp/preserve_legacy/tools/__init__.py            src/core/graph_agent/tools/
cp /tmp/preserve_legacy/config/__init__.py           src/core/graph_agent/config/

# providers.py:旧版接口被 understand_video 等依赖,用旧版覆盖
cp /tmp/preserve_legacy/tools/providers.py           src/core/graph_agent/tools/
```

### Step 6:改写 SKILL.md 去掉 `<node>` 包裹

把 `src/skills/visual_gt_analysis/SKILL.md` 从老语法:

```markdown
<node id="edl_prepare">
<phase_config>
name: edl_prepare
tier: fast
tools:
  - tools.edl.prepare_edl
  - tools.thumbnails.extract_thumbnails
</phase_config>
</node>

<node id="scene_recognition">
<phase_config>
name: scene_recognition
tier: analyst
tools:
  - tools.scene_tools.analyze_scene_structure
validator: validators.phase1.validate_scene_context
retry_target: scene_recognition
max_retries: 2
max_iterations: 12
</phase_config>
</node>

<node id="shot_analysis">
<phase_config>
name: shot_analysis
tier: fast
tools:
  - tools.shot_tools.analyze_all_shots
  - tools.project_io.write_final_outputs
</phase_config>
</node>
```

改成新版 frontmatter 里的 `phases:` 列表(完整可用版):

```markdown
---
schema_version: "2.0"
name: visual-gt-analysis
description: 当用户从桌面端上传视频并需要提取场景、角色、地点、道具和逐镜头描述时使用。
type: graph
context_mapping:
  project_name: "{input.project_name}"
  video_path: "{input.video_path}"
  service: "{input.service}"
  run_id: "{input.run_id}"
  run_dir: "{input.run_dir}"
  project_path: "{input.project_path}"
  max_concurrent_shots: "{input.max_concurrent_shots}"
io:
  inputs:
    - name: project_name
      type: str
      source: runtime
    - name: video_path
      type: str
      source: runtime
    - name: service
      type: str
      source: runtime
    - name: run_id
      type: str
      source: runtime
    - name: run_dir
      type: str
      source: runtime
    - name: project_path
      type: str
      source: runtime
    - name: max_concurrent_shots
      type: int
      source: runtime
phases:
  - name: edl_prepare
    mode: logic
    execute_steps:
      - tools.edl.prepare_edl
      - tools.thumbnails.extract_thumbnails

  - name: scene_recognition
    mode: llm
    llm_role: analyst
    max_iterations: 12
    max_nudges: 2
    agent_tools:
      - tools.scene_tools.analyze_scene_structure
    validator: validators.phase1.validate_scene_context
    max_retries: 2
    retry_target: scene_recognition

  - name: shot_analysis
    mode: logic
    execute_steps:
      - tools.shot_tools.analyze_all_shots
      - tools.project_io.write_final_outputs
---
```

字段映射规则:
- `<node id="X"><phase_config>` 包裹 → `phases:` 列表里的一项,直接去掉 `<node>` 标签和 `<phase_config>` 标签
- `tier: fast` 且没有 `<system_prompt>` → `mode: logic`,`tools` 字段改名为 `execute_steps`
- `tier: <角色>` 且**有** `<system_prompt>` → `mode: llm`,`tier` 改名为 `llm_role`,`tools` 改名为 `agent_tools`,如果该 phase 还有 prompt 内容,把 `<system_prompt>` / `<user_prompt>` 标签**保留在 frontmatter 之后**,与对应的 phase name 关联
- `validator` / `retry_target` / `max_retries` / `max_iterations` 字段名不变,直接搬过去

如果原 SKILL.md 里 `<node>` 块外面还有 `<system_prompt>` / `<user_prompt>`
之类的 XML 块,保留在 frontmatter 后面即可,不需要改。

### Step 7:装新版引擎依赖

新版引擎用了较新的 langchain/langgraph,版本要求严格(每个上界都不是装饰)。
在项目 venv 里装:

```bash
# 用项目自己的 venv;如果没有就 python3.11 -m venv .venv
source .venv/bin/activate

pip install \
    "langchain>=1.2.3,<1.2.11" \
    "langchain-core>=1.3.1,<1.4.0" \
    "langchain-anthropic>=1.3.4,<1.5.0" \
    "langchain-deepseek>=1.0.1,<1.1.0" \
    "langchain-openai>=1.1.7,<1.3.0" \
    "langgraph>=1.0.10,<1.1.0" \
    "langgraph-prebuilt>=1.0.6,<1.0.9" \
    "langgraph-checkpoint>=4.0.0,<5.0.0" \
    "langgraph-checkpoint-sqlite>=3.0.3,<4.0.0" \
    "pydantic>=2.12.5,<3.0.0" \
    "pyyaml>=6.0.3,<7.0.0" \
    "ruamel.yaml>=0.18.0,<0.19.0" \
    "httpx>=0.28.0,<0.29.0" \
    "anthropic>=0.96.0,<1.0.0" \
    "openai>=2.0.0,<3.0.0" \
    "markdownify>=1.2.2,<2.0.0" \
    "readabilipy>=0.3.0,<1.0.0" \
    "python-dotenv>=1.0.0,<2.0.0"
```

如果 pip 报 conflict,以这套版本为准——这是 graph_agent 严格 pin 的范围。

### Step 8:验证

```bash
# 1) 公共 API + 旧版多模态 API 都能 import
python -c "
import sys; sys.path.insert(0, 'src')
# 新版 33 个公共 API
from src.core.graph_agent import (
    run_skill, GraphAgentHarness, Phase, WorkflowState,
    ContextBridge, ModelResolver, IOManager, ContextResolver,
    Callback, LoggingCallback, MetricsCallback, TracingCallback,
    GraphAgentError, SkillLoadError, SkillCompilationError,
    AllProvidersFailedError, MaxRetriesExceededError,
    load_workflow_from_md, compile_skill,
)
# 保留下来的旧版多模态符号
from src.core.graph_agent.tools.understand_video import understand_video_tool
from src.core.graph_agent.config.multimodal_config import ResolvedMultimodalProvider
print('OK: imports clean')
"

# 2) 业务 SKILL.md 编译通过
python -c "
import sys; sys.path.insert(0, 'src')
from src.core.graph_agent import compile_skill
result = compile_skill('src/skills/visual_gt_analysis/SKILL.md')
print('compile OK:', result)
"

# 3) 跑测试套件
pytest test/ -v
```

三步全过 → 替换成功,可以提 PR。
任意一步失败 → 看 §Rollback,先恢复再排查。

---

## Rollback(60 秒)

替换过程中**任意一步爆炸**且短时间内修不好:

```bash
cd /Users/sevenx/Documents/coding/video_analysis

# 恢复 graph_agent 目录
rm -rf src/core/graph_agent
mv src/core/graph_agent_bak_v1 src/core/graph_agent

# 恢复 SKILL.md(如果改了)
git checkout src/skills/visual_gt_analysis/SKILL.md

# 恢复依赖
pip install -r requirements.txt --force-reinstall

# 删工作分支
git checkout main
git branch -D feat/upgrade-graph-agent
```

回到 1.0.0 状态,继续用旧版,无任何残留。

---

## 完成标准

- [ ] Step 1-7 顺序执行完毕
- [ ] Step 8 三个验证全部通过(pytest 0 失败)
- [ ] `du -sh src/core/graph_agent/` 升级前 5.5 MB → 升级后约 3 MB(deerflow 删了)
- [ ] 提一个 PR `feat/upgrade-graph-agent`,标题 `chore: upgrade vendored graph_agent to v1-reset (engine 0.1.0)`,body 里贴 `git diff --stat src/core/graph_agent/` 的输出
