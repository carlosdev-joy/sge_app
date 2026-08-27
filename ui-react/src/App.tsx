import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { apiFetch } from './lib/api'
import { useAuthStore, readLegacyToken } from './store/auth'
import { AppShell } from './components/layout/AppShell'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Chamados from './pages/Chamados'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import Logs from './pages/Logs'
import DSMonitor from './pages/DSMonitor'
import Governanca from './pages/Governanca'
import Malha from './pages/Malha'
import Pipelines from './pages/Pipelines'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token && !readLegacyToken()) {
    window.location.href = '/'
    return null
  }
  return <>{children}</>
}

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
      .catch(() => {})
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
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShell /></PrivateRoute>}>
            <Route index element={<Navigate to="/chamados" replace />} />
            <Route path="chamados/*" element={<Chamados />} />
            <Route path="admin/*" element={<Admin />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="logs" element={<Logs />} />
            <Route path="ds-monitor" element={<DSMonitor />} />
            <Route path="governanca" element={<Governanca />} />
            <Route path="malha" element={<Malha />} />
            <Route path="pipelines" element={<Pipelines />} />
          </Route>
          <Route path="*" element={<Navigate to="/chamados" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
