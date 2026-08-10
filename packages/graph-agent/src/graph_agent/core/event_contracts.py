from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SENSITIVE_DETAIL_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "secret",
        "token",
        "traceback",
    }
)


def _contains_sensitive_error_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "api_key",
            "apikey",
            "authorization",
            "secret",
            "sk-",
            "token",
            "traceback",
        )
    )


def _sanitize_error_details(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_DETAIL_KEYS or _contains_sensitive_error_text(normalized):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize_error_details(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_error_details(item) for item in value]
    if isinstance(value, str) and _contains_sensitive_error_text(value):
        return "[redacted]"
    return value


def _sanitize_error_message(value: Any) -> Any:
    if isinstance(value, str) and _contains_sensitive_error_text(value):
        return "[redacted]"
    return value


class StreamCursor(BaseModel):
    model_config = ConfigDict(frozen=True)
    stream_id: str
    cursor: str
    next_seq: int
    window_start_seq: int


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = "studio.event.v1"
    stream_id: str
    seq: int
    run_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cursor: str
    timestamp: datetime
    error_code: str | None = None
    error_payload: TransportErrorPayload | None = None


class DeltaEnvelope(BaseModel):
    """One piece of a step's output, on its way to whoever is watching.

    It deliberately has no ``seq`` and no ``cursor``. Those two are what make a
    frame replayable — a reader who dropped off asks for everything after
    number N — and that only works while every number exists. A delta may be
    merged with its neighbour or dropped when a watcher falls behind, so
    numbering it would turn every permitted drop into a hole the reader reports
    as data loss. Nothing is lost by leaving them off: the text spelled out
    here is written whole, once, on the step's closing frame, which does carry
    a number.

    ``step_id`` is what makes a piece usable at all. An agent turn runs several
    calls at once, so a piece that cannot name its call cannot be shown.
    """

    model_config = ConfigDict(frozen=True)
    schema_version: str = "studio.delta.v1"
    stream_id: str
    run_id: str
    step_id: str
    channel: str
    text: str = ""
    restarts_step: bool = False
    timestamp: datetime


class TransportErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool

    @field_validator("message", mode="before")
    @classmethod
    def sanitize_message(cls, value: Any) -> Any:
        return _sanitize_error_message(value)

    @field_validator("details", mode="before")
    @classmethod
    def sanitize_details(cls, value: Any) -> Any:
        sanitized = _sanitize_error_details(value)
        return sanitized if isinstance(sanitized, dict) else {}


class ResponseEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str
    ok: bool
    data: Any | None = None
    error_code: str | None = None
    error_payload: TransportErrorPayload | None = None

    @field_validator("error_payload")
    @classmethod
    def validate_error_payload(cls, v: Any) -> Any:
        if v is not None and not isinstance(v, TransportErrorPayload):
            raise ValueError("error_payload must be a TransportErrorPayload")
        return v


def make_event_envelope(
    *,
    stream_id: str,
    seq: int,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    cursor: str | None = None,
    timestamp: datetime | None = None,
    schema_version: str = "studio.event.v1",
    error_code: str | None = None,
    error_payload: TransportErrorPayload | None = None,
) -> EventEnvelope:
    if cursor is None:
        cursor = f"{stream_id}:{seq}"
    if timestamp is None:
        timestamp = datetime.now(UTC)
    return EventEnvelope(
        schema_version=schema_version,
        stream_id=stream_id,
        seq=seq,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        cursor=cursor,
        timestamp=timestamp,
        error_code=error_code,
        error_payload=error_payload,
    )


def success_response(data: Any, *, schema_version: str = "engine.response.v1") -> ResponseEnvelope:
    return ResponseEnvelope(
        schema_version=schema_version,
        ok=True,
        data=data,
        error_code=None,
        error_payload=None,
    )


def error_response(error: TransportErrorPayload, *, schema_version: str = "engine.response.v1") -> ResponseEnvelope:
    return ResponseEnvelope(
        schema_version=schema_version,
        ok=False,
        data=None,
        error_code=error.error_code,
        error_payload=error,
    )


class EventStreamResumeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    events: list[EventEnvelope]
    next_cursor: str | None


class StreamCursorGapError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "stream.cursor_gap"


class StreamCursorExpiredError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "stream.cursor_expired"


class StreamBackpressureError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "stream.backpressure"


class StreamOutOfOrderError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "stream.out_of_order"


class EventStreamBuffer:
    def __init__(self, *, stream_id: str, capacity: int) -> None:
        self.stream_id = stream_id
        self.capacity = capacity
        self.events: dict[int, EventEnvelope] = {}
        self.evicted_seqs: set[int] = set()

    def append(self, event: EventEnvelope) -> None:
        if event.stream_id != self.stream_id:
            raise ValueError(f"stream_id mismatch: expected {self.stream_id}, got {event.stream_id}")

        if event.seq in self.events or event.seq in self.evicted_seqs:
            # Idempotent deduplication
            return

        if self.events:
            max_seq = max(self.events.keys())
            if event.seq > max_seq:
                if event.seq != max_seq + 1:
                    raise StreamCursorGapError(f"Gap detected: expected {max_seq + 1}, got {event.seq}")

        if len(self.events) >= self.capacity:
            if self.capacity == 1:
                raise StreamBackpressureError("Stream capacity reached")
            # Evict oldest event
            min_s = min(self.events.keys())
            self.events.pop(min_s)
            self.evicted_seqs.add(min_s)

        self.events[event.seq] = event

    def resume(self, *, cursor: str | None) -> EventStreamResumeResult:
        if cursor is None:
            sorted_events = [self.events[s] for s in sorted(self.events.keys())]
            next_cursor = sorted_events[-1].cursor if sorted_events else None
            return EventStreamResumeResult(events=sorted_events, next_cursor=next_cursor)

        try:
            parts = cursor.split(":")
            N = int(parts[-1])
        except Exception as err:
            raise ValueError(f"Invalid cursor format: {cursor}") from err

        if self.events:
            min_seq = min(self.events.keys())
            if N < min_seq - 1:
                raise StreamCursorExpiredError(f"Cursor expired: requested seq > {N}, but min available is {min_seq}")

            res_events = [self.events[s] for s in sorted(self.events.keys()) if s > N]
            next_cursor = res_events[-1].cursor if res_events else cursor
            return EventStreamResumeResult(events=res_events, next_cursor=next_cursor)

        return EventStreamResumeResult(events=[], next_cursor=cursor)
