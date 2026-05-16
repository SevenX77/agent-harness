---
schema_version: "2.1"
name: hello-world
description: "Minimal V2.1 smoke fixture for parser, tools, and finish_task."
metadata:
  legacy_type: simple
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="greet" src="phases/greet" depends_on="" />
