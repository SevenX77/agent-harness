/**
 * What the New Skill wizard opens the conversation with.
 *
 * Written the way a real new user would ask (用户裁决 2026-08-27): it names the
 * skill being built and what the person wants, and deliberately does NOT name
 * any agent-skill asset. Which asset hosts the conversation (the shipped
 * `brainstorming` skill, `app/agents/skills/brainstorming/`) is the agent's own
 * call, routed by that asset's description — the same description matching the
 * chat entry ("help me build an X") already relies on. A canned opener that
 * named the asset would exercise a routing path no real user's prompt takes,
 * masking description-matching failures.
 *
 * Design: copilot-assist/mvp1-alignment.md F6.
 */

export function buildSkillWizardDraft(skill: { skillId: string }): string {
  return [
    `我想做一个叫「${skill.skillId}」的 skill,现在它还是个空壳,我也没想清楚要怎么搭,`,
    '带我把它设计出来吧。请**一次问一个问题**,',
    '别一口气丢给我一张表格;每问清一步就把结论说回来让我确认。',
    '',
    '最后要落到盘上并且能编译通过——不要只在对话里给我一份设计。',
  ].join('\n')
}
