---
# frontmatter comment stays with YAML
schema_version: "2.1"
name: with-comments-v21
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<!-- prepare attachment -->
Prepare prose belongs to prepare.
<phase id="prepare" src="phases/prepare" depends_on="" />
<!-- branch attachment -->
Branch prose belongs to branch.
<phase id="branch" src="phases/branch" depends_on="prepare" />
<!-- assemble attachment -->
Assemble prose belongs to assemble.
<phase id="assemble" src="phases/assemble" depends_on="branch" />
<!-- global footer -->
Footer prose remains.
