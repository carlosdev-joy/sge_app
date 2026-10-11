// Bancada da primeira entrega da UX de Pipeline (cinco destinos).
//
// O que prova, executando o código REAL do src/ (sucrase + minireact):
//  1. Aliases antigos (fluxo, etapas, ferramentas, execucoes, logs, parametros)
//     chegam ao destino novo preservando toda a query e o hash.
//  2. Navegação entre destinos do mesmo Pipeline/experiência/fonte é a mesma
//     sessão; outro pipeline, outra experiência ou outra fonte não é.
//  3. O cabeçalho da Execução nunca identifica o rascunho como executado.
//  4. O WorkspaceEditor real mantém rascunho, alterações locais, posse e fence
//     ao alternar Montagem → Configuração → Execução → Montagem: uma única
//     posse é adquirida e o save envia a mesma fence com as alterações das duas
//     abas, preservando campos desconhecidos e referências protegidas.
//  5. A Configuração tem seis grupos, um visível por vez, e cada campo do
//     pipeline tem um único editor.
//
//  6. Vistas conservadas: Montagem continua renderizada (oculta) na Configuração
//     com uma única instância de publicação; todo elemento com `hidden` fica sem
//     utilitário de display que anule o atributo.
//  7. WorkspaceOperations real: etapa/tentativa da URL abrem o log da tentativa
//     corrente ou histórica da corrida exibida, nunca uma tentativa inventada ou
//     de outra corrida; texto do log é texto; vista inativa não abre log nem ação.
//  8. Modal real dentro de área oculta (contexto injetado): fica montado, sem
//     role de diálogo e com display none.
//  9. Guarda de navegação real (lib/navigationGuard) contra um History simulado
//     com o índice `idx` do router: voltar/avançar para fora da sessão é desfeito
//     e só acontece após confirmar; dentro da sessão passa direto; clique em link
//     e navegação programática pedem o diálogo da aplicação e verificam a intenção.
// 10. Escopo de overlay composto (aba E grupo), com OverlayScope propagado pela
//     árvore e o WorkspaceParameters/DependenciasModal reais: catálogo aberto em
//     Parâmetros fica inerte ao voltar para Identificação, reativa com o conteúdo
//     conservado ao voltar ao grupo, e nenhum grupo reativa overlay de aba
//     oculta (Execução, ou área externa inativa). Posse e rascunho seguem os mesmos.
//
// Limites da bancada (minireact): useEffect não roda (sem renovação/intervalos);
// useLayoutEffect roda durante o render para atualizar as refs de guarda, como o
// React faria antes do próximo evento. O canvas React Flow e o FluxoEditor são
// dublês. O estado do minireact é por caminho, então a bancada NÃO prova
// preservação de instância nem CSS/foco/overlay no DOM: isso é do navegador real.
'use strict'
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert/strict')
const RAIZ = path.resolve(__dirname, '..', '..'), SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = ['components/workspace/WorkspaceEditor.tsx', 'components/workspace/WorkspaceOperations.tsx', 'components/ui/Modal.tsx', 'lib/navigationGuard.ts', 'lib/dialogs.ts', 'lib/workspaceTabs.ts', 'lib/workspaceNavigation.ts', 'lib/workspace.ts', 'components/workspace/WorkspaceParameters.tsx', 'components/pipelines/DependenciasModal.tsx']
const DUBLES = {
 'lib/api.ts': `
const calls = []; let responder = () => ({})
exports.__calls = calls; exports.__responder = fn => { responder = fn }
const record = (p, o = {}) => { const call = { p, method: o.method || 'GET', body: o.body ? JSON.parse(o.body) : undefined }; calls.push(call); return call }
exports.apiFetch = async (p, o) => responder(record(p, o))
exports.apiFetchBruto = async (p, o) => { record(p, o); return { status: 204, text: async () => '' } }
exports.esquecerConversasDeAgentes = () => {}
exports.currentToken = () => null
exports.BASE = '/orquestra'
`,
 'components/workspace/WorkspaceCanvas.tsx': `
const { jsx } = require('react/jsx-runtime')
exports.WorkspaceCanvas = function WorkspaceCanvas(p) { return jsx('div', { 'data-canvas': p.definition.nodes.map(n => n.id).join(','), 'data-editable': String(p.editable) }) }
`,
 'components/etapas/FluxoEditor.tsx': `
const { jsx } = require('react/jsx-runtime')
exports.FluxoEditor = function FluxoEditor(p) { exports.__ultimo = p; return jsx('div', { 'data-grafo': p.pipeline, 'data-ativo': String(p.workspace.active), 'data-etapa': p.workspace.stage || '' }) }
`,
}
function resolver(de, esp) {
 const base = path.resolve(de, esp)
 for (const alvo of [base + '.tsx', base + '.ts', path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) if (fs.existsSync(alvo)) return alvo
 return null
}
function preparar(destino) {
 const feitos = new Set(), fila = ENTRADAS.map(e => path.join(SRC, e))
 while (fila.length) {
  const arquivo = fila.pop(); if (feitos.has(arquivo)) continue; feitos.add(arquivo)
  const rel = path.relative(SRC, arquivo), alvo = path.join(destino, rel.replace(/\.tsx?$/, '.js'))
  fs.mkdirSync(path.dirname(alvo), { recursive: true })
  if (DUBLES[rel]) { fs.writeFileSync(alvo, DUBLES[rel]); continue }
  const fonte = fs.readFileSync(arquivo, 'utf8')
  fs.writeFileSync(alvo, transform(fonte, { transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true, filePath: arquivo }).code)
  // Só imports de valor: `import type` some na transpilação e não entra na bancada.
  // Inclui imports em várias linhas (`import {\n a,\n b } from './x'`).
  for (const m of fonte.matchAll(/^\s*import\s+(?!type\s)[^;'"]*?from\s*['"](\.[^'"]+)['"]/gm)) {
   const dep = resolver(path.dirname(arquivo), m[1]); if (dep) fila.push(dep)
  }
 }
}
function shims(destino) {
 const nm = path.join(destino, 'node_modules')
 const escrever = (pacote, arquivo, conteudo) => { const dir = path.join(nm, pacote); fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(path.join(dir, arquivo), conteudo) }
 const pacote = (nome, conteudo) => { escrever(nome, 'package.json', JSON.stringify({ name: nome, main: 'index.js' })); escrever(nome, 'index.js', conteudo) }
 const MINI = JSON.stringify(path.join(__dirname, 'minireact.cjs'))
 pacote('react', `
const mini = require(${MINI}); let seq = 0
function forwardRef(render) { const C = props => render(props, null); Object.defineProperty(C, 'name', { value: render.name || 'forwardRef' }); return C }
// lazy não carrega nada, salvo o módulo que o teste registrar (__lazy: caminho do
// import → componente real já carregado), renderizado de forma síncrona.
const __lazy = new Map()
function lazy(fabrica) { const fonte = String(fabrica); return function Lazy(p) { for (const [alvo, C] of __lazy) if (fonte.includes("'" + alvo + "'") || fonte.includes('"' + alvo + '"')) return mini.criar(C, p); return null } }
function Suspense(p) { return p.children }
// Contexto propagado pelo Provider (minireact). Sem Provider acima, vale o valor
// injetado pelo teste (__contexto), que simula uma área externa, e depois o padrão.
const __contexto = new Map()
function useContext(c) { return c.pilha.length ? mini.hooks.useContext(c) : __contexto.has(c) ? __contexto.get(c) : c.padrao }
module.exports = Object.assign({}, mini.hooks, { createElement: mini.criar, Fragment: mini.FRAGMENT, forwardRef, lazy, Suspense, useContext, __contexto, __lazy, useDeferredValue: v => v, useId: () => 'orq-' + (++seq), useLayoutEffect: fn => { fn() } })
module.exports.default = module.exports
`)
 const runtime = `const mini = require(${MINI}); const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key }); module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }`
 escrever('react', 'jsx-runtime.js', runtime); escrever('react', 'jsx-dev-runtime.js', runtime)
 pacote('react-dom', 'module.exports = { createPortal: el => el }; module.exports.default = module.exports')
 pacote('react-router-dom', `const { jsx } = require('react/jsx-runtime'); exports.__navegacoes = []; const navegar = to => exports.__navegacoes.push(to); exports.useNavigate = () => navegar; exports.useLocation = () => ({ pathname: '/', search: '', hash: '', key: 'k' }); exports.Link = p => jsx('a', Object.assign({}, p, { href: p.to }))`)
 pacote('@tanstack/react-query', `
const fixtures = { 'pipeline-projects': { projects: ['PROJ_A'] }, 'pipeline-domains': { domains: ['FIN'] }, 'agenda-calendarios': { calendarios: [{ calendario_nome: 'NACIONAL' }] } }
exports.__dados = fixtures
exports.useQuery = o => { const f = fixtures[o.queryKey[0]]; return { data: typeof f === 'function' ? f(o.queryKey) : f, isPending: false, isError: false, error: null, fetchStatus: 'idle', refetch() {} } }
exports.useMutation = o => ({ isPending: false, mutate(v) { Promise.resolve().then(() => { if (o.onMutate) o.onMutate(v); return o.mutationFn(v) }).then(r => { if (o.onSuccess) o.onSuccess(r, v) }, e => { if (o.onError) o.onError(e, v) }).finally(() => { if (o.onSettled) o.onSettled() }) } })
exports.useQueryClient = () => ({ invalidateQueries() {}, setQueryData() {} })
`)
 pacote('zustand', `
function make(init) { let state; const api = { getState: () => state, setState: p => { state = Object.assign({}, state, typeof p === 'function' ? p(state) : p) }, subscribe: () => () => {} }; state = init(api.setState, api.getState, api); const hook = sel => sel ? sel(state) : state; return Object.assign(hook, api) }
exports.create = init => init ? make(init) : make
`)
 escrever('zustand', 'middleware.js', 'exports.persist = fn => fn')
 const proxy = `module.exports = new Proxy({}, { get: (_, nome) => { if (nome === '__esModule') return true; const C = () => ({ __el: true, tipo: 'svg', props: { 'data-icone': String(nome) } }); Object.defineProperty(C, 'name', { value: String(nome) }); return C } })`
 pacote('lucide-react', proxy); pacote('@xyflow/react', proxy)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'workspace-ux-'))
preparar(tmp); shims(tmp)
const tabs = require(path.join(tmp, 'lib/workspaceTabs.js'))
const ws = require(path.join(tmp, 'lib/workspace.js'))
const nav = require(path.join(tmp, 'lib/workspaceNavigation.js'))
const api = require(path.join(tmp, 'lib/api.js'))
const { WorkspaceEditor } = require(path.join(tmp, 'components/workspace/WorkspaceEditor.js'))
const { jsx } = require(path.join(tmp, 'node_modules/react/jsx-runtime.js'))
const resultado = {}

// ── 1. Destinos e aliases ───────────────────────────────────────────────────
assert.deepEqual(tabs.WORKSPACE_DESTINATIONS.map(t => t[1]), ['Visão geral', 'Montagem', 'Execução', 'Configuração', 'Versões'])
for (const antigo of ['fluxo', 'etapas', 'ferramentas', 'execucoes', 'logs', 'parametros']) assert(!tabs.isWorkspaceDestination(antigo), antigo)
const NOME = 'Cobrança/A %25 & ç'
const legado = new URLSearchParams({ experiencia: 'sustentacao', fonte: 'rascunho', data: '2026-10-09', run_id: 'manual__a/b%#?', etapa: 'carga x', tentativa: '2', de: 'malha:Origem & B', desconhecido: 'mantido' })
const esperado = { fluxo: ['montagem', {}], etapas: ['montagem', {}], ferramentas: ['montagem', {}], execucoes: ['execucao', {}], logs: ['execucao', { vista: 'tabela' }], parametros: ['configuracao', { grupo: 'parametros' }] }
for (const [antigo, [destino, extra]] of Object.entries(esperado)) {
 const url = new URL(tabs.workspaceAliasRedirect(NOME, antigo, legado, '#no-x'), 'http://local')
 assert.equal(decodeURIComponent(url.pathname.split('/')[2]), NOME)
 assert.equal(url.pathname.split('/')[3], destino)
 assert.equal(url.hash, '#no-x')
 for (const [chave, valor] of legado) assert.equal(url.searchParams.get(chave), valor, `${antigo}:${chave}`)
 for (const [chave, valor] of Object.entries(extra)) assert.equal(url.searchParams.get(chave), valor)
 assert.equal(tabs.workspaceAliasRedirect(NOME, destino, url.searchParams), null, 'destino canônico não redireciona de novo')
}
for (const atual of ['visao-geral', 'montagem', 'execucao', 'configuracao', 'versoes', '', 'constructor', '__proto__']) assert.equal(tabs.workspaceAliasRedirect(NOME, atual, legado), null, atual)
const daMalha = new URL(nav.legacyWorkspacePath('fluxos', new URLSearchParams({ pipeline: NOME, modo: 'execucao', data: '2026-10-09', run_id: 'r/1', de: 'malha:M' })), 'http://local')
assert(daMalha.pathname.endsWith('/execucao')); assert.equal(daMalha.searchParams.get('experiencia'), 'sustentacao'); assert.equal(daMalha.searchParams.get('run_id'), 'r/1'); assert.equal(daMalha.searchParams.get('de'), 'malha:M'); assert.equal(daMalha.searchParams.get('pipeline'), null)
assert(new URL(nav.legacyWorkspacePath('jobs', new URLSearchParams({ pipeline: NOME })), 'http://local').pathname.endsWith('/montagem'))
const logs = new URL(nav.contextualPath(NOME, 'logs', legado), 'http://local'); assert(logs.pathname.endsWith('/execucao')); assert.equal(logs.searchParams.get('vista'), 'tabela'); assert.equal(logs.searchParams.get('tentativa'), '2')
const params = new URL(ws.workspacePath(NOME, 'parametros', 'desenvolvimento'), 'http://local'); assert(params.pathname.endsWith('/configuracao')); assert.equal(params.searchParams.get('grupo'), 'parametros'); assert.equal(params.searchParams.get('experiencia'), 'desenvolvimento')
assert(new URL(ws.workspacePath(NOME, 'fluxo', 'desenvolvimento'), 'http://local').pathname.endsWith('/montagem'))
resultado.aliases = Object.keys(esperado).length

// ── 2. Mesma sessão ─────────────────────────────────────────────────────────
const base = `http://local/pipelines/${encodeURIComponent(NOME)}`
const aqui = `${base}/montagem?experiencia=desenvolvimento`
for (const destino of ['configuracao?grupo=agenda', 'execucao?run_id=x', 'visao-geral', 'versoes', 'montagem', 'logs', 'fluxo'])
 assert(tabs.sameWorkspaceSession(NOME, aqui, `${base}/${destino}${destino.includes('?') ? '&' : '?'}experiencia=desenvolvimento&fonte=rascunho`), destino)
assert(tabs.sameWorkspaceSession(NOME, aqui, `${base}/montagem?experiencia=desenvolvimento#etapa`), 'hash')
assert(!tabs.sameWorkspaceSession(NOME, aqui, `${base}/configuracao?experiencia=consulta`), 'outra experiência')
assert(!tabs.sameWorkspaceSession(NOME, aqui, `http://local/pipelines/OUTRO/configuracao?experiencia=desenvolvimento`), 'outro pipeline')
assert(!tabs.sameWorkspaceSession(NOME, aqui, `http://outro/pipelines/${encodeURIComponent(NOME)}/configuracao?experiencia=desenvolvimento`), 'outra origem')
assert(!tabs.sameWorkspaceSession(NOME, aqui, `${base}/desconhecido?experiencia=desenvolvimento`), 'rota desconhecida')
assert(!tabs.sameWorkspaceSession(NOME, aqui, 'http://local/pipelines?experiencia=desenvolvimento'), 'lista')
assert(!tabs.sameWorkspaceSession(NOME, `${base}/montagem?experiencia=consulta&fonte=rascunho`, `${base}/configuracao?experiencia=consulta&fonte=publicado`), 'outra fonte')

// ── 3. Cabeçalho ────────────────────────────────────────────────────────────
for (const run of [null, { runId: null, date: null, versionNumber: null }, { runId: 'manual__1', date: '2026-10-09', versionNumber: null }, { runId: 'manual__2', date: '2026-10-10', versionNumber: 4 }]) {
 for (const aba of ['execucao', 'execucoes', 'logs']) {
  const h = tabs.workspaceHeaderContext(aba, { revision: 7 }, true, run)
  assert.equal(h.tone, 'run'); assert(!/rascunho|revisão/i.test(h.label), h.label)
 }
}
assert.match(tabs.workspaceHeaderContext('execucao', { revision: 7 }, true, { runId: 'manual__2', date: '2026-10-10', versionNumber: 4 }).label, /manual__2.*2026-10-10.*versão 4/)
assert.match(tabs.workspaceHeaderContext('execucao', null, true, { runId: 'r', date: null, versionNumber: null }).label, /versão da corrida não vinculada/)
assert.equal(tabs.workspaceHeaderContext('montagem', { revision: 7 }, true, null).label, 'Rascunho · revisão 7')
assert.equal(tabs.workspaceHeaderContext('configuracao', null, true, null).tone, 'published')
assert.equal(tabs.configurationGroup('xx'), 'identificacao'); assert.equal(tabs.configurationGroup('politicas'), 'politicas'); assert.equal(tabs.executionView('tabela'), 'tabela'); assert.equal(tabs.executionView('logs'), 'grafo')

// ── 4/5. Sessão real do editor entre abas ──────────────────────────────────
const TIPOS = ['datastage', 'sql', 'python', 'shell', 'storedproc', 'http', 'decisao', 'aguarde', 'notificacao', 'email', 'valida_arquivo']
const definition = {
 schemaVersion: 1, identity: { pipelineName: NOME, displayName: 'Cobrança diária', extraIdentity: { keep: true } },
 metadata: { legacyPipeline: { pipeline_name: NOME, project_name: 'PROJ_LEGADO', domain: 'FIN', descricao: 'Base', schedule_type: 'daily', scheduled_time: '06:00:00', active: 1, sla_minutos: 60, ambiente: 'DEV', depends_on: 'PRED_A', campo_desconhecido: { a: [1, null] } }, legacyTables: { etl_pipeline_param: [{ param_name: 'cifrado', param_type: 'Encrypted', secretReference: { id: 9 }, param_value: '***' }], tabela_desconhecida: [{ x: null }] }, outro: { z: 1 } },
 nodes: TIPOS.map((type, i) => ({ id: `n${i}`, type, extension: { keep: i }, configuration: { legacyJob: { job_name: `n${i}`, job_type: type, job_command: `cmd ${i}`, execution_order: i + 1, especial: [null, { f: i }] }, unknownConfig: { nested: [i] }, etl_pipeline_job_param: [{ param_name: 'protegido', secretReference: { id: i }, param_value: '***' }] } })),
 edges: [{ source: 'n0', target: 'n1', unknown: 9 }, { source: 'n6', target: 'n7', branch: 'sim' }], topoDesconhecido: { q: null },
}
const layout = { schemaVersion: 1, nodes: Object.fromEntries(TIPOS.map((_, i) => [`n${i}`, { x: i * 10, y: i * 5, extra: 'k' }])), custom: null }
const original = structuredClone(definition)
const draft = { draftId: 'draft-1', pipelineName: NOME, baseVersionId: null, definition, layout, revision: 7, state: 'ativo', createdBy: 'ana', responsible: 'Ana', createdAt: '2026-10-11T10:00:00Z', updatedAt: '2026-10-11T10:00:00Z', readOnlyReasons: [], lease: null }
const LEASE = { holderUser: 'ana', fence: 41, expiresAt: '2999-01-01T00:00:00Z', heldBySession: true }
api.__responder(call => {
 if (call.method === 'GET' && call.p === '/workspace/drafts/draft-1') return structuredClone(draft)
 if (call.method === 'POST' && call.p === '/workspace/drafts/draft-1/lease') return { ...LEASE }
 if (call.method === 'PUT' && call.p === '/workspace/drafts/draft-1') return { ...structuredClone(draft), revision: 8, definition: call.body.definition, layout: call.body.layout, lease: { ...LEASE } }
 throw new Error(`chamada inesperada ${call.method} ${call.p}`)
})
const caps = { schemaVersion: 1, enabled: true, knownNodeTypes: TIPOS, actions: { consultDefinition: true, consultStages: true, consultLogs: true, consultVersions: true, editDraft: true, administer: false, publish: false, execute: false } }
const controle = {}
function Tela({ development }) {
 const [tab, setTab] = mini.hooks.useState('montagem'); const [grupo, setGrupo] = mini.hooks.useState('identificacao')
 controle.tab = setTab; controle.grupo = setGrupo
 return jsx(WorkspaceEditor, { name: NOME, draft, definition, layout, reasons: [], capabilities: caps, development, tab, configGroup: grupo, onConfigGroup: setGrupo, onOpenTab: setTab, onSaved: next => { controle.salvo = next }, onDiscarded() {} })
}
const textoDe = n => typeof n === 'string' ? n : n.filhos.map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const descendentes = n => typeof n === 'string' ? [] : [n, ...n.filhos.flatMap(descendentes)]
const raiz = tela => tela.achar(n => n.props.ref !== undefined && n.tag === 'div' && n.props.className === 'space-y-3')[0]
const controlePor = (escopo, rotulo) => {
 const caixa = escopo.find(n => n.tag === 'div' && n.filhos.some(f => typeof f !== 'string' && f.tag === 'label' && textoDe(f) === rotulo) && n.filhos.some(f => typeof f !== 'string' && ['input', 'select', 'textarea'].includes(f.tag)))
 if (caixa) return caixa.filhos.find(f => typeof f !== 'string' && ['input', 'select', 'textarea'].includes(f.tag))
 const marcado = escopo.find(n => n.tag === 'label' && textoDe(n) === rotulo && n.filhos.some(f => typeof f !== 'string' && f.tag === 'input'))
 return marcado && marcado.filhos.find(f => typeof f !== 'string' && f.tag === 'input')
}
const secoes = tela => tela.achar(n => n.tag === 'section' && (String(n.props['aria-labelledby'] || '').startsWith('workspace-config-') || n.props['aria-label'] === 'Parâmetros'))
const visivel = tela => secoes(tela).filter(s => !s.props.hidden)
const flush = () => new Promise(r => setImmediate(r))
// Nó oculto por um ancestral `hidden` (o minireact não guarda pai: procura de cima).
const ocultoPor = (tela, pred) => tela.achar(n => n.props.hidden === true && descendentes(n).some(d => typeof d !== 'string' && pred(d)))
// `hidden` só oculta se nenhum utilitário de display do mesmo elemento o anular.
const DISPLAY = /(^|\s)([a-z0-9-]+:)?(block|inline|inline-block|flex|inline-flex|grid|inline-grid|table|contents|flow-root)(?=\s|$)/
const hiddenAnulado = tela => tela.achar(n => !!n.props.hidden && DISPLAY.test(String(n.props.className || '')))
const publicacoes = tela => tela.achar(n => n.tag === 'section' && n.props['aria-label'] === 'Validação e publicação')

;(async () => {
 const tela = mini.montar(jsx(Tela, { development: true })).sincronizar()
 assert.equal(raiz(tela).props.hidden, false)
 tela.clicar(tela.botoes('Iniciar edição')[0]); await flush(); await flush(); tela.sincronizar()
 assert.match(tela.texto, /Você está editando o rascunho · revisão 7/)
 // Montagem: adiciona uma etapa pelo catálogo real dos 11 tipos.
 const biblioteca = tela.achar(n => n.tag === 'button' && n.props.draggable !== undefined)
 assert.deepEqual(biblioteca.map(textoDe).sort(), ['Aguarde', 'DataStage', 'Decisão', 'E-mail', 'HTTP', 'Notificação', 'Python', 'SQL', 'Shell', 'Stored Proc', 'Valida Arquivo'])
 tela.clicar(biblioteca.find(b => textoDe(b) === 'Shell'))
 assert.match(tela.achar(n => n.props['data-canvas'] !== undefined)[0].props['data-canvas'], /shell_1/)

 assert.equal(publicacoes(tela).length, 1, 'publicação única na Montagem')
 // Configuração: mesma instância, seis grupos, um visível. A Montagem continua
 // renderizada, oculta por um wrapper sem utilitário de display.
 controle.tab('configuracao'); tela.sincronizar()
 const canvasOculto = tela.achar(n => n.props['data-canvas'] !== undefined)
 assert.equal(canvasOculto.length, 1, 'canvas conservado'); assert.match(canvasOculto[0].props['data-canvas'], /shell_1/)
 assert(ocultoPor(tela, n => n.props['data-canvas'] !== undefined).length >= 1, 'canvas sob ancestral hidden')
 assert(ocultoPor(tela, n => n.props['aria-label'] === 'Ferramentas do fluxo').length >= 1, 'ferramentas ocultas')
 assert.deepEqual(hiddenAnulado(tela).map(n => n.props.className), [], 'nenhum hidden anulado por display')
 assert.equal(publicacoes(tela).length, 1, 'publicação única na Configuração')
 assert.equal(ocultoPor(tela, n => n.props['aria-label'] === 'Validação e publicação').length, 0, 'publicação visível na Configuração')
 const grupos = tela.achar(n => n.tag === 'nav' && n.props['aria-label'] === 'Grupos da configuração')[0]
 assert.deepEqual(descendentes(grupos).filter(n => n.tag === 'button').map(textoDe), ['Identificação', 'Agenda e dependências', 'Parâmetros', 'Políticas de execução', 'Notificações', 'Documentação'])
 assert.deepEqual(visivel(tela).map(s => s.props['aria-labelledby']), ['workspace-config-identificacao'])
 // Inventário: cada campo do pipeline existe uma vez e no grupo canônico.
 const CANONICO = {
  identificacao: ['Projeto', 'Domínio', 'Descrição do pipeline', 'Tags', 'Criticidade', 'Ambiente de destino'],
  agenda: ['Tipo de agendamento', 'Horário da agenda', 'Somente dias úteis', 'Calendário de feriados', 'Data de início DAG (opcional)', 'Hora de virada do dia (ODATE)', 'Não iniciar antes', 'Avisar se dependências não liberarem até'],
  politicas: ['SLA (minutos)', 'Pipeline ativo após publicar', 'Runs simultâneas', 'Retries', 'Delay retry (s)', 'Fila de execução (pool)', 'Liberar pipelines dependentes mesmo sem movimento', 'Notificar conclusão sem movimento'],
  notificacoes: ['Notificar início', 'Notificar conclusão', 'Notificar falha', 'Destinatários de e-mail do fluxo'],
  documentacao: ['Runbook (Markdown)'],
 }
 const porSecao = Object.fromEntries(secoes(tela).map(s => [String(s.props['aria-labelledby'] || 'parametros').replace('workspace-config-', ''), descendentes(s)]))
 for (const [grupo, rotulos] of Object.entries(CANONICO)) for (const rotulo of rotulos) {
  assert(controlePor(porSecao[grupo], rotulo), `${rotulo} em ${grupo}`)
  for (const [outro, nos] of Object.entries(porSecao)) if (outro !== grupo) assert(!controlePor(nos, rotulo), `${rotulo} duplicado em ${outro}`)
 }
 assert(descendentes({ filhos: porSecao.agenda }).some(n => n.tag === 'button' && textoDe(n) === 'Escolher predecessores'))
 assert.equal(controlePor(porSecao.agenda, 'Tipo de agendamento').filhos.length, 8, 'oito agendas')
 // Edita em três grupos.
 tela.clicar(descendentes(grupos).find(n => n.tag === 'button' && textoDe(n) === 'Políticas de execução'))
 assert.deepEqual(visivel(tela).map(s => s.props['aria-labelledby']), ['workspace-config-politicas'])
 const atual = rotulo => controlePor(tela.achar(() => true), rotulo)
 tela.disparar(atual('SLA (minutos)'), 'onChange', { target: { value: '45' } })
 tela.disparar(atual('Descrição do pipeline'), 'onChange', { target: { value: 'Base revisada' } })
 tela.disparar(atual('Tipo de agendamento'), 'onChange', { target: { value: 'hourly_n' } })
 assert.match(tela.texto, /Há alterações não salvas neste rascunho/)

 // Execução: editor oculto, sem ações de rascunho; nada é desmontado.
 controle.tab('execucao'); tela.sincronizar()
 assert.equal(raiz(tela).props.hidden, true)
 const visiveis = n => typeof n === 'string' || n.props.hidden ? [] : [n, ...n.filhos.flatMap(visiveis)]
 assert.equal(visiveis(raiz(tela)).length, 0, 'nada do rascunho visível na Execução')
 assert.equal(tela.botoes('Iniciar edição').length, 0)
 assert(tela.botoes('Salvar rascunho').every(b => !b.props.disabled), 'sessão segue montada, oculta')

 // Volta à Montagem: a etapa nova continua, a posse continua; salva.
 controle.tab('montagem'); tela.sincronizar()
 assert.match(tela.achar(n => n.props['data-canvas'] !== undefined)[0].props['data-canvas'], /shell_1/)
 assert.equal(tela.achar(n => n.props['data-canvas'] !== undefined)[0].props['data-editable'], 'true')
 tela.clicar(tela.botoes('Salvar rascunho')[0]); await flush(); await flush(); tela.sincronizar()

 const leases = api.__calls.filter(c => c.p.endsWith('/lease')), saves = api.__calls.filter(c => c.method === 'PUT')
 assert.equal(leases.length, 1, 'uma única posse'); assert.deepEqual(leases[0].body, {})
 assert.equal(api.__calls.filter(c => /transfer/.test(c.p)).length, 0)
 assert.equal(saves.length, 1)
 const enviado = saves[0].body
 assert.equal(enviado.fence, 41); assert.equal(enviado.expectedRevision, 7)
 assert.deepEqual(enviado.definition.nodes.slice(0, 11), original.nodes, '11 tipos intactos')
 assert.equal(enviado.definition.nodes[11].id, 'shell_1')
 assert.deepEqual(enviado.definition.edges, original.edges)
 assert.deepEqual(enviado.definition.identity, original.identity); assert.deepEqual(enviado.definition.topoDesconhecido, original.topoDesconhecido)
 assert.deepEqual(enviado.definition.metadata.legacyTables, original.metadata.legacyTables, 'referências protegidas e tabelas desconhecidas')
 assert.deepEqual(enviado.definition.metadata.outro, original.metadata.outro)
 const pipeline = enviado.definition.metadata.legacyPipeline
 assert.equal(pipeline.sla_minutos, 45); assert.equal(pipeline.descricao, 'Base revisada'); assert.equal(pipeline.schedule_type, 'custom'); assert.match(pipeline.horarios_especificos, /^\d\d:\d\d(,\d\d:\d\d)*$/)
 for (const chave of ['campo_desconhecido', 'project_name', 'domain', 'depends_on', 'ambiente', 'active']) assert.deepEqual(pipeline[chave], original.metadata.legacyPipeline[chave], chave)
 assert.deepEqual(enviado.layout.nodes.n3, layout.nodes.n3); assert.equal(enviado.layout.custom, null)
 assert.equal(controle.salvo.revision, 8)
 assert.match(tela.texto, /revisão 8/)
 resultado.sessao = { posses: leases.length, saves: saves.length, fence: enviado.fence, abas: ['montagem', 'configuracao', 'execucao', 'montagem'] }

 // Leitura: experiência sem edição não oferece editores ativos nem save.
 api.__calls.length = 0
 const leitura = mini.montar(jsx(Tela, { development: false })).sincronizar()
 controle.tab('configuracao'); leitura.sincronizar()
 const editaveis = (n, travado = false) => typeof n === 'string' ? [] : [...(['input', 'select', 'textarea'].includes(n.tag) && !travado && !n.props.disabled && !n.props.readOnly ? [n] : []), ...n.filhos.flatMap(f => editaveis(f, travado || (n.tag === 'fieldset' && !!n.props.disabled)))]
 const camposLeitura = secoes(leitura).flatMap(s => editaveis(s))
 assert.deepEqual(camposLeitura.map(c => c.props.id || c.props.type), [], 'nenhum campo do pipeline editável em leitura')
 assert(secoes(leitura).flatMap(descendentes).filter(n => ['input', 'select', 'textarea'].includes(n.tag)).length >= 25)
 assert.equal(leitura.botoes('Escolher predecessores').length, 0); assert.equal(leitura.botoes('Salvar rascunho').length, 0); assert.equal(leitura.botoes('Iniciar edição').length, 0)
 assert.equal(api.__calls.length, 0, 'leitura não chama a API de escrita')
 resultado.leitura = true

 // ── 7. Execução: investigação pela URL, vistas e log ──────────────────────
 const rq = require(path.join(tmp, 'node_modules/@tanstack/react-query/index.js'))
 const fluxo = require(path.join(tmp, 'components/etapas/FluxoEditor.js'))
 const { WorkspaceOperations } = require(path.join(tmp, 'components/workspace/WorkspaceOperations.js'))
 rq.__dados['workspace-execution'] = { data_referencia: '2026-10-10', identidade: { run_id: 'r1', dag_run_id: 'manual__r1', candidatos: [{ run_id: 'manual__r1', status: 'success' }] }, workspaceVersion: { number: 4, definition, layout }, etapas: [
  { job_name: 'carga', task_id: 'carga', status: 'success', inicio: '10:00', attempt: 3, tentativas: [{ attempt: 1 }, { attempt: 2 }], total_tentativas: 3, sem_execucao: false },
  { job_name: 'aviso', task_id: null, status: null, inicio: null, attempt: null, tentativas: [], total_tentativas: 0, sem_execucao: true } ] }
 rq.__dados['workspace-log'] = chave => `<script>alert("x")</script> tentativa ${chave[5]}`
 const op = { investigacoes: [] }
 const capsOp = { ...caps, actions: { ...caps.actions, execute: true } }
 function Operacao() {
  const [view, setView] = mini.hooks.useState('grafo'); const [stage, setStage] = mini.hooks.useState(''); const [attempt, setAttempt] = mini.hooks.useState(null); const [ativo, setAtivo] = mini.hooks.useState(true); const [runId, setRunId] = mini.hooks.useState('')
  Object.assign(op, { setView, setStage, setAttempt, setAtivo, setRunId })
  return jsx(WorkspaceOperations, { name: NOME, date: '2026-10-10', runId, stage, attempt, definition, layout, caps: capsOp, view, active: ativo, onView: setView, onDate() {}, onRun: setRunId, onInvestigate: (s, a) => { op.investigacoes.push([s, a]); setStage(s || ''); setAttempt(a) }, actionsHost: null })
 }
 const ex = mini.montar(jsx(Operacao, {})).sincronizar()
 const tabela = n => n.props['aria-label'] === 'Etapas, tentativas e logs da corrida'
 const grafo = () => ex.achar(n => n.props['data-grafo'] !== undefined)
 const logDe = () => ex.achar(n => n.tag === 'section' && n.props['aria-label'] === 'Log da tentativa')
 const mensagem = () => ex.achar(n => n.tag === 'p' && n.props.role === 'status').map(textoDe)
 assert.equal(grafo().length, 1); assert.equal(grafo()[0].props['data-ativo'], 'true'); assert(ocultoPor(ex, tabela).length, 'tabela oculta no gráfico')
 assert.equal(ex.botoes('Executar pipeline').length, 1)
 // Etapa vinda do gráfico/link sem tentativa: abre a tentativa corrente (3) desta corrida.
 op.setStage('carga'); ex.sincronizar(); assert.equal(grafo()[0].props['data-etapa'], 'carga')
 op.setView('tabela'); ex.sincronizar()
 assert.equal(grafo().length, 1, 'gráfico conservado na Tabela'); assert.equal(grafo()[0].props['data-ativo'], 'false'); assert(ocultoPor(ex, n => n.props['data-grafo'] !== undefined).length)
 assert.equal(logDe().length, 1); assert.match(textoDe(logDe()[0]), /carga · tentativa 3 · Airflow/)
 const pre = descendentes(logDe()[0]).find(n => n.tag === 'pre')
 assert.deepEqual(pre.filhos, ['<script>alert("x")</script> tentativa 3'], 'log é texto, não HTML')
 assert.equal(ex.achar(n => n.props.dangerouslySetInnerHTML !== undefined).length, 0)
 assert.equal(controlePor(ex.achar(() => true), 'Buscar etapa nesta corrida').props.value, '', 'busca vazia já mostra a etapa')
 assert.equal(ex.achar(n => n.tag === 'tr' && n.props['aria-current'] === 'true').map(textoDe)[0].startsWith('carga'), true)
 // Tentativa histórica pela tabela: grava etapa+tentativa (contrato da URL).
 ex.clicar(ex.botoes('Tentativa 1')[0]); assert.deepEqual(op.investigacoes.at(-1), ['carga', 1]); assert.match(textoDe(logDe()[0]), /tentativa 1 · Airflow/)
 // Tentativa que não pertence à corrida: nenhum log, motivo explícito.
 op.setAttempt(7); ex.sincronizar(); assert.equal(logDe().length, 0); assert(mensagem().some(t => /tentativa 7 da etapa carga não pertence a esta corrida/.test(t)), mensagem())
 // Corrida pedida diferente da exibida: não abre log de outra corrida.
 op.setAttempt(null); op.setRunId('manual__r2'); ex.sincronizar(); assert.equal(logDe().length, 0); assert(mensagem().some(t => /corrida pedida/.test(t)))
 op.setRunId('manual__r1'); ex.sincronizar(); assert.equal(logDe().length, 1, 'corrida fixada pelo dag_run_id')
 op.setRunId('r1'); ex.sincronizar(); assert.equal(logDe().length, 1, 'corrida fixada pelo run_id')
 // Etapa sem tentativa: nada inventado.
 ex.disparar(controlePor(ex.achar(() => true), 'Buscar etapa nesta corrida'), 'onChange', { target: { value: '' } })
 assert.equal(textoDe(ex.achar(n => n.tag === 'tr' && textoDe(n).startsWith('aviso'))[0]).includes('Sem tentativas'), true)
 assert.equal(ex.achar(n => n.tag === 'tr' && textoDe(n).startsWith('aviso')).flatMap(descendentes).filter(n => n.tag === 'button').length, 0)
 op.setStage('aviso'); ex.sincronizar(); assert.equal(logDe().length, 0); assert(mensagem().some(t => /aviso ainda não tem tentativas/.test(t)))
 // Busca local continua ao alternar vistas (não depende da vista).
 ex.disparar(controlePor(ex.achar(() => true), 'Buscar etapa nesta corrida'), 'onChange', { target: { value: 'avi' } })
 op.setView('grafo'); ex.sincronizar(); op.setView('tabela'); ex.sincronizar()
 assert.equal(controlePor(ex.achar(() => true), 'Buscar etapa nesta corrida').props.value, 'avi')
 // Etapa escolhida no gráfico que a busca esconderia: a busca passa a mostrá-la.
 op.setStage('carga'); ex.sincronizar(); assert.equal(controlePor(ex.achar(() => true), 'Buscar etapa nesta corrida').props.value, 'carga')
 // Execução oculta (outro destino): sem log, sem ação no cabeçalho, gráfico inativo.
 op.setStage('carga'); op.setAtivo(false); ex.sincronizar()
 assert.equal(logDe().length, 0); assert.equal(ex.botoes('Executar pipeline').length, 0)
 op.setView('grafo'); ex.sincronizar(); assert.equal(grafo()[0].props['data-ativo'], 'false')
 assert.deepEqual(hiddenAnulado(ex).map(n => n.props.className), [])
 assert.equal(typeof fluxo.__ultimo.workspace.onStage, 'function')
 resultado.execucao = { corrente: 3, historica: 1, inventada: false, outraCorrida: false, texto: true }

 // Identidade e retorno à Malha.
 assert.notEqual(tabs.runIdentityOrigin(NOME, '2026-10-10', ''), tabs.runIdentityOrigin(NOME, '2026-10-11', ''))
 assert.notEqual(tabs.runIdentityOrigin(NOME, 'a', 'b|c'), tabs.runIdentityOrigin(NOME, 'a|b', 'c'))
 assert.equal(nav.malhaReturnPath(new URLSearchParams({ de: 'malha:M & 1', data: '2026-10-10', corrida: '42', run_id: 'x' })), `/malha?${new URLSearchParams({ malha: 'M & 1', modo: 'execucao', corrida: '42', data: '2026-10-10' })}`)
 assert.equal(nav.malhaReturnPath(new URLSearchParams({ de: 'malha:M', corrida: '-3' })), '/malha?malha=M&modo=execucao')
 for (const de of ['', 'http://mal.example', 'malha:', 'malha:  ']) assert.equal(nav.malhaReturnPath(new URLSearchParams({ de })), null, de)
 const comHash = new URL(nav.contextualPath(NOME, 'configuracao', legado, undefined, '#grupo-x'), 'http://local')
 assert.equal(comHash.hash, '#grupo-x'); for (const [chave, valor] of legado) assert.equal(comHash.searchParams.get(chave), valor)
 assert.equal(new URL(nav.legacyWorkspacePath('fluxos', new URLSearchParams({ pipeline: NOME, modo: 'execucao' }), '#etapa'), 'http://local').hash, '#etapa')
 assert.equal(tabs.parseAttempt('2'), 2); for (const v of ['0', '-1', '1.5', 'x', '', null]) assert.equal(tabs.parseAttempt(v), null)

 // ── 8. Modal numa área oculta ─────────────────────────────────────────────
 const react = require(path.join(tmp, 'node_modules/react/index.js'))
 const overlay = require(path.join(tmp, 'components/ui/overlay.js'))
 const { Modal } = require(path.join(tmp, 'components/ui/Modal.js'))
 const modal = () => mini.montar(jsx(Modal, { open: true, onClose() {}, title: 'Configurar', children: jsx('textarea', { value: 'staging' }) }))
 react.__contexto.set(overlay.OverlayScope, false)
 const inerte = modal()
 assert.equal(inerte.porPapel('dialog').length, 0); assert.equal(inerte.achar(n => n.props['aria-modal'] !== undefined).length, 0)
 assert.deepEqual(inerte.achar(n => n.props.className && String(n.props.className).includes('fixed inset-0'))[0].props.style, { display: 'none' })
 assert.equal(inerte.achar(n => n.tag === 'textarea')[0].props.value, 'staging', 'conteúdo conservado')
 react.__contexto.delete(overlay.OverlayScope)
 const ativo = modal(); assert.equal(ativo.porPapel('dialog').length, 1); assert.equal(ativo.achar(n => n.props.className && String(n.props.className).includes('fixed inset-0'))[0].props.style, undefined)
 resultado.modalOculto = true

 // ── 9. Guarda de navegação (History simulado com idx do router) ───────────
 const dialogs = require(path.join(tmp, 'lib/dialogs.js'))
 const guarda = require(path.join(tmp, 'lib/navigationGuard.js'))
 class Alvo { constructor() { this.l = {} } addEventListener(t, f) { (this.l[t] = this.l[t] || []).push(f) } removeEventListener(t, f) { this.l[t] = (this.l[t] || []).filter(x => x !== f) } emitir(t, e = {}) { let parar = false; e.stopImmediatePropagation = () => { parar = true }; e.preventDefault = () => { e.defaultPrevented = true }; for (const f of [...(this.l[t] || [])]) { f(e); if (parar) break } return e } }
 const BASE = `http://local/pipelines/${encodeURIComponent(NOME)}`
 const entradas = [{ url: 'http://local/pipelines', state: { idx: 0 } }, { url: `${BASE}/montagem?experiencia=desenvolvimento`, state: { idx: 1 } }, { url: `${BASE}/configuracao?experiencia=desenvolvimento&grupo=agenda`, state: { idx: 2 } }]
 let pos = 2; const atribuidos = []
 const win = new Alvo(); win.document = new Alvo()
 win.location = { get href() { return entradas[pos].url }, get origin() { return new URL(entradas[pos].url).origin }, assign: u => atribuidos.push(u) }
 win.history = { get state() { return entradas[pos].state }, go(d) { setImmediate(() => { pos += d; win.emitir('popstate') }) } }
 guarda.installNavigationGuard(win)
 const router = []; win.addEventListener('popstate', () => router.push(win.location.href)) // registrado depois, como o BrowserRouter
 const saidas = []; const navegacoes = []
 guarda.acceptNavigation()
 const registrar = () => guarda.registerNavigationGuard({ guard: () => ({ leaves: (de, para) => !tabs.sameWorkspaceSession(NOME, de, para), message: 'Há alterações não salvas.', onLeave: () => saidas.push('cache descartado') }), navigate: to => navegacoes.push(to) })
 let desfazer = registrar()
 assert.equal((win.l.beforeunload || []).length, 1, 'beforeunload só com guarda ativa')
 // Voltar dentro da sessão: o router recebe direto, sem diálogo.
 win.history.go(-1); await flush(); assert.equal(router.length, 1); assert.equal(dialogs.currentDialog(), null); guarda.acceptNavigation()
 // Voltar para a lista: desfeito antes do router, diálogo da aplicação.
 win.history.go(-1); await flush(); await flush()
 assert.equal(router.length, 1, 'router não viu a saída'); assert.equal(pos, 1, 'endereço restaurado'); assert.match(dialogs.currentDialog().message, /alterações não salvas/)
 dialogs.finishDialog(null); await flush(); assert.equal(pos, 1); assert.equal(router.length, 1); assert.deepEqual(saidas, [], 'cancelar conserva o trabalho')
 win.history.go(-1); await flush(); await flush(); dialogs.finishDialog(true); await flush(); await flush()
 assert.equal(pos, 0); assert.deepEqual(router.slice(1), ['http://local/pipelines'], 'confirmado: o router navega uma vez'); assert.deepEqual(saidas, ['cache descartado'])
 // Fora do Pipeline o editor desmonta (guarda removida); avançar de volta não pergunta nada.
 desfazer(); assert.equal((win.l.beforeunload || []).length, 0)
 guarda.acceptNavigation(); win.history.go(1); await flush(); assert.equal(router.length, 3); assert.equal(dialogs.currentDialog(), null)
 guarda.acceptNavigation(); desfazer = registrar()
 // Clique em link: mesma sessão passa; outra fonte/experiência/pipeline pede confirmação.
 const clique = href => win.document.emitir('click', { button: 0, target: { closest: () => ({ href, target: '', hasAttribute: () => false }) } })
 assert.equal(clique(`${BASE}/execucao?experiencia=desenvolvimento&run_id=1`).defaultPrevented, undefined)
 assert.equal(clique(`${BASE}/configuracao?experiencia=consulta&fonte=publicado`).defaultPrevented, true)
 dialogs.finishDialog(null); await flush(); assert.deepEqual(navegacoes, [])
 assert.equal(clique('http://local/pipelines/OUTRO/montagem?experiencia=desenvolvimento#x').defaultPrevented, true)
 dialogs.finishDialog(true); await flush(); assert.deepEqual(navegacoes, ['/pipelines/OUTRO/montagem?experiencia=desenvolvimento#x'])
 // Programática: intenção verificada no momento da confirmação.
 const programadas = []
 guarda.guardedNavigation(`${BASE}/montagem?experiencia=consulta`, to => programadas.push(to)); await flush()
 const pergunta = dialogs.currentDialog(); assert(pergunta); entradas[pos] = { ...entradas[pos], url: `${BASE}/montagem?experiencia=desenvolvimento&mudou=1` }
 dialogs.finishDialog(true); await flush(); assert.deepEqual(programadas, [], 'tela mudou: navegação antiga descartada')
 guarda.guardedNavigation(`${BASE}/configuracao?experiencia=desenvolvimento`, to => programadas.push(to)); await flush(); assert.equal(dialogs.currentDialog(), null); assert.equal(programadas.length, 1, 'mesma sessão sem diálogo')
 // Entrada sem índice do router não é desfeita (limite declarado).
 entradas.push({ url: 'http://local/fora', state: null }); guarda.acceptNavigation(); const antes = router.length
 win.history.go(entradas.length - 1 - pos); await flush(); assert.equal(router.length, antes + 1)
 desfazer(); assert.equal((win.l.beforeunload || []).length, 0)
 resultado.guarda = { voltarSessao: 'sem diálogo', voltarSaida: 'desfeito+confirmado', cancelar: 'conserva', clique: true, programatica: true }

 // ── 10. Escopo de overlay composto: aba E grupo ───────────────────────────
 // O defeito: Identificação → Parâmetros → abrir catálogo → Back ocultava a
 // seção, mas o escopo do Editor (configuring=true) mantinha o Modal ativo e
 // invisível, prendendo foco e Esc. O escopo agora é por grupo.
 react.__lazy.set('./WorkspaceParameters', require(path.join(tmp, 'components/workspace/WorkspaceParameters.js')).WorkspaceParameters)
 react.__lazy.set('../pipelines/DependenciasModal', require(path.join(tmp, 'components/pipelines/DependenciasModal.js')).DependenciasModal)
 api.__calls.length = 0
 const cfg = mini.montar(jsx(Tela, { development: true })).sincronizar()
 cfg.clicar(cfg.botoes('Iniciar edição')[0]); await flush(); await flush(); cfg.sincronizar()
 controle.tab('configuracao'); cfg.sincronizar()
 const CATALOGO = 'Parâmetros do pipeline', DEPENDENCIAS = 'Escolher dependências'
 const grupoBotao = rotulo => descendentes(cfg.achar(n => n.tag === 'nav' && n.props['aria-label'] === 'Grupos da configuração')[0]).find(n => n.tag === 'button' && textoDe(n) === rotulo)
 // Estado de um overlay real pelo que o Modal renderiza: ativo (diálogo
 // exibido), inerte (montado, display none, sem role/aria-modal) ou fechado.
 const overlayEstado = titulo => {
  const raizes = cfg.achar(n => n.tag === 'div' && String(n.props.className || '').includes('fixed inset-0') && descendentes(n).some(d => typeof d !== 'string' && d.props['aria-label'] === titulo))
  if (!raizes.length) return 'fechado'
  assert.equal(raizes.length, 1, `uma instância de ${titulo}`)
  const painel = descendentes(raizes[0]).find(d => typeof d !== 'string' && d.props['aria-label'] === titulo)
  if (raizes[0].props.style === undefined && painel.props.role === 'dialog' && painel.props['aria-modal'] === 'true') return 'ativo'
  if (raizes[0].props.style && raizes[0].props.style.display === 'none' && painel.props.role === undefined && painel.props['aria-modal'] === undefined) return 'inerte'
  return 'inconsistente'
 }
 const estados = () => ({ catalogo: overlayEstado(CATALOGO), dependencias: overlayEstado(DEPENDENCIAS), dialogos: cfg.porPapel('dialog').length, modais: cfg.achar(n => n.props['aria-modal'] !== undefined).length })
 const referencia = () => controlePor(cfg.achar(() => true), 'Simular com a referência').props.value
 // Identificação → Parâmetros → abre o catálogo e altera um campo local dele.
 cfg.clicar(grupoBotao('Parâmetros')); cfg.clicar(cfg.botoes('Configurar parâmetros')[0])
 assert.deepEqual(estados(), { catalogo: 'ativo', dependencias: 'fechado', dialogos: 1, modais: 1 })
 cfg.disparar(controlePor(cfg.achar(() => true), 'Simular com a referência'), 'onChange', { target: { value: '2026-01-31' } })
 // Back do navegador: a URL volta a Identificação. Catálogo montado e inerte.
 controle.grupo('identificacao'); cfg.sincronizar()
 assert.deepEqual(visivel(cfg).map(s => s.props['aria-labelledby']), ['workspace-config-identificacao'])
 assert.deepEqual(estados(), { catalogo: 'inerte', dependencias: 'fechado', dialogos: 0, modais: 0 }, 'catálogo de grupo oculto não fica ativo')
 // Escopo por grupo, não por aba: Agenda abre o seu, o catálogo segue inerte.
 cfg.clicar(grupoBotao('Agenda e dependências')); cfg.clicar(cfg.botoes('Escolher predecessores')[0])
 assert.deepEqual(estados(), { catalogo: 'inerte', dependencias: 'ativo', dialogos: 1, modais: 1 })
 // Volta a Parâmetros: catálogo reativa com o rascunho local conservado.
 controle.grupo('parametros'); cfg.sincronizar()
 assert.deepEqual(estados(), { catalogo: 'ativo', dependencias: 'inerte', dialogos: 1, modais: 1 })
 assert.equal(referencia(), '2026-01-31', 'conteúdo do catálogo conservado')
 // Aba oculta: grupo === id não reativa nada (Parâmetros segue na URL).
 for (const aba of ['execucao', 'montagem']) {
  controle.tab(aba); cfg.sincronizar()
  assert.deepEqual(estados(), { catalogo: 'inerte', dependencias: 'inerte', dialogos: 0, modais: 0 }, aba)
 }
 // Área externa inativa acima do Editor (herdado false): nem a aba
 // Configuração nem o grupo visível reativam.
 react.__contexto.set(overlay.OverlayScope, false)
 controle.tab('configuracao'); cfg.sincronizar()
 assert.deepEqual(visivel(cfg).map(s => s.props['aria-label']), ['Parâmetros'])
 assert.deepEqual(estados(), { catalogo: 'inerte', dependencias: 'inerte', dialogos: 0, modais: 0 }, 'herdado inativo prevalece')
 react.__contexto.delete(overlay.OverlayScope)
 controle.grupo('identificacao'); cfg.sincronizar(); controle.grupo('parametros'); cfg.sincronizar()
 assert.deepEqual(estados(), { catalogo: 'ativo', dependencias: 'inerte', dialogos: 1, modais: 1 })
 assert.equal(referencia(), '2026-01-31')
 // Sessão intacta: uma posse, nenhuma liberação ou save, rascunho em edição.
 assert.equal(api.__calls.filter(c => c.p.endsWith('/lease')).length, 1)
 assert.deepEqual(api.__calls.filter(c => c.method !== 'GET' && !c.p.endsWith('/lease')), [])
 assert.match(cfg.texto, /Você está editando o rascunho · revisão 7/)
 assert.deepEqual(hiddenAnulado(cfg).map(n => n.props.className), [])
 resultado.overlayGrupo = { voltar: 'inerte', porGrupo: true, abaOculta: 'inerte', herdadoInativo: 'inerte', reativa: 'conservado', posses: 1 }

 console.log(JSON.stringify({ ...resultado, passed: true }))
})().catch(e => { console.error(e); process.exit(1) })
