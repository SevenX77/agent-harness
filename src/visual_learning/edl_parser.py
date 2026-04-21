"""
EDL (Edit Decision List) 解析器

职责：
- 解析CMX 3600 EDL格式文件
- 提取镜头切点（时间码）
- 转换时间码为秒数

EDL格式参考：
001  AX       V     C        00:03:24:20 00:03:30:06 00:00:00:00 00:00:05:16
│    │        │     │        │           │           │           │
编号  音视频   轨道  类型     源入点      源出点      时间线入点  时间线出点
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EDLShot:
    """单个镜头信息"""
    shot_number: int
    source_in_tc: str  # 源时间码入点（HH:MM:SS:FF）
    source_out_tc: str  # 源时间码出点
    timeline_in_tc: str  # Timeline时间码入点
    timeline_out_tc: str  # Timeline时间码出点
    
    # 转换后的秒数（基于Timeline时间码）
    start_seconds: float
    end_seconds: float
    duration_seconds: float


class EDLParser:
    """
    EDL解析器
    
    支持格式：CMX 3600 EDL（DaVinci Resolve标准导出格式）
    """
    
    def __init__(self, fps: int = 30):
        """
        Args:
            fps: 帧率（默认30fps）
                - 24fps: 电影标准
                - 25fps: PAL标准（欧洲）
                - 30fps: NTSC标准（北美，DaVinci Resolve默认）
        """
        self.fps = fps
        logger.info(f"[EDLParser] 初始化，fps={fps}")
    
    def parse(self, edl_path: str) -> List[EDLShot]:
        """
        解析EDL文件
        
        Args:
            edl_path: EDL文件路径
        
        Returns:
            镜头列表（按时间顺序）
        """
        edl_file = Path(edl_path)
        if not edl_file.exists():
            raise FileNotFoundError(f"EDL文件不存在: {edl_path}")
        
        logger.info(f"[EDLParser] 开始解析: {edl_file.name}")
        
        shots = []
        
        with open(edl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 跳过空行和注释行
                if not line or line.startswith('TITLE:') or line.startswith('FCM:') or line.startswith('*'):
                    continue
                
                # 匹配EDL行格式
                # 格式: 001  AX       V     C        HH:MM:SS:FF HH:MM:SS:FF HH:MM:SS:FF HH:MM:SS:FF
                match = re.match(
                    r'(\d+)\s+(\w+)\s+V\s+C\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',
                    line
                )
                
                if match:
                    shot_number = int(match.group(1))
                    source_in_tc = match.group(3)
                    source_out_tc = match.group(4)
                    timeline_in_tc = match.group(5)
                    timeline_out_tc = match.group(6)
                    
                    # 转换Timeline时间码为秒数
                    start_seconds = self._timecode_to_seconds(timeline_in_tc)
                    end_seconds = self._timecode_to_seconds(timeline_out_tc)
                    duration = end_seconds - start_seconds
                    
                    shot = EDLShot(
                        shot_number=shot_number,
                        source_in_tc=source_in_tc,
                        source_out_tc=source_out_tc,
                        timeline_in_tc=timeline_in_tc,
                        timeline_out_tc=timeline_out_tc,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                        duration_seconds=duration
                    )
                    
                    shots.append(shot)
                    logger.debug(
                        f"  Shot {shot_number}: {timeline_in_tc}-{timeline_out_tc} "
                        f"({start_seconds:.2f}s - {end_seconds:.2f}s, {duration:.2f}s)"
                    )
        
        logger.info(f"[EDLParser] ✅ 解析完成：{len(shots)}个镜头")
        
        # 验证镜头连续性
        self._validate_continuity(shots)
        
        return shots
    
    def _timecode_to_seconds(self, timecode: str) -> float:
        """
        时间码转秒数
        
        格式: HH:MM:SS:FF
        例如: 00:00:05:16 → 0*3600 + 0*60 + 5 + 16/30 = 5.53秒
        
        Args:
            timecode: 时间码字符串
        
        Returns:
            秒数（浮点数）
        """
        try:
            parts = timecode.split(':')
            if len(parts) != 4:
                raise ValueError(f"时间码格式错误: {timecode}（期望HH:MM:SS:FF）")
            
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            frames = int(parts[3])
            
            total_seconds = hours * 3600 + minutes * 60 + seconds + frames / self.fps
            return total_seconds
        
        except Exception as e:
            logger.error(f"时间码解析失败: {timecode}, error={e}")
            raise ValueError(f"时间码解析失败: {timecode}") from e
    
    def _seconds_to_timecode(self, seconds: float) -> str:
        """
        秒数转时间码
        
        Args:
            seconds: 秒数
        
        Returns:
            时间码字符串（HH:MM:SS:FF）
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * self.fps)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def _validate_continuity(self, shots: List[EDLShot]) -> None:
        """
        验证镜头连续性
        
        检查：
        1. 镜头编号连续
        2. 时间码连续（前一镜头的出点 = 后一镜头的入点）
        """
        if not shots:
            return
        
        # 检查编号连续性
        for i, shot in enumerate(shots, 1):
            if shot.shot_number != i:
                logger.warning(
                    f"⚠️  镜头编号不连续: 期望{i}，实际{shot.shot_number}"
                )
        
        # 检查时间码连续性
        for i in range(len(shots) - 1):
            current_shot = shots[i]
            next_shot = shots[i + 1]
            
            # 允许0.1秒的误差（帧率转换误差）
            if abs(current_shot.end_seconds - next_shot.start_seconds) > 0.1:
                logger.warning(
                    f"⚠️  镜头{current_shot.shot_number}和{next_shot.shot_number}时间不连续: "
                    f"{current_shot.end_seconds:.2f}s → {next_shot.start_seconds:.2f}s "
                    f"(gap: {next_shot.start_seconds - current_shot.end_seconds:.2f}s)"
                )
        
        logger.info(f"[EDLParser] ✅ 连续性检查完成")
    
    def get_total_duration(self, shots: List[EDLShot]) -> float:
        """获取总时长"""
        if not shots:
            return 0.0
        return shots[-1].end_seconds
    
    def get_shot_by_time(self, shots: List[EDLShot], time_seconds: float) -> Optional[EDLShot]:
        """根据时间查找对应的镜头"""
        for shot in shots:
            if shot.start_seconds <= time_seconds < shot.end_seconds:
                return shot
        return None
    
    def filter_short_shots(
        self,
        shots: List[EDLShot],
        min_duration: float = 1.0
    ) -> List[EDLShot]:
        """
        过滤过短的镜头
        
        Args:
            min_duration: 最小时长（秒）
        
        Returns:
            过滤后的镜头列表
        """
        filtered = [shot for shot in shots if shot.duration_seconds >= min_duration]
        
        if len(filtered) < len(shots):
            logger.info(
                f"[EDLParser] 过滤掉{len(shots) - len(filtered)}个过短镜头（<{min_duration}s）"
            )
        
        return filtered


# ============================================================
# 辅助函数
# ============================================================

def parse_edl(edl_path: str, fps: int = 30) -> List[EDLShot]:
    """便捷函数：解析EDL文件"""
    parser = EDLParser(fps=fps)
    return parser.parse(edl_path)


def edl_to_simple_dict(shots: List[EDLShot]) -> List[Dict]:
    """将EDLShot转换为简单字典格式（用于JSON序列化）"""
    return [
        {
            "shot_number": shot.shot_number,
            "start_tc": shot.timeline_in_tc,
            "end_tc": shot.timeline_out_tc,
            "start_seconds": round(shot.start_seconds, 2),
            "end_seconds": round(shot.end_seconds, 2),
            "duration_seconds": round(shot.duration_seconds, 2)
        }
        for shot in shots
    ]
