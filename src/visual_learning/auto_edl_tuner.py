"""
自动EDL参数调优器

通过对比GT EDL自动找到最佳参数组合
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple
from .auto_edl_generator import AutoEDLGenerator
from .edl_parser import EDLParser

logger = logging.getLogger(__name__)


class AutoEDLTuner:
    """自动调优EDL生成参数"""
    
    def __init__(self):
        self.parser = EDLParser(fps=30)
    
    def find_best_params(
        self,
        video_path: str,
        gt_edl_path: str,
        output_dir: str
    ) -> Dict:
        """
        自动寻找最佳参数
        
        策略：
        1. 尝试多种threshold值（25-50，步长5）
        2. 尝试多种min_shot_duration值（1.5-6.0，步长0.5）
        3. 选择镜头数量最接近GT的组合
        """
        logger.info("[AutoEDLTuner] 开始参数搜索...")
        
        # 解析GT
        gt_shots = self.parser.parse(gt_edl_path)
        gt_count = len(gt_shots)
        
        logger.info(f"[Target] GT镜头数: {gt_count}")
        
        # 参数搜索空间
        thresholds = [30, 33, 36, 39, 42]
        merge_durations = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
        
        best_params = None
        best_diff = float('inf')
        best_gen_count = 0
        
        results = []
        
        output_path = Path(output_dir) / "temp_test.edl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        total_tests = len(thresholds) * len(merge_durations)
        test_num = 0
        
        for threshold in thresholds:
            for merge_dur in merge_durations:
                test_num += 1
                
                try:
                    # 生成EDL
                    generator = AutoEDLGenerator(fps=30, threshold=threshold)
                    generator.generate_edl(
                        video_path=video_path,
                        output_edl_path=str(output_path),
                        min_scene_length=30,
                        merge_short_scenes=True,
                        min_shot_duration=merge_dur
                    )
                    
                    # 解析生成的EDL
                    gen_shots = self.parser.parse(str(output_path))
                    gen_count = len(gen_shots)
                    
                    # 计算差异
                    diff = abs(gen_count - gt_count)
                    
                    results.append({
                        'threshold': threshold,
                        'merge_duration': merge_dur,
                        'gen_count': gen_count,
                        'diff': diff
                    })
                    
                    # 更新最佳参数
                    if diff < best_diff:
                        best_diff = diff
                        best_params = {
                            'threshold': threshold,
                            'merge_duration': merge_dur
                        }
                        best_gen_count = gen_count
                    
                    status = "✅" if diff == 0 else f"±{diff}"
                    logger.info(
                        f"[{test_num}/{total_tests}] threshold={threshold}, merge={merge_dur:.1f}s "
                        f"→ {gen_count}个镜头 {status}"
                    )
                    
                    # 如果找到完美匹配，提前结束
                    if diff == 0:
                        logger.info(f"🎉 找到完美匹配的参数！")
                        break
                
                except Exception as e:
                    logger.error(f"[{test_num}/{total_tests}] 测试失败: {e}")
            
            if best_diff == 0:
                break
        
        # 输出结果
        logger.info("\n" + "="*60)
        logger.info("参数搜索结果")
        logger.info("="*60)
        logger.info(f"GT镜头数: {gt_count}")
        logger.info(f"\n最佳参数:")
        logger.info(f"  threshold: {best_params['threshold']}")
        logger.info(f"  min_shot_duration: {best_params['merge_duration']:.1f}s")
        logger.info(f"  生成镜头数: {best_gen_count}")
        logger.info(f"  差异: {best_diff}个镜头")
        
        if best_diff == 0:
            logger.info(f"\n🎉 完美匹配！")
        else:
            logger.info(f"\n⚠️  最接近的结果差异{best_diff}个镜头")
            
            # 显示接近的结果
            close_results = [r for r in results if r['diff'] <= best_diff + 1]
            logger.info(f"\n接近的参数组合（差异≤{best_diff+1}）:")
            for r in sorted(close_results, key=lambda x: x['diff']):
                logger.info(
                    f"  threshold={r['threshold']}, merge={r['merge_duration']:.1f}s "
                    f"→ {r['gen_count']}个 (±{r['diff']})"
                )
        
        return {
            'best_params': best_params,
            'best_diff': best_diff,
            'best_gen_count': best_gen_count,
            'gt_count': gt_count,
            'all_results': results
        }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    project_root = Path(__file__).parent.parent.parent.parent
    
    video_path = project_root / "raw_data" / "没有原小说" / "005_末世寒潮" / "video" / "ep05.mp4"
    gt_edl = project_root / "raw_data" / "没有原小说" / "005_末世寒潮" / "edl" / "mshc_ep05.edl"
    output_dir = project_root / "outputs" / "edl_tuning"
    
    tuner = AutoEDLTuner()
    result = tuner.find_best_params(
        video_path=str(video_path),
        gt_edl_path=str(gt_edl),
        output_dir=str(output_dir)
    )
