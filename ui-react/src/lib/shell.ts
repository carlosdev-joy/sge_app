// Flag de shell — escolhe entre o app shell clássico e o novo (v2), no espírito
// de `lib/theme.ts`: preferência em localStorage['orquestra_shell'], com atalho
// `?shell=v2` / `?shell=classic` na URL. Default 'v2'.
//
// O shell v2 é o PADRÃO para todos os usuários. O clássico permanece como
// kill-switch: qualquer um pode voltar a ele pelo toggle "Interface" no perfil
// (persistido por usuário). Reversão trivial, sem mexer no deploy.

import { useEffect, useState } from 'react'
import { type User } from '../store/auth'

export type ShellVariant = 'classic' | 'v2'

const SHELL_KEY = 'orquestra_shell'
const SHELL_EVENT = 'orquestra:shell-change'

// Recurso RBAC que liberava o shell novo ao grupo beta.
// @deprecated Não gateia mais o shell — v2 é o default para todos. Mantido por
// compat para quem ainda importa.
export const SHELL_BETA_PERM = 'tela_shell_v2'

// Preferência salva pelo usuário. `?shell=` tem precedência e é persistido (para
// um link de validação "grudar"). Default 'v2' — só cai no clássico quando o
// usuário escolhe explicitamente.
export function getShellPref(): ShellVariant {
  try {
    const q = new URLSearchParams(window.location.search).get('shell')
    if (q === 'v2' || q === 'classic') {
      localStorage.setItem(SHELL_KEY, q)
      return q
    }
    return localStorage.getItem(SHELL_KEY) === 'classic' ? 'classic' : 'v2'
  } catch {
    return 'v2'
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

// @deprecated O shell v2 não é mais gateado por RBAC (é o default para todos).
// Mantido por compat. Admin e quem tem `tela_shell_v2` continuam retornando true.
export function canUseShellV2(user: User | null): boolean {
  if (!user) return false
  if (user.perfil === 'admin') return true
  return (user.permissoes ?? []).includes(SHELL_BETA_PERM)
}

// Variante efetiva do shell: a preferência do usuário (default 'v2'). Reage a
// toggles (evento próprio) e a mudanças em outra aba (storage).
export function useShellVariant(): ShellVariant {
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
  return pref
}
