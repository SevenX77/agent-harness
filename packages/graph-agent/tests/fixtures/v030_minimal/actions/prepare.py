def run(data: dict, *, phase_id: str, run_id: str | None = None) -> dict:
    del phase_id, run_id
    return {"prepared_topic": data["topic"].strip()}

