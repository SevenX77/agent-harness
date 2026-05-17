---
schema_version: "2.1"
name: product-manual
description: "Generate consumer-facing product manuals from product specifications."
metadata:
  legacy_type: graph
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="extract_highlights" src="phases/extract_highlights" depends_on="" />
<phase id="write_scenarios" src="phases/write_scenarios" depends_on="extract_highlights" />
<phase id="synthesize_report" src="phases/synthesize_report" depends_on="write_scenarios" />
