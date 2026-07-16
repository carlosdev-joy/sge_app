// ── DropdownMenu: menu suspenso nativo do DS ─────────────────────────────────
// Caseiro, sem Radix: trigger com aria-haspopup/aria-expanded, painel absolute
// com role="menu". Fecha em clique-fora e Esc (devolvendo o foco ao trigger);
// setas circulam entre os itens habilitados; abrir com ArrowDown foca o 1º.
// API orientada a itens (não compound): centraliza foco/teclado num só lugar.
import React from 'react'

export interface DropdownItem {
  label: React.ReactNode
  onSelect: () => void
  disabled?: boolean
}

export interface DropdownMenuProps {
  /** Conteúdo do botão que abre o menu. */
  trigger: React.ReactNode
  items: DropdownItem[]
  align?: 'start' | 'end'
  triggerClassName?: string
  menuClassName?: string
}

const TRIGGER_PADRAO =
  'inline-flex items-center gap-2 rounded-md border border-edge bg-panel px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:bg-canvas transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500'

export function DropdownMenu({ trigger, items, align = 'start', triggerClassName = '', menuClassName = '' }: DropdownMenuProps) {
  const [open, setOpen] = React.useState(false)
  const rootRef = React.useRef<HTMLDivElement>(null)
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const itemRefs = React.useRef<(HTMLButtonElement | null)[]>([])

  // Fecha em clique-fora, Esc (global — mesmo com o foco fora do painel,
  // devolvendo-o ao trigger) e quando o foco sai do menu (Tab).
  React.useEffect(() => {
    if (!open) return
    const foraDoMenu = (alvo: EventTarget | null) =>
      rootRef.current != null && !rootRef.current.contains(alvo as Node)
    const onDown = (e: MouseEvent) => {
      if (foraDoMenu(e.target)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    const onFocusIn = (e: FocusEvent) => {
      if (foraDoMenu(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    document.addEventListener('focusin', onFocusIn)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('focusin', onFocusIn)
    }
  }, [open])

  React.useEffect(() => {
    if (open) itemRefs.current.find(Boolean)?.focus()
  }, [open])

  const mover = (dir: 1 | -1, atual: number) => {
    const habilitados = itemRefs.current
      .map((el, i) => ({ el, i }))
      .filter((x) => x.el && !items[x.i]?.disabled)
    if (!habilitados.length) return
    const pos = habilitados.findIndex((x) => x.i === atual)
    habilitados[(pos + dir + habilitados.length) % habilitados.length].el!.focus()
  }

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        className={triggerClassName || TRIGGER_PADRAO}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-50 mt-1 min-w-[14rem] rounded-md border border-edge bg-panel py-1 shadow-lg ${align === 'end' ? 'right-0' : 'left-0'} ${menuClassName}`}
        >
          {items.map((item, i) => (
            <button
              key={i}
              ref={(el) => {
                itemRefs.current[i] = el
              }}
              role="menuitem"
              type="button"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false)
                item.onSelect()
              }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  mover(1, i)
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  mover(-1, i)
                }
              }}
              className="block w-full px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-canvas focus:bg-canvas focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
