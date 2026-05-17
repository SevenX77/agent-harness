# F1_T3_FILE_INPUT_SPEC (基于文件的测试输入与校验)

**版本**: 1.0
**日期**: 2026-05-06
**作者**: a2 Gemini (Skill Studio 产品设计顾问)
**状态**: 替代 `F1_T3_INPUT_PLAYGROUND_SPEC` (已过时)

---

## 1. Executive Summary (执行摘要)

在技能（Skill）的研发生命周期中，“输入数据”的质量直接决定了测试结果的可靠性。早期的 `InputPlayground` 设计倾向于通过动态表单让用户填入参数，虽然降低了上手门槛，但在处理复杂、嵌套且具有强 Schema 约束的生产级数据时显得力不从心。

**F1_T3_FILE_INPUT_SPEC** 确立了一个全新的原则：**测试输入即文件 (Test Input as Code)**。我们废弃了碎片化的表单填入，改为支持 JSON/YAML 文件的选择与加载。这一转变解决了三个核心问题：
1.  **数据复用**：PM 可以直接使用生产环境捕获的真实数据文件进行回归测试。
2.  **前置拦截**：在进行昂贵的 `Predict` (虚拟跑) 或 `Run` (真跑) 之前，强制进行 Schema 级别的数据校验。
3.  **开发闭环**：将输入文件纳入版本控制（Git），使“输入-技能-结果”构成完整的、可审计的研发链路。

本 Spec 定义了 Tauri 桌面端的文件选择交互、后端的 Pydantic 动态校验逻辑以及面向 PM 的精准错误反馈机制。

---

## 2. PM 用户故事 (User Stories)

*   **场景 1：极速回归验证 (Regression in a Snap)**
    *   *“PM 刚优化了一个内容摘要技能的 Prompt。她手里有一个包含 50 组复杂输入案例的 `regression_suite.json`。她直接点击 Input 区域的 'Select File'，选择该文件。Studio 几乎瞬间提示 'Validation Passed'，两个紫色和绿色的按钮 (Predict/Run) 亮起。她点击 Predict，几秒钟内就确认了新的 Prompt 没有破坏之前的数据处理逻辑。”*
*   **场景 2：精准的输入排错 (Precision Debugging)**
    *   *“PM 尝试运行一个新技能，并拖拽了一个旧版本的输入文件。UI 立即变红，提示：`Missing required field: 'target_language' at root`。PM 点击错误提示，Studio 自动定位到编辑器中对应文件的第 12 行。她补全了字段，保存文件，UI 自动检测并转绿，允许下一步操作。”*
*   **场景 3：多格式兼容性 (Format Agnostic)**
    *   *“PM 习惯用 YAML 编写易读的测试用例。她创建了一个 `test_case.yaml`，包含多行字符串和注释。她将其拖入 Studio，系统识别并解析了 YAML，将其与 `SKILL.md` 的 `io.inputs` 声明对齐，验证无误。这种比 JSON 更好维护的方式让她感到非常顺手。”*

---

## 3. 技术设计 (Technical Design)

### 3.1 前端：文件选择与管理 (Frontend UX)

我们将 `InputPlayground.tsx` 从“表单生成器”改造为“文件状态管理中心”。

*   **交互形式**：
    *   **Dropzone**：主区域支持拖拽 `.json` 或 `.yaml` 文件。
    *   **Native Dialog**：点击按钮调用 `@tauri-apps/api` 的 `dialog.open({ filters: [...] })`。这是 Tauri 桌面端的原生优势，可以直接获取本地完整文件路径。
*   **状态维护**：
    *   前端维护 `selected_input_file_path`。由于 Studio 后端运行在本地，**后端应通过路径直接读取文件**，而不是由前端读取全文再通过 API 发送，以避免大文件的性能瓶颈。
    *   增加一个 `ValidationStatus` 状态：`Idle | Validating | Success | Failed`。
*   **格式支持**：严格限定为 `.json`、`.yaml`、`.yml`。

### 3.2 后端：动态 Schema 校验流程 (Backend Validation)

后端不再接收 inline JSON，而是接收一个 `input_file_path` 参数 (利用 Tauri 前后端同机的优势, 后端直接按本地路径读文件, 不走 multipart form 这种常规 Web 上传方式; Studio 后端永远是 Tauri sidecar, 跟前端同机, 这是合理且最优的做法, 不要误以为是历史遗留)。

**校验管道 (Pipeline)**：
1.  **解析文件**：根据扩展名选择解析器。
    *   `.json` -> `json.load()`。
    *   `.yaml/.yml` -> `ruamel.yaml.safe_load()`。
2.  **获取契约**：调用 `graph_agent` SDK 解析当前编辑技能的 `SkillManifest`，提取其 `io.inputs` 列表。
3.  **反射 Pydantic Model**：
    *   利用 `pydantic.create_model` 动态创建一个临时模型。
    *   遍历 `io.inputs` 中的 `IoInput` 定义（如 `name="query", type="str"`），将其转换为 Pydantic 字段声明。
4.  **执行校验**：调用 `model.model_validate(file_data)`。
5.  **构建结果**：
    *   **Success**：返回 `{"valid": true}`。
    *   **Failed**：捕获 `ValidationError`，将其转换为结构化错误清单（见 3.3）。

### 3.3 错误反馈与精确定位 (Error Feedback)

当校验失败时，后端需返回足够丰富的信息，让前端实现 IDE 级的反馈。

*   **错误模型**：
    ```json
    {
      "valid": false,
      "errors": [
        {
          "loc": ["users", 0, "email"],
          "msg": "invalid email format",
          "type": "value_error",
          "input_value": "not-an-email",
          "line": 42,
          "col": 15
        }
      ]
    }
    ```
*   **UI 呈现**：
    *   **错误面板**：在 `InputPlayground` 底部列出错误清单。
    *   **点击定位**：点击错误条目，如果当前 Studio 正在预览该输入文件（例如在一个 Tab 中），Monaco 编辑器自动滚动并高亮第 42 行第 15 列。
    *   **置灰策略**：只要 `ValidationStatus !== Success`，Predict 和 Run 按钮必须强制置灰，并显示 Tooltip 说明原因。

### 3.4 流程衔接与门禁逻辑 (The "Gatekeeper" Logic)

为了保证研发的严谨性，Studio 将实施以下门禁（Gates）：

1.  **Gate 1: Compile** (技能本身正确)。如果 `compile_skill` 失败，不允许进入 Input 选择环节（UI 显示“请先修复技能语法错误”）。
2.  **Gate 2: Validate** (输入数据与技能契约匹配)。
    *   必须在 Gate 1 绿灯后开启。
    *   校验通过后，激活 **Predict** 按钮。
3.  **Gate 3: Predict** (逻辑流向正确)。
    *   *建议*：不强制要求 Predict 必须在 Run 之前跑。但在 UX 上，Predict 应该放在更显眼的位置，引导 PM 优先推演。
4.  **Gate 4: Run** (实测通过)。

**状态维护权**：
*   **Frontend 负责**维护按钮的视觉状态（置灰/高亮）。
*   **Backend 负责**每个 API 的独立完整性（即使前端绕过置灰调 Run，后端仍需在内部执行一次 Validate 保证引擎不崩溃）。

---

## 4. 实施任务拆解 (Task Breakdown for a1 codex)

### Task 1: 后端 `Validate` 接口开发 (4h) — ✅ 已完成 (2026-05-06, commit `dcd81ac`)
*   **目标**：在 `apps/studio/backend/app/routers/skills.py` 增加 `/api/skills/{id}/validate_input` POST 接口。
*   **涉及文件**：`backend/app/routers/skills.py`, `backend/app/services/validator.py` (新建), `backend/app/models/validation.py` (新建)。
*   **验收标准**：通过 API 传入一个本地路径，能正确识别 JSON/YAML 错误或类型不匹配。
*   **关键设计** (Gemini R2 audit 强调): **Validate 逻辑必须封装为独立 Service 模块** (`services/validator.py`), 不要直接写在 router 里。这样未来 `/api/skills/{id}/runs` 接口内部也可以复用这个 Service 做"前置校验防穿透" (对应 `POST_PLAN_C_FINAL_DECISIONS.md` §3.1 的 RESTful 无状态门禁原则——前端按钮门禁可被 curl 绕过, 后端 Run 内部必须再调一次 Validate)。
*   **实际交付**: a1 codex 实施的 `services/validator.py` 已经按 Service 模块封装, 暴露 `validate_skill_input_file()` 公共函数 + `ValidationHttpError` dataclass, /runs 内部可直接 import 复用。

### Task 2: `InputPlayground` 组件重构 (6h)
*   **目标**：移除旧的动态表单生成代码，引入 Tauri 文件选择器和 Dropzone。
*   **涉及文件**：`frontend/src/components/playground/InputPlayground.tsx`。
*   **验收标准**：UI 能够显示已选文件名，并在点击时弹出系统文件选择框。

### Task 3: 实时联动与校验反馈 (4h)
*   **目标**：实现“文件选择 -> 调接口校验 -> 按钮状态更新”的自动流。
*   **涉及文件**：`frontend/src/App.tsx`, `frontend/src/hooks/useInputValidation.ts` (新建)。
*   **验收标准**：选错文件类型或格式不对时，Run 按钮能即时置灰并显示原因。

### Task 4: 错误定位导航 (4h)
*   **目标**：在校验错误清单中集成“点击跳转”逻辑。
*   **涉及文件**：`frontend/src/components/playground/ValidationErrorPanel.tsx` (新建)。
*   **验收标准**：点击错误条目，Monaco 编辑器能正确定位到行。

---

## 5. 风险与未知 (Risks & Unknowns)

1.  **YAML 错误定位的准确性**：`ruamel.yaml` 在解析失败时提供行号。但在 Pydantic 校验成功 parse 但 `model_validate` 失败时，Pydantic 并不总是能回溯到 YAML 的原始物理行号。
    *   *缓解*：初期优先保证 JSON 的精准定位，YAML 错误如果拿不到行号，则高亮整个文件或对应路径的 Key。
2.  **大文件解析性能**：如果 PM 选了一个 100MB 的 JSON。
    *   *缓解*：在后端读取前增加文件大小限制（如默认 10MB），并在 UI 上给出提示。
3.  **Tauri 权限限制**：在某些 OS 环境下，Tauri 读取用户下载目录外的文件可能需要配置权限。
    *   *策略*：在 `capabilities` 中确保文件系统读取权限已正确开启。

---

*(End of Spec)*
