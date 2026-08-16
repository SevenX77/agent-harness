"""compile_skill 的 agent 侧投影:诊断全量保留,前端负载不外泄。

现场(2026-08-15,story-deconstruction-v3-lab):MoirAI 调 `studio:compile_skill`
拿回一个 216,838 字节 / 61,160 token 的结果,SDK 溢写成 tool-result 文件后她
`Read` 不动(上限 25,000 token),转 grep 被判 "too long",再转 jq / PowerShell
拆 JSON 连着三轮卡在审批 —— 她读不了自己刚拿到的工具结果。而那次编译
`status="ok"`、0 个 issue:全部代价只为换回"没问题"三个字。

体积来源已量化:`detail.files`(68 个文件的完整正文)165,910 字符,占 88%;
`node_schema_v21` 14,254;二者都是**前端**填编辑器/画布用的负载。工具自己的
描述写的是「成功给编译产物摘要」,实现却回了整个 `CompileSuccess`。
"""

from __future__ import annotations

from app.models.errors import LintError
from app.models.lint import LintResult
from app.models.skills import CompileSuccess, SkillDetail
from app.services.diagnostic_export import export_compile_diagnostics

_FILE_BODY = "x" * 5000


def _compile_success(*, errors: list[LintError]) -> CompileSuccess:
    return CompileSuccess(
        skill_id="lab",
        status="ok",
        phase_count=4,
        manifest_name="lab",
        artifact_ref={"artifact_id": "lab", "content_hash": "sha256:dead"},
        source_map_ref="file:///store/source_map.json",
        execution_fingerprint="fp-1",
        detail=SkillDetail(
            manifest={
                "schema_version": "v0.3.0",
                "name": "lab",
                "io": {
                    "inputs": {"text": {"type": "string"}},
                    "outputs": {"result": {"type": "string"}},
                },
            },
            graph_topology=[{"id": "a"}],
            node_schema_v21={"a": {"blob": _FILE_BODY}},
            io_schema={"a": {"blob": _FILE_BODY}},
            file_paths={"GRAPH.md": "GRAPH.md"},
            files={"GRAPH.md": _FILE_BODY, "phases/a.md": _FILE_BODY},
            has_golden=False,
            lint_result=LintResult(status="failed" if errors else "passed", errors=errors),
        ),
    )


def test_export_carries_every_issue_untruncated() -> None:
    """diagnostics SSOT(AGENTS.md):一趟返回引擎的**全量**缺陷集,绝不只给第一条。

    这条投影是给 agent 的那个面,和前端各面同源;裁掉的只能是非诊断负载。
    """

    errors = [
        LintError(
            file=f"phases/p{i}.md",
            line=i,
            error_code=f"[F-v3-code-{i}]",
            severity="error",
            message=f"boom {i}",
        )
        for i in range(1, 13)
    ]

    export = export_compile_diagnostics(_compile_success(errors=errors))

    assert export.lint_status == "failed"
    assert [e.error_code for e in export.issues] == [f"[F-v3-code-{i}]" for i in range(1, 13)]
    assert export.issue_count == 12


def test_export_leaves_the_frontend_payload_behind() -> None:
    """agent 要的是"编译过没有 / 哪里错了";文件正文她有 read_skill_file 按需分页读,
    图结构她有 get_skill_overview。把前端负载塞给她,换来的是读不动的 dump。"""

    export = export_compile_diagnostics(_compile_success(errors=[]))
    dumped = export.model_dump_json()

    assert _FILE_BODY not in dumped, "文件正文/节点 schema 不得进 agent 侧结果"
    assert len(dumped) < 2000, f"agent 侧结果应当是摘要级,实测 {len(dumped)} 字符"
    # 摘要仍要够她接着干活:状态、规模、下一步读哪些文件。
    assert export.status == "ok"
    assert export.phase_count == 4
    assert export.file_paths == {"GRAPH.md": "GRAPH.md"}
