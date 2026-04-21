"""
Learning Flow Phase 1: GT数据提取（Overall-to-Local设计 v3.0）

执行流程：
1. 自动生成EDL（如未提供）
2. Step 1: Overall Scene Recognition — 整体场景识别
   → Phase1SceneRecognitionAgent(LightweightAgentHarness) 质量控制
3. Step 2: Per-Shot Analysis（Strategy B：逐镜头切片）
   → Phase1ShotAnalysisAgent(LightweightAgentHarness) 质量控制
4. 输出3个文件：scene_structure / reference_list / shot_descriptions

Schema v3 变更：
- time_range 改为帧号（List[int]，30fps）
- SceneStructure 新增 location_list，移除 extras，scene 用 loc_ids 引用
- ShotDescription 用 loc_id/look_id/key_props_in_shot ID 引用

设计文档：docs/design/learning/visual_learning.md
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError

from src.core.config import AppConfig, config
from src.core.data_manager import DataManager
from src.core.exceptions import FileOperationError, WorkflowError
from src.core.agent_harness import LightweightAgentHarness, QualityCheckResult, QualityMetrics
from src.core.multimodal_client_manager import (
    MultimodalClientManager,
    VideoUnderstandingService
)
from src.core.error_recovery_agent import ErrorRecoveryAgent, ErrorContext

from .edl_parser import EDLParser, EDLShot
from .auto_edl_generator import AutoEDLGenerator
from .phase1_validation import (
    validate_scene_structure,
    validate_shot_description,
    get_scene_structure_expected_format,
    get_shot_description_expected_format
)

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型（Schema v3）
# ============================================================

class LocationItem(BaseModel):
    """全局地点注册表条目"""
    loc_id: str                                        # L001, L002...
    description: str                                   # 详细环境描述
    scene_ids: List[str] = Field(default_factory=list) # 出现的场景列表


class CharacterLook(BaseModel):
    """角色单套妆造"""
    look_id: str           # C001_SC001，同场景多套加 a/b 后缀
    scene_id: str
    clothing: str          # 服装详细描述（>30字符）
    hairstyle: str
    makeup: str
    accessories: List[str] = Field(default_factory=list)


class MainCharacter(BaseModel):
    """主要角色"""
    character_id: str      # C001
    name_or_trait: str
    looks: List[CharacterLook]


class KeyProp(BaseModel):
    """重要道具"""
    prop_id: str           # P001
    description: str
    appearances: List[str] = Field(default_factory=list)


class SceneStructure(BaseModel):
    """整体Scene结构（Step 1输出）"""
    video_title: str
    total_duration: float                              # 秒（兼容性保留）

    # scenes 每条：scene_id, time_range[帧,帧], shots[int], loc_ids[str], plot_description, narrative_purpose
    scenes: List[Dict[str, Any]]
    main_characters: List[Dict[str, Any]]
    location_list: List[Dict[str, Any]] = Field(default_factory=list)  # LocationItem dicts
    key_props: List[Dict[str, Any]] = Field(default_factory=list)
    insert_shots: List[str] = Field(default_factory=list)

    extracted_at: str = ""
    video_understanding_service: str = ""


class ShotDescription(BaseModel):
    """单镜头描述（Step 2输出）"""
    shot_id: str
    time_range: List[int]                              # [start_frame, end_frame]

    shot_type: str
    narrative_function: str

    visual_content: Dict[str, Any]
    characters: List[Dict[str, Any]]                   # character_id, look_id, actions
    loc_id: str                                        # 引用 location_list
    key_props_in_shot: List[str] = Field(default_factory=list)  # prop_id 列表
    narration_relation: Dict[str, Any]
    emotion: Dict[str, Any]

    metadata: Dict[str, Any] = Field(default_factory=dict)


class Phase1Output(BaseModel):
    """Phase 1完整输出"""
    version: str = "3.0"
    video_path: str
    edl_path: str

    scene_structure: SceneStructure
    shot_descriptions: List[ShotDescription]

    extracted_at: str
    video_understanding_service: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# AgentHarness 子类（质量控制层）
# ============================================================

class Phase1SceneRecognitionAgent(LightweightAgentHarness):
    """
    Step1 场景识别 + 语义质量控制

    继承 LightweightAgentHarness：
    - execute_core → 调用 _step1_raw（LLM + ErrorRecovery）
    - judge → 规则检查 loc_id 引用合规、场景时间完整性
    """

    def __init__(self, extraction_agent: "Phase1GTExtractionAgent", max_iterations: int = 2):
        super().__init__(max_iterations=max_iterations, quality_threshold=0.8)
        self._agent = extraction_agent

    async def execute_core(
        self, task_input, execution_plan, previous_output, previous_quality_result, iteration, **kwargs
    ):
        edl_shots = task_input
        refine_hints = (
            previous_quality_result.issues
            if previous_quality_result and not previous_quality_result.passed
            else []
        )
        return await self._agent._step1_raw(edl_shots, refine_hints)

    async def judge(self, task_input, output: SceneStructure, execution_plan, **kwargs):
        return self._agent._judge_scene_structure(output)


class Phase1ShotAnalysisAgent(LightweightAgentHarness):
    """
    Step2 单镜头分析 + ID引用质量控制

    继承 LightweightAgentHarness：
    - execute_core → 调用 _analyze_shot_raw（LLM + ErrorRecovery）
    - judge → 规则检查 loc_id/look_id/prop_id 合规性
    """

    def __init__(
        self,
        extraction_agent: "Phase1GTExtractionAgent",
        shot_id: str,
        edl_shot: EDLShot,
        scene_structure: SceneStructure,
        video_override: str,
        clip_offset: float = 0.0,
        max_iterations: int = 2,
    ):
        super().__init__(max_iterations=max_iterations, quality_threshold=0.8)
        self._agent = extraction_agent
        self._shot_id = shot_id
        self._edl_shot = edl_shot
        self._scene_structure = scene_structure
        self._video_override = video_override
        self._clip_offset = clip_offset

    async def execute_core(
        self, task_input, execution_plan, previous_output, previous_quality_result, iteration, **kwargs
    ):
        refine_hints = (
            previous_quality_result.issues
            if previous_quality_result and not previous_quality_result.passed
            else []
        )
        return await self._agent._analyze_shot_raw(
            self._shot_id, self._edl_shot, self._scene_structure,
            self._video_override, self._clip_offset, refine_hints
        )

    def judge(self, task_input, output: ShotDescription, execution_plan, **kwargs):
        return self._agent._judge_shot_description(output, self._scene_structure)


# ============================================================
# Phase 1 主 Agent
# ============================================================

class Phase1GTExtractionAgent:
    """
    Phase 1: GT数据提取 Agent（v3.0 Overall-to-Local + AgentHarness质量控制）

    全自动流程，无需人工干预：
    1. 自动生成EDL
    2. Step 1 场景识别 → Phase1SceneRecognitionAgent 质量控制（最多2轮）
    3. Step 2 逐镜头切片分析 → Phase1ShotAnalysisAgent 质量控制（每镜头最多2轮）
    4. 输出3个文件
    """

    def __init__(
        self,
        gt_video_path: str,
        project_name: str,
        config: AppConfig,
        edl_path: Optional[str] = None,
        episode_name: Optional[str] = None,
        video_service: VideoUnderstandingService = VideoUnderstandingService.SEED20_PRO,
        fps: int = 30,
        auto_edl_threshold: int = 22,
        auto_edl_min_shot_duration: float = 0.5,
        max_concurrent_shots: int = 5,
        data_manager: Optional[DataManager] = None,
    ):
        self.gt_video_path = Path(gt_video_path)
        self.project_name = project_name
        self.config = config
        self.video_service = video_service
        self.fps = fps
        self.auto_edl_threshold = auto_edl_threshold
        self.auto_edl_min_shot_duration = auto_edl_min_shot_duration
        self.max_concurrent_shots = max_concurrent_shots
        self.episode_name = episode_name or self.gt_video_path.stem
        self._shot_semaphore: Optional[asyncio.Semaphore] = None
        self.dm = data_manager or DataManager(project_name)

        if not self.gt_video_path.exists():
            raise FileOperationError(
                message=f"GT视频不存在: {gt_video_path}",
                file_path=str(gt_video_path),
                operation="validate_input"
            )

        # 视频标准化预处理：格式不符或超过 50MB 时自动转换为 HEVC 720p
        self.gt_video_path = self._maybe_standardize_video(self.gt_video_path)

        if edl_path:
            self.edl_path = Path(edl_path)
            if not self.edl_path.exists():
                raise FileOperationError(
                    message=f"EDL文件不存在: {edl_path}",
                    file_path=str(edl_path),
                    operation="validate_input"
                )
            self.auto_generate_edl = False
        else:
            edl_dir = self.dm.resolve_path("learning/visual/edl")
            self.edl_path = edl_dir / f"{self.episode_name}.edl"
            self.auto_generate_edl = True

        logger.info(
            f"[Phase1Agent v3] 初始化，project={project_name}, episode={self.episode_name}, "
            f"video={self.gt_video_path.name}, service={video_service.value}"
        )

    async def execute(self) -> Phase1Output:
        """主执行流程（全自动，带质量控制）"""
        logger.info(f"[Phase1Agent] 开始GT数据提取: {self.gt_video_path.name}")

        self._shot_semaphore = asyncio.Semaphore(self.max_concurrent_shots)

        try:
            # Step 0: EDL
            if self.auto_generate_edl:
                self._generate_edl()
            edl_shots = self._parse_edl()
            logger.info(f"[Phase1Agent] EDL解析完成: {len(edl_shots)}个镜头")

            # ⭐ Step 1: Scene Recognition（带 AgentHarness 质量控制）
            scene_rec_harness = Phase1SceneRecognitionAgent(self, max_iterations=2)
            step1_result = await scene_rec_harness.aexecute_with_quality_control(edl_shots)
            scene_structure: SceneStructure = step1_result["output"]
            logger.info(
                f"[Phase1Agent] ✅ Step 1完成: {len(scene_structure.scenes)}个Scenes, "
                f"质量分={step1_result['quality_metrics'].overall_score:.2f}, "
                f"{step1_result['iterations']}次迭代"
            )

            # ⭐ Step 2: Per-Shot Analysis（Strategy B，带 AgentHarness 质量控制）
            shot_descriptions = await self._step2_per_shot(edl_shots, scene_structure)
            logger.info(f"[Phase1Agent] ✅ Step 2完成: {len(shot_descriptions)}个Shots")

            # 构建完整输出
            output = Phase1Output(
                video_path=str(self.gt_video_path),
                edl_path=str(self.edl_path),
                scene_structure=scene_structure,
                shot_descriptions=shot_descriptions,
                extracted_at=datetime.now().isoformat(),
                video_understanding_service=self.video_service.value,
                metadata={
                    "total_scenes": len(scene_structure.scenes),
                    "total_shots": len(shot_descriptions),
                    "total_main_characters": len(scene_structure.main_characters),
                    "step1_quality_score": step1_result["quality_metrics"].overall_score,
                    "step1_iterations": step1_result["iterations"],
                }
            )

            self._save_output(output)
            return output

        except Exception as e:
            logger.error(f"[Phase1Agent] 执行失败: {e}", exc_info=True)
            raise WorkflowError(
                f"Phase 1 GT数据提取失败: {e}",
                details={"video": str(self.gt_video_path), "project": self.project_name}
            ) from e

    # ══════════════════════════════════════════════════════════
    # 视频标准化预处理（HEVC + 720p + 30fps）
    # ══════════════════════════════════════════════════════════

    _MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50MB API 上限

    def _maybe_standardize_video(self, video_path: Path) -> Path:
        """检测视频规格，满足以下任一条件时转换为 HEVC 720p 30fps：
        - 编码非 HEVC/H.265
        - 帧率不是 30fps
        - 短边（横屏高度 / 竖屏宽度）超过 720
        - 文件大小超过 50MB

        标准化缓存写入 learning/visual/std_cache/{episode}_std.mp4，
        已存在且大小正常时直接复用，不重复转码。
        """
        spec = self._detect_video_spec(video_path)
        is_landscape = spec["width"] >= spec["height"]
        short_side = spec["height"] if is_landscape else spec["width"]
        file_size = video_path.stat().st_size

        needs_codec = spec["codec_name"].lower() not in ("hevc", "h265", "libx265")
        needs_fps = abs(spec["fps"] - 30) > 0.1
        needs_res = short_side > 720
        needs_size = file_size > self._MAX_VIDEO_BYTES

        if not (needs_codec or needs_fps or needs_res or needs_size):
            logger.info(
                f"[Phase1Agent] 视频规格已符合标准（codec={spec['codec_name']}, "
                f"fps={spec['fps']:.1f}, {spec['width']}x{spec['height']}, "
                f"{file_size / 1024 / 1024:.1f}MB），跳过标准化"
            )
            return video_path

        reasons = []
        if needs_codec:
            reasons.append(f"codec={spec['codec_name']}→HEVC")
        if needs_fps:
            reasons.append(f"fps={spec['fps']:.0f}→30")
        if needs_res:
            reasons.append(f"short_side={short_side}→720p")
        if needs_size:
            reasons.append(f"size={file_size / 1024 / 1024:.1f}MB>50MB")
        logger.info(f"[Phase1Agent] 视频需要标准化: {', '.join(reasons)}")

        cache_dir = self.dm.resolve_path("learning/visual/std_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        std_path = cache_dir / f"{self.episode_name}_std.mp4"

        if std_path.exists() and std_path.stat().st_size > 1024 * 1024:
            logger.info(
                f"[Phase1Agent] ✅ 标准化缓存已存在，复用: {std_path.name} "
                f"({std_path.stat().st_size / 1024 / 1024:.1f}MB)"
            )
            return std_path

        # 构建 ffmpeg 命令：libx265 + 720p scale + 30fps + aac
        if is_landscape:
            scale_filter = "scale=-2:720"
        else:
            scale_filter = "scale=720:-2"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", scale_filter,
            "-c:v", "libx265",
            "-r", "30",
            "-c:a", "aac",
            str(std_path),
        ]
        logger.info(f"[Phase1Agent] 运行 ffmpeg 标准化...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise WorkflowError(
                f"视频标准化失败: {result.stderr[-500:]}",
                details={"video": str(video_path)},
            )

        out_mb = std_path.stat().st_size / 1024 / 1024
        logger.info(f"[Phase1Agent] ✅ 标准化完成: {std_path.name} ({out_mb:.1f}MB)")

        if std_path.stat().st_size > self._MAX_VIDEO_BYTES:
            raise WorkflowError(
                f"视频标准化后仍超过 50MB（{out_mb:.1f}MB），无法处理",
                details={"video": str(std_path)},
            )

        return std_path

    def _detect_video_spec(self, video_path: Path) -> dict:
        """用 ffprobe 获取视频流基本规格。"""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise WorkflowError(
                f"ffprobe 失败: {result.stderr}",
                details={"video": str(video_path)},
            )
        data = json.loads(result.stdout)
        video_streams = [s for s in data["streams"] if s["codec_type"] == "video"]
        if not video_streams:
            raise WorkflowError("未找到视频流", details={"video": str(video_path)})
        vs = video_streams[0]
        r_frame_rate = vs.get("r_frame_rate", "30/1")
        parts = r_frame_rate.split("/")
        fps = int(parts[0]) / int(parts[1]) if len(parts) == 2 and int(parts[1]) > 0 else float(r_frame_rate)
        return {
            "codec_name": vs.get("codec_name", ""),
            "fps": fps,
            "width": int(vs.get("width", 0)),
            "height": int(vs.get("height", 0)),
        }

    # ══════════════════════════════════════════════════════════
    # Step 0: EDL
    # ══════════════════════════════════════════════════════════

    def _generate_edl(self) -> None:
        logger.info(f"[Phase1Agent] 自动生成EDL: {self.gt_video_path.name}")
        self.edl_path.parent.mkdir(parents=True, exist_ok=True)
        generator = AutoEDLGenerator(fps=self.fps, threshold=self.auto_edl_threshold)
        generator.generate_edl(
            video_path=str(self.gt_video_path),
            output_edl_path=str(self.edl_path),
            min_scene_length=15,
            merge_short_scenes=True,
            min_shot_duration=self.auto_edl_min_shot_duration
        )
        logger.info(f"[Phase1Agent] ✅ EDL自动生成: {self.edl_path}")

    def _parse_edl(self) -> List[EDLShot]:
        parser = EDLParser(fps=self.fps)
        shots = parser.parse(str(self.edl_path))
        shots = parser.filter_short_shots(shots, min_duration=1.0)
        logger.info(f"[Phase1Agent] EDL: {len(shots)}镜头, 总时长{parser.get_total_duration(shots):.2f}s")
        return shots

    # ══════════════════════════════════════════════════════════
    # ⭐ Step 1: 场景识别核心（供 Phase1SceneRecognitionAgent 调用）
    # ══════════════════════════════════════════════════════════

    async def _step1_raw(
        self,
        edl_shots: List[EDLShot],
        refine_hints: List[str] = None
    ) -> SceneStructure:
        """Step1 原始执行：LLM调用 + ErrorRecovery（结构层）"""
        edl_summary = self._build_edl_summary(edl_shots)
        prompt = self._build_overall_scene_prompt(edl_summary, refine_hints or [])

        llm_output = None
        auto_recovered = False

        try:
            result = await MultimodalClientManager.understand_video(
                service=self.video_service,
                video_source=str(self.gt_video_path),
                question=prompt,
                max_tokens=4096
            )
            llm_output = self._parse_json_from_text(result.content)
            scene_structure_data = SceneStructure(**llm_output)

            # 规则检查：日志记录，但不 raise——由 Harness judge 处理并触发下一轮迭代
            rule_errors = validate_scene_structure(llm_output)
            if rule_errors:
                logger.warning(
                    f"⚠️ Step 1规则问题（由Harness judge处理）: {rule_errors}"
                )

        except (ValidationError, KeyError, json.JSONDecodeError) as e:
            # Schema层错误（字段缺失/JSON无效）→ ErrorRecovery
            logger.warning(f"⚠️ Step 1 Schema错误: {type(e).__name__}: {e}")
            context = ErrorContext(
                error_type=type(e).__name__,
                error_message=str(e),
                traceback=traceback.format_exc(),
                failed_output=llm_output,
                tool_name="Phase1_SceneRecognition",
                expected_format=get_scene_structure_expected_format()
            )
            agent = ErrorRecoveryAgent()
            recovery = agent.analyze_and_fix(context, max_retries=2)
            fixed_output = recovery.fixed_output if recovery and recovery.success else None
            if fixed_output:
                logger.info("✅ ErrorRecoveryAgent修复成功")
                auto_recovered = True
                scene_structure_data = SceneStructure(**fixed_output)
            else:
                logger.error("❌ ErrorRecoveryAgent修复失败")
                raise

        scene_structure_data.extracted_at = datetime.now().isoformat()
        scene_structure_data.video_understanding_service = self.video_service.value
        if auto_recovered:
            logger.info("[Phase1Agent] ⚠️ Scene Structure经过结构修复")

        return scene_structure_data

    def _judge_scene_structure(self, scene_structure: SceneStructure) -> QualityCheckResult:
        """语义层质量检查：loc_id引用合规、时间范围完整性"""
        issues = []
        suggestions = []

        valid_loc_ids = {
            loc.get("loc_id", "") for loc in scene_structure.location_list
        }

        # 规则验证（复用 validate_scene_structure 结果）
        rule_errors = validate_scene_structure(scene_structure.model_dump())
        for err in rule_errors:
            issues.append(f"[规则] {err}")

        # 检查 location_list 非空
        if not scene_structure.location_list:
            issues.append("location_list 为空，需要至少1个地点条目")
            suggestions.append("在 location_list 中为每个场景地点添加条目")

        for scene in scene_structure.scenes:
            sid = scene.get("scene_id", "?")
            loc_ids = scene.get("loc_ids", [])
            time_range = scene.get("time_range", [])

            # loc_ids 存在性
            if not loc_ids:
                issues.append(f"{sid}: loc_ids 为空，必须引用至少1个地点")
                suggestions.append(f"{sid}: 在 loc_ids 中添加对应的 location_list 条目")
            else:
                for lid in loc_ids:
                    if lid not in valid_loc_ids:
                        issues.append(f"{sid}: loc_id '{lid}' 不在 location_list 中")
                        suggestions.append(f"在 location_list 中添加 {lid}，或修正 {sid}.loc_ids")

            # time_range 是帧号（整数）
            if time_range and not all(isinstance(x, int) for x in time_range):
                issues.append(f"{sid}: time_range 应为整数帧号，当前值={time_range}")
                suggestions.append(f"{sid}: time_range 改为帧号，如 [0, 150]（30fps×秒数）")

            # plot_description 存在
            if not scene.get("plot_description", "").strip():
                issues.append(f"{sid}: plot_description 为空")

        total_checks = max(len(scene_structure.scenes) * 4, 1)
        passed_checks = total_checks - len(issues)
        accuracy = max(0.0, passed_checks / total_checks)
        completeness = 1.0 if scene_structure.location_list and scene_structure.main_characters else 0.6
        overall = completeness * 0.3 + accuracy * 0.7

        return QualityCheckResult(
            passed=len(issues) == 0,
            metrics=QualityMetrics(
                completeness=round(completeness, 3),
                accuracy=round(accuracy, 3),
                consistency=round(max(0.0, 1.0 - len(issues) * 0.05), 3),
                overall_score=round(overall, 3)
            ),
            issues=issues,
            suggestions=suggestions
        )

    # ══════════════════════════════════════════════════════════
    # ⭐ Step 2: 逐镜头切片分析（Strategy B）
    # ══════════════════════════════════════════════════════════

    async def _step2_per_shot(
        self,
        edl_shots: List[EDLShot],
        scene_structure: SceneStructure
    ) -> List[ShotDescription]:
        """Strategy B: 每个镜头独立切片 + Phase1ShotAnalysisAgent 质量控制"""
        tasks = [
            self._run_shot_with_semaphore(
                f"shot_{shot.shot_number:03d}", shot, scene_structure
            )
            for shot in edl_shots
        ]
        logger.info(
            f"[Phase1Agent] 并发分析 {len(tasks)} 个镜头（最多 {self.max_concurrent_shots} 路并发）..."
        )
        return list(await asyncio.gather(*tasks))

    async def _run_shot_with_semaphore(
        self,
        shot_id: str,
        edl_shot: EDLShot,
        scene_structure: SceneStructure
    ) -> ShotDescription:
        """带并发控制的单镜头处理：切片 + Harness分析"""
        async with self._shot_semaphore:
            with tempfile.TemporaryDirectory() as tmp_dir:
                clip_path = Path(tmp_dir) / f"{shot_id}.mp4"
                await self._cut_shot_clip(
                    edl_shot.start_seconds, edl_shot.end_seconds, str(clip_path)
                )

                shot_agent = Phase1ShotAnalysisAgent(
                    extraction_agent=self,
                    shot_id=shot_id,
                    edl_shot=edl_shot,
                    scene_structure=scene_structure,
                    video_override=str(clip_path),
                    clip_offset=edl_shot.start_seconds,
                    max_iterations=2,
                )
                result = await shot_agent.aexecute_with_quality_control(shot_id)
                shot_desc: ShotDescription = result["output"]

                if not result["quality_passed"]:
                    logger.warning(
                        f"[{shot_id}] ⚠️ 质量未完全达标（分数={result['quality_metrics'].overall_score:.2f}），"
                        f"已记录剩余问题: {result['final_issues']}"
                    )
                    shot_desc.metadata["quality_issues"] = result["final_issues"]

                return shot_desc

    async def _analyze_shot_raw(
        self,
        shot_id: str,
        edl_shot: EDLShot,
        scene_structure: SceneStructure,
        video_override: str,
        clip_offset: float,
        refine_hints: List[str] = None
    ) -> ShotDescription:
        """单镜头原始执行：LLM调用 + ErrorRecovery（结构层）"""
        start_time = edl_shot.start_seconds
        end_time = edl_shot.end_seconds
        start_frame = round(start_time * self.fps)
        end_frame = round(end_time * self.fps)

        parent_scene = self._find_parent_scene(start_frame, scene_structure)
        prompt = self._build_shot_analysis_prompt(
            shot_id, start_frame, end_frame, start_time, end_time,
            parent_scene, scene_structure, clip_offset, refine_hints or []
        )

        llm_output = None
        auto_recovered = False

        try:
            result = await MultimodalClientManager.understand_video(
                service=self.video_service,
                video_source=video_override,
                question=prompt,
                max_tokens=1024
            )
            llm_output = self._parse_json_from_text(result.content)
            shot_desc = ShotDescription(**llm_output)
            rule_errors = validate_shot_description(llm_output)
            if rule_errors:
                raise ValueError(f"Shot规则错误: {rule_errors}")

        except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ [{shot_id}] 分析失败: {type(e).__name__}: {e}")
            context = ErrorContext(
                error_type=type(e).__name__,
                error_message=str(e),
                traceback=traceback.format_exc(),
                failed_output=llm_output,
                tool_name=f"Phase1_ShotAnalysis_{shot_id}",
                expected_format=get_shot_description_expected_format(),
                additional_context={"shot_id": shot_id, "time_range": [start_frame, end_frame]}
            )
            agent = ErrorRecoveryAgent()
            recovery = agent.analyze_and_fix(context, max_retries=2)
            fixed_output = recovery.fixed_output if recovery and recovery.success else None
            if fixed_output:
                logger.info(f"   ✅ [{shot_id}] ErrorRecoveryAgent修复成功")
                auto_recovered = True
                shot_desc = ShotDescription(**fixed_output)
            else:
                logger.error(f"   ❌ [{shot_id}] 修复失败，使用默认值")
                shot_desc = self._create_default_shot_description(shot_id, start_frame, end_frame)

        if auto_recovered:
            logger.info(f"[{shot_id}] ⚠️ Shot描述经过结构修复")

        logger.info(f"[{shot_id}] ✅ 分析完成")
        return shot_desc

    def _judge_shot_description(
        self, shot_desc: ShotDescription, scene_structure: SceneStructure
    ) -> QualityCheckResult:
        """语义层质量检查：loc_id/look_id/prop_id 引用合规"""
        issues = []
        suggestions = []

        valid_loc_ids = {loc.get("loc_id", "") for loc in scene_structure.location_list}
        valid_look_ids = {
            look.get("look_id", "")
            for char in scene_structure.main_characters
            for look in char.get("looks", [])
        }
        valid_prop_ids = {p.get("prop_id", "") for p in scene_structure.key_props}

        # loc_id 合规
        if valid_loc_ids and shot_desc.loc_id not in valid_loc_ids:
            issues.append(
                f"loc_id '{shot_desc.loc_id}' 不在 location_list 中，"
                f"有效值: {sorted(valid_loc_ids)}"
            )
            if valid_loc_ids:
                suggestions.append(f"将 loc_id 修正为 '{next(iter(sorted(valid_loc_ids)))}'")

        # look_id 合规
        if valid_look_ids:
            for char in shot_desc.characters:
                look_id = char.get("look_id", "")
                if look_id and look_id not in valid_look_ids:
                    issues.append(
                        f"角色 look_id '{look_id}' 不在 main_characters.looks 中，"
                        f"有效值: {sorted(valid_look_ids)[:5]}"
                    )
                    suggestions.append(f"将 look_id '{look_id}' 修正为最近一场的有效 look_id")

        # prop_id 合规
        if valid_prop_ids:
            for pid in shot_desc.key_props_in_shot:
                if pid not in valid_prop_ids:
                    issues.append(f"prop_id '{pid}' 不在 key_props 中，有效值: {sorted(valid_prop_ids)}")

        accuracy = max(0.0, 1.0 - len(issues) * 0.25)
        return QualityCheckResult(
            passed=len(issues) == 0,
            metrics=QualityMetrics(
                completeness=1.0,
                accuracy=round(accuracy, 3),
                consistency=1.0,
                overall_score=round(accuracy, 3)
            ),
            issues=issues,
            suggestions=suggestions
        )

    # ══════════════════════════════════════════════════════════
    # Prompt 构建
    # ══════════════════════════════════════════════════════════

    def _build_edl_summary(self, edl_shots: List[EDLShot]) -> str:
        """构建EDL摘要（帧号格式）"""
        lines = [f"总共 {len(edl_shots)} 个镜头（30fps）：\n"]
        for shot in edl_shots:
            start_frame = round(shot.start_seconds * self.fps)
            end_frame = round(shot.end_seconds * self.fps)
            duration_frames = end_frame - start_frame
            lines.append(
                f"Shot {shot.shot_number:02d}: 帧 {start_frame} - 帧 {end_frame} "
                f"（{duration_frames}帧 = {shot.end_seconds - shot.start_seconds:.2f}s）"
            )
        return "\n".join(lines)

    def _build_overall_scene_prompt(
        self, edl_summary: str, refine_hints: List[str] = None
    ) -> str:
        """构建Step1 Overall Scene Recognition prompt"""

        refine_section = ""
        if refine_hints:
            hint_lines = "\n".join(f"- {h}" for h in refine_hints)
            refine_section = f"""
⚠️ 上次分析存在以下问题，请在本次分析中改正：
{hint_lines}

"""

        return f"""
你是专业的影视分析师，请观看这段视频并结合以下镜头时间表，完成整体结构分析。

{refine_section}【镜头时间表（EDL，帧号 30fps）】
{edl_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⭐ Scene定义（严格遵守）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**同一物理地点 + 连续时间 = 同一Scene**

强制规则：
- 地点切换 → 必须创建新Scene，即使叙事上相关
- 电话/视频通话（双方视角）→ 各自独立Scene
- A地和B地之间的交叉剪辑 → A地所有镜头为Scene_X，B地所有镜头为Scene_Y
- 仅在同一房间/区域内连续叙事才允许合并

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务1: 识别Scenes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

每个Scene必须包含：
- scene_id: "scene_001"（从001顺序编号）
- time_range: [start_frame, end_frame]（整数帧号，30fps）
- shots: 该场景包含的镜头编号列表（整数，如[1, 2, 3]）
- loc_ids: 该场景涉及的地点ID列表（引用location_list，如["L001"]）
- plot_description: 该场戏的情节概述（50-150字，说清楚发生了什么）
- narrative_purpose: 叙事目的（如"建立末日氛围"）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务2: 建立地点列表（location_list）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

为每个物理地点建立索引：
- loc_id: L001、L002...（按首次出现顺序）
- description: 地点详细描述（大环境类型、具体位置、环境氛围、陈设特征，如"室内·破旧仓库·昏黄灯光·木箱堆积"）
- scene_ids: 该地点出现的scene_id列表

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务3: 识别主要角色及各场景妆造
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

主要角色：有明确戏份的角色（非路人/群演）。

编号规则：
- 角色主编号：C001、C002...（按首次出场顺序）
- 妆造编号：C001_SC001（角色C001在scene_001的妆造）
- 同场景多套妆造：C001_SC001a、C001_SC001b...

每个主要角色输出：
- character_id: 如"C001"
- name_or_trait: 角色名或特征
- looks: 妆造列表，每套含：look_id、scene_id、clothing（>30字符）、hairstyle、makeup、accessories

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务4: 识别重要道具
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- prop_id: P001、P002...
- description: 详细描述
- appearances: 出现的scene_id列表

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务5: Insert Shots（独立镜头）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

独立于主叙事的镜头：环境空镜、过渡镜头、插入特写。
输出：shot_id列表（如["shot_005"]）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请严格按以下JSON格式输出，不要有额外文字：

{{
  "video_title": "视频标题",
  "total_duration": 视频总时长（秒，浮点数）,
  "scenes": [
    {{
      "scene_id": "scene_001",
      "time_range": [0, 450],
      "shots": [1, 2, 3],
      "loc_ids": ["L001"],
      "plot_description": "这场戏情节概述（50-150字）",
      "narrative_purpose": "叙事目的"
    }}
  ],
  "location_list": [
    {{
      "loc_id": "L001",
      "description": "室内·破旧仓库·昏黄灯光·木箱堆积",
      "scene_ids": ["scene_001"]
    }}
  ],
  "main_characters": [
    {{
      "character_id": "C001",
      "name_or_trait": "角色名或特征",
      "looks": [
        {{
          "look_id": "C001_SC001",
          "scene_id": "scene_001",
          "clothing": "详细服装（>30字符，包含款式/颜色/材质/细节）",
          "hairstyle": "发型",
          "makeup": "妆容",
          "accessories": ["饰品"]
        }}
      ]
    }}
  ],
  "key_props": [
    {{
      "prop_id": "P001",
      "description": "道具详细描述",
      "appearances": ["scene_001"]
    }}
  ],
  "insert_shots": ["shot_005"]
}}

注意：
1. time_range 必须使用整数帧号（秒×30取整），如5秒=帧150
2. 严格JSON格式，所有Scene的time_range不能重叠
3. 每个scene的loc_ids必须引用location_list中已定义的loc_id
4. 不要输出extras/群演字段
"""

    def _build_shot_analysis_prompt(
        self,
        shot_id: str,
        start_frame: int,
        end_frame: int,
        start_time: float,
        end_time: float,
        parent_scene: Optional[Dict],
        scene_structure: SceneStructure,
        clip_offset: float = 0.0,
        refine_hints: List[str] = None
    ) -> str:
        """构建Step2单镜头分析prompt（ID引用格式）"""

        duration = end_time - start_time
        refine_section = ""
        if refine_hints:
            hint_lines = "\n".join(f"- {h}" for h in refine_hints)
            refine_section = f"\n⚠️ 上次分析问题，请改正：\n{hint_lines}\n"

        # 父场景上下文
        scene_context = ""
        scene_loc_ids = []
        if parent_scene:
            scene_loc_ids = parent_scene.get("loc_ids", [])
            loc_descs = []
            for lid in scene_loc_ids:
                for loc in scene_structure.location_list:
                    if loc.get("loc_id") == lid:
                        loc_descs.append(f"{lid}: {loc.get('description', '')}")
                        break
            scene_context = f"""
【所属Scene】
- Scene ID: {parent_scene.get('scene_id')}
- 可用地点（loc_ids）: {', '.join(loc_descs) if loc_descs else ', '.join(scene_loc_ids)}
- 情节: {parent_scene.get('plot_description', '')}
"""

        # look_id 清单
        look_lines = []
        for char in scene_structure.main_characters:
            char_id = char.get("character_id", "")
            name = char.get("name_or_trait", "")
            for look in char.get("looks", []):
                lid = look.get("look_id", "")
                clothing = look.get("clothing", "")[:50]
                look_lines.append(f"  {lid} ({char_id} {name}): {clothing}")
        characters_context = "\n".join(look_lines) if look_lines else "（无主要角色信息）"

        # prop_id 清单
        prop_lines = [
            f"  {p.get('prop_id')}: {p.get('description', '')}"
            for p in scene_structure.key_props
        ]
        props_context = "\n".join(prop_lines) if prop_lines else "（无已知道具）"

        # 时间信息
        if clip_offset == 0.0:
            time_hint = f"帧 {start_frame}–{end_frame}（{start_time:.2f}s–{end_time:.2f}s）"
        else:
            rel_start = round((start_time - clip_offset) * self.fps)
            rel_end = round((end_time - clip_offset) * self.fps)
            time_hint = (
                f"片段内帧 {rel_start}–{rel_end}（绝对帧 {start_frame}–{end_frame}）"
            )

        return f"""
你是专业的镜头分析师，请分析视频的 **{shot_id}**（{time_hint}，时长{duration:.2f}s）。
{refine_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 上下文信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{scene_context}
【可用妆造（look_id → 角色+服装）】
{characters_context}

【可用道具（prop_id）】
{props_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 分析任务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请以JSON格式输出以下字段：

1. shot_type: scene_shot | insert_shot | shot_group_member
2. narrative_function: establish_location | introduce_character | show_action | reveal_detail | create_atmosphere | transition
3. visual_content: {{main_subject, actions: [], camera_work: {{shot_size, camera_movement}}}}
4. characters: 出现的角色列表，每个角色：
   - character_id: 角色ID（如"C001"）
   - look_id: 使用上文列表中的 look_id（如"C001_SC001"）；若换装写"CHANGE:描述"
   - actions: 动作列表
5. loc_id: 该镜头的地点ID（从上文可用地点中选择，如"L001"）
6. key_props_in_shot: 本镜头出现的道具ID列表（如["P001"]，无则为[]）
7. narration_relation: {{type: echo|supplement|independent, visual_info: [], echo_points?: [], supplement_points?: []}}
8. emotion: {{type: tension|suspense|calm|joy|despair|hope, intensity: 1-10}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请严格按以下JSON格式输出，不要有额外文字：

{{
  "shot_id": "{shot_id}",
  "time_range": [{start_frame}, {end_frame}],
  "shot_type": "...",
  "narrative_function": "...",
  "visual_content": {{"main_subject": "...", "actions": [], "camera_work": {{"shot_size": "...", "camera_movement": "..."}}}},
  "characters": [{{"character_id": "C001", "look_id": "C001_SC001", "actions": []}}],
  "loc_id": "L001",
  "key_props_in_shot": [],
  "narration_relation": {{"type": "...", "visual_info": []}},
  "emotion": {{"type": "...", "intensity": 5}}
}}
"""

    # ══════════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════════

    def _find_parent_scene(
        self,
        shot_start_frame: int,
        scene_structure: SceneStructure
    ) -> Optional[Dict]:
        """根据帧号查找Shot所属Scene"""
        for scene in scene_structure.scenes:
            scene_start, scene_end = scene.get("time_range", [0, 0])
            if scene_start <= shot_start_frame < scene_end:
                return scene
        return None

    async def _cut_shot_clip(
        self,
        start: float,
        end: float,
        output_path: str
    ) -> None:
        """ffmpeg trim滤镜精确切割单个镜头（帧精确）"""
        frame_duration = 1.0 / 30.0
        safe_end = end - frame_duration * 0.5  # 末端退半帧，防B-frame溢出

        cmd = [
            "ffmpeg", "-y",
            "-i", str(self.gt_video_path),
            "-vf", f"trim=start={start:.6f}:end={safe_end:.6f},setpts=PTS-STARTPTS",
            "-force_key_frames", "expr:gte(t,0)",
            "-c:v", "libx265",
            "-crf", "28",
            "-preset", "fast",
            "-c:a", "aac",
            output_path
        ]
        logger.debug(f"[Phase1Agent] 切割: {start:.2f}s–{end:.2f}s → {Path(output_path).name}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                f"[Phase1Agent] ffmpeg警告 (rc={proc.returncode}): "
                f"{stderr.decode('utf-8', errors='ignore')[-200:]}"
            )

    def _parse_json_from_text(self, text: str) -> Dict[str, Any]:
        """从文本中解析JSON（容错处理markdown代码块）"""
        import re
        text = text.strip()
        # 去除 markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except Exception:
                    pass
            raise json.JSONDecodeError(
                f"无法解析JSON，原始文本: {text[:200]}...", text, 0
            )

    def _create_default_shot_description(
        self, shot_id: str, start_frame: int, end_frame: int
    ) -> ShotDescription:
        """创建默认Shot描述（降级方案）"""
        return ShotDescription(
            shot_id=shot_id,
            time_range=[start_frame, end_frame],
            shot_type="scene_shot",
            narrative_function="show_action",
            visual_content={
                "main_subject": "分析失败",
                "actions": [],
                "camera_work": {"shot_size": "unknown", "camera_movement": "unknown"}
            },
            characters=[],
            loc_id="UNKNOWN",
            key_props_in_shot=[],
            narration_relation={"type": "independent", "visual_info": ["分析失败"]},
            emotion={"type": "calm", "intensity": 5},
            metadata={"analysis_failed": True}
        )

    # ══════════════════════════════════════════════════════════
    # 输出保存
    # ══════════════════════════════════════════════════════════

    def _save_output(self, output: Phase1Output) -> None:
        """通过 DataManager 版本化保存3个独立输出文件"""
        ep = self.episode_name

        scene_path = self.dm.save(
            output.scene_structure.model_dump(),
            "learning/visual/phase1",
            f"{ep}_scene_structure",
        )

        ref_list = _build_reference_list(output.scene_structure)
        ref_path = self.dm.save(
            ref_list,
            "learning/visual/phase1",
            f"{ep}_reference_list",
        )

        shots_data = [s.model_dump() for s in output.shot_descriptions]
        shots_path = self.dm.save(
            shots_data,
            "learning/visual/phase1",
            f"{ep}_shot_descriptions",
        )

        logger.info(
            f"[Phase1Agent] ✅ 保存3个输出文件至: "
            f"{self.dm.resolve_path('learning/visual/phase1')}"
        )

        output.metadata["output_files"] = {
            "scene_structure": scene_path,
            "reference_list": ref_path,
            "shot_descriptions": shots_path,
        }


# ============================================================
# 辅助函数
# ============================================================

def _build_reference_list(scene_structure: SceneStructure) -> Dict[str, Any]:
    """构建扁平 ID 索引表，便于下游快速查找"""
    ref: Dict[str, Any] = {
        "locations": {},
        "characters": {},
        "key_props": {}
    }

    for loc in scene_structure.location_list:
        ref["locations"][loc.get("loc_id", "")] = loc.get("description", "")

    for char in scene_structure.main_characters:
        cid = char.get("character_id", "")
        ref["characters"][cid] = {
            "name": char.get("name_or_trait", ""),
            "looks": {
                look.get("look_id", ""): look.get("clothing", "")
                for look in char.get("looks", [])
            }
        }

    for prop in scene_structure.key_props:
        ref["key_props"][prop.get("prop_id", "")] = prop.get("description", "")

    return ref


async def extract_gt_data(
    gt_video_path: str,
    project_name: str,
    config: Optional[AppConfig] = None,
    edl_path: Optional[str] = None,
    episode_name: Optional[str] = None,
) -> Phase1Output:
    """便捷函数：提取GT数据"""
    agent = Phase1GTExtractionAgent(
        gt_video_path=gt_video_path,
        project_name=project_name,
        config=config or AppConfig(),
        edl_path=edl_path,
        episode_name=episode_name,
    )
    return await agent.execute()
