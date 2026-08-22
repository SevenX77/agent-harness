/** Which images this turn will carry, decided at the moment they are picked.
 *
 * Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
 * decision COPILOT_ASSIST-11.
 *
 * Pure: reading a `File` off the clipboard or the file dialog happens in the
 * component; everything that decides yes-or-no happens here, on plain bytes.
 */
import type { CopilotImageAttachment } from '../../../types/copilot'

/**
 * How many bytes of image one turn may carry, before base64.
 *
 * The whole turn — message, mentions and images — leaves in ONE WebSocket
 * frame, and uvicorn caps a frame at 16 MiB (`ws_max_size`, default
 * `16 * 1024 * 1024`). Going over is not an error the user sees: the connection
 * is closed and the message disappears without explanation. Base64 inflates
 * bytes by 4/3, so 8 MB of image encodes to about 10.7 MiB and leaves the
 * sentence and its mentions plenty of room inside the frame.
 *
 * The backend enforces the same number on the boundary
 * (`app/models/copilot.py::TURN_IMAGE_BUDGET_BYTES`), and a test there reads
 * this line to assert the two have not drifted apart.
 */
export const TURN_IMAGE_BUDGET_BYTES = 8 * 1024 * 1024

/** The four the wire has a word for — `CopilotImageAttachment.media_type`. */
export const SUPPORTED_IMAGE_TYPES = [
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
] as const

type SupportedImageType = (typeof SUPPORTED_IMAGE_TYPES)[number]

export interface IncomingImage {
  name: string
  mediaType: string
  bytes: Uint8Array
}

export type AttachmentRefusal =
  | { reason: 'unsupported_type'; mediaType: string }
  | { reason: 'over_turn_budget'; totalBytes: number; budgetBytes: number }

export interface RefusedImage {
  name: string
  refusal: AttachmentRefusal
}

export interface AttachmentIntake {
  /** What the turn now carries — the ones already attached, plus what fit. */
  accepted: CopilotImageAttachment[]
  /** The ones that did not, each with the reason to show the user. */
  refused: RefusedImage[]
}

/** How many bytes a base64 string decodes to, without decoding it. */
export function decodedByteLength(base64: string): number {
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0
  return (base64.length * 3) / 4 - padding
}

function toBase64(bytes: Uint8Array): string {
  // Chunked because `String.fromCharCode(...bytes)` on a multi-megabyte array
  // blows the argument limit — the failure is a RangeError deep in the browser,
  // not something the caller could diagnose.
  const CHUNK = 0x8000
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + CHUNK))
  }
  return btoa(binary)
}

function isSupported(mediaType: string): mediaType is SupportedImageType {
  return (SUPPORTED_IMAGE_TYPES as readonly string[]).includes(mediaType)
}

/**
 * Add the picked images to what is already attached.
 *
 * A refusal never disturbs what was already there, and never stops a sibling
 * that fits: one file dialog can hand over several files and only one of them
 * be wrong. Nothing is resized or re-encoded to make it fit — a smaller picture
 * is a different picture, and the user may be asking about the pixel that
 * shrinking would erase (COPILOT_ASSIST-11 ③).
 */
export function admitAttachments(
  existing: readonly CopilotImageAttachment[],
  incoming: readonly IncomingImage[],
): AttachmentIntake {
  const accepted = [...existing]
  const refused: RefusedImage[] = []
  let spent = existing.reduce((total, item) => total + decodedByteLength(item.data), 0)

  for (const image of incoming) {
    if (!isSupported(image.mediaType)) {
      refused.push({
        name: image.name,
        refusal: { reason: 'unsupported_type', mediaType: image.mediaType },
      })
      continue
    }
    const wouldBe = spent + image.bytes.length
    if (wouldBe > TURN_IMAGE_BUDGET_BYTES) {
      refused.push({
        name: image.name,
        refusal: {
          reason: 'over_turn_budget',
          totalBytes: wouldBe,
          budgetBytes: TURN_IMAGE_BUDGET_BYTES,
        },
      })
      continue
    }
    spent = wouldBe
    accepted.push({
      kind: 'image',
      media_type: image.mediaType,
      data: toBase64(image.bytes),
      name: image.name,
    })
  }

  return { accepted, refused }
}
