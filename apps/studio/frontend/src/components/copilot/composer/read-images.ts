/** Getting the bytes out of what the user handed over.
 *
 * The one IO step of attaching: a `File` from the clipboard or the file dialog
 * becomes plain bytes, and every decision about them happens in
 * `attachment-intake.ts`, which is pure.
 */
import type { IncomingImage } from './attachment-intake'

/** Read each picked file into memory, in the order they were picked. */
export async function readIncomingImages(files: readonly File[]): Promise<IncomingImage[]> {
  return Promise.all(
    files.map(async (file) => ({
      name: file.name,
      mediaType: file.type,
      bytes: new Uint8Array(await file.arrayBuffer()),
    })),
  )
}

/** The image files on a clipboard payload, if any. */
export function imageFilesFromClipboard(data: DataTransfer | null): File[] {
  if (!data) return []
  return [...data.files].filter((file) => file.type.startsWith('image/'))
}
