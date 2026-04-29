# text-segmentation SKILL 版本归档

每个目录保留一个历史版本的 `SKILL.md`，用作 compiler test fixture + A/B 对比测试基线。

## 版本时间线

| 版本 | 来源 commit | 改动者 | 关键问题 / 改进 | 已知 review crash |
|------|-------------|--------|------------------|-------------------|
| `v0-main-baseline` | `8850bb6` (main, 2026-04-27) | 原始 SKILL 作者 | 137+ 行 system prompt + user prompt 4 步骤完整重写 | ✅ 撞 GraphRecursionError 30 |
| `v1-codex-attempt` | `ab4018a` (feat/text-segmentation-prompt-rewrite, 2026-04-27) | Codex (a1) | 加退出契约 + 瘦身 system prompt 至 ~22 行 | ❌ review 仍 crash（指令"对每个段落"诱导遍历模式 + user_prompt 维度依然重写） |
| `v2-gemini-rewrite-r1` | `chore/text-segmentation-skill-versions` (2026-04-28) | Gemini (a2) | 渐进披露 (references/segmentation-guide.md) + 退出契约前置 + 移除"对每一个"诱导词 + user_prompt 不重述 + 每个 phase 加 `references:` 字段挂载 read_file | （待验证） |

## 归档结构

```
versions/
├── README.md                            ← 你正在读
├── v0-main-baseline/SKILL.md            ← 268 行
├── v1-codex-attempt/SKILL.md            ← 180 行
└── v2-gemini-rewrite-r1/
    ├── SKILL.md                         ← 128 行（含 references: 字段）
    └── references/segmentation-guide.md ← 50 行（A/B/C 类详细鉴别案例）
```

## 测试方法（控制变量）

由于 `tool-path-escape` validator 拒绝 SKILL 引用 base_dir 之外的 script/，**版本归档目录里的 SKILL.md 不能直接被 loader 加载**。要跑某个版本的 smoke test：

### 方法 A：临时替换 active SKILL.md

```bash
# 备份当前 active
cp skills/text-segmentation/SKILL.md /tmp/active-skill-backup.md

# 替换为 v2
cp skills/text-segmentation/versions/v2-gemini-rewrite-r1/SKILL.md skills/text-segmentation/SKILL.md
cp -r skills/text-segmentation/versions/v2-gemini-rewrite-r1/references skills/text-segmentation/

# 跑 smoke
python -m graph_agent --skill skills/text-segmentation/SKILL.md \
  --inputs-file /tmp/e2e-smoke-1ch.json \
  --output /tmp/smoke-v2-sonnet --verbose

# 恢复
git checkout skills/text-segmentation/SKILL.md
rm -rf skills/text-segmentation/references
```

### 方法 B：CLI 直接指向 active 路径下临时 mirror（推荐 Codex 跑测试时用）

将 swap 步骤封装成一次性命令链，在每个版本测试完后立刻恢复，避免 working tree 污染。

## llm_role 切换（控制变量第二维：模型差异）

要在不同模型上跑同一 SKILL，**改 SKILL.md 里两个 llm phase 的 `llm_role:` 字段**：

| llm_role | 模型 | provider |
|----------|------|----------|
| `analyst` (默认) | CL46T fallback DS32R fallback GM31P | OneChats Anthropic / WaveSpeed / DeepSeek |
| `test_sonnet46_jk` | CL46T 单模型 | jiekou Anthropic 端点 |
| `test_dsv4` | DS32C 单模型 | DeepSeek 官方 |
| `test_opus47_ws` | CLO47T 单模型 | WaveSpeed |

`test_*` 角色不带 fallback——能精确观察该模型的固有行为，不被 fallback 链路掩盖。

## compiler test 用法（待 G1.5 A 类规则落地后）

A 类规则落地后，期望：

```bash
python -m graph_agent --skill skills/text-segmentation/versions/v0-main-baseline/SKILL.md --validate-only
# 期望: 报 W-PROMPT-DUPLICATION + W-FINISH-TASK-VISIBILITY (system+user 重复 4 步骤)

python -m graph_agent --skill skills/text-segmentation/versions/v2-gemini-rewrite-r1/SKILL.md --validate-only
# 期望: 全部 pass（如果 v2 设计是合格的）
```

注：当前 `versions/*/SKILL.md` 跑 `validate-only` 会撞 `F-tool-path-escape`，需先把 framework 加 `--base-dir-override` flag（A 类规则同期 PR）。

## 控制变量测试矩阵（用户方针 1）

| SKILL 版本 | LLM role | 预期结果 | 实际结果 |
|-----------|----------|----------|----------|
| v0 | test_sonnet46_jk | 撞 30 (基准) | 待跑 |
| v0 | test_dsv4 | ? | 待跑 |
| v2 | test_sonnet46_jk | finish_task 调用 | 待跑 |
| v2 | test_dsv4 | finish_task 调用 | 待跑 |
