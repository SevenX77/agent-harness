/**
 * What the New Skill wizard opens the conversation with.
 *
 * The wizard itself — the four beats, which knowledge to open when, the starter
 * shapes — lives in the `brainstorming` skill asset shipped with the backend
 * (`app/agents/skills/brainstorming/`), not here. This is only the opening
 * line: it names the skill being built and hands the conversation to that
 * asset. Restating the method here would put the same instructions in two
 * places, and the copy in the UI bundle would be the one nobody updates.
 *
 * Design: copilot-assist/mvp1-alignment.md F6.
 */

export function buildSkillWizardDraft(skill: { skillId: string }): string {
  return [
    `用 brainstorming 技能带我把「${skill.skillId}」这个 skill 设计出来。`,
    '',
    '它现在是个空壳,我还没想清楚要怎么搭。请**一次问一个问题**,',
    '别一口气丢给我一张表格;每问清一步就把结论说回来让我确认。',
    '',
    '最后要落到盘上并且能编译通过——不要只在对话里给我一份设计。',
  ].join('\n')
}
