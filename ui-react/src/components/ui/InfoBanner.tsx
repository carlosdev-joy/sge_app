import { useState, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface InfoBannerProps {
  icon?: ReactNode
  children: ReactNode
  /** Chave de persistência; se informada, o banner lembra que foi dispensado. */
  storageKey?: string
}

// Banner informativo dispensável — descrição humanizada da tela.
// Mesmo padrão visual usado em Jobs/Malha, com suporte a tema claro/escuro.
export function InfoBanner({ icon = 'ⓘ', children, storageKey }: InfoBannerProps) {
  const [open, setOpen] = useState(() => {
    if (!storageKey) return true
    try { return localStorage.getItem(`banner_dismissed_${storageKey}`) !== '1' } catch { return true }
  })

  if (!open) return null

  const dismiss = () => {
    setOpen(false)
    if (storageKey) { try { localStorage.setItem(`banner_dismissed_${storageKey}`, '1') } catch { /* noop */ } }
  }

  return (
    <div className="flex items-start gap-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-3">
      <span className="text-base shrink-0">{icon}</span>
      <div className="flex-1 text-[12px] leading-relaxed text-blue-800 dark:text-blue-200">
        {children}
      </div>
      <button
        onClick={dismiss}
        className="shrink-0 text-blue-400 hover:text-blue-700 dark:hover:text-blue-100 transition-colors"
        aria-label="Dispensar"
      >
        <X size={14} />
      </button>
    </div>
  )
}
