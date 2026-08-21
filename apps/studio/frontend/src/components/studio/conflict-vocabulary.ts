/**
 * One vocabulary for every conflict Studio raises.
 *
 * Studio has two places where it stops and asks "this would overwrite
 * something — proceed?": the file-save conflict dialog in the editor, and the
 * sequential-overwrite popover anchored on a canvas node. They stay two
 * containers on purpose — the save conflict blocks a pending write and must be
 * answered now, while the canvas conflict has to stay pinned to the node it is
 * about — and the design source says so in as many words: "canvas popovers,
 * editor conflict dialogs, and compile drawer should use the same conflict
 * severity/copy vocabulary"
 * (`docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md` F3).
 *
 * What must not differ is the words. Before this table the same decision was
 * offered as "Allow Overwrite / Cancel" in one place and "Overwrite/Retry Save
 * / Keep Local" in the other, so a user had to learn twice that the affirmative
 * button is the destructive one. Both titles are written here side by side for
 * the same reason: kept together, they stay one grammar — "<what> would be
 * overwritten" — and a new conflict surface has an existing sentence to copy
 * instead of a fresh invention.
 */

export const CONFLICT_VERB = {
  /** Proceed: let the write land on top of what is already there. */
  overwrite: 'Overwrite',
  /** Decline: nothing is written, the conflict stays unresolved. */
  cancel: 'Cancel',
  /** Save-conflict only — an upstream output has no "remote" version to take. */
  useRemote: 'Use Remote',
  /** Save-conflict only — the canvas conflict has no two texts to compare. */
  viewDiff: 'View Diff',
} as const

export const CONFLICT_TITLE = {
  fileSave: 'Remote changes would be overwritten',
  sequentialOverwrite: 'An upstream output would be overwritten',
} as const

/** The one severity treatment both conflict surfaces mark themselves with. */
export const CONFLICT_ICON_CLASS = 'size-4 shrink-0 text-warning'
