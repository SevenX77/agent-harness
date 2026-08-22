/** When a key press means "send this message".
 *
 * Lives in its own module because both the panel and the editor plugin ask, and
 * the answer must be the same one in both places: the composer used to be a
 * `<textarea>` reading React's synthetic event, and is now a ProseMirror
 * `handleKeyDown` reading the native one. Two copies of this rule would drift
 * the day one of them forgot the IME guard.
 */
export interface ComposerKeyEvent {
  key: string
  shiftKey: boolean
  /**
   * True while an input method is still composing a character.
   *
   * The guard is not a nicety: typing Chinese, Enter is how you ACCEPT the
   * candidate the IME is offering. Sending on that Enter cuts the word in half
   * and fires a half-written message.
   */
  isComposing: boolean
}

export function isComposerSendKey(event: ComposerKeyEvent): boolean {
  return event.key === 'Enter' && !event.shiftKey && !event.isComposing
}
