---
schema_version: "2.1"
name: text-segmentation
description: "ABC paragraph segmentation with Two-Pass validation."
metadata:
  legacy_type: graph
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" />
<phase id="segment" src="phases/segment" depends_on="setup" />
<phase id="review" src="phases/review" depends_on="segment" />
