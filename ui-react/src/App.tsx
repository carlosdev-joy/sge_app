import { ApplicationDialogs } from './components/ui/ApplicationDialogs'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './store/auth'
import { NAV, canAccess, firstVisiblePath } from './lib/nav'
import { ErrorBoundary } from './components/ErrorBoundary'
import { AppShellV2 } from './components/layout/AppShellV2'
import Login from './pages/Login'
const Malha = lazy(() => import('./pages/Malha'))
const Governanca = lazy(() => import('./pages/Governanca'))
const ImpactoCampo = lazy(() => import('./pages/ImpactoCampo'))
const PlanosAjuste = lazy(() => import('./pages/PlanosAjuste'))
const Logs = lazy(() => import('./pages/Logs'))
const Jobs = lazy(() => import('./pages/Jobs'))
const Pipelines = lazy(() => import('./pages/Pipelines'))
import Dashboard from './pages/Dashboard'
const PowerBI = lazy(() => import('./pages/PowerBI'))
const DsConsole = lazy(() => import('./pages/DsConsole'))
const Avisos = lazy(() => import('./pages/Avisos'))
const GestaoFalhas = lazy(() => import('./pages/GestaoFalhas'))
const Publicacao = lazy(() => import('./pages/Publicacao'))
const Performance = lazy(() => import('./pages/Performance'))
const CopiaDados = lazy(() => import('./pages/CopiaDados'))
const Inventario = lazy(() => import('./pages/Inventario'))
const Chamados = lazy(() => import('./pages/Chamados'))
const Finalizacao = lazy(() => import('./pages/Finalizacao'))
const Fluxos = lazy(() => import('./pages/Fluxos'))
const Utilitarios = lazy(() => import('./pages/Utilitarios'))
const Agentes = lazy(() => import('./pages/Agentes'))
const Monitoramento = lazy(() => import('./caixa/pages/Monitoramento'))
const Index = lazy(() => import('./caixa/pages/Index'))
const Portabilidades = lazy(() => import('./caixa/pages/Portabilidades'))
const PainelIA = lazy(() => import('./caixa/pages/PainelIA'))
const Acompanhamento = lazy(() => import('./caixa/pages/Acompanhamento'))
import { ProfileProvider } from './caixa/contexts/ProfileContext'
import { LegacyWorkspaceEntry } from './components/workspace/LegacyWorkspaceEntry'
import { PageSpinner } from './components/ui/Spinner'

// Páginas fora da entrada inicial carregam sob demanda; login, Dashboard e casca
// permanecem síncronos. Guards continuam externos ao Suspense.
// Admin sob demanda (docs/spec-admin-reestruturacao.md, F2): antes entrava no
// bundle principal com as 24 abas; agora a casca é um chunk e cada aba outro.
const PipelineWorkspace = lazy(() => import('./pages/PipelineWorkspace'))
const PipelineCreate = lazy(() => import('./pages/PipelineCreate'))
const Admin = lazy(() => import('./pages/Admin'))

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
  '/jobs': <LegacyWorkspaceEntry kind="jobs"><Jobs /></LegacyWorkspaceEntry>,
  '/fluxos': <LegacyWorkspaceEntry kind="fluxos"><Fluxos /></LegacyWorkspaceEntry>,
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
  '/agentes': <Agentes />,
  '/admin': <Suspense fallback={<PageSpinner />}><Admin /></Suspense>,
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
            <Route path="pipelines/novo" element={<RequirePerm perm="tela_pipelines"><Suspense fallback={<PageSpinner />}><PipelineCreate /></Suspense></RequirePerm>} />
            <Route path="pipelines/:nome/*" element={<RequirePerm perm="tela_pipelines"><Suspense fallback={<PageSpinner />}><PipelineWorkspace /></Suspense></RequirePerm>} />
            {/* Home "Consulta de Propostas" no visual NATIVO do Orquestra —
                tela oficial desde a F3 da migração (docs/spec-caixa-ds-nativo.md).
                Rota estática exata: vence o splat caixa-seguro/* no ranking do
                router; tema shadcn aposentado na F10. */}
            <Route
              path="caixa-seguro"
              element={
                <RequirePerm perm="tela_caixa_seguro">
                  <Suspense fallback={<PageSpinner />}><ProfileProvider><Index /></ProfileProvider></Suspense>
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
                  <Suspense fallback={<PageSpinner />}><ProfileProvider><Monitoramento /></ProfileProvider></Suspense>
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
                  <Suspense fallback={<PageSpinner />}><ProfileProvider><Portabilidades /></ProfileProvider></Suspense>
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
                  <Suspense fallback={<PageSpinner />}><ProfileProvider><Acompanhamento /></ProfileProvider></Suspense>
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
                  <Suspense fallback={<PageSpinner />}><ProfileProvider><PainelIA /></ProfileProvider></Suspense>
                </RequirePerm>
              }
            />
            <Route path="jobs" element={<RequirePerm perm="tela_jobs"><Suspense fallback={<PageSpinner />}><LegacyWorkspaceEntry kind="jobs"><Jobs /></LegacyWorkspaceEntry></Suspense></RequirePerm>} />
            {NAV.map((n) => {
              const element = PAGE_ELEMENT[n.to]
              if (!element) return null
              const path = n.to.replace(/^\//, '') + (WILDCARD_ROUTES.has(n.to) ? '/*' : '')
              return <Route key={n.to} path={path} element={<RequirePerm perm={n.perm}><Suspense fallback={<PageSpinner />}>{element}</Suspense></RequirePerm>} />
            })}
          </Route>
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
        <ApplicationDialogs/>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
