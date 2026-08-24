import { useTranslation } from 'react-i18next'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'

interface CommunitySharingConsentDialogProps {
  open: boolean
  onShare: () => void
  onDecline: () => void
}

/**
 * First-run community-sharing consent dialog (docs/studio/mvp1/01_workflows/00_settings.md §3.0).
 *
 * Fires once, exactly when `AppSettings.community_sharing_choice === "unset"` —
 * never asked before. Both buttons are a valid, final answer ("shared" or
 * "declined"); there is no third way to dismiss it, because an unanswered
 * dialog would leave the choice ambiguous forever. Per that same design,
 * closing is intentionally NOT wired to Escape / an outside click / an X
 * button (`showCloseButton={false}`, no `onOpenChange` — the same pattern
 * `ConflictDialog` already uses in this codebase for a must-answer dialog):
 * Radix's Dialog.Root treats `open` as fully controlled when no `onOpenChange`
 * is supplied, so its internal dismiss handlers have nothing to call and the
 * dialog only closes when the parent's `open` prop itself changes — which
 * here only happens once `community_sharing_choice` leaves "unset".
 *
 * The title/body/button copy is a consent statement cross-checked word-for-word
 * against the upload allowlist (`EvidenceUpload` in
 * packages/graph-agent-gateway/src/graph_agent_gateway/registry/evidence_wire.py)
 * and the public-host filter (`is_safe_to_publish`) — do not edit the wording
 * here; a wording change must go through that same cross-check.
 */
export function CommunitySharingConsentDialog({ open, onShare, onDecline }: CommunitySharingConsentDialogProps) {
  const { t } = useTranslation('settings')

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        data-testid="community-sharing-consent-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t('communitySharingConsent.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription
          className="whitespace-pre-line text-foreground"
          data-testid="community-sharing-consent-body"
        >
          {t('communitySharingConsent.body')}
        </DialogDescription>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDecline}>
            {t('communitySharingConsent.secondaryButton')}
          </Button>
          <Button type="button" onClick={onShare}>
            {t('communitySharingConsent.primaryButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
