# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- fix(studio): the WSL launchers no longer share one credential chain across
  the Windows/WSL boundary (ah decision 0006). The Codex launcher copied the
  Windows `auth.json` into WSL on every start and the Claude launcher force-
  symlinked the WSL store to the Windows `.credentials.json`; refresh tokens
  rotate on every use, so both arrangements fork the chain and whichever side
  refreshes less dies of "refresh token already used" — the recorded cause of
  a real WSL Codex login death, and the re-armed fuse ah's doorman kept
  flagging for Claude. The WSL-native login is now authoritative: a leftover
  Windows credential link is removed, and when the environment has no login
  the launcher runs the provider's own sign-in (`codex login`,
  `claude auth login`) right in the launch terminal before continuing.

### Changed
- **Baseline cleanup (2026-05-19)**: 200 份历史文档收敛到 5 支柱 (~30 份精华 doc)
  - 物理归档 160+ 份到 `docs/archive/*` + `.kiro/specs/_archive/`
  - 新建 11 份逻辑融合 doc (`PROD_DEV_SEPARATION.md`, `AGENT_COGNITIVE_ARCHITECTURE.md`, 等)
  - README 彻底重写，定调为大而全（自包含，不杂糅命令行碎碎念）
  - 明确生产端/研发端架构分离的法典文档，引入 Level 3 与 Level 4 规范的双向链接标准

### Added
- feat(studio): API key plaintext display + design round 2 reversal (#74)
- feat(studio-frontend): API Key row full-width + shorten Test button label (#73)
- docs(llm-providers): add provider reference docs (Anthropic / Gemini / OpenAI)
- docs(.kiro): add studio-frontend v2.1 multifile editor spec

### Fixed
- fix(studio-backend): keep last_test_status='untested' on missing API key
- fix(studio-backend): satisfy ruff in skills service

## [v0.2.0] - 2026-05-18

### Changed
- feat(studio): 任意文件夹 = skill + VS Code 风格 Asset 文件树
- refactor(studio-backend): API Keys schema v3 with UUID id and user-owned name
- feat(studio-frontend): API Keys shadcn redesign with provider cards
- feat(studio-backend): apply ruff import order
- feat(studio): wire Compile button end-to-end
