"""批B′ 第 4 阶段 —— MoirAI 资产的跨 owner 指纹校验。

病灶(域报告 `gskill-restructure-inventory-2026-08-31/domain-reports/
a66fac8a014fefd6b_v1.md:80,313` 原文):`assets_fingerprint()` 只对主仓
`app/agents/` 一棵树取指纹,于是它"检测得到单 owner 内漂移,检测不到跨 owner
分叉 —— 恰好给了错误的安心感"。资产的单一 owner 已按决议 §4.6-2 定到
graph-skill-runtime,主仓这一份是**即将退役的读者副本**;一个只证明"退役副本
没变"的指纹,在迁移期证明的恰好是最没用的那件事。

本套测试钉住替代机制:两个 owner 各有一条**登记在册**的内容指纹与版本锚,任一
侧内容变动而未同批重钉,门禁即红;并且回显串必须同时说出"本次会话实际吃了哪
棵树"与"权威 owner 是谁、哪一版"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services import agent_asset_owners as owners


def test_record_declares_exactly_one_authoritative_owner_and_one_retiring_reader() -> None:
    assert len(owners.OWNERS) == 2
    assert owners.authoritative_owner().owner_id == "graph-skill-runtime"
    assert owners.retiring_owner().owner_id == "studio-legacy-copy"
    # 权威 owner 必须带版本锚,否则"宿主读的是哪一版"没有判据
    assert owners.authoritative_owner().version_anchor
    # 退役副本没有版本锚:它不发布,只被读
    assert owners.retiring_owner().version_anchor is None


def test_live_legacy_tree_matches_its_pinned_digest_and_file_count() -> None:
    problems = owners.verify()
    assert problems == [], "\n".join(problems)


def test_pinned_digest_is_checkout_independent() -> None:
    """指纹按 LF 归一化后再取,所以它不随 checkout 的行尾设置改变。

    与 `tests/test_doc_hash_lock.py` 的哈希锁同一取舍:该锁也先
    `replace("\\r\\n", "\\n")` 再 sha256。行尾是 checkout 的属性,不是内容的属性;
    把它算进指纹会让同一份内容在两台机器上得出两个身份。
    """

    digest_lf, count_lf = owners.tree_digest(owners.retiring_owner().resolved_path())
    assert digest_lf == owners.retiring_owner().tree_digest
    assert count_lf == owners.retiring_owner().file_count


def test_unrecorded_drift_in_either_owner_is_reported(tmp_path: Path) -> None:
    import shutil

    clone = tmp_path / "agents"
    shutil.copytree(owners.retiring_owner().resolved_path(), clone)
    baseline, count = owners.tree_digest(clone)
    assert baseline == owners.retiring_owner().tree_digest

    (clone / "roles" / "moirai.md").write_bytes(
        (clone / "roles" / "moirai.md").read_bytes() + b"\nunrecorded edit"
    )
    drifted, drifted_count = owners.tree_digest(clone)
    assert drifted != baseline
    assert drifted_count == count

    problems = owners.problems_for_digest(
        owners.retiring_owner(), digest=drifted, file_count=drifted_count
    )
    assert problems, "an unrecorded content change must be reported"
    assert any("tree digest" in problem for problem in problems)
    assert any("re-pin" in problem for problem in problems)


def test_a_removed_file_is_reported_even_if_someone_repins_only_the_digest(
    tmp_path: Path,
) -> None:
    """文件数与指纹分别登记:少一个文件是一类独立事实,不许被"只重钉指纹"盖过。"""

    import shutil

    clone = tmp_path / "agents"
    shutil.copytree(owners.retiring_owner().resolved_path(), clone)
    (clone / "knowledge" / "KB-10-golden.md").unlink()
    digest, count = owners.tree_digest(clone)

    problems = owners.problems_for_digest(
        owners.retiring_owner(), digest=digest, file_count=count
    )
    assert any("file count" in problem for problem in problems)


def test_the_legacy_skill_map_is_isomorphic_to_the_authoritative_relation() -> None:
    """跨 owner 分叉的第一个可机检面:agent→skill 关系。

    两侧技能 id 不同(权威侧带 `moirai-` 词缀,入口技能对象也不同),但**关系本身**
    必须一致:同样的四个角色、同样的成员、同样的顺序。任一侧改了关系而另一侧没改,
    这里就红——这正是旧指纹看不见的那一类分叉。
    """

    problems = owners.verify_role_skill_relation()
    assert problems == [], "\n".join(problems)


def test_relation_check_catches_a_one_sided_reorder() -> None:
    legacy = {
        "moirai": ["brainstorming", "moirai-intro"],  # 顺序被单侧调换
        "clotho": ["domain-analysis", "graph-design", "agent-prompt-design"],
        "lachesis": ["compile-error-repair", "graph-design"],
        "atropos": ["eval-judgement", "agent-prompt-design"],
    }

    problems = owners.problems_for_relation(legacy)

    assert problems
    assert any("moirai" in problem for problem in problems)


def test_relation_check_catches_a_one_sided_membership_change() -> None:
    legacy = {
        "moirai": ["moirai-intro", "brainstorming"],
        "clotho": ["domain-analysis", "graph-design"],  # 单侧少一项
        "lachesis": ["compile-error-repair", "graph-design"],
        "atropos": ["eval-judgement", "agent-prompt-design"],
    }

    problems = owners.problems_for_relation(legacy)

    assert problems
    assert any("clotho" in problem for problem in problems)


def test_translation_table_covers_every_live_skill_and_nothing_else() -> None:
    """翻译表是迁移期的**校验用记录**,不是运行期兼容层。

    它必须与两侧的实际技能集合双向吻合,否则"关系一致"这个结论建立在一张过期的
    对照表上。
    """

    from app.services import agent_assets

    live = set(agent_assets.skill_names())
    assert set(owners.LEGACY_TO_AUTHORITATIVE_SKILL_ID) == live

    authoritative = set()
    for skills in owners.AUTHORITATIVE_ROLE_SKILLS.values():
        authoritative.update(skills)
    assert set(owners.LEGACY_TO_AUTHORITATIVE_SKILL_ID.values()) >= authoritative


def test_this_repository_holds_no_second_moirai_asset_tree() -> None:
    """单一 owner 的可机检面之二:主仓内不得再出现第二份 MoirAI 角色资产集合。

    检查范围是 git 追踪的源文件——`apps/studio/tauri/vendor/backend/` 下的构建
    快照被 `apps/studio/tauri/.gitignore` 忽略,它是产物而非事实源,不在此列。
    """

    trees = owners.tracked_moirai_role_trees()

    assert trees == [owners.retiring_owner().relative_path], (
        f"expected exactly the retiring copy, found: {trees}"
    )


def test_provenance_label_names_the_tree_read_and_the_authoritative_owner() -> None:
    label = owners.provenance_label()

    assert label.startswith("assets@")
    assert owners.retiring_owner().tree_digest[:8] in label
    assert "graph-skill-runtime" in label
    assert owners.authoritative_owner().version_anchor in label
    assert owners.authoritative_owner().tree_digest[:8] in label


def test_verify_reports_every_problem_in_one_list(tmp_path: Path) -> None:
    """fail-loud 完整诊断:与 `agent_assets.missing_assets()` 同一契约,一次报全,
    不是修一个才看见下一个。"""

    broken = owners.MoiraiAssetOwner(
        owner_id="studio-legacy-copy",
        stance="retiring-reader",
        relative_path="apps/studio/backend/app/agents",
        version_anchor=None,
        tree_digest="0" * 64,
        file_count=1,
        source_reference="local checkout",
    )

    problems = owners.problems_for_digest(broken, digest="1" * 64, file_count=2)

    assert len(problems) >= 2


def test_record_is_json_serializable_for_a_report(tmp_path: Path) -> None:
    """记录必须能整段落到报告里:重钉是人做的评审动作,评审要看得见前后值。"""

    payload = owners.record_as_json()

    assert json.loads(json.dumps(payload)) == payload
    assert payload["authoritative_owner"] == "graph-skill-runtime"


def test_agent_assets_fingerprint_is_the_first_eight_of_the_pinned_digest() -> None:
    from app.services import agent_assets

    assert agent_assets.assets_fingerprint() == owners.retiring_owner().tree_digest[:8]


@pytest.mark.parametrize("owner", list(owners.OWNERS))
def test_every_owner_records_a_full_sha256_and_a_positive_file_count(
    owner: owners.MoiraiAssetOwner,
) -> None:
    assert len(owner.tree_digest) == 64
    assert all(character in "0123456789abcdef" for character in owner.tree_digest)
    assert owner.file_count > 0
    assert owner.source_reference
