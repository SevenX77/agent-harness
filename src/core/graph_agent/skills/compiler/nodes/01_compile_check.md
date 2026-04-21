<phase_config>
name: compile_check
max_iterations: 1
requires_llm: false
tools:
  - script.compile.compile_skill
</phase_config>

<system_prompt>
执行静态编译检查。
</system_prompt>

<user_prompt>
检查目标 Skill: {skill_path}
</user_prompt>
