import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { apiFetch } from './lib/api'
import { useAuthStore, readLegacyToken } from './store/auth'
import { AppShell } from './components/layout/AppShell'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Malha from './pages/Malha'
import ImpactoCampo from './pages/ImpactoCampo'
import PlanosAjuste from './pages/PlanosAjuste'

// Telas já migradas para React são montadas abaixo. As demais permanecem na UI
// legada (raiz) — ver src/lib/nav.ts. Mantemos os imports das páginas prontas
// fora do bundle de rotas até que cada uma seja validada e ativada.

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  // Sem sessão React nem legada → manda para o login centralizado (UI legada, raiz).
  if (!token && !readLegacyToken()) {
    window.location.href = '/'
    return null
  }
  return <>{children}</>
}

// Adota a sessão da UI legada (orq_session) na primeira entrada no /v2, para
// evitar login duplicado. Busca /me com o token legado e popula a store.
function useLegacySessionBridge() {
  const { token, setAuth } = useAuthStore()
  const [ready, setReady] = useState(!!token)

  useEffect(() => {
    if (token) { setReady(true); return }
    const legacy = readLegacyToken()
    if (!legacy) { setReady(true); return }
    let cancelled = false
    apiFetch<any>('/me')
      .then((user) => { if (!cancelled) setAuth(user, legacy) })
      .catch(() => { /* token legado inválido — PrivateRoute trata o redirect */ })
      .finally(() => { if (!cancelled) setReady(true) })
    return () => { cancelled = true }
  }, [token, setAuth])

  return ready
}

export default function App() {
  const ready = useLegacySessionBridge()
  if (!ready) return null

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/v2">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShell /></PrivateRoute>}>
            <Route index element={<Navigate to="/admin" replace />} />
            <Route path="admin/*" element={<Admin />} />
            <Route path="malha" element={<Malha />} />
            <Route path="impacto-campo" element={<ImpactoCampo />} />
            <Route path="planos-ajuste" element={<PlanosAjuste />} />
          </Route>
          {/* Telas ainda não migradas caem na raiz (UI legada) */}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
