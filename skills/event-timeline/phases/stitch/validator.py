from __future__ import annotations


def _event_identity_set(event: dict) -> set[str]:
    identities = set()
    event_id = event.get("event_id")
    if event_id:
        identities.add(str(event_id))

    source_event_ids = event.get("source_event_ids") or []
    if isinstance(source_event_ids, str):
        source_event_ids = [source_event_ids]
    for source_event_id in source_event_ids:
        if source_event_id:
            identities.add(str(source_event_id))
    return identities


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Validate stitched timeline shape, growth, ordering, and chapter monotonicity."""
    stitched_timeline = output.get("stitched_timeline") or {}
    events = stitched_timeline.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("stitched_timeline.events must be a non-empty array")

    previous_events = (state_slice.get("global_timeline") or {}).get("events") or []
    if len(events) < len(previous_events):
        raise ValueError(
            "stitched_timeline.events must not be shorter than accumulated global_timeline.events"
        )

    current_events = (
        state_slice.get("current_chapter_timeline") or {}
    ).get("events") or []
    stitched_event_ids = set()
    for event in events:
        stitched_event_ids.update(_event_identity_set(event))

    missing_current_event_ids = []
    for event in current_events:
        event_id = event.get("event_id")
        if not event_id:
            raise ValueError("current_chapter_timeline event missing event_id")
        if str(event_id) not in stitched_event_ids:
            missing_current_event_ids.append(str(event_id))

    if missing_current_event_ids:
        missing = ", ".join(missing_current_event_ids)
        raise ValueError(
            f"stitched_timeline missing current chapter event ids: {missing}"
        )

    previous_order = None
    seen_orders = set()
    previous_chapter = None

    for index, event in enumerate(events):
        order = event.get("global_order")
        if not isinstance(order, int):
            raise ValueError(f"event at index {index} has non-integer global_order")
        if order in seen_orders:
            raise ValueError(f"duplicate global_order: {order}")
        if previous_order is not None and order <= previous_order:
            raise ValueError("global_order must be strictly increasing")
        seen_orders.add(order)
        previous_order = order

        chapter_number = event.get("chapter_number")
        if not isinstance(chapter_number, int):
            raise ValueError(f"event at index {index} missing integer chapter_number")
        if previous_chapter is not None and chapter_number < previous_chapter:
            raise ValueError("chapter_number must not move backward across chapters")
        previous_chapter = chapter_number

    return {"stitched_timeline": stitched_timeline, "global_timeline": stitched_timeline}
