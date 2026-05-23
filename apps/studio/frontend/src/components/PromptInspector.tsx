import { CheckCircle, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { eventPhase, jsonText } from '../utils/trace'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'

interface PromptInspectorProps {
  promptEvent: CallbackEvent | null
  onClose: () => void
}

type InspectorTab = 'template' | 'variables' | 'rendered'

export function PromptInspector({ promptEvent, onClose }: PromptInspectorProps) {
  const [tab, setTab] = useState<InspectorTab>('template')

  if (!promptEvent) {
    return null
  }

  return (
    <Dialog
      open={Boolean(promptEvent)}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose()
        }
      }}
    >
      <DialogContent className="flex h-[80vh] max-w-5xl flex-col overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b border-border bg-muted/30 px-6 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <MessageSquare className="size-5 text-primary" />
            Prompt Inspector: {eventPhase(promptEvent)}
          </DialogTitle>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as InspectorTab)}
          className="min-h-0 flex-1 px-6 pb-6"
        >
          <TabsList variant="line" className="mb-4">
            <TabsTrigger value="template">Template</TabsTrigger>
            <TabsTrigger value="variables">Variables</TabsTrigger>
            <TabsTrigger value="rendered">Rendered</TabsTrigger>
          </TabsList>
          <TabsContent value="template" className="min-h-0">
            <PromptPayload>{promptEvent.template_source ?? 'inline'}</PromptPayload>
          </TabsContent>
          <TabsContent value="variables" className="min-h-0">
            <PromptPayload>{jsonText(promptEvent.variables)}</PromptPayload>
          </TabsContent>
          <TabsContent value="rendered" className="min-h-0">
            <PromptPayload>
              {promptEvent.event_type === 'prompt_captured'
                ? jsonText(promptEvent.resolved_prompt)
                : jsonText(promptEvent.messages ?? undefined)}
            </PromptPayload>
            <div className="mt-3 flex items-center gap-1 text-xs font-medium text-primary">
              <CheckCircle className="size-3" />
              Rendered prompt payload
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function PromptPayload({ children }: { children: string }) {
  return (
    <pre className="h-full min-h-[24rem] overflow-auto rounded-md border border-border bg-muted/40 p-4 text-sm whitespace-pre-wrap text-foreground">
      {children}
    </pre>
  )
}
