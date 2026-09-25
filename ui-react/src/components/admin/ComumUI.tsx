import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { renderMarkdown } from '../../lib/markdown'
import { AlertTriangle } from 'lucide-react'

// ── Confirm Modal ────────────────────────────────────────────────
interface ConfirmProps {
  open: boolean
  title: string
  message: string
  danger?: boolean
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}
export function ConfirmModal({ open, title, message, danger, confirmLabel = 'Confirmar', onConfirm, onCancel }: ConfirmProps) {
  if (!open) return null
  return (
    <Modal open onClose={onCancel} title={title} size="sm">
      <div className="flex flex-col gap-5">
        {danger ? (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{message}</p>
          </div>
        ) : <p className="text-sm text-ink">{message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>Cancelar</Button>
          <Button variant={danger ? 'danger' : 'primary'} size="sm" onClick={() => { onConfirm(); onCancel() }}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Markdown render ──────────────────────────────────────────────
export function Markdown({ text }: { text?: string }) {
  return <div className="text-ink" dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />
}
