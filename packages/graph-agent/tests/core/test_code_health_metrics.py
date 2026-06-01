"""test_code_health_metrics.py - 卓越代码健康度诊断集成单测

该测试通过集成调用项目根目录下的顶级 `code-diagnostics` 套件，
对全仓的死代码、类型逃避及测试活性进行高保真的健康体检评分。
如果最终打分低于 85 分，测试将自动断言失败，阻断合并流程。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_warehouse_code_health_diagnostics_oracle() -> None:
    """运行顶级诊断套件，校验全仓的硬性与美学打分是否达到合格红线 (85分)"""
    import time
    repo_root = Path(__file__).resolve().parents[4]
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    target_md = repo_root / "code-diagnostics" / "reports" / f"diag_report_{timestamp}.md"
    
    # 1. 运行 build_tree.py 初始化扫描
    build_tree_script = repo_root / "code-diagnostics" / "build_tree.py"
    assert build_tree_script.exists(), "必须存在顶级代码健康诊断 build_tree.py 脚本"
    
    build_result = subprocess.run(
        [sys.executable, str(build_tree_script), "--file", str(target_md)],
        capture_output=True,
        text=True,
        cwd=str(repo_root)
    )
    assert build_result.returncode == 0, f"结构树扫描 build_tree.py 执行失败:\n{build_result.stderr}"

    # 2. 运行 run_static_audit.py 进行打分与卡口核算
    run_static_script = repo_root / "code-diagnostics" / "run_static_audit.py"
    assert run_static_script.exists(), "必须存在顶级代码健康诊断 run_static_audit.py 脚本"

    audit_result = subprocess.run(
        [sys.executable, str(run_static_script), "--file", str(target_md)],
        capture_output=True,
        text=True,
        cwd=str(repo_root)
    )

    # 打印体检输出便于诊断和查看分数
    print("\n======= CODE-DIAGNOSTICS 体检报告输出 =======")
    print(audit_result.stdout)
    if audit_result.stderr:
        print(audit_result.stderr, file=sys.stderr)
    print("=============================================")

    # 如果返回状态码不为 0 (如分数低于 85 分)，则测试强力失败
    assert audit_result.returncode == 0, (
        f"❌ 代码健康诊断静态体检未达合格红线(85分)或执行出错！\n"
        f"请在 {target_md} 中查看【维度扣分与证据明细】进行技术债清理！"
    )
