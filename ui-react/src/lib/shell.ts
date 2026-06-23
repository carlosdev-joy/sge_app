// Flag de shell — escolhe entre o app shell clássico (atual) e o novo (v2), no
// espírito de `lib/theme.ts`: preferência em localStorage['orquestra_shell'],
// com atalho `?shell=v2` / `?shell=classic` na URL. Default 'classic'.
//
// O shell novo é beta: só aparece para o grupo liberado por RBAC (admin ou o
// recurso `tela_shell_v2`). Quem não é beta enxerga sempre o clássico, mesmo
// com a flag ligada — reversão trivial, sem mexer no deploy. Os incrementos
// seguintes (registry, sidebar, header fino, responsividade) fazem o v2 divergir.

import { useEffect, useState } from 'react'
import { useAuthStore, type User } from '../store/auth'

export type ShellVariant = 'classic' | 'v2'

const SHELL_KEY = 'orquestra_shell'
const SHELL_EVENT = 'orquestra:shell-change'

// Recurso RBAC que libera o shell novo ao grupo beta (além de admin).
export const SHELL_BETA_PERM = 'tela_shell_v2'

// Preferência salva pelo usuário (ainda sem considerar RBAC). `?shell=` tem
// precedência e é persistido, para o link de validação "grudar" sem o usuário
// precisar mexer no localStorage manualmente.
export function getShellPref(): ShellVariant {
  try {
    const q = new URLSearchParams(window.location.search).get('shell')
    if (q === 'v2' || q === 'classic') {
      localStorage.setItem(SHELL_KEY, q)
      return q
    }
    return localStorage.getItem(SHELL_KEY) === 'v2' ? 'v2' : 'classic'
  } catch {
    return 'classic'
  }
}

export function setShellPref(v: ShellVariant) {
  try { localStorage.setItem(SHELL_KEY, v) } catch { /* ignore */ }
  window.dispatchEvent(new Event(SHELL_EVENT))
}

export function toggleShellPref(): ShellVariant {
  const next: ShellVariant = getShellPref() === 'v2' ? 'classic' : 'v2'
  setShellPref(next)
  return next
}

// O usuário pode ver o shell novo? Gate beta fail-closed: só admin ou quem tem
// o recurso `tela_shell_v2`. Sem migration nesta etapa — admins já testam.
export function canUseShellV2(user: User | null): boolean {
  if (!user) return false
  if (user.perfil === 'admin') return true
  return (user.permissoes ?? []).includes(SHELL_BETA_PERM)
}

// Variante efetiva do shell: 'v2' só quando a flag está ligada E o usuário é
// beta. Reage a toggles (evento próprio) e a mudanças em outra aba (storage).
export function useShellVariant(): ShellVariant {
  const user = useAuthStore((s) => s.user)
  const [pref, setPref] = useState<ShellVariant>(getShellPref)
  useEffect(() => {
    const sync = () => setPref(getShellPref())
    window.addEventListener(SHELL_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(SHELL_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return pref === 'v2' && canUseShellV2(user) ? 'v2' : 'classic'
}
