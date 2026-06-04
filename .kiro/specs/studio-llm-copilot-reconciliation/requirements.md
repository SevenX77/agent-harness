# requirements.md — 大模型凭证、角色与 Copilot 交互心智对齐规范

## 1. 目标与背景

本规范旨在重新对齐并规范 Studio 平台在 **API Keys**（凭证管理）、**LLM Roles**（逻辑角色配置）以及 **Copilot**（应用交互层）三大模块中的测试流程、信息同步及持久化逻辑。
当前系统在实现上存在物理通道与逻辑层校验混淆、测试结果持久化不完整、以及 Copilot 专属 SDK 连通性校验未落实等问题。本 Spec 旨在拉齐开发心智，并指导后续的代码重构与收敛。

---

## 2. API Keys 页面：递进式连通性校验心智

API Keys 页面的核心定位是管理大模型的**物理硬体配置（Credentials）**。用户心智上，其连通性校验应当分为层层递进的两个步骤：

### 2.1 参数连通性验证（参数级达标 - Get Models / Test）
* **触发动作**：
  * **官方（Official）渠道**：点击 **"Test"**。
  * **第三方（Third-party）渠道**：点击 **"Get Models"**。
* **业务逻辑**：
  * 系统发起极简的模型列表拉取请求，验证 API Key 与 Base URL 的网络可达性。
  * **多方草稿同步**：拉取并比对 1. 全局已存模型列表、2. 从 API 实时拉取的模型列表、3. 远端 Draft 模型列表。
  * **合并机制**：
    * 如果 API 成功拉取到模型列表 -> 更新至本地全局。
    * 如果 API 拉取失败，但全局配置中缺失该模型 -> 采用远端 Draft 中的模型列表更新全局。
    * 如果本地全局已有模型配置，但缺失 Draft 里的高阶属性（能力集、输入输出上限等） -> 执行 diff 合并，将缺失部分补齐至全局。
* **UX 状态反馈**：
  * 只要接口成功返回 200，说明**参数能够连通**。输入框（API Key / Base URL）右侧应立即亮起**绿色小勾**（`CheckCircle2`）。
  * 此时，卡片右上角状态**依然保持为“未测试 (Untested)”**，不可直接宣告 Endpoint 测通。

### 2.2 端点及真实模型验证（端点级测通 - Endpoint Model Test）
* **触发动作**：
  * 针对**第三方渠道**，必须强制使用一个真实模型进行真机探测（Probe）。用户复制一个拉取到的模型名称，粘贴到 **"Endpoint test"** 输入框，点击 **"Test"**。
* **业务逻辑**：
  * 发起一次包含真实模型与对应协议（OpenAI/Anthropic compatible）的极简生成探测（Model Probe）。
* **UX 状态反馈**：
  * 一旦此步骤返回 200：
    1. **模型通过验证**：该特定模型的标签（Tag）亮起**绿色边框**，写入全局已验证（`verified`）。
    2. **Endpoint 级测通**：Provider Card 头部亮起绿色 **`connected`** 标签。
    3. **Roles 页面开通授权**：此 Provider 及其下属所有模型，正式在 LLM Roles 页面的 `Available Models`（可用模型）侧边栏中授权展示。

---

## 3. LLM Roles 页面：Graph Agent 逻辑角色的闭环测试

LLM Roles 页面仅服务于 **Graph Agent 逻辑角色** 的 fallback 与策略配置。

### 3.1 Copilot 角色的剥离
* **UX 约束**：
  * LLM Roles 页面中必须**彻底移除**关于 Copilot 角色（`category === "copilot"`）的所有 Accordion 手风琴折叠面板与管理界面。

### 3.2 角色测试结果的全局回写
* **触发动作**：
  * 点击 Role Card 右上角的 **"Test"**（角色链路即时验证）。
* **业务逻辑**：
  * 系统对该角色配置的 fallback 链中的每一个物理 route 发起单模型 probe 探测。
  * **全局写回**：测试的成功与失败结果，**必须立刻持久化回写至本地全局 `credentials.json`**（置为 `verified`）**并同步更新至本地 Draft 库 (`import_drafts.json`)**。
* **UX 状态反馈**：
  * 路线完全打通，且符合角色偏好设置（如 `thinking` 推理开启成功）-> 显示**绿色边框**。
  * 路线连通，但能力与角色意图发生降级（如要求 required thinking 但模型未支持）-> 显示**黄色边框**并在悬浮 Tooltip 给出具体警告（`Warning:`）。
  * 路线网络不通或认证失效 -> 显示**红色边框/背景**。

---

## 4. Copilot 专属页面：SDK 级工具调用验证

Copilot 专属页面聚焦于应用交互智能体的可用性验证。

### 4.1 固定内置角色与提供商编排
* **内置角色**：
  * 自动填充两个固定 Claude SDK 角色：`opus 4.7` 和 `deepseek v4 pro`。
  * 用户仅需对其 fallback 的 providers 物理渠道进行上下拖拽排序。
* **自定义角色**：
  * 用户可以新建自定义 Copilot 角色，但仅能选择具备 Claude SDK 调用合规协议（如 Anthropic 原生、DeepSeek/Ark 的兼容调用模式）的模型。

### 4.2 专属 SDK 工具调用探测 (SDK-Level Tool Call Test)
* **触发动作**：
  * 点击 Copilot Role Card 上的 **"Test"**。
* **业务逻辑**：
  * **测试方法有别**：这里不进行普通的极简文本探测，而是必须使用 **Claude SDK 专属的调用指令与协议格式**（合规 URL、Header 以及 Tool schemas），向大模型发送一段包含工具定义的真实对话请求。
  * **验证标准**：验证大模型是否能**成功识别工具并正常执行 Tool Calling（工具调用）**。
  * **高阶结果写入**：若测试成功，将这一极具价值的 **“Claude SDK 专属验证通过信息”** 回写持久化到本地全局凭证（credentials）与远端草稿（draft）中。这证明该通道具备最高阶的智能体控制能力（等价于 LLM Roles 的高级验证通过）。
