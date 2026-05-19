# Phase T3 跨平台 Build 与签名 — 需求规范 (Round 1)

## 1. Background

随着 Phase T1 (基础 Setup) 与 Phase T2 (Python Sidecar 集成) 的顺利落盘并 100% 验收通过，Skill Studio 的核心本地化能力已经就绪。然而，未签名的桌面应用在 macOS 和 Windows 上会被 Gatekeeper 和 SmartScreen 等安全机制严重拦截，甚至可能因为包含外部 Python 解释器而触发“病毒误报 P0”风险 (根据 `TAURI_KICKOFF_PLAN.md` §5)。

Phase T3 旨在彻底解决分发与安全信任问题，搭建跨三平台 (macOS, Windows, Linux) 的自动化构建矩阵，并引入严格的 Code Signing 与 macOS Notarization 机制。这是将产品交到真实终端用户手中的必经之路。

## 2. 业务目标

1.  **零拦截分发**：确保应用在三大平台上均不触发阻断级的安全警告（特别消除含有 Python 环境带来的病毒误报风险）。
2.  **全自动发版**：解放开发人员，实现基于 Git Tag 的全自动化构建、签名与 GitHub Release 上传流程。
3.  **多平台覆盖**：为不同的用户群体提供对应架构的安装包 (DMG, MSI, AppImage)。

## 3. EARS 需求

### 3.1 跨平台 Build Artifacts (Cross-platform Artifacts)

*   **Requirement 3.1.1: macOS Universal DMG**
    **When** 构建 macOS 目标时，**the build pipeline shall** 产出包含 x86_64 和 aarch64 (Apple Silicon) 支持的 Universal 二进制，并打包为 `.dmg` 格式分发。
*   **Requirement 3.1.2: Windows MSI Installer**
    **When** 构建 Windows 目标时，**the build pipeline shall** 产出 x64 架构支持的 `.msi` 安装包。
*   **Requirement 3.1.3: Linux AppImage**
    **When** 构建 Linux 目标时，**the build pipeline shall** 产出 x86_64 架构的便携式 `.AppImage` 文件。

### 3.2 macOS Code Signing & Notarization

*   **Requirement 3.2.1: Developer ID 签名**
    **The system shall** 使用 Apple Developer ID Application 证书对 `.app` 内所有的可执行文件（包含 Rust 主程序与 Vendored Python 环境）进行强签名。
*   **Requirement 3.2.2: Hardened Runtime & Entitlements**
    **The macOS build shall** 启用 Hardened Runtime 机制，并配置必要的 Entitlements (如 JIT 权限，若 Python 解释器需要) 以确保签名通过。
*   **Requirement 3.2.3: 公证与 Staple (Notarization & Stapling)**
    **After** 签名完成，**the pipeline shall** 使用 `notarytool` 将 `.app` 提交至 Apple 公证服务器，并在公证成功后将 Ticket staple 到对应的应用包上。

### 3.3 Windows Code Signing

*   **Requirement 3.3.1: MSI 与 EXE 签名**
    **The Windows pipeline shall** 使用 `signtool.exe` (或等效工具) 对编译出的主 `.exe` 及最终的 `.msi` 安装包进行数字签名。
*   **Requirement 3.3.2: 证书链验证**
    **The signature shall** 包含完整的信任链 (Root CA, Intermediate, Developer cert) 以及可信的时间戳 (Timestamping)。

### 3.4 Linux Signing (轻量方案)

*   **Requirement 3.4.1: GPG 签名 (可选)**
    **When** 构建 Linux AppImage 时，**the pipeline shall** (可选) 使用 GPG 私钥对 AppImage 产出 `.sig` 签名文件。

### 3.5 GitHub Actions CI Matrix

*   **Requirement 3.5.1: macOS Build Runner**
    **The CI shall** 使用 `macos-latest` (或指定版本如 `macos-14` arm64) 构建 macOS Universal 环境。
*   **Requirement 3.5.2: Windows Build Runner**
    **The CI shall** 使用 `windows-latest` 环境进行 Windows 构建。
*   **Requirement 3.5.3: Linux Build Runner**
    **The CI shall** 使用 `ubuntu-22.04` (或更高 LTS) 环境进行 Linux 构建。

### 3.6 Secret 管理机制

*   **Requirement 3.6.1: Apple Credentials 注入**
    **The macOS pipeline shall** 从 GitHub Secrets 中安全读取并注入 Developer ID 证书 (`.p12` 及其密码)、Apple ID、Team ID 和 App-Specific Password。
*   **Requirement 3.6.2: Windows Certificate 注入**
    **The Windows pipeline shall** 从 GitHub Secrets 中安全读取 `.pfx` 证书的 Base64 编码及导出密码。

### 3.7 Release 释放流程

*   **Requirement 3.7.1: Tag 驱动触发 (Tag-driven Trigger)**
    **When** 开发者 push 符合 `v*` 格式的 Git Tag 时，**the CI shall** 自动触发完整的三平台 Build & Sign 流水线。
*   **Requirement 3.7.2: Artifact 上传 (Upload to Release)**
    **After** 各平台构建与签名成功，**the pipeline shall** 将 `.dmg`, `.msi`, `.AppImage` 及相关签名文件统一上传挂载到对应的 GitHub Release 草稿或发布中。

### 3.8 Portable Python Sidecar 跨平台 Sign 处理

*   **Requirement 3.8.1: Vendored Python 级联签名 (Nested Signing)**
    **The macOS pipeline shall** 确保通过 `--deep` 或自定义脚本遍历签名策略，对 `vendor/` 目录下携带的所有 `.so`, `.dylib` 和可执行二进制进行强制签名，否则将无法通过 Notarization。

## 4. Out of Scope

1.  **自动更新 (Auto Updater)**: T3 不包含 Tauri 自动更新机制，仅聚焦首次发布包的生成。
2.  **应用商店分发 (App Store/Microsoft Store)**: 仅分发直接下载包，不涉及上架流程配置。

## 5. Open Questions
(见回复)
