# Phase T3 跨平台 Build 与签名 — Design (Round 1 Outline)

> **Status**: DRAFT (Outline Only)

## §1 架构总览 (Architecture Overview)
*   **Workflow 流转**: Developer `git push origin v1.0.0` → GitHub Action 触发 → 解析 Tag 版本号 → 扇出 3 并发 Matrix Build → 各平台完成打包与签名 → Notarization (仅 macOS) → 并发汇总上传至 GitHub Release。
*   **跨平台输出契约**: macOS 产出 `SkillStudio-1.0.0-universal.dmg`；Windows 产出 `SkillStudio-1.0.0-x64.msi`；Linux 产出 `SkillStudio-1.0.0-x86_64.AppImage`。
*   **Sidecar 预备**: 构建执行前，复用 T2.1/T2.5 的环境配置脚本 `download_runtime.js` 准备好对应目标架构的 Portable Python 依赖集。

## §2 Build matrix 配置
*   定义核心构建矩阵：基于 `matrix.platform` 循环构建 (`macos-latest`, `windows-latest`, `ubuntu-22.04`)。
*   配置通用的前置 Node.js 和 Rust 缓存环境 (`actions/setup-node`, `Swatinem/rust-cache`)。
*   配置触发器：监听 `tags: ['v*']` 以及用于测试流水线的 `workflow_dispatch` 手动触发。
*   使用官方 `tauri-apps/tauri-action` 管理基础打包并映射发布目标。

## §3 macOS pipeline
*   **证书导入**: 使用社区可靠的 Action 导入 p12 证书并存入系统 Keychain。
*   **编译与 Universal 化**: 强制指定目标为 `universal-apple-darwin`，利用 Rust 交叉编译特性构建胖二进制。
*   **级联签名**: 执行自定义 bash 脚本遍历 `vendor/` 目录下所有 `dylib` 和 `python` 二进制先进行签名，再对整体 App 签名并施加 Hardened Runtime entitlements。
*   **Notarization**: 利用 App Store Connect API Key 与 `notarytool` 发起公证，轮询并 `staple` DMG 产物。

## §4 Windows pipeline
*   **证书挂载**: Base64 解码存储在 GitHub Secret 的 `.pfx` 到运行环境，注册对应变量。
*   **MSI 生成**: 执行 Tauri Build，生成默认的 Windows `.msi` 及内联的 WebView2 运行时安装配置。
*   **签名注入**: 调用 `signtool.exe`，应用 Timestamp 服务器 (`/tr http://timestamp.digicert.com`) 对产物进行双重签章确保可信度。

## §5 Linux pipeline
*   **环境依赖准备**: `sudo apt-get install` 装齐 GTK 和 WebKit 必备系统 dev 依赖。
*   **构建 AppImage**: 默认直接通过 Tauri 的 bundler 流水线出包。
*   **GPG 签名 (Optional)**: 导入私钥挂载 GPG Keyring，执行分离签名生成 `.AppImage.sig` 文件，并与本体一起上传。

## §6 Secret 管理与 OIDC
*   统一定义所需的 GitHub Repo Secrets 清单，防止硬编码泄露。
*   对于 macOS API Key，采用 `AuthKey_*.p8` 形式配置以替代账号密码。
*   探索未来利用 GitHub Actions OIDC 直接对接 Azure Trusted Signing 的无密码签名方案架构。

## §7 Sidecar Python 跨平台 Sign 处理
*   重点处理 Astral 分发包在 Apple 生态的排异反应。针对 `install_only_stripped` 包中存在的特殊静态库进行清理或特定权限声明豁免。
*   在 `tauri.conf.json` 中添加 Mac 特供的 entitlements 文件，如允许执行未签名的匿名内存页 (`allow-unsigned-executable-memory`) 应对部分 Python FFI 行为。

## §8 错误处理 & Rollback
*   **Matrix 容错**: 任意单个平台的构建失败应当上报 CI Error，但不应强制删除已成功产出并推送到 Release 的其他平台产物（Partial Success）。
*   **Notarization 失败排查**: 发生公证失败时，导出包含 `notarytool log` 的详细分析报告作为 CI Artifact，便于事后排查 Gatekeeper 拦截原因。
*   **重试机制**: 允许基于现有的 Tag 通过手动 `workflow_dispatch` 补建失败的特定平台并追加上传至同一 Release ID。
