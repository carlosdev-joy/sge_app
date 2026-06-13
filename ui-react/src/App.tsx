import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { AppShell } from './components/layout/AppShell'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Pipelines from './pages/Pipelines'
import Jobs from './pages/Jobs'
import Logs from './pages/Logs'
import DSMonitor from './pages/DSMonitor'
import Governanca from './pages/Governanca'
import Malha from './pages/Malha'
import Admin from './pages/Admin'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShell /></PrivateRoute>}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard"  element={<Dashboard />} />
            <Route path="pipelines"  element={<Pipelines />} />
            <Route path="jobs"       element={<Jobs />} />
            <Route path="logs"       element={<Logs />} />
            <Route path="ds-monitor" element={<DSMonitor />} />
            <Route path="governanca" element={<Governanca />} />
            <Route path="malha"      element={<Malha />} />
            <Route path="admin/*"    element={<Admin />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
