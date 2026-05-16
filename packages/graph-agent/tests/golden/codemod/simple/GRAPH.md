---
schema_version: '2.1'
name: hello-world
description: 最简单的打招呼 skill
metadata:
  legacy_type: simple
  context_mapping: {}
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="greet" src="phases/greet" depends_on="" />
