# Phase T3 跨平台 Build 与签名 — Research (Round 1)

## 主题 1: macOS Notarization 流程最佳实践
*   **证书选择**: 必须使用 `Developer ID Application` 证书进行 macOS 外部应用的分发签名。不能用 App Store 证书。
*   **工具变迁**: 传统的 `altool` 已经废弃，目前官方强制要求使用 `notarytool` 提交应用公证。
*   **Hardened Runtime**: 桌面分发公证的硬性要求。开启 Hardened Runtime 后，由于我们内置了 Python Sidecar，极大可能需要声明 `com.apple.security.cs.allow-jit`, `com.apple.security.cs.disable-library-validation` (以加载第三方预编译 C 扩展)，或 `com.apple.security.cs.allow-unsigned-executable-memory`。
*   **Staple**: 必须在 Notarization 成功后对应用包执行 `xcrun stapler staple`，这样在断网环境下 Gatekeeper 才能验证应用安全。

## 主题 2: Windows Code Signing 机制选型
*   **签名工具**: 标准方案使用 Windows SDK 提供的 `signtool.exe` 对 `.exe` 和 `.msi` 签名，必须包含可靠的时间戳服务 (`/tr`)。
*   **EV vs OV Cert**: EV (Extended Validation) 证书需要硬件 U 盾或 HSM，极难在云端 CI 全自动化。OV (Organization Validation) 证书（如普通 Code Signing Cert .pfx 文件）可以存入 GitHub Secrets，但会面临 SmartScreen 的“未知发布者”冷启动拦截期（需累积信誉下载量才能消除）。
*   **Azure Trusted Signing**: 微软近期推出的云原生签名服务 (取代传统的本地 .pfx)。如果是新申请，强烈建议走此路径，彻底消除证书文件管理的泄露风险。

## 主题 3: Linux AppImage 与桌面集成
*   **打包工具**: Tauri 默认通过 `appimage-builder` 或内置封装流程产出 `.AppImage`。它自带所有的 `.so` 依赖。
*   **GPG 签名**: Linux 下没有中心化的强拦截机制，但为防篡改，可使用 GPG 生成签名文件 (`.sig`) 或直接对 AppImage 使用 `appimage-builder` 的签名特性。此项非阻塞性必填项。
*   **桌面集成**: AppImage 可以借助第三方工具如 `appimaged` 自动生成 `.desktop` 文件注册到启动器中。

## 主题 4: GitHub Actions Multi-platform Matrix
*   **Runner 选择**:
    *   macOS: `macos-14` 默认为 Apple Silicon (M1/M2) 架构，适合构建 aarch64。若要构建 Universal (同时含 x86_64 和 arm64)，可利用 Rust 的跨平台编译 target 并在单个 runner 完成，或用 `lipo` 工具将不同 runner 的产物合并。
    *   Windows: `windows-latest` (Windows Server 2022) 即可。
    *   Linux: `ubuntu-22.04`，需前置安装 `webkit2gtk-4.1`, `libgtk-3-dev`, `libayatana-appindicator3-dev`。
*   **Tauri Action**: 官方推荐使用 `tauri-apps/tauri-action`。它封装了 build、基于 target 的工件命名和 GitHub Release 上传功能。
*   **依赖缓存**: 需要使用 `Swatinem/rust-cache` 缓存 Cargo registry 与 target 目录；使用 `actions/setup-node` 缓存 npm。

## 主题 5: Secret 安全管理方案
*   **Apple Secrets**: 需在 GitHub 仓库注入 `APPLE_CERTIFICATE` (.p12 的 Base64), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_API_KEY_ID`, `APPLE_API_KEY_ISSUER_ID`, `APPLE_API_KEY_BASE64`。推荐使用 Apple API Keys (App Store Connect 申请) 替代传统的 App-Specific Password 方案来走 `notarytool`，权限控制更安全。
*   **Windows Secrets**: 若使用传统方案，需注入 `WINDOWS_CERTIFICATE` (.pfx Base64) 和 `WINDOWS_CERTIFICATE_PASSWORD`。对于 Action 集成，可采用开源 Action `import-codesign-certs`。
*   **GitHub Release Token**: 需要配置 `GITHUB_TOKEN` 具有 `contents: write` 权限才能自动挂载产物。

## 主题 6: Tauri Sidecar 跨平台 Sign 处理难点
*   **Astral Portable Python**: `python-build-standalone` 是一个庞大的目录。在 macOS 上，`codesign` 必须涵盖 Bundle 内部**所有**的共享库 (`.dylib`) 和可执行文件 (`bin/python3`)。
*   **`--deep` 的局限性**: 仅使用 `codesign --deep` 往往不够，尤其针对内嵌在非常规目录 (如 `vendor/`) 的大量第三方 binary wheel。Apple 官方和诸多踩坑经验指出，应当使用特定的 find 脚本找出所有可执行和动态库文件，进行自底向上的逐个签名。
*   **Windows 豁免**: Windows `.msi` 签名后，内部的文件如果不被 Windows Defender 识别为直接病毒通常可被信任。但稳妥起见，亦可通过 PowerShell 脚本遍历 `vendor/` 下的 `.exe` 与 `.dll` 先进行预签名。
