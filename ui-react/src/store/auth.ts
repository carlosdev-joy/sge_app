import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  matricula: string
  primeiro_nome?: string
  ultimo_nome?: string
  perfil: string
  email?: string
  permissoes?: string[]
}

interface AuthState {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  logout: () => void
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      setAuth: (user, token) => {
        localStorage.setItem('orquestra_token', token)
        set({ user, token })
      },
      logout: () => {
        localStorage.removeItem('orquestra_token')
        set({ user: null, token: null })
      },
      isAdmin: () => get().user?.perfil === 'admin',
    }),
    { name: 'orquestra-auth', partialize: (s) => ({ user: s.user, token: s.token }) }
  )
)

// ── Bridge com a UI legada ────────────────────────────────────────────────────
// O sistema legado grava a sessão em localStorage['orq_session'] = { token, exp }.
// Como o app React roda na mesma origin (sub-path /v2), conseguimos reaproveitar
// essa sessão e evitar login duplicado. Lê o token legado (se válido) sem precisar
// de nova autenticação.
const LEGACY_SESSION_KEY = 'orq_session'

export function readLegacyToken(): string | null {
  try {
    const raw = localStorage.getItem(LEGACY_SESSION_KEY)
    if (!raw) return null
    const s = JSON.parse(raw)
    if (s && s.token && (!s.exp || s.exp > Date.now())) return s.token
  } catch {
    /* ignora JSON inválido */
  }
  return null
}
