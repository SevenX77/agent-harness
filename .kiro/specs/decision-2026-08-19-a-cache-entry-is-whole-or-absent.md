# 决议：一条编译缓存要么是完整快照，要么不存在

- 日期：2026-08-19
- 状态：已裁决，随本 PR 落地
- 模块：engine（`packages/graph-agent`）

## 决策

`save_to_cache` 发布缓存条目改为**写临时文件 + `os.replace` 原子替换**。目标文件
从此只有两种可观察状态：不存在，或完整快照。读方在替换瞬间可能遇到一次
`PermissionError`（Windows），按既有语义算一次缓存 miss（`load_from_cache`
捕 OSError 走重编译），不是损坏。

## 事实与证据

**修改前的代码**（`core/cache.py:52-59`）：

```python
cache_file.write_text(
    json.dumps(_dehydrate_compiled_skill(compiled), ...),
    encoding="utf-8",
)
```

`write_text` 先打开并**截断**目标文件再写入。两个后果，测试线程各自逮到过：

- 并发读方读到半截 JSON（RED 实测：watcher 线程在 50 次写入里抓到多次
  `destination readable but not whole JSON`）。这一半是软的——读方降级重编译——
  但两个进程撞同一个 skill 时缓存恰好在最需要时失效。
- Windows 上第二个进程对同一路径 `write_text` 会命中共享冲突
  `PermissionError`，从 `save_to_cache` 冒出去，**杀掉一次本已成功的编译**。

## 关键设计决定（借了什么、拒了什么、为什么）

1. **借 CPython 写 `.pyc` 的做法**（`importlib._bootstrap_external._write_atomic`）：
   写唯一命名的同目录临时文件，`os.replace` 落位——同卷内在 POSIX 和 Windows 都
   是原子替换。同目录保证同卷。
2. **一处明写的分歧**：CPython 让替换失败冒出去；这里**只**吞替换/清理这一步的
   `OSError`（记 warning + 删临时文件）。理由：缓存是优化，它服务的那次编译已经
   成功，丢一条缓存不许反过来把编译打死。Windows 上读方握着目标文件时替换会被
   拒——而缓存键是内容哈希，同键内容相同，丢掉这次替换零损失。
3. **读方的瞬时 `PermissionError` 判为 miss，不判为损坏**。实测（本 PR 调试脚本）：
   修复后 80 次并发写只出现 1 次读方瞬时拒绝、0 次解析失败。`load_from_cache`
   对 OSError 的既有处理就是重编译，语义不变。
4. **不加缓存目录环境变量**。测试用 `monkeypatch.setattr(get_cache_dir)` 即可，
   为测试加配置项违反 YAGNI。

## 验收判据

- `test_cache_write_is_atomic.py` 三条：watcher 线程 50 次重写抓不到任何可解析
  失败态；读方握着目标文件时 `save_to_cache` 不抛；不留 `.tmp` 残骸。
- 双向验证：撤销修复 RED（1 failed），带修复 GREEN（3 passed）。
- 引擎全套 1586 passed;ruff / mypy --strict 全绿。
