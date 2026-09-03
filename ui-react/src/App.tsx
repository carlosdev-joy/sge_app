import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { NAV, canAccess, firstVisiblePath } from './lib/nav'
import { ErrorBoundary } from './components/ErrorBoundary'
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
import Chamados from './pages/Chamados'
import Finalizacao from './pages/Finalizacao'
import Fluxos from './pages/Fluxos'
import Utilitarios from './pages/Utilitarios'
import Monitoramento from './caixa/pages/Monitoramento'
import Index from './caixa/pages/Index'
import Portabilidades from './caixa/pages/Portabilidades'
import PainelIA from './caixa/pages/PainelIA'
import Acompanhamento from './caixa/pages/Acompanhamento'
import { ProfileProvider } from './caixa/contexts/ProfileContext'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

// Subpath desconhecido de /caixa-seguro/* → home da seção. Herdeiro do splat
// do CaixaSeguroApp, aposentado na F10 junto com o tema shadcn.
function CaixaSeguroFallback() {
  return <Navigate to="/caixa-seguro" replace />
}

// Redirect da rota paralela das F6–F8 preservando o :status.
function RedirectAcompanhamentoStatus() {
  const { status } = useParams<{ status: string }>()
  return <Navigate to={`/caixa-seguro/acompanhamento/${status}`} replace />
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
  '/chamados': <Chamados />,
  '/powerbi': <PowerBI />,
  '/ds-console': <DsConsole />,
  '/utilitarios': <Utilitarios />,
  '/performance': <Performance />,
  '/finalizacao': <Finalizacao />,
  '/caixa-seguro': <CaixaSeguroFallback />,
  '/admin': <Admin />,
}

// Rotas que agrupam navegação interna por estado (abas) e precisam casar
// subpaths — preserva o comportamento do antigo `admin/*`.
const WILDCARD_ROUTES = new Set(['/admin', '/caixa-seguro'])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<PrivateRoute><AppShellV2 /></PrivateRoute>}>
            <Route index element={<HomeRedirect />} />
            {/* Home "Consulta de Propostas" no visual NATIVO do Orquestra —
                tela oficial desde a F3 da migração (docs/spec-caixa-ds-nativo.md).
                Rota estática exata: vence o splat caixa-seguro/* no ranking do
                router; tema shadcn aposentado na F10. */}
            <Route
              path="caixa-seguro"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><Index /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Monitoramento Tático no visual NATIVO do Orquestra — tela oficial
                desde a F2 da migração (docs/spec-caixa-ds-nativo.md). Rota mais
                específica que o splat caixa-seguro/* (vence no ranking do router)
                com tokens canvas/panel/ink puros, claro+escuro. Mesmo RBAC; o
                ProfileProvider (perfil operacional/funcionário) vem na rota. */}
            <Route
              path="caixa-seguro/acompanhamento"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><Monitoramento /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Rota do antigo piloto A/B — redirect permanente para a oficial. */}
            <Route path="caixa-seguro/acompanhamento-orq" element={<Navigate to="/caixa-seguro/acompanhamento" replace />} />
            {/* Portabilidades no visual NATIVO — tela oficial desde a F4 da
                migração (docs/spec-caixa-ds-nativo.md). Mesmo padrão: rota
                estática vence o splat. */}
            <Route
              path="caixa-seguro/portabilidades"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><Portabilidades /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Acompanhamento por status nativo — tela oficial desde a F9 da
                migração (nasceu como rota paralela na F6; diálogos nas F7/F8).
                Rota estática+param vence o splat no ranking do router. */}
            <Route
              path="caixa-seguro/acompanhamento/:status"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><Acompanhamento /></ProfileProvider>
                </RequirePerm>
              }
            />
            {/* Rota paralela das F6–F8 — redirect permanente para a oficial. */}
            <Route path="caixa-seguro/acompanhamento-orq/:status" element={<RedirectAcompanhamentoStatus />} />
            {/* Painel de IA Operacional no visual NATIVO — tela oficial desde
                a F5 da migração (docs/spec-caixa-ds-nativo.md). */}
            <Route
              path="caixa-seguro/ia-operacional"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <ProfileProvider><PainelIA /></ProfileProvider>
                </RequirePerm>
              }
            />
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
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
