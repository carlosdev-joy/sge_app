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
