// Estado de colapso da sidebar do shell v2, persistido no padrão de lib/theme.ts:
// localStorage['orquestra_sidebar_collapsed'] ('1' = colapsada, só ícones).
// Reage a mudanças via evento próprio e entre abas (storage).

import { useEffect, useState } from 'react'

const KEY = 'orquestra_sidebar_collapsed'
const EVENT = 'orquestra:sidebar-change'

export function getSidebarCollapsed(): boolean {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}

export function setSidebarCollapsed(v: boolean) {
  try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* ignore */ }
  window.dispatchEvent(new Event(EVENT))
}

export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setC] = useState(getSidebarCollapsed)
  useEffect(() => {
    const sync = () => setC(getSidebarCollapsed())
    window.addEventListener(EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return [collapsed, () => setSidebarCollapsed(!getSidebarCollapsed())]
}
