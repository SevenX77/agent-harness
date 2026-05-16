---
schema_version: "2.1"
name: batch-analysis
description: "Analyze a batch across entity, narrative, continuity, and accumulator dimensions."
metadata:
  legacy_type: graph
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="prepare" src="phases/prepare" depends_on="" />
<phase id="entity_and_characters" src="phases/entity_and_characters" depends_on="prepare" />
<phase id="parallel_analysis" src="phases/parallel_analysis" depends_on="prepare" />
<phase id="continuity" src="phases/continuity" depends_on="prepare" />
<phase id="assemble" src="phases/assemble" depends_on="entity_and_characters,parallel_analysis,continuity" />
