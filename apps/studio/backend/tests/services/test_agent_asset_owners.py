"""批B′ 第 4 阶段 —— MoirAI 资产的跨 owner 出处记录与本地树校验。

病灶(域报告 `gskill-restructure-inventory-2026-08-31/domain-reports/
a66fac8a014fefd6b_v1.md:80,313` 原文):`assets_fingerprint()` 只对主仓
`app/agents/` 一棵树取指纹,于是它"检测得到单 owner 内漂移,检测不到跨 owner
分叉 —— 恰好给了错误的安心感"。资产的单一 owner 已按决议 §4.6-2 定到
graph-skill-runtime,主仓这一份是**即将退役的读者副本**。

本套测试钉住两件事,并且把它们各自能证明什么说清楚:

1. **本地树**在这里,所以可以现算:回显串报的必须是本次进程**实际读到的字节**,
   门禁比的也是同一棵树。部署树漂移时,回显跟着变、门禁跟着红。
2. **上游那棵树不在这里**,本仓既没有它的副本也不依赖它,因此无法验证它。
   本仓留的是一份**出处记录**(转录自上游自己的锁文件),它的作用是给人审
   对账提供坐标(版本锚 + digest + 上游门禁产物路径),不是"权威校验"。
   上游"变了没重钉即红"这句话由上游自己的门禁编码
   (`graph-skill-runtime` `tests/integrations/test_moirai_asset_lock.py`)。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.services import agent_asset_owners as owners
from app.services import agent_assets


@pytest.fixture
def served_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """把 loader 实际读的目录换成一棵可改的克隆,收尾时把缓存清干净。

    `agent_assets` 的三个 memo(`_load` / `load_skill_map` / `assets_fingerprint`)
    都在调用时读模块级 `_AGENTS_DIR`,所以换目录前后都要清一次:换之前清,是为了
    不让真实树的旧值污染本测试;`monkeypatch` 还原之后再清,是为了不让克隆树的值
    留给后面的测试。
    """

    clone = tmp_path / "agents"
    shutil.copytree(agent_assets.agents_dir(), clone)
    agent_assets.clear_caches()
    monkeypatch.setattr(agent_assets, "_AGENTS_DIR", clone)
    try:
        yield clone
    finally:
        monkeypatch.undo()
        agent_assets.clear_caches()


# --------------------------------------------------------------------------
# 出处记录:它记了什么,以及它明确不声称什么
# --------------------------------------------------------------------------


def test_upstream_record_carries_everything_a_human_reconciliation_needs() -> None:
    """出处记录的唯一用途是让人能去上游核对,所以对账坐标必须齐。

    版本锚回答"记的是哪一版",digest 回答"那一版是什么内容",
    `source_reference` 回答"去哪儿比对"——少任何一项,这份记录就只是个
    无从查证的数字。
    """

    record = owners.UPSTREAM_RECORD

    assert record.owner_id == "graph-skill-runtime"
    assert record.asset_version, "没有版本锚,这份记录说不清自己记的是哪一版"
    assert len(record.tree_digest) == 64
    assert all(character in "0123456789abcdef" for character in record.tree_digest)
    assert record.file_count > 0
    assert record.role_skills, "关系也是转录内容的一部分,必须和 digest 同批"
    # 对账点坐标:上游那份锁文件,以及重钉它的命令
    assert "moirai-asset-lock.json" in record.source_reference
    assert "assets/moirai" in record.source_reference


def test_the_record_does_not_claim_this_repository_verifies_the_upstream_bundle() -> None:
    """旧命名宣称"权威校验",而本仓没有那棵树、验不了——该措辞已撤回。

    与 `test_copilot_rules_chain_is_gone` 同一形状的下线锁:no-backward-compat,
    旧名字直接删除而不是留别名,所以断言它们**不存在**。
    """

    assert not hasattr(owners, "AUTHORITATIVE_ROLE_SKILLS")
    assert not hasattr(owners, "LEGACY_TO_AUTHORITATIVE_SKILL_ID")
    assert not hasattr(owners, "authoritative_owner")
    assert not hasattr(owners, "retiring_owner")
    assert not hasattr(owners, "OWNERS")


def test_upstream_facts_are_transcribed_as_one_record_not_as_loose_constants() -> None:
    """digest、文件数、关系来自上游**同一个**快照,所以它们必须一起被转录。

    拆成三个平级常量时,重钉一个忘记另一个不会被任何东西挡住;放进同一条记录里,
    "只改了 digest 没改关系"这种半截转录在阅读时就是显式的。
    """

    record = owners.UPSTREAM_RECORD

    assert isinstance(record, owners.UpstreamAssetRecord)
    assert record.role_skills["moirai"] == ("moirai", "moirai-brainstorming")
    assert record.role_skills["clotho"] == (
        "moirai-domain-analysis",
        "moirai-graph-design",
        "moirai-agent-prompt-design",
    )
    assert set(record.role_skills) == {"moirai", "clotho", "lachesis", "atropos"}


# --------------------------------------------------------------------------
# 本地树:在这里,所以现算、可验
# --------------------------------------------------------------------------


def test_the_recorded_relative_path_is_the_tree_the_loader_reads() -> None:
    """本地树有两个地址,它们必须指同一处。

    `LOCAL_TREE.relative_path` 是**仓内相对路径**,只有 checkout 里有意义,给
    `tracked_moirai_role_trees()` 的源码扫描用;`agent_assets.agents_dir()` 是
    **运行期地址**,打包 sidecar 里也成立(vendor 快照的目录层级不同)。指纹一律
    走后者,所以这里把两者在 checkout 下的重合钉住:有人挪了树而没改常量,这里红。
    """

    assert agent_assets.agents_dir().as_posix().endswith(owners.LOCAL_TREE.relative_path)


def test_live_local_tree_matches_its_pinned_digest_and_file_count() -> None:
    problems = owners.verify()
    assert problems == [], "\n".join(problems)


def test_verify_digests_the_tree_the_loader_serves(served_tree: Path) -> None:
    """门禁必须对 loader 实际服务的那棵树取指纹,而不是另算一个仓内路径。

    两个地址在 checkout 下重合、在打包 sidecar 下不重合;门禁与回显必须共用一个,
    否则"门禁绿"与"用户看到的指纹"可以指向两棵不同的树。
    """

    (served_tree / "roles" / "moirai.md").write_bytes(b"replaced\n")
    agent_assets.clear_caches()

    problems = owners.verify()

    assert problems, "loader 读的树被改了,门禁却没看见"
    assert any("tree digest" in problem for problem in problems)


def test_pinned_digest_is_checkout_independent() -> None:
    """指纹按 LF 归一化后再取,所以它不随 checkout 的行尾设置改变。

    与 `tests/test_doc_hash_lock.py` 的哈希锁同一取舍:该锁也先
    `replace("\\r\\n", "\\n")` 再 sha256。行尾是 checkout 的属性,不是内容的属性;
    把它算进指纹会让同一份内容在两台机器上得出两个身份。
    """

    digest_lf, count_lf = owners.tree_digest(agent_assets.agents_dir())
    assert digest_lf == owners.LOCAL_TREE.tree_digest
    assert count_lf == owners.LOCAL_TREE.file_count


def test_digest_order_does_not_depend_on_platform_path_comparison(tmp_path: Path) -> None:
    """指纹的顺序必须来自 POSIX 相对路径**字符串**,不能来自 `Path` 对象排序。

    `PurePath` 的比较在 Windows 上不区分大小写、在 POSIX 上区分,于是 `README.md`
    在 Windows 上排在 `operating-manual.md` 之后、在 Linux 上排在
    `agent-skill-map.json` 之前 —— 同一棵树,两个指纹。实证:第一版钉子在 Windows
    上算出,Ubuntu 与 macOS 两个 runner 的 `pytest studio backend` 同时红。

    本测试用一棵大小写混排的最小树把这条不变量钉住:两种排序键会给出不同的
    digest,只有按字符串排的那个与两个平台一致。
    """

    tree = tmp_path / "mixed-case"
    tree.mkdir()
    (tree / "README.md").write_bytes(b"upper\n")
    (tree / "agent-skill-map.json").write_bytes(b"lower\n")
    (tree / "operating-manual.md").write_bytes(b"middle\n")

    digest, count = owners.tree_digest(tree)
    assert count == 3

    expected = hashlib.sha256()
    for name in ("README.md", "agent-skill-map.json", "operating-manual.md"):
        expected.update(name.encode("utf-8"))
        expected.update(b"\0")
        expected.update((tree / name).read_bytes())
        expected.update(b"\0")
    assert digest == expected.hexdigest()


def test_digest_ignores_the_checkout_line_ending(tmp_path: Path) -> None:
    crlf = tmp_path / "crlf"
    crlf.mkdir()
    (crlf / "a.md").write_bytes(b"one\r\ntwo\r\n")
    lf = tmp_path / "lf"
    lf.mkdir()
    (lf / "a.md").write_bytes(b"one\ntwo\n")

    assert owners.tree_digest(crlf) == owners.tree_digest(lf)


def test_unrecorded_drift_in_the_local_tree_is_reported(tmp_path: Path) -> None:
    clone = tmp_path / "agents"
    shutil.copytree(agent_assets.agents_dir(), clone)
    baseline, count = owners.tree_digest(clone)
    assert baseline == owners.LOCAL_TREE.tree_digest

    (clone / "roles" / "moirai.md").write_bytes(
        (clone / "roles" / "moirai.md").read_bytes() + b"\nunrecorded edit"
    )
    drifted, drifted_count = owners.tree_digest(clone)
    assert drifted != baseline
    assert drifted_count == count

    problems = owners.problems_for_pinned_digest(
        owners.LOCAL_TREE, digest=drifted, file_count=drifted_count
    )
    assert problems, "an unrecorded content change must be reported"
    assert any("tree digest" in problem for problem in problems)
    assert any("re-pin" in problem for problem in problems)


def test_a_removed_file_is_reported_even_if_someone_repins_only_the_digest(
    tmp_path: Path,
) -> None:
    """文件数与指纹分别登记:少一个文件是一类独立事实,不许被"只重钉指纹"盖过。"""

    clone = tmp_path / "agents"
    shutil.copytree(agent_assets.agents_dir(), clone)
    (clone / "knowledge" / "KB-10-golden.md").unlink()
    digest, count = owners.tree_digest(clone)

    problems = owners.problems_for_pinned_digest(
        owners.LOCAL_TREE, digest=digest, file_count=count
    )
    assert any("file count" in problem for problem in problems)


def test_verify_reports_every_problem_in_one_list() -> None:
    """fail-loud 完整诊断:与 `agent_assets.missing_assets()` 同一契约,一次报全,
    不是修一个才看见下一个。"""

    broken = owners.LocalAssetTree(
        relative_path="apps/studio/backend/app/agents",
        tree_digest="0" * 64,
        file_count=1,
    )

    problems = owners.problems_for_pinned_digest(broken, digest="1" * 64, file_count=2)

    assert len(problems) >= 2


# --------------------------------------------------------------------------
# 关系比对:比的是出处记录,不是"权威"
# --------------------------------------------------------------------------


def test_the_local_skill_map_is_isomorphic_to_the_recorded_relation() -> None:
    """跨 owner 分叉的第一个可机检面:agent→skill 关系。

    两侧技能 id 不同(上游带 `moirai-` 词缀,入口技能对象也不同),但**关系本身**
    必须一致:同样的四个角色、同样的成员、同样的顺序。本地这侧改了关系而记录没同批
    更新,这里就红——这正是旧的单树指纹看不见的那一类分叉。

    能证明的边界要说清:它证明的是"本地关系 == 上次转录下来的上游关系",不是
    "本地关系 == 上游此刻的关系"。后者只有上游自己的门禁能证。
    """

    problems = owners.verify_role_skill_relation()
    assert problems == [], "\n".join(problems)


def test_relation_check_catches_a_one_sided_reorder() -> None:
    local = {
        "moirai": ["brainstorming", "moirai-intro"],  # 顺序被单侧调换
        "clotho": ["domain-analysis", "graph-design", "agent-prompt-design"],
        "lachesis": ["compile-error-repair", "graph-design"],
        "atropos": ["eval-judgement", "agent-prompt-design"],
    }

    problems = owners.problems_for_relation(local)

    assert problems
    assert any("moirai" in problem for problem in problems)


def test_relation_check_catches_a_one_sided_membership_change() -> None:
    local = {
        "moirai": ["moirai-intro", "brainstorming"],
        "clotho": ["domain-analysis", "graph-design"],  # 单侧少一项
        "lachesis": ["compile-error-repair", "graph-design"],
        "atropos": ["eval-judgement", "agent-prompt-design"],
    }

    problems = owners.problems_for_relation(local)

    assert problems
    assert any("clotho" in problem for problem in problems)


def test_relation_failure_text_names_the_record_not_an_authority() -> None:
    """诊断文字也不许再宣称"权威侧说了算"——本仓比的是一份转录记录。

    措辞不是装饰:读到"authoritative owner declares"的人会以为门禁刚刚核对过
    上游,而它没有,也做不到。
    """

    local = {
        "moirai": ["moirai-intro"],
        "clotho": ["domain-analysis", "graph-design", "agent-prompt-design"],
        "lachesis": ["compile-error-repair", "graph-design"],
        "atropos": ["eval-judgement", "agent-prompt-design"],
    }

    problems = owners.problems_for_relation(local)

    assert problems
    joined = " ".join(problems).lower()
    assert "authoritative" not in joined
    assert "recorded" in joined


def test_translation_table_covers_every_live_skill_and_nothing_else() -> None:
    """翻译表是迁移期的**校验用记录**,不是运行期兼容层。

    它必须与两侧的实际技能集合双向吻合,否则"关系一致"这个结论建立在一张过期的
    对照表上。
    """

    live = set(agent_assets.skill_names())
    assert set(owners.LOCAL_TO_UPSTREAM_SKILL_ID) == live

    recorded = set()
    for skills in owners.UPSTREAM_RECORD.role_skills.values():
        recorded.update(skills)
    assert set(owners.LOCAL_TO_UPSTREAM_SKILL_ID.values()) >= recorded


def test_this_repository_holds_no_second_moirai_asset_tree() -> None:
    """单一 owner 的可机检面之二:主仓内不得再出现第二份 MoirAI 角色资产集合。

    检查范围是 git 追踪的源文件——`apps/studio/tauri/vendor/backend/` 下的构建
    快照被 `apps/studio/tauri/.gitignore` 忽略,它是产物而非事实源,不在此列。
    """

    trees = owners.tracked_moirai_role_trees()

    assert trees == [owners.LOCAL_TREE.relative_path], (
        f"expected exactly the retiring copy, found: {trees}"
    )


# --------------------------------------------------------------------------
# 回显串:必须现算
# --------------------------------------------------------------------------


def test_provenance_label_names_the_tree_read_and_the_recorded_upstream() -> None:
    label = owners.provenance_label()

    assert label.startswith("assets@")
    assert agent_assets.assets_fingerprint() in label
    assert "graph-skill-runtime" in label
    assert owners.UPSTREAM_RECORD.asset_version in label
    assert owners.UPSTREAM_RECORD.tree_digest[:8] in label


def test_provenance_label_reports_the_bytes_actually_read_not_the_pin(
    served_tree: Path,
) -> None:
    """部署树漂移后,回显必须跟着变。

    这是本轮修的第二条 P1:回显如果报的是**登记常量**,那么部署出去的那棵树被改动
    之后,服务读的是新字节、回显报的还是旧指纹——漂移恰好被这条回显掩盖,而回显
    存在的全部理由就是让人看见读了什么。
    """

    before = owners.provenance_label()

    target = served_tree / "knowledge" / "KB-00-hub.md"
    target.write_bytes(target.read_bytes() + b"\ndrifted after deployment\n")
    agent_assets.clear_caches()

    after = owners.provenance_label()

    assert after != before, "树变了而回显没变——这正是要修掉的掩盖"
    assert owners.LOCAL_TREE.tree_digest[:8] not in after, "回显不许退回登记常量"
    assert agent_assets.assets_fingerprint() in after


def test_drift_turns_the_echo_and_the_gate_red_together(served_tree: Path) -> None:
    """同一处漂移,回显与门禁必须同时反应——它们读的是同一棵树。

    回显负责"让人看见",门禁负责"挡住";两者若取自不同来源,就会出现"门禁绿、
    回显旧、实际已漂移"的三方不一致。
    """

    target = served_tree / "operating-manual.md"
    target.write_bytes(target.read_bytes() + b"\nlocal edit\n")
    agent_assets.clear_caches()

    assert owners.LOCAL_TREE.tree_digest[:8] not in owners.provenance_label()
    assert any("tree digest" in problem for problem in owners.verify())


# --------------------------------------------------------------------------
# 记录整体
# --------------------------------------------------------------------------


def test_record_is_json_serializable_for_a_report() -> None:
    """记录必须能整段落到报告里:重钉是人做的评审动作,评审要看得见前后值。"""

    payload = owners.record_as_json()

    assert json.loads(json.dumps(payload)) == payload
    assert payload["upstream_record"]["owner_id"] == "graph-skill-runtime"  # type: ignore[index]
    assert payload["local_tree"]["relative_path"] == owners.LOCAL_TREE.relative_path  # type: ignore[index]


def test_agent_assets_fingerprint_is_the_first_eight_of_the_live_digest() -> None:
    assert agent_assets.assets_fingerprint() == owners.tree_digest(agent_assets.agents_dir())[0][:8]
