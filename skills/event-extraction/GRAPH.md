---
schema_version: "2.1"
name: event-extraction
description: "Extract event timeline from ABC-segmented paragraphs."
metadata:
  legacy_type: graph
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" depends_on="" />
<phase id="aggregate" src="phases/aggregate" depends_on="setup" />
<phase id="review" src="phases/review" depends_on="aggregate" />
<phase id="settings" src="phases/settings" depends_on="review" />
