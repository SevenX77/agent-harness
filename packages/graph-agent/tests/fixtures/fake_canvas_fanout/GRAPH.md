---
schema_version: "2.1"
name: fake-canvas-fanout
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="prepare" src="phases/prepare" depends_on="" />
<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />
<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />
<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />
