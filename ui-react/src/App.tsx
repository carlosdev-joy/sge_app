import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { MIGRATED } from './lib/nav'
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
import MalhaDS from './pages/MalhaDS'
import DsConsole from './pages/DsConsole'
import Avisos from './pages/Avisos'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

// Elemento de cada rota migrada, chaveado por `NavItem.to`. É a única coisa que
// App precisa declarar além do NAV (os componentes têm de ser importados aqui de
// qualquer forma); o conjunto e a ordem das rotas saem de MIGRATED, sem duplicar
// a lista de telas. Adicionar uma tela = registrar no nav.ts + mapear aqui.
const PAGE_ELEMENT: Record<string, React.ReactNode> = {
  '/dashboard': <Dashboard />,
  '/pipelines': <Pipelines />,
  '/jobs': <Jobs />,
  '/logs': <Logs />,
  '/avisos': <Avisos />,
  '/governanca': <Governanca />,
  '/malha': <Malha />,
  '/impacto-campo': <ImpactoCampo />,
  '/planos-ajuste': <PlanosAjuste />,
  '/powerbi': <PowerBI />,
  '/malha-ds': <MalhaDS />,
  '/ds-console': <DsConsole />,
  '/admin': <Admin />,
}

// Rotas que agrupam navegação interna por estado (abas) e precisam casar
// subpaths — preserva o comportamento do antigo `admin/*`.
const WILDCARD_ROUTES = new Set(['/admin'])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShell /></PrivateRoute>}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            {MIGRATED.map((n) => {
              const element = PAGE_ELEMENT[n.to]
              if (!element) return null
              const path = n.to.replace(/^\//, '') + (WILDCARD_ROUTES.has(n.to) ? '/*' : '')
              return <Route key={n.to} path={path} element={element} />
            })}
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
