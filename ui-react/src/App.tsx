import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { AppShell } from './components/layout/AppShell'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Malha from './pages/Malha'
import Governanca from './pages/Governanca'
import ImpactoCampo from './pages/ImpactoCampo'
import PlanosAjuste from './pages/PlanosAjuste'
import Logs from './pages/Logs'
import Jobs from './pages/Jobs'
import Pipelines from './pages/Pipelines'
import Dashboard from './pages/Dashboard'
import PowerBI from './pages/PowerBI'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShell /></PrivateRoute>}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="admin/*" element={<Admin />} />
            <Route path="malha" element={<Malha />} />
            <Route path="governanca" element={<Governanca />} />
            <Route path="impacto-campo" element={<ImpactoCampo />} />
            <Route path="planos-ajuste" element={<PlanosAjuste />} />
            <Route path="logs" element={<Logs />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="pipelines" element={<Pipelines />} />
            <Route path="powerbi" element={<PowerBI />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
