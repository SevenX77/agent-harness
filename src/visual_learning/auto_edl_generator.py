"""
自动EDL生成器

职责：
- 自动检测视频的镜头切点（Scene Cut Detection）
- 生成CMX 3600 EDL格式文件
- 与DaVinci Resolve导出的EDL兼容

使用方法：
    python auto_edl_generator.py --video path/to/video.mp4 --output path/to/output.edl
"""

import logging
import argparse
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass
import subprocess
import json

logger = logging.getLogger(__name__)


@dataclass
class ShotCut:
    """镜头切点"""
    shot_number: int
    start_frame: int
    end_frame: int
    start_timecode: str
    end_timecode: str


class AutoEDLGenerator:
    """
    自动EDL生成器
    
    使用PySceneDetect检测镜头切点，生成EDL文件
    """
    
    def __init__(self, fps: int = 30, threshold: float = 27.0):
        """
        Args:
            fps: 视频帧率（默认30）
            threshold: 场景切换阈值（默认27.0，越低越敏感）
        """
        self.fps = fps
        self.threshold = threshold
        logger.info(f"[AutoEDLGenerator] 初始化，fps={fps}, threshold={threshold}")
    
    def generate_edl(
        self,
        video_path: str,
        output_edl_path: str,
        min_scene_length: int = 15,  # 最小场景长度（帧数）
        merge_short_scenes: bool = True,  # 是否合并短镜头
        min_shot_duration: float = 3.0  # 合并阈值（秒）
    ) -> str:
        """
        自动生成EDL文件
        
        Args:
            video_path: 视频文件路径
            output_edl_path: 输出EDL文件路径
            min_scene_length: 最小场景长度（帧数），用于过滤过短的镜头
            merge_short_scenes: 是否合并短镜头（后处理）
            min_shot_duration: 合并阈值，短于此值的镜头将与相邻镜头合并（秒）
        
        Returns:
            EDL文件路径
        """
        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        logger.info(f"[AutoEDLGenerator] 开始处理: {video_file.name}")
        
        # Step 1: 使用PySceneDetect检测镜头切点
        logger.info(f"[Step 1] 检测镜头切点...")
        cuts = self._detect_scene_cuts(str(video_file), min_scene_length)
        logger.info(f"[Step 1] ✅ 检测到{len(cuts)}个镜头")
        
        # Step 2: 合并短镜头（后处理）
        if merge_short_scenes:
            logger.info(f"[Step 2] 合并短镜头（<{min_shot_duration}秒）...")
            cuts = self._merge_short_shots(cuts, min_shot_duration)
            logger.info(f"[Step 2] ✅ 合并后剩余{len(cuts)}个镜头")
        
        # Step 3: 生成EDL文件
        logger.info(f"[Step 3] 生成EDL文件...")
        edl_content = self._generate_edl_content(cuts, video_file.name)
        
        # Step 4: 保存EDL文件
        output_path = Path(output_edl_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(edl_content, encoding='utf-8')
        
        logger.info(f"[Step 4] ✅ EDL已保存: {output_path}")
        logger.info(f"[AutoEDLGenerator] 完成！{len(cuts)}个镜头 → {output_path}")
        
        return str(output_path)
    
    def _detect_scene_cuts(
        self,
        video_path: str,
        min_scene_length: int
    ) -> List[ShotCut]:
        """
        使用PySceneDetect检测镜头切点
        
        注意：需要先安装 PySceneDetect
        pip install scenedetect[opencv]
        """
        try:
            # 尝试导入scenedetect
            from scenedetect import detect, ContentDetector, split_video_ffmpeg
            
            logger.info(f"[PySceneDetect] 使用ContentDetector检测...")
            logger.info(f"   阈值: {self.threshold}")
            logger.info(f"   最小场景长度: {min_scene_length}帧")
            
            # 检测场景切换
            scene_list = detect(
                video_path,
                ContentDetector(threshold=self.threshold, min_scene_len=min_scene_length)
            )
            
            logger.info(f"[PySceneDetect] ✅ 检测到{len(scene_list)}个场景")
            
            # 转换为ShotCut格式
            cuts = []
            for i, (start_time, end_time) in enumerate(scene_list, 1):
                start_frame = start_time.get_frames()
                end_frame = end_time.get_frames()
                
                start_tc = self._frame_to_timecode(start_frame)
                end_tc = self._frame_to_timecode(end_frame)
                
                cuts.append(ShotCut(
                    shot_number=i,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    start_timecode=start_tc,
                    end_timecode=end_tc
                ))
                
                logger.debug(
                    f"   Shot {i:03d}: Frame {start_frame}-{end_frame} "
                    f"({start_tc} - {end_tc})"
                )
            
            return cuts
        
        except ImportError as e:
            logger.error("❌ PySceneDetect未安装！")
            logger.error("   请运行: pip install scenedetect[opencv]")
            raise ImportError(
                "需要安装 scenedetect[opencv]。\n"
                "运行: pip install scenedetect[opencv]"
            ) from e
        
        except Exception as e:
            logger.error(f"❌ 场景检测失败: {e}")
            raise
    
    def _merge_short_shots(
        self,
        cuts: List[ShotCut],
        min_duration: float
    ) -> List[ShotCut]:
        """
        合并过短的镜头
        
        策略：
        - 如果镜头时长 < min_duration秒，则与下一个镜头合并
        - 重新编号
        """
        if not cuts:
            return cuts
        
        merged = []
        i = 0
        
        while i < len(cuts):
            current = cuts[i]
            current_duration = (current.end_frame - current.start_frame) / self.fps
            
            # 如果当前镜头太短，且不是最后一个，则与下一个合并
            if current_duration < min_duration and i < len(cuts) - 1:
                next_shot = cuts[i + 1]
                
                # 合并：使用当前的start，下一个的end
                merged_shot = ShotCut(
                    shot_number=len(merged) + 1,
                    start_frame=current.start_frame,
                    end_frame=next_shot.end_frame,
                    start_timecode=current.start_timecode,
                    end_timecode=next_shot.end_timecode
                )
                
                merged_duration = (merged_shot.end_frame - merged_shot.start_frame) / self.fps
                logger.debug(
                    f"   合并Shot {current.shot_number}+{next_shot.shot_number}: "
                    f"{current_duration:.2f}s + {(next_shot.end_frame-next_shot.start_frame)/self.fps:.2f}s "
                    f"→ {merged_duration:.2f}s"
                )
                
                merged.append(merged_shot)
                i += 2  # 跳过下一个（已合并）
            else:
                # 重新编号
                current.shot_number = len(merged) + 1
                merged.append(current)
                i += 1
        
        logger.info(f"   原始镜头数: {len(cuts)}, 合并后: {len(merged)}")
        return merged
    
    def _frame_to_timecode(self, frame: int) -> str:
        """
        帧数转时间码
        
        格式: HH:MM:SS:FF
        """
        total_seconds = frame / self.fps
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        frames = int(frame % self.fps)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    def _generate_edl_content(
        self,
        cuts: List[ShotCut],
        clip_name: str
    ) -> str:
        """
        生成EDL文件内容（CMX 3600格式）
        
        格式示例:
        TITLE: ep05_proj001
        FCM: NON-DROP FRAME
        
        001  AX       V     C        00:03:24:20 00:03:30:06 00:00:00:00 00:00:05:16
        * FROM CLIP NAME: video.MP4
        """
        lines = []
        
        # EDL头部
        project_name = Path(clip_name).stem
        lines.append(f"TITLE: {project_name}")
        lines.append("FCM: NON-DROP FRAME")
        lines.append("")
        
        # 每个镜头的EDL条目
        timeline_start_frame = 0
        
        for cut in cuts:
            # 计算Timeline时间码
            timeline_end_frame = timeline_start_frame + (cut.end_frame - cut.start_frame)
            timeline_start_tc = self._frame_to_timecode(timeline_start_frame)
            timeline_end_tc = self._frame_to_timecode(timeline_end_frame)
            
            # EDL行
            # 格式: 编号 音视频 轨道 类型 源入点 源出点 Timeline入点 Timeline出点
            edl_line = (
                f"{cut.shot_number:03d}  AX       V     C        "
                f"{cut.start_timecode} {cut.end_timecode} "
                f"{timeline_start_tc} {timeline_end_tc}"
            )
            lines.append(edl_line)
            lines.append(f"* FROM CLIP NAME: {clip_name}")
            lines.append("")
            
            # 更新Timeline起始点
            timeline_start_frame = timeline_end_frame
        
        return "\n".join(lines)
    
    def compare_with_ground_truth(
        self,
        generated_edl_path: str,
        ground_truth_edl_path: str
    ) -> dict:
        """
        对比生成的EDL与Ground Truth
        
        Returns:
            对比结果（镜头数量、时间码差异等）
        """
        from .edl_parser import EDLParser
        
        parser = EDLParser(fps=self.fps)
        
        generated_shots = parser.parse(generated_edl_path)
        gt_shots = parser.parse(ground_truth_edl_path)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"EDL对比分析")
        logger.info(f"{'='*60}")
        logger.info(f"生成镜头数: {len(generated_shots)}")
        logger.info(f"GT镜头数: {len(gt_shots)}")
        
        # 镜头数量对比
        shot_count_match = len(generated_shots) == len(gt_shots)
        if shot_count_match:
            logger.info(f"✅ 镜头数量匹配")
        else:
            logger.warning(f"⚠️  镜头数量不匹配（差异: {len(generated_shots) - len(gt_shots)}）")
        
        # 时间码对比（前5个镜头）
        logger.info(f"\n前5个镜头时间码对比:")
        time_diffs = []
        
        for i in range(min(5, len(generated_shots), len(gt_shots))):
            gen_shot = generated_shots[i]
            gt_shot = gt_shots[i]
            
            start_diff = abs(gen_shot.start_seconds - gt_shot.start_seconds)
            end_diff = abs(gen_shot.end_seconds - gt_shot.end_seconds)
            time_diffs.append((start_diff, end_diff))
            
            logger.info(f"\n  Shot {i+1}:")
            logger.info(f"    生成: {gen_shot.start_seconds:.2f}s - {gen_shot.end_seconds:.2f}s ({gen_shot.duration_seconds:.2f}s)")
            logger.info(f"    GT:   {gt_shot.start_seconds:.2f}s - {gt_shot.end_seconds:.2f}s ({gt_shot.duration_seconds:.2f}s)")
            logger.info(f"    差异: 入点±{start_diff:.2f}s, 出点±{end_diff:.2f}s")
        
        # 平均时间差
        if time_diffs:
            avg_start_diff = sum(d[0] for d in time_diffs) / len(time_diffs)
            avg_end_diff = sum(d[1] for d in time_diffs) / len(time_diffs)
            logger.info(f"\n平均时间差:")
            logger.info(f"  入点: ±{avg_start_diff:.2f}s")
            logger.info(f"  出点: ±{avg_end_diff:.2f}s")
        
        return {
            "generated_shot_count": len(generated_shots),
            "gt_shot_count": len(gt_shots),
            "shot_count_match": shot_count_match,
            "avg_start_diff": avg_start_diff if time_diffs else None,
            "avg_end_diff": avg_end_diff if time_diffs else None
        }


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="自动从视频生成EDL文件"
    )
    parser.add_argument(
        "--video",
        required=True,
        help="输入视频文件路径"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="输出EDL文件路径"
    )
    parser.add_argument(
        "--ground-truth",
        help="Ground Truth EDL文件路径（用于对比）"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="视频帧率（默认30）"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=27.0,
        help="场景切换阈值（默认27.0，越低越敏感）"
    )
    parser.add_argument(
        "--min-scene-length",
        type=int,
        default=15,
        help="最小场景长度（帧数，默认15）"
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="不合并短镜头（默认会合并）"
    )
    parser.add_argument(
        "--min-shot-duration",
        type=float,
        default=3.0,
        help="合并阈值，短于此值的镜头将与相邻镜头合并（秒，默认3.0）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建生成器
    generator = AutoEDLGenerator(fps=args.fps, threshold=args.threshold)
    
    # 生成EDL
    try:
        output_path = generator.generate_edl(
            video_path=args.video,
            output_edl_path=args.output,
            min_scene_length=args.min_scene_length,
            merge_short_scenes=not args.no_merge,
            min_shot_duration=args.min_shot_duration
        )
        
        logger.info(f"\n🎉 EDL生成成功: {output_path}")
        
        # 如果提供了Ground Truth，进行对比
        if args.ground_truth:
            logger.info(f"\n{'='*60}")
            logger.info(f"开始对比Ground Truth...")
            logger.info(f"{'='*60}")
            
            result = generator.compare_with_ground_truth(
                generated_edl_path=output_path,
                ground_truth_edl_path=args.ground_truth
            )
            
            logger.info(f"\n{'='*60}")
            logger.info(f"对比完成")
            logger.info(f"{'='*60}")
    
    except Exception as e:
        logger.error(f"\n❌ 生成失败: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
