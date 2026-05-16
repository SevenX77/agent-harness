---
schema_version: "2.1"
name: producer
description: "Actor-Critic producer persona review for audience-attention quality gates."
metadata:
  legacy_type: persona
  review_subskill_internalized: true
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="producer" src="phases/producer" depends_on="" />
