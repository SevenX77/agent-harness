"""
Phase 1 规则检查与验证（v3.0）

Schema v3 变更：
- time_range 为帧号（List[int]）
- SceneStructure 有 location_list，scene 用 loc_ids 引用，无 extras
- ShotDescription 用 loc_id: str（ID引用），无 location: Dict
"""

import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# Scene层面规则检查
# ============================================================

def validate_scene_structure(scene_structure: Dict[str, Any]) -> List[str]:
    """
    验证Scene结构的业务规则（v3.0）

    规则：
    1. Scene时间范围不重叠
    2. Scene的time_range有效（start < end，均为整数帧号）
    3. Scene包含至少1个shot
    4. Scene有loc_ids引用
    5. location_list中每个条目有loc_id和description
    6. Character looks完整性
    """
    errors = []
    scenes = scene_structure.get("scenes", [])

    if not scenes:
        errors.append("scenes为空，至少需要1个Scene")
        return errors

    # 规则1 & 2: 每个Scene时间有效性
    for idx, scene in enumerate(scenes):
        sid = scene.get("scene_id", f"scene_{idx}")
        time_range = scene.get("time_range", [0, 0])

        if len(time_range) != 2:
            errors.append(f"{sid}: time_range必须是[start_frame, end_frame]格式")
            continue

        start, end = time_range

        if not (isinstance(start, int) and isinstance(end, int)):
            errors.append(
                f"{sid}: time_range应为整数帧号（30fps），当前为{[type(start).__name__, type(end).__name__]}"
            )

        if start >= end:
            errors.append(f"{sid}: 时间范围无效（start={start} >= end={end}）")

        # 规则3: 包含至少1个shot
        if not scene.get("shots"):
            errors.append(f"{sid}: 必须包含至少1个shot")

        # 规则4: 有loc_ids
        if not scene.get("loc_ids"):
            errors.append(f"{sid}: loc_ids为空，必须引用至少1个地点")

    # 规则1: 时间范围不重叠
    for i in range(len(scenes) - 1):
        cur = scenes[i]
        nxt = scenes[i + 1]
        cur_end = cur.get("time_range", [0, 0])[1]
        nxt_start = nxt.get("time_range", [0, 0])[0]
        if cur_end > nxt_start:
            errors.append(
                f"Scene时间重叠: {cur.get('scene_id')}结束帧{cur_end}, "
                f"{nxt.get('scene_id')}开始帧{nxt_start}"
            )

    # 规则5: location_list完整性
    location_list = scene_structure.get("location_list", [])
    for loc in location_list:
        if not loc.get("loc_id"):
            errors.append("location_list条目缺少loc_id")
        if not loc.get("description"):
            errors.append(f"location {loc.get('loc_id', '?')}: description为空")

    # 规则6: Character looks完整性
    for char in scene_structure.get("main_characters", []):
        char_id = char.get("character_id", "?")
        for look in char.get("looks", []):
            clothing = look.get("clothing", "")
            if isinstance(clothing, str) and len(clothing) < 20:
                errors.append(
                    f"角色{char_id} look {look.get('look_id', '?')}: clothing描述过短（<20字符）"
                )
            required = ["look_id", "scene_id", "clothing", "hairstyle", "makeup"]
            missing = [f for f in required if not look.get(f)]
            if missing:
                errors.append(
                    f"角色{char_id} look {look.get('look_id', '?')}: 缺少字段 {missing}"
                )

    return errors


def validate_shot_description(shot: Dict[str, Any]) -> List[str]:
    """
    验证单个Shot描述的业务规则（v3.0）

    规则：
    1. time_range有效（[int, int]，start < end）
    2. shot_type有效（枚举值）
    3. narrative_function有效（枚举值）
    4. loc_id非空
    5. narration_relation.type有效
    6. characters结构完整（character_id, look_id, actions）
    """
    errors = []

    VALID_SHOT_TYPES = ["scene_shot", "insert_shot", "shot_group_member"]
    VALID_NARRATIVE_FUNCTIONS = [
        "establish_location", "introduce_character", "show_action",
        "reveal_detail", "create_atmosphere", "transition"
    ]
    VALID_NARRATION_RELATIONS = ["echo", "supplement", "independent"]

    shot_id = shot.get("shot_id", "?")
    time_range = shot.get("time_range", [])

    # 规则1: time_range
    if len(time_range) != 2:
        errors.append(f"{shot_id}: time_range必须是[start_frame, end_frame]格式")
    else:
        start, end = time_range
        if not (isinstance(start, int) and isinstance(end, int)):
            errors.append(f"{shot_id}: time_range应为整数帧号")
        if start >= end:
            errors.append(f"{shot_id}: 时间范围无效（start={start} >= end={end}）")

    # 规则2: shot_type
    if shot.get("shot_type") not in VALID_SHOT_TYPES:
        errors.append(
            f"{shot_id}: shot_type='{shot.get('shot_type')}'无效，"
            f"必须是: {', '.join(VALID_SHOT_TYPES)}"
        )

    # 规则3: narrative_function
    if shot.get("narrative_function") not in VALID_NARRATIVE_FUNCTIONS:
        errors.append(
            f"{shot_id}: narrative_function='{shot.get('narrative_function')}'无效"
        )

    # 规则4: loc_id
    if not shot.get("loc_id"):
        errors.append(f"{shot_id}: loc_id为空，必须引用location_list中的ID")

    # 规则5: narration_relation
    narration = shot.get("narration_relation", {})
    if narration.get("type") not in VALID_NARRATION_RELATIONS:
        errors.append(
            f"{shot_id}: narration_relation.type='{narration.get('type')}'无效"
        )

    # 规则6: characters结构
    for char in shot.get("characters", []):
        char_id = char.get("character_id", "?")
        required = ["character_id", "look_id", "actions"]
        missing = [f for f in required if f not in char or char[f] is None]
        if missing:
            errors.append(f"{shot_id}: 角色'{char_id}'缺少字段: {missing}")

    return errors


# ============================================================
# 组合验证
# ============================================================

def validate_phase1_output(phase1_output: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """验证Phase 1完整输出"""
    all_errors = []

    scene_structure = phase1_output.get("scene_structure", {})
    scene_errors = validate_scene_structure(scene_structure)
    all_errors.extend([f"[Scene] {e}" for e in scene_errors])

    shot_descriptions = phase1_output.get("shot_descriptions", [])
    for shot in shot_descriptions:
        shot_errors = validate_shot_description(shot)
        all_errors.extend([f"[{shot.get('shot_id', '?')}] {e}" for e in shot_errors])

    is_valid = len(all_errors) == 0
    if is_valid:
        logger.info("✅ Phase 1输出验证通过")
    else:
        logger.warning(f"⚠️ Phase 1输出验证失败，发现{len(all_errors)}个错误")
        for e in all_errors:
            logger.warning(f"   - {e}")

    return is_valid, all_errors


# ============================================================
# Expected Format（用于 ErrorRecoveryAgent）
# ============================================================

def get_scene_structure_expected_format() -> str:
    return """
期望格式：Scene Structure JSON（v3.0，帧号时间）

{
  "video_title": "视频标题",
  "total_duration": 浮点数（秒）,
  "scenes": [
    {
      "scene_id": "scene_001",
      "time_range": [整数帧号, 整数帧号],  // 30fps，如5秒=150帧
      "shots": [1, 2, 3],                  // 镜头编号列表（整数）
      "loc_ids": ["L001"],                 // 引用location_list的loc_id
      "plot_description": "情节概述（50-150字）",
      "narrative_purpose": "叙事目的"
    }
  ],
  "location_list": [
    {
      "loc_id": "L001",
      "description": "室内·废弃仓库·昏黄灯光",
      "scene_ids": ["scene_001"]
    }
  ],
  "main_characters": [
    {
      "character_id": "C001",
      "name_or_trait": "角色名或特征",
      "looks": [
        {
          "look_id": "C001_SC001",
          "scene_id": "scene_001",
          "clothing": "详细服装（>20字符）",
          "hairstyle": "发型",
          "makeup": "妆容",
          "accessories": []
        }
      ]
    }
  ],
  "key_props": [
    {"prop_id": "P001", "description": "道具描述", "appearances": ["scene_001"]}
  ],
  "insert_shots": ["shot_005"]
}

关键规则：
1. time_range必须是整数帧号（秒×30取整）
2. 不要有extras字段
3. 每个scene的loc_ids必须引用location_list中定义的loc_id
4. 相邻Scene不能时间重叠
"""


def get_shot_description_expected_format() -> str:
    return """
期望格式：Shot Description JSON（v3.0，帧号时间，ID引用）

{
  "shot_id": "shot_001",
  "time_range": [整数帧号, 整数帧号],
  "shot_type": "scene_shot | insert_shot | shot_group_member",
  "narrative_function": "establish_location | introduce_character | show_action | reveal_detail | create_atmosphere | transition",
  "visual_content": {
    "main_subject": "画面主体",
    "actions": ["动作列表"],
    "camera_work": {
      "shot_size": "close_up | medium_shot | wide_shot | establishing_shot",
      "camera_movement": "static | pan | tilt | zoom | dolly | following"
    }
  },
  "characters": [
    {
      "character_id": "C001",
      "look_id": "C001_SC001",    // 引用scene_structure.main_characters.looks
      "actions": ["动作列表"]
    }
  ],
  "loc_id": "L001",               // 引用location_list（字符串，非Dict）
  "key_props_in_shot": ["P001"],  // 本镜头出现的prop_id列表
  "narration_relation": {
    "type": "echo | supplement | independent",
    "visual_info": ["视觉信息"],
    "echo_points": [],
    "supplement_points": []
  },
  "emotion": {
    "type": "tension | suspense | calm | joy | despair | hope",
    "intensity": 1-10
  }
}

关键规则：
1. time_range必须是整数帧号
2. loc_id是字符串（非Dict），引用location_list中的loc_id
3. characters中用look_id引用，不是attire_note
4. key_props_in_shot是prop_id字符串列表
"""
