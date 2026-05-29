def score(context):
    segments = context["segments"]
    return {"report": f"scored {len(segments)} segments"}
