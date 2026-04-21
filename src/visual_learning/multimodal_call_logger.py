"""
Multimodal Call Logger - 多模态调用日志系统

完整记录所有多模态 API 调用（视频理解 / 图片生成 / 图片编辑 / 视频生成）。
设计与 LLMCallLogger 对称，针对多模态特性适配：
  - 无 token，按次计费，记录 cost_usd
  - 异步任务分段耗时：submit_ms + poll_count + total_ms
  - 输出是 URL，不是文本
  - _model 字段记录内部实际使用的模型（对 Agent 不可见，仅供日志分析）

日志目录：data/logs/multimodal_calls/YYYY-MM-DD/
  - calls.log    ：人类可读的结构化日志
  - calls.jsonl  ：JSON Lines，每行一条完整记录
  - errors.jsonl ：仅包含失败/超时记录
"""

import json
import logging
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import config

_module_log = logging.getLogger(__name__)

# ── 成本参考表（实测，单位 USD）────────────────────────────────────────────────

_COST_TABLE: Dict[str, float] = {
    "seed18":            0.003,   # 估算，token-based，约 2000-5000 tokens/次
    "gemini_31_pro":     0.025,   # 估算，token-based
    "seedream_45":       0.04,    # 实测（火山方舟）
    "nano_banana_edit":  0.15,    # 实测（WaveSpeed）
    "seedance_v15_i2v":  0.26,    # 实测（WaveSpeed，5s 视频）
    "veo31_i2v":         3.20,    # 实测（WaveSpeed，8s + Foley）
    "veo31_ref2v":       3.20,    # 实测（WaveSpeed，8s + Foley）
}

_COST_BASIS: Dict[str, str] = {
    "seed18":            "token-based (~2000-5000 tokens/call)",
    "gemini_31_pro":     "token-based",
    "seedream_45":       "$0.04/call (Volcengine Seedream 4.5)",
    "nano_banana_edit":  "$0.15/call (WaveSpeed Nano Banana)",
    "seedance_v15_i2v":  "$0.26/call (WaveSpeed Seedance 5s)",
    "veo31_i2v":         "$3.20/call (WaveSpeed Veo 3.1 I2V 8s+audio)",
    "veo31_ref2v":       "$3.20/call (WaveSpeed Veo 3.1 Ref2V 8s+audio)",
}

# 敏感字段（自动脱敏）
_SENSITIVE_FIELDS = {"api_key", "apikey", "token", "secret", "password", "credential"}


# ── Logger 类 ──────────────────────────────────────────────────────────────────


class MultimodalCallLogger:
    """多模态调用日志记录器（单例）"""

    _instance: Optional["MultimodalCallLogger"] = None

    def __new__(cls) -> "MultimodalCallLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._base_dir = Path(config.base_dir) / "data" / "logs" / "multimodal_calls"
        self._initialized = True

    # ── 公开日志方法 ──────────────────────────────────────────────────────────

    def log_call(
        self,
        *,
        call_id: str,
        task_id: str,
        task_type: str,
        model: str,
        provider: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        execution: Dict[str, Any],
    ) -> None:
        """记录一次成功的多模态 API 调用"""
        if not config.multimodal_logging_enabled:
            return

        cost_usd = _COST_TABLE.get(model, 0.0)
        cost_basis = _COST_BASIS.get(model, "unknown")

        record: Dict[str, Any] = {
            "call_id": call_id,
            "task_id": task_id,
            "timestamp": _now_iso(),
            "task_type": task_type,
            "_model": model,
            "provider": provider,
            "request": self._sanitize(request),
            "response": response,
            "execution": {**execution, "status": "success"},
            "cost": {"estimated_usd": cost_usd, "basis": cost_basis},
        }

        log_file, jsonl_file, _ = self._get_log_files()

        if config.multimodal_log_format_enabled:
            self._write_log(log_file, self._format_success(record))

        if config.multimodal_jsonl_format_enabled:
            self._write_jsonl(jsonl_file, record)

    def log_error(
        self,
        *,
        call_id: str,
        task_id: str,
        task_type: str,
        model: Optional[str],
        provider: Optional[str],
        request: Dict[str, Any],
        error: Exception,
        stage: str,
        execution: Dict[str, Any],
    ) -> None:
        """记录一次失败/超时的多模态 API 调用"""
        if not config.multimodal_logging_enabled:
            return

        record: Dict[str, Any] = {
            "call_id": call_id,
            "task_id": task_id,
            "timestamp": _now_iso(),
            "task_type": task_type,
            "_model": model,
            "provider": provider,
            "request": self._sanitize(request),
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "stage": stage,
                "traceback": traceback.format_exc(),
            },
            "execution": {**execution, "status": _error_status(error)},
        }

        log_file, jsonl_file, error_file = self._get_log_files()

        if config.multimodal_log_format_enabled:
            self._write_log(log_file, self._format_error(record))

        if config.multimodal_jsonl_format_enabled:
            self._write_jsonl(jsonl_file, record)
            if config.multimodal_log_errors_separately:
                self._write_jsonl(error_file, record)

    # ── 私有工具方法 ──────────────────────────────────────────────────────────

    def _get_log_files(self, date: Optional[str] = None) -> Tuple[Path, Path, Path]:
        """返回 (calls.log, calls.jsonl, errors.jsonl) 路径，按需创建目录"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        day_dir = self._base_dir / date
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / "calls.log", day_dir / "calls.jsonl", day_dir / "errors.jsonl"

    def _sanitize(self, data: Any) -> Any:
        """递归脱敏：对敏感字段保留前4位和后4位，中间替换为 ****"""
        if isinstance(data, dict):
            return {
                k: (
                    _mask(v)
                    if any(s in k.lower() for s in _SENSITIVE_FIELDS) and isinstance(v, str)
                    else self._sanitize(v)
                )
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self._sanitize(item) for item in data]
        return data

    def _write_log(self, path: Path, content: str) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content + "\n")
        except Exception as e:
            _module_log.warning("multimodal_call_logger: 写入 .log 失败: %s", e)

    def _write_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, default=str)
                f.write("\n")
        except Exception as e:
            _module_log.warning("multimodal_call_logger: 写入 .jsonl 失败: %s", e)

    @staticmethod
    def _format_success(r: Dict[str, Any]) -> str:
        exec_info = r.get("execution", {})
        total_s = exec_info.get("total_ms", 0) / 1000
        submit_s = exec_info.get("submit_ms")
        poll_count = exec_info.get("poll_count")
        cost = r.get("cost", {})
        resp = r.get("response", {})

        submit_line = ""
        if submit_s is not None:
            submit_line = f"\n  async     : submit={submit_s/1000:.1f}s  polls={poll_count}"

        output_line = ""
        if resp.get("output_url"):
            output_line = f"\n  output    : {resp['output_url']}"
        elif resp.get("output_text"):
            preview = (resp["output_text"] or "")[:120].replace("\n", " ")
            output_line = f"\n  output    : [{len(resp['output_text'])} chars] {preview}..."

        return (
            f"[{r['timestamp']}] CALL_START  call_id={r['call_id']} task_id={r['task_id']}\n"
            f"  task_type : {r['task_type']}\n"
            f"  _model    : {r['_model']}  (provider={r['provider']})\n"
            f"  request   : {_fmt_request(r.get('request', {}))}\n"
            f"[{_now_short()}] CALL_SUCCESS call_id={r['call_id']}  total={total_s:.1f}s"
            f"{submit_line}"
            f"{output_line}\n"
            f"  cost      : ~${cost.get('estimated_usd', 0):.3f}  ({cost.get('basis', '')})\n"
            "---"
        )

    @staticmethod
    def _format_error(r: Dict[str, Any]) -> str:
        exec_info = r.get("execution", {})
        total_s = exec_info.get("total_ms", 0) / 1000
        err = r.get("error", {})
        return (
            f"[{r['timestamp']}] CALL_START  call_id={r['call_id']} task_id={r['task_id']}\n"
            f"  task_type : {r['task_type']}\n"
            f"  _model    : {r.get('_model', 'N/A')}  (provider={r.get('provider', 'N/A')})\n"
            f"  request   : {_fmt_request(r.get('request', {}))}\n"
            f"[{_now_short()}] CALL_FAILED  call_id={r['call_id']}  "
            f"total={total_s:.1f}s  status={exec_info.get('status', 'failed')}\n"
            f"  error     : {err.get('type')}  stage={err.get('stage')}  {err.get('message', '')}\n"
            "---"
        )


# ── 全局单例 ───────────────────────────────────────────────────────────────────

call_logger = MultimodalCallLogger()


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def new_call_id() -> str:
    return str(uuid.uuid4())


# ── 查询接口 ───────────────────────────────────────────────────────────────────


def query_calls(
    start_date: str,
    end_date: Optional[str] = None,
    status: str = "all",
    task_type: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    按日期范围查询调用记录（从 calls.jsonl 读取）。

    Args:
        start_date: "YYYY-MM-DD"
        end_date:   "YYYY-MM-DD"，默认与 start_date 相同
        status:     "success" | "failed" | "timeout" | "all"
        task_type:  "video_understanding" | "image_generation" | "image_editing" | "video_generation" | None
        model:      内部模型名（如 "seedance_v15_i2v"）或 None
    """
    if end_date is None:
        end_date = start_date

    base_dir = Path(config.base_dir) / "data" / "logs" / "multimodal_calls"
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    results: List[Dict[str, Any]] = []
    current = start
    while current <= end:
        jsonl = base_dir / current.strftime("%Y-%m-%d") / "calls.jsonl"
        if jsonl.exists():
            with open(jsonl, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    exec_status = record.get("execution", {}).get("status", "")
                    if status != "all" and exec_status != status:
                        continue
                    if task_type and record.get("task_type") != task_type:
                        continue
                    if model and record.get("_model") != model:
                        continue
                    results.append(record)
        current = current.replace(day=current.day + 1) if current.day < 28 else _next_day(current)

    return results


def query_task_calls(task_id: str, include_errors: bool = True) -> List[Dict[str, Any]]:
    """查询特定 task_id 的所有调用记录（扫描最近30天的日志）"""
    today = datetime.now()
    results: List[Dict[str, Any]] = []
    base_dir = Path(config.base_dir) / "data" / "logs" / "multimodal_calls"

    for day_dir in sorted(base_dir.iterdir(), reverse=True)[:30]:
        if not day_dir.is_dir():
            continue
        jsonl = day_dir / "calls.jsonl"
        if not jsonl.exists():
            continue
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("task_id") != task_id:
                    continue
                exec_status = record.get("execution", {}).get("status", "")
                if not include_errors and exec_status in ("failed", "timeout"):
                    continue
                results.append(record)

    return sorted(results, key=lambda r: r.get("timestamp", ""))


def get_call_statistics(
    start_date: str,
    end_date: Optional[str] = None,
    group_by: str = "task_type",
) -> Dict[str, Any]:
    """
    获取统计信息。

    Args:
        group_by: "task_type" | "model" | "provider"

    Returns:
        各分组的统计数据，包含：total_calls, success_calls, failed_calls,
        total_cost_usd, avg_total_ms, model_distribution（group_by=task_type时）
    """
    all_calls = query_calls(start_date, end_date)

    groups: Dict[str, Dict[str, Any]] = {}

    for record in all_calls:
        key = record.get(
            "_model" if group_by == "model" else group_by,
            "unknown"
        )
        if key not in groups:
            groups[key] = {
                "total_calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "total_cost_usd": 0.0,
                "total_ms_sum": 0,
                "model_distribution": {},
            }
        g = groups[key]
        g["total_calls"] += 1

        exec_status = record.get("execution", {}).get("status", "")
        if exec_status == "success":
            g["success_calls"] += 1
        else:
            g["failed_calls"] += 1

        g["total_cost_usd"] += record.get("cost", {}).get("estimated_usd", 0.0)
        g["total_ms_sum"] += record.get("execution", {}).get("total_ms", 0)

        if group_by == "task_type":
            m = record.get("_model", "unknown")
            g["model_distribution"][m] = g["model_distribution"].get(m, 0) + 1

    # 后处理：计算均值，删除中间字段
    for g in groups.values():
        total = g["total_calls"]
        g["avg_total_ms"] = round(g["total_ms_sum"] / total) if total > 0 else 0
        del g["total_ms_sum"]
        g["total_cost_usd"] = round(g["total_cost_usd"], 4)

    return groups


# ── 内部工具 ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _now_short() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _error_status(error: Exception) -> str:
    from src.core.exceptions import TaskTimeoutError

    return "timeout" if isinstance(error, TaskTimeoutError) else "failed"


def _fmt_request(req: Dict[str, Any]) -> str:
    """生成请求摘要，用于 .log 文件的单行展示"""
    parts = []
    for key in ("prompt", "question", "video_source", "image_url", "images", "size", "duration", "quality"):
        val = req.get(key)
        if val is None:
            continue
        if isinstance(val, str) and len(val) > 60:
            val = val[:57] + "..."
        parts.append(f'{key}={json.dumps(val, ensure_ascii=False)}')
    return "  ".join(parts) if parts else str(req)


def _next_day(d: datetime) -> datetime:
    """跨月日期递进"""
    from datetime import timedelta

    return d + timedelta(days=1)
