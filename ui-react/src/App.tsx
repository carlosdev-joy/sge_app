import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { NAV, canAccess, firstVisiblePath } from './lib/nav'
import { AppShellV2 } from './components/layout/AppShellV2'
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
import DsConsole from './pages/DsConsole'
import Avisos from './pages/Avisos'
import GestaoFalhas from './pages/GestaoFalhas'
import Publicacao from './pages/Publicacao'
import Performance from './pages/Performance'
import CopiaDados from './pages/CopiaDados'
import Inventario from './pages/Inventario'
import Finalizacao from './pages/Finalizacao'
import Fluxos from './pages/Fluxos'
import CaixaSeguroApp from './caixa/CaixaSeguroApp'
import MonitoramentoOrq from './caixa/pages/MonitoramentoOrq'
import IndexOrq from './caixa/pages/IndexOrq'
import { ProfileProvider } from './caixa/contexts/ProfileContext'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

// Destino padrão ("/", catch-all e rota negada): 1ª tela visível pelo RBAC.
function HomeRedirect() {
  const perms = useAuthStore((s) => s.user?.permissoes)
  return <Navigate to={firstVisiblePath(perms)} replace />
}

// Guard de rota: espelha a visibilidade do menu (canAccess). URL digitada de
// tela sem permissão redireciona para a 1ª tela visível; a proteção de dados
// continua sendo o 403 do backend.
function RequirePerm({ perm, children }: { perm?: string; children: React.ReactNode }) {
  const perms = useAuthStore((s) => s.user?.permissoes) ?? []
  if (!canAccess(perm, perms)) return <HomeRedirect />
  return <>{children}</>
}

// Elemento de cada rota, chaveado por `NavItem.to`. É a única coisa que App
// precisa declarar além do NAV (os componentes têm de ser importados aqui de
// qualquer forma); o conjunto e a ordem das rotas saem de NAV, sem duplicar a
// lista de telas. Adicionar uma tela = registrar no nav.ts + mapear aqui.
const PAGE_ELEMENT: Record<string, React.ReactNode> = {
  '/dashboard': <Dashboard />,
  '/gestao-falhas': <GestaoFalhas />,
  '/pipelines': <Pipelines />,
  '/jobs': <Jobs />,
  '/fluxos': <Fluxos />,
  '/publicacao': <Publicacao />,
  '/logs': <Logs />,
  '/avisos': <Avisos />,
  '/governanca': <Governanca />,
  '/malha': <Malha />,
  '/impacto-campo': <ImpactoCampo />,
  '/planos-ajuste': <PlanosAjuste />,
  '/copia-dados': <CopiaDados />,
  '/inventario': <Inventario />,
  '/powerbi': <PowerBI />,
  '/ds-console': <DsConsole />,
  '/performance': <Performance />,
  '/finalizacao': <Finalizacao />,
  '/caixa-seguro': <CaixaSeguroApp />,
  '/admin': <Admin />,
}

// Rotas que agrupam navegação interna por estado (abas) e precisam casar
// subpaths — preserva o comportamento do antigo `admin/*`.
const WILDCARD_ROUTES = new Set(['/admin', '/caixa-seguro'])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShellV2 /></PrivateRoute>}>
            <Route index element={<HomeRedirect />} />
            {/* Home "Consulta de Propostas" no visual NATIVO do Orquestra —
                tela oficial desde a F3 da migração (docs/spec-caixa-ds-nativo.md).
                Rota estática exata: vence o splat caixa-seguro/* no ranking do
                router e fica FORA do CaixaSeguroApp/.caixa-theme. */}
            <Route
              path="caixa-seguro"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><IndexOrq /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Monitoramento Tático no visual NATIVO do Orquestra — tela oficial
                desde a F2 da migração (docs/spec-caixa-ds-nativo.md). Rota mais
                específica que o splat caixa-seguro/* (vence no ranking do router)
                e FORA do CaixaSeguroApp, logo sem o wrapper .caixa-theme — usa
                tokens canvas/panel/ink puros, claro+escuro. Mesmo RBAC; o
                ProfileProvider (perfil operacional/funcionário) vem na rota
                porque a tela não passa mais pelo CaixaSeguroApp. */}
            <Route
              path="caixa-seguro/acompanhamento"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><MonitoramentoOrq /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Rota do antigo piloto A/B — redirect permanente para a oficial. */}
            <Route path="caixa-seguro/acompanhamento-orq" element={<Navigate to="/caixa-seguro/acompanhamento" replace />} />
            {NAV.map((n) => {
              const element = PAGE_ELEMENT[n.to]
              if (!element) return null
              const path = n.to.replace(/^\//, '') + (WILDCARD_ROUTES.has(n.to) ? '/*' : '')
              return <Route key={n.to} path={path} element={<RequirePerm perm={n.perm}>{element}</RequirePerm>} />
            })}
          </Route>
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
