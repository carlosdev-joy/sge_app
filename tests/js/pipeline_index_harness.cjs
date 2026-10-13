// Bancada da F2 da UX de Pipeline (descoberta e entrada única).
//
// Executa o código REAL do src/ (sucrase + minireact; carregador copiado de
// workspace_ux_contexto_harness.cjs):
//  1. lib/pipelineIndex: filtros na URL (padrões, valores inválidos, editing para
//     todo leitor, chaves alheias preservadas, página volta a 1), caminho da
//     consulta com limit/offset reais, resumo de página, rótulos de situação que
//     coexistem (publicado + em desenvolvimento na mesma linha), posse só quando
//     informada, menu coerente com capacidades, registro legado pela grafia exata,
//     erros 503/422/403, validação e conflito da criação.
//  2. PipelineCatalog real: uma linha por item; nome e situação em texto visível
//     (sem title/hover); "Continuar montagem" só com rascunho e edição; filtro
//     "Em edição" e quem edita também sem tela_jobs; filtros e páginas na URL; a
//     leitura repassa o AbortSignal (cancelamento) e a chave muda com os filtros;
//     503 mostra o motivo do servidor e oferece a lista clássica.
//  3. Pipelines real: coorte entra pela lista única; fora dela, sem capacidade
//     ou com ?legado=1, a lista anterior (com volta à lista única na coorte).
//  4. PipelineCreate real: sem agenda na criação; identificador inválido não
//     chama a API e aponta o campo; criação envia rascunho sob demanda, sem DAG,
//     e abre a Montagem; 409 vira erro no campo com o existente localizável.
//
// Limites: minireact não roda useEffect (o debounce de 250 ms é coberto pela
// constante e pelo navegador real), não tem DOM/CSS/foco.
'use strict'
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert/strict')
const RAIZ = path.resolve(__dirname, '..', '..'), SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
// Foco pedido por id: registra o campo que receberia o foco no navegador.
const focos = []; globalThis.document = { getElementById: id => ({ focus() { focos.push(id) } }) }

const ENTRADAS = ['lib/pipelineIndex.ts', 'lib/workspaceApi.ts', 'components/pipelines/PipelineCatalog.tsx', 'pages/Pipelines.tsx', 'pages/PipelineCreate.tsx', 'store/auth.ts']
const DUBLES = {
 'lib/api.ts': `
const calls = []; let responder = () => ({})
exports.__calls = calls; exports.__responder = fn => { responder = fn }
const record = (p, o = {}) => { const call = { p, method: o.method || 'GET', body: o.body ? JSON.parse(o.body) : undefined, signal: o.signal }; calls.push(call); return call }
exports.apiFetch = async (p, o) => responder(record(p, o))
exports.apiFetchBruto = async (p, o) => { record(p, o); return { status: 204, text: async () => '' } }
exports.esquecerConversasDeAgentes = () => {}
exports.currentToken = () => null
exports.BASE = '/orquestra'
`,
 // Telas legadas pesadas: a bancada só precisa saber qual foi aberta.
 'components/pipelines/PipelineModals.tsx': `
const { jsx } = require('react/jsx-runtime')
for (const nome of ['ViewModal', 'AuditModal', 'LineageModal', 'InactivateModal', 'GenDagModal', 'ExecModal']) exports[nome] = p => jsx('div', { 'data-modal': nome, 'data-pipeline': p.pipeline && p.pipeline.pipeline_name })
`,
 'components/pipelines/PipelineFormModal.tsx': `const { jsx } = require('react/jsx-runtime'); exports.PipelineFormModal = () => jsx('div', { 'data-modal': 'PipelineFormModal' })`,
 'components/workspace/WorkspacePipelineFields.tsx': `
const { jsx } = require('react/jsx-runtime')
exports.WorkspaceCatalogFields = p => { exports.__catalog = p; return jsx('div', { 'data-catalogo': p.project + '|' + p.domain }) }
exports.WorkspaceScheduleFields = () => jsx('div', { 'data-agenda': 'sim', children: 'Tipo de agendamento' })
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
function lazy() { return function Lazy() { return null } }
function Suspense(p) { return p.children }
module.exports = Object.assign({}, mini.hooks, { createElement: mini.criar, Fragment: mini.FRAGMENT, forwardRef, lazy, Suspense, memo: C => C, useDeferredValue: v => v, useId: () => { const r = mini.hooks.useRef(null); if (r.current === null) r.current = 'orq-' + (++seq); return r.current }, useSyncExternalStore: (_assinar, ler) => ler() })
module.exports.default = module.exports
`)
 const runtime = `const mini = require(${MINI}); const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key }); module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }`
 escrever('react', 'jsx-runtime.js', runtime); escrever('react', 'jsx-dev-runtime.js', runtime)
 pacote('react-dom', `module.exports = { createPortal: el => el }; module.exports.default = module.exports`)
 // URL simulada: setSearchParams grava a próxima query (o teste remonta a tela com ela).
 pacote('react-router-dom', `
const { jsx } = require('react/jsx-runtime')
let params = new URLSearchParams()
exports.__navegacoes = []; exports.__escritas = []
exports.__url = q => { params = new URLSearchParams(q) }
exports.useNavigate = () => to => exports.__navegacoes.push(to)
exports.useSearchParams = () => [params, (next, opts) => { params = new URLSearchParams(next); exports.__escritas.push({ query: String(params), replace: !!(opts && opts.replace) }) }]
exports.useLocation = () => ({ pathname: '/pipelines', search: '?' + params, hash: '', key: 'k' })
exports.Link = p => jsx('a', Object.assign({}, p, { to: undefined, href: typeof p.to === 'string' ? p.to : (p.to.pathname || '') + (p.to.search || '') }))
exports.Navigate = p => jsx('navigate', { to: p.to })
`)
 pacote('@tanstack/react-query', `
const fixtures = {}, opcoes = {}, estados = {}
exports.__dados = fixtures; exports.__opcoes = opcoes; exports.__estados = estados; exports.__invalidadas = []; exports.__refetch = 0
exports.useQuery = o => { opcoes[o.queryKey[0]] = o; const f = fixtures[o.queryKey[0]]; const data = typeof f === 'function' ? f(o.queryKey) : f; return Object.assign({ data, isPending: false, isError: false, error: null, fetchStatus: 'idle', isFetching: false, isPlaceholderData: false, refetch() { exports.__refetch++ } }, estados[o.queryKey[0]] || {}) }
exports.useMutation = o => ({ isPending: false, mutate(v) { Promise.resolve().then(() => o.mutationFn(v)).then(r => { if (o.onSuccess) o.onSuccess(r, v) }, e => { if (o.onError) o.onError(e, v) }) } })
exports.useQueryClient = () => ({ invalidateQueries(q) { exports.__invalidadas.push(q) }, setQueryData() {} })
`)
 pacote('zustand', `
function make(init) { let state; const api = { getState: () => state, setState: p => { state = Object.assign({}, state, typeof p === 'function' ? p(state) : p) }, subscribe: () => () => {} }; state = init(api.setState, api.getState, api); const hook = sel => sel ? sel(state) : state; return Object.assign(hook, api) }
exports.create = init => init ? make(init) : make
`)
 escrever('zustand', 'middleware.js', 'exports.persist = fn => fn')
 const proxy = `module.exports = new Proxy({}, { get: (_, nome) => { if (nome === '__esModule') return true; const C = () => ({ __el: true, tipo: 'svg', props: { 'data-icone': String(nome) } }); Object.defineProperty(C, 'name', { value: String(nome) }); return C } })`
 pacote('lucide-react', proxy)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pipeline-index-'))
preparar(tmp); shims(tmp)
const req = rel => require(path.join(tmp, rel))
const ix = req('lib/pipelineIndex.js'), ws = req('lib/workspace.js'), api = req('lib/api.js'), { workspaceApi } = req('lib/workspaceApi.js')
const rq = req('node_modules/@tanstack/react-query/index.js'), router = req('node_modules/react-router-dom/index.js')
const { useAuthStore } = req('store/auth.js')
const { jsx } = req('node_modules/react/jsx-runtime.js')
const resultado = {}
const cru = n => typeof n === 'string' ? n : n.filhos.map(cru).join('')
const textoDe = n => cru(n).replace(/\s+/g, ' ').trim()

// ── 1. Contrato puro ────────────────────────────────────────────────────────
const ACTIONS = { consultDefinition: true, consultStages: true, consultLogs: true, consultVersions: true, editDraft: true, administer: false, publish: true, execute: true, contextualNavigation: true }
const READER = { ...ACTIONS, consultStages: false, consultLogs: false, consultVersions: false, editDraft: false, publish: false, execute: false }
const f0 = ix.filtersFromSearch(new URLSearchParams())
assert.deepEqual(f0, { search: '', project: '', domain: '', state: 'all', page: 1 })
assert.deepEqual(ix.filtersFromSearch(new URLSearchParams('busca=%20Cobran%C3%A7a%20&projeto=BI&dominio=Fin&estado=draft&pagina=3')), { search: 'Cobrança', project: 'BI', domain: 'Fin', state: 'draft', page: 3 })
for (const q of ['estado=x', 'estado=ALL', 'pagina=0', 'pagina=-2', 'pagina=1.5', 'pagina=abc', 'pagina=99999999']) { const f = ix.filtersFromSearch(new URLSearchParams(q)); assert(f.state === 'all' && f.page === 1, q) }
assert.equal(ix.filtersFromSearch(new URLSearchParams('estado=editing')).state, 'editing', 'posse válida é resumo de todo leitor')
assert.equal(ix.filtersFromSearch(new URLSearchParams('busca=' + 'x'.repeat(300))).search.length, 200)
const escrita = ix.filtersToSearch({ search: 'a b', project: '', domain: 'D', state: 'all', page: 1 }, new URLSearchParams('legado=0&busca=velha&pagina=4'))
assert.equal(escrita.get('legado'), '0'); assert.equal(escrita.get('busca'), 'a b'); assert(!escrita.has('pagina') && !escrita.has('estado') && !escrita.has('projeto')); assert.equal(escrita.get('dominio'), 'D')
assert.deepEqual(ix.filtersFromSearch(ix.filtersToSearch({ search: 'ç%_&', project: 'P/1', domain: 'd', state: 'inactive', page: 7 })), { search: 'ç%_&', project: 'P/1', domain: 'd', state: 'inactive', page: 7 })
assert.equal(ix.withFilter({ ...f0, page: 9 }, { state: 'published' }).page, 1, 'filtro novo volta à primeira página')
assert(!ix.hasActiveFilters(f0) && ix.hasActiveFilters({ ...f0, domain: 'x' }) && ix.hasActiveFilters({ ...f0, state: 'draft' }))
const caminho = new URL('http://x' + ix.pipelineIndexPath({ search: 'a&b%', project: 'P', domain: '', state: 'editing', page: 3 }))
assert.equal(caminho.pathname, '/workspace/pipeline-index'); assert.equal(caminho.searchParams.get('limit'), '50'); assert.equal(caminho.searchParams.get('offset'), '100')
assert.equal(caminho.searchParams.get('search'), 'a&b%'); assert.equal(caminho.searchParams.get('project'), 'P'); assert(!caminho.searchParams.has('domain')); assert.equal(caminho.searchParams.get('state'), 'editing')
assert(!new URL('http://x' + ix.pipelineIndexPath(f0)).searchParams.has('state'))
assert.equal(ix.PIPELINE_INDEX_LIMIT, 50); assert.equal(ix.PIPELINE_INDEX_DEBOUNCE_MS, 250)
assert.notDeepEqual(ix.pipelineIndexQueryKey('t', f0), ix.pipelineIndexQueryKey('t', { ...f0, page: 2 })); assert.notDeepEqual(ix.pipelineIndexQueryKey('t', f0), ix.pipelineIndexQueryKey('u', f0))
assert.deepEqual(ix.pageSummary({ total: 123, limit: 50, offset: 50, count: 50 }), { text: '51–100 de 123', hasPrevious: true, hasNext: true, pages: 3, current: 2 })
assert.deepEqual(ix.pageSummary({ total: 123, limit: 50, offset: 100, count: 23 }).hasNext, false)
assert.equal(ix.pageSummary({ total: 0, limit: 50, offset: 0, count: 0 }).text, 'Nenhum pipeline')
assert.match(ix.pageSummary({ total: 10, limit: 50, offset: 200, count: 0 }).text, /sem resultados; 10 no total/)

const item = over => ({ pipelineName: 'cobranca_diaria', displayName: 'Cobrança diária', project: 'BI', domain: 'Cobrança', responsible: 'ALICE', hasDraft: false, draftRevision: null, hasPublished: true, publishedVersionNumber: null, isActive: true, managed: false, updatedAt: null, updatedSource: null, editorUser: null, editorName: null, leaseExpiresAt: null, ...over })
const chips = it => ix.pipelineChips(it, 'ALICE').map(c => c.label)
assert.deepEqual(chips(item({ hasDraft: true, draftRevision: 4, publishedVersionNumber: 3 })), ['Publicado · versão 3', 'Em desenvolvimento · revisão 4'], 'publicado + draft na mesma linha')
assert.deepEqual(chips(item({ hasPublished: false, hasDraft: true, draftRevision: 1, isActive: null })), ['Ainda não publicado', 'Em desenvolvimento · revisão 1'])
assert.deepEqual(chips(item({ hasDraft: true, draftRevision: 2, editorUser: 'BOB', editorName: 'Bob Silva' })), ['Publicado', 'Em desenvolvimento · revisão 2', 'Em edição por Bob Silva'])
assert.deepEqual(chips(item({ hasDraft: true, draftRevision: 2, editorUser: 'alice' })), ['Publicado', 'Em desenvolvimento · revisão 2', 'Em edição por você'])
assert.deepEqual(chips(item({ hasDraft: true, editorUser: 'BOB' })).at(-1), 'Em edição por BOB', 'sem nome, matrícula')
assert.deepEqual(chips(item({ isActive: false })), ['Publicado', 'Inativo']); assert.deepEqual(chips(item({ isActive: null })), ['Publicado'], 'NULL não é inativo')
assert.deepEqual(chips(item({ hasPublished: false, isActive: false })), ['Ainda não publicado'], 'inativo exige publicado')
assert(!chips(item({ hasDraft: true })).some(c => /edição/.test(c)), 'draft sem posse não é edição em andamento')
assert.equal(ix.pipelineTitle(item({ displayName: '  ' })), 'cobranca_diaria'); assert.equal(ix.pipelineTitle(item({})), 'Cobrança diária')
assert.equal(ix.updatedLabel(item({ updatedAt: '2026-10-11T12:00:00Z', updatedSource: 'draft' }), () => 'D'), 'Rascunho salvo em D')
assert.equal(ix.updatedLabel(item({ updatedAt: '2026-10-11T12:00:00Z', updatedSource: 'version' }), () => 'D'), 'Versão criada em D')
assert.equal(ix.updatedLabel(item({ updatedAt: '2026-10-11T12:00:00Z', updatedSource: null })), null, 'sem origem nada é inventado')
assert.equal(ix.updatedLabel(item({ updatedAt: 'lixo', updatedSource: 'draft' })), null)

assert.deepEqual(ix.resumeAction(item({ hasDraft: true }), ACTIONS, 'ALICE'), { label: 'Continuar montagem', route: { tab: 'montagem', experience: 'desenvolvimento' } })
assert.equal(ix.resumeAction(item({ hasDraft: true, editorUser: 'BOB' }), ACTIONS, 'ALICE').label, 'Abrir montagem')
assert.equal(ix.resumeAction(item({ hasDraft: true }), READER, 'ALICE'), null); assert.equal(ix.resumeAction(item({}), ACTIONS, 'ALICE'), null)
assert.deepEqual(ix.overviewRoute(READER), { tab: 'visao-geral', experience: 'consulta' }); assert.deepEqual(ix.overviewRoute(ACTIONS), { tab: 'visao-geral', experience: 'desenvolvimento' })
const rotulos = (it, a) => ix.pipelineMenu(it, a).map(e => e.label)
assert.deepEqual(rotulos(item({}), ACTIONS), ['Visão geral', 'Montagem', 'Execução', 'Configuração', 'Versões', 'Ver cadastro publicado', 'Lineage', 'Histórico de alterações'])
assert.deepEqual(rotulos(item({ hasPublished: false, hasDraft: true }), ACTIONS), ['Visão geral', 'Montagem', 'Configuração', 'Versões'], 'sem publicado: sem Execução nem cadastro legado')
assert.deepEqual(rotulos(item({}), READER), ['Visão geral', 'Configuração', 'Ver cadastro publicado', 'Lineage', 'Histórico de alterações'], 'leitor sem tela_jobs/logs/versões')
assert(ix.pipelineMenu(item({}), ACTIONS).filter(e => e.kind === 'route').every(e => ['visao-geral', 'montagem', 'execucao', 'configuracao', 'versoes'].includes(e.route.tab)))
const linhas = [{ pipeline_name: 'a_b' }, { pipeline_name: 'aXb' }, { pipeline_name: 'A_B2' }]
assert.equal(ix.legacyRecord(linhas, 'a_b'), linhas[0]); assert.equal(ix.legacyRecord([{ pipeline_name: 'Árvore' }], 'árvore').pipeline_name, 'Árvore')
assert.equal(ix.legacyRecord([{ pipeline_name: 'X' }, { pipeline_name: 'x ' }], 'y'), null); assert.equal(ix.legacyRecord([{ pipeline_name: 'Ab' }, { pipeline_name: 'aB' }], 'ab'), null, 'ambíguo não escolhe')
assert.deepEqual(ix.indexErrorMessage({ status: 503, message: 'Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql' }), { text: 'Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql', offerLegacy: true })
assert.equal(ix.indexErrorMessage({ status: 500, message: 'stack interno' }).text, 'Não foi possível carregar os pipelines agora.', 'só 503 exibe o motivo do servidor')
assert.equal(ix.indexErrorMessage({ status: 403 }).offerLegacy, false); assert.equal(ix.indexErrorMessage({ status: 422, message: 'Limite deve estar entre 1 e 100' }).text, 'Limite deve estar entre 1 e 100')

assert.deepEqual(ix.createFieldErrors({ name: ' ', identifier: '', description: '' }), { name: 'Informe o nome do pipeline.', identifier: 'Informe o identificador técnico.' })
for (const ruim of ['com espaço', 'ação', 'a/b', 'x'.repeat(201)]) assert(ix.createFieldErrors({ name: 'N', identifier: ruim, description: '' }).identifier, ruim)
for (const bom of ['etl_cobranca', 'A.B-c_1']) assert.deepEqual(ix.createFieldErrors({ name: 'N', identifier: bom, description: '' }), {}, bom)
assert(ix.createFieldErrors({ name: 'N', identifier: 'a', description: 'x'.repeat(501) }).description); assert.equal(ix.DESCRIPTION_MAX, 500)
for (const nome of ['Cobrança diária', 'Carga ÇÃO 2026 / Lote', '東京 ação']) { const s = ws.technicalSuggestion(nome); assert(!s || !ix.createFieldErrors({ name: nome, identifier: s, description: '' }).identifier, nome + ' → ' + s) }
assert.match(ix.createConflict({ status: 409, code: 'pipeline_exists' }), /publicado/); assert.match(ix.createConflict({ status: 409, code: 'draft_conflict' }), /rascunho/)
assert.equal(ix.createConflict({ status: 409, code: 'lease_held' }), null); assert.equal(ix.createConflict({ status: 503, code: 'pipeline_exists' }), null)
resultado.contrato = 'ok'

// ── 2. PipelineCatalog real ────────────────────────────────────────────────
useAuthStore.setState({ user: { matricula: 'ALICE', perfil: 'dev', primeiro_nome: 'Alice', ultimo_nome: 'Souza' }, token: 'tok' })
const { PipelineCatalog } = req('components/pipelines/PipelineCatalog.js')
const ITENS = [
 item({ pipelineName: 'cobranca_diaria', hasDraft: true, draftRevision: 4, publishedVersionNumber: 3, managed: true, updatedAt: '2026-10-11T12:00:00Z', updatedSource: 'draft', editorUser: 'BOB', editorName: 'Bob Silva' }),
 item({ pipelineName: 'novo_rascunho', displayName: 'Novo rascunho', hasPublished: false, hasDraft: true, draftRevision: 1, isActive: null, project: null, domain: null }),
 item({ pipelineName: 'legado_inativo', displayName: null, isActive: false, responsible: null }),
]
let chaves = []
rq.__dados['pipeline-index'] = key => { chaves.push(key); return { total: 123, limit: 50, offset: 50, items: ITENS } }
rq.__dados['pipeline-projects'] = { projects: ['BI'] }; rq.__dados['pipeline-domains'] = { domains: ['Cobrança'] }
router.__url('busca=cob&pagina=2&legado=0')
let tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
const lista = tela.achar(n => n.tag === 'ul' && n.props['aria-label'] === 'Pipelines')[0]
const itens = lista.filhos.filter(n => typeof n !== 'string' && n.tag === 'li' && !n.props['aria-hidden'])
assert.equal(itens.length, 3, 'uma linha por pipeline')
for (const frase of ['Cobrança diária', 'cobranca_diaria', 'Publicado · versão 3', 'Em desenvolvimento · revisão 4', 'Em edição por Bob Silva', 'Ainda não publicado', 'Inativo', '51–53 de 123', 'Página 2 de 3', 'Responsável: ALICE']) assert(tela.texto.includes(frase), frase)
assert.equal(tela.achar(n => n.props.title !== undefined).length, 0, 'nada depende de title/hover')
assert.equal(tela.botoes('Continuar montagem').length, 1, 'só a linha com rascunho e sem outro editor continua; com editor alheio abre')
assert.equal(tela.botoes('Abrir montagem').length, 1)
const links = tela.achar(n => n.tag === 'a').map(a => a.props.href)
assert(links.includes(ws.workspacePath('cobranca_diaria', 'visao-geral', 'desenvolvimento')), 'nome leva à Visão geral')
assert(links.includes('?legado=1'), 'lista clássica disponível')
assert.equal(tela.botoes('Em edição').length, 1, 'filtro de posse')
const chave = chaves.at(-1); assert.deepEqual(chave, ['pipeline-index', 'tok', 'cob', '', '', 'all', 2])
const sinal = new AbortController().signal
api.__calls.length = 0; api.__responder(() => ({ total: 0, limit: 50, offset: 0, items: [] }))
;(async () => {
 await rq.__opcoes['pipeline-index'].queryFn({ signal: sinal })
 assert.equal(api.__calls[0].signal, sinal, 'cancelamento: o AbortSignal chega à leitura')
 assert.equal(api.__calls[0].p, '/workspace/pipeline-index?limit=50&offset=50&search=cob')
 assert.equal(typeof rq.__opcoes['pipeline-index'].placeholderData, 'function')

 // Filtros e página escritos na URL (replace), página volta a 1 ao filtrar; chaves alheias ficam.
 router.__escritas.length = 0
 tela.clicar(tela.botoes('Publicados')[0]); assert.deepEqual(router.__escritas.at(-1), { query: 'busca=cob&legado=0&estado=published', replace: true })
 router.__url('busca=cob&pagina=2'); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 tela.clicar(tela.botoes('Próxima')[0]); assert.equal(new URLSearchParams(router.__escritas.at(-1).query).get('pagina'), '3')
 router.__url('busca=cob&pagina=2'); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 tela.clicar(tela.botoes('Anterior')[0]); assert(!new URLSearchParams(router.__escritas.at(-1).query).has('pagina'))
 tela.clicar(tela.botoes('Filtros')[0]); assert(tela.texto.includes('Todos os projetos'))
 const projeto = tela.achar(n => n.tag === 'select')[0]; tela.disparar(projeto, 'onChange', { target: { value: 'BI' } })
 assert.equal(new URLSearchParams(router.__escritas.at(-1).query).get('projeto'), 'BI')

 // Menu: rotas do workspace e consultas legadas pela grafia exata.
 router.__url(''); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 const menus = tela.achar(n => n.tag === 'button' && n.props['aria-haspopup'] === 'menu')
 assert.equal(menus.length, 3); assert.deepEqual(menus.map(textoDe), ['Mais ações de Cobrança diária', 'Mais ações de Novo rascunho', 'Mais ações de legado_inativo'], 'menu nomeado por linha')
 tela.clicar(menus[0])
 const opcoes = tela.porPapel('menuitem').map(n => n.filhos.join(''))
 assert.deepEqual(opcoes, ['Visão geral', 'Montagem', 'Execução', 'Configuração', 'Versões', 'Ver cadastro publicado', 'Lineage', 'Histórico de alterações'])
 router.__navegacoes.length = 0; tela.clicar(tela.porPapel('menuitem')[2]); assert.equal(router.__navegacoes[0], ws.workspacePath('cobranca_diaria', 'execucao', 'sustentacao'))
 api.__calls.length = 0; api.__responder(() => ({ data: [{ pipeline_name: 'cobrancaXdiaria' }, { pipeline_name: 'cobranca_diaria', active: 1 }] }))
 tela.clicar(tela.achar(n => n.tag === 'button' && n.props['aria-haspopup'] === 'menu')[0]); tela.clicar(tela.porPapel('menuitem')[5])
 await new Promise(r => setTimeout(r, 0)); tela.sincronizar()
 assert.equal(api.__calls[0].p, '/pipelines?limit=100&filter_name=cobranca_diaria')
 assert.equal(tela.achar(n => n.props['data-modal'] === 'ViewModal')[0].props['data-pipeline'], 'cobranca_diaria', 'grafia exata, não o curinga do LIKE')

 // Leitor sem tela_jobs: vê quem edita e filtra edição em andamento, sem continuar montagem.
 rq.__dados['pipeline-index'] = key => { chaves.push(key); return { total: 3, limit: 50, offset: 0, items: ITENS } }
 router.__url('estado=editing'); chaves = []; tela = mini.montar(jsx(PipelineCatalog, { actions: READER }))
 assert.equal(tela.botoes('Em edição').length, 1); assert.equal(chaves.at(-1)[5], 'editing', 'estado editing da URL respeitado sem tela_jobs')
 assert.equal(tela.botoes('Em edição')[0].props['aria-pressed'], true)
 assert(tela.texto.includes('Em edição por Bob Silva'), 'leitor encontra quem edita')
 assert.equal(tela.botoes('Continuar montagem').length + tela.botoes('Abrir montagem').length, 0); assert.equal(tela.botoes('Novo pipeline').length, 0)

 // 503 honesto com a lista clássica; vazio com filtros oferece limpar.
 rq.__estados['pipeline-index'] = { isError: true, error: Object.assign(new Error('Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql'), { status: 503 }), data: undefined }
 router.__url(''); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 assert(tela.texto.includes('aplique a migration 141')); assert.equal(tela.porPapel('alert').length, 1)
 tela.clicar(tela.botoes('Tentar novamente')[0]); assert.equal(rq.__refetch, 1)
 tela.clicar(tela.botoes('Usar lista clássica')[0]); assert.equal(router.__escritas.at(-1).query, 'legado=1')
 delete rq.__estados['pipeline-index']
 rq.__dados['pipeline-index'] = () => ({ total: 0, limit: 50, offset: 0, items: [] })
 router.__url('busca=zzz'); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 assert(tela.texto.includes('Nenhum pipeline corresponde a esta busca.')); assert.equal(tela.botoes('Limpar filtros').length, 1)
 router.__url(''); tela = mini.montar(jsx(PipelineCatalog, { actions: ACTIONS }))
 assert(tela.texto.includes('Nenhum pipeline cadastrado ainda.')); assert.equal(tela.botoes('Novo pipeline').length, 2)
 resultado.lista = 'ok'

 // ── 3. Portão da coorte ──────────────────────────────────────────────────
 const Pipelines = req('pages/Pipelines.js').default
 rq.__dados.pipelines = { total: 0, data: [] }
 rq.__dados['pipeline-index'] = () => ({ total: 1, limit: 50, offset: 0, items: [ITENS[1]] })
 const caps = actions => { rq.__dados['workspace-capabilities'] = { schemaVersion: 1, enabled: true, knownNodeTypes: [], actions } }
 caps(ACTIONS); router.__url(''); tela = mini.montar(jsx(Pipelines, {}))
 assert(tela.texto.includes('Publicados e em desenvolvimento numa única lista')); assert(!tela.texto.includes('Pipelines: são os fluxos'))
 caps({ ...ACTIONS, contextualNavigation: false }); tela = mini.montar(jsx(Pipelines, {}))
 assert(tela.texto.includes('são os fluxos de ETL'), 'fora da coorte: lista anterior'); assert(!tela.texto.includes('Voltar à lista única'))
 caps(ACTIONS); router.__url('legado=1'); tela = mini.montar(jsx(Pipelines, {}))
 assert(tela.texto.includes('são os fluxos de ETL') && tela.texto.includes('Voltar à lista única de pipelines'), '?legado=1 na coorte')
 rq.__dados['workspace-capabilities'] = { schemaVersion: 1, enabled: false, knownNodeTypes: [], actions: ACTIONS }; router.__url(''); tela = mini.montar(jsx(Pipelines, {}))
 assert(tela.texto.includes('são os fluxos de ETL'), 'workspace desabilitado: lista anterior')
 rq.__estados['workspace-capabilities'] = { isPending: true, fetchStatus: 'fetching', data: undefined }; tela = mini.montar(jsx(Pipelines, {}))
 assert(!tela.texto.includes('são os fluxos') && !tela.texto.includes('única lista'), 'aguarda capacidades')
 delete rq.__estados['workspace-capabilities']
 resultado.coorte = 'ok'

 // ── 4. Criação essencial ─────────────────────────────────────────────────
 const PipelineCreate = req('pages/PipelineCreate.js').default
 caps(ACTIONS); rq.__invalidadas.length = 0; router.__navegacoes.length = 0
 tela = mini.montar(jsx(PipelineCreate, {}))
 assert(!tela.texto.includes('Tipo de agendamento'), 'agenda fica na Configuração'); assert(tela.texto.includes('Sob demanda') && tela.texto.includes('Nenhuma DAG é criada ou disparada'))
 assert(tela.texto.includes('Responsável Alice Souza'))
 const campo = rotulo => tela.achar(n => n.tag === 'input' && n.props.id && tela.achar(l => l.tag === 'label' && l.props.htmlFor === n.props.id && JSON.stringify(l.filhos).includes(rotulo)).length)[0]
 tela.disparar(campo('Nome'), 'onChange', { target: { value: 'Carga de clientes' } })
 assert.equal(campo('Identificador').props.value, 'carga_de_clientes'); assert.equal(campo('Identificador').props.readOnly, true)
 tela.clicar(tela.botoes('Editar identificador')[0]); tela.disparar(campo('Identificador'), 'onChange', { target: { value: 'carga com espaço' } })
 api.__calls.length = 0
 tela.disparar(tela.achar(n => n.tag === 'form')[0], 'onSubmit', {})
 assert.equal(api.__calls.length, 0, 'inválido não chama a API'); assert.equal(tela.porPapel('alert').length, 1); assert.match(tela.texto, /Identificador\s*:\s*Use letras sem acento, números, sublinhado \(_\), ponto ou hífen/)
 assert.equal(campo('Identificador').props['aria-invalid'], true)
 assert.equal(focos.at(-1), campo('Identificador').props.id, 'foco no primeiro campo inválido')
 tela.disparar(campo('Identificador'), 'onChange', { target: { value: 'carga_clientes' } })
 api.__responder(call => call.method === 'POST' ? { draftId: 'd1', pipelineName: 'carga_clientes' } : {})
 tela.disparar(tela.achar(n => n.tag === 'form')[0], 'onSubmit', {})
 await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0))
 const post = api.__calls.find(c => c.method === 'POST'); assert.equal(post.p, '/workspace/pipelines')
 assert.equal(post.body.definition.identity.pipelineName, 'carga_clientes'); assert.equal(post.body.definition.identity.displayName, 'Carga de clientes')
 assert.equal(post.body.definition.metadata.legacyPipeline.schedule_type, 'on_demand'); assert.deepEqual(post.body.definition.nodes, [])
 assert(!/dag|cron/i.test(JSON.stringify(post.body.definition.metadata)), 'nenhuma DAG pedida na criação')
 assert.equal(router.__navegacoes.at(-1), ws.workspacePath('carga_clientes', 'montagem', 'desenvolvimento')); assert.deepEqual(rq.__invalidadas.at(-1), { queryKey: ['pipeline-index'] })
 // 409: erro no campo, existente localizável, formulário conservado.
 router.__navegacoes.length = 0; tela = mini.montar(jsx(PipelineCreate, {}))
 tela.disparar(campo('Nome'), 'onChange', { target: { value: 'Já existe' } })
 api.__responder(() => { throw Object.assign(new Error('Pipeline já publicado; importe sua configuração'), { status: 409, code: 'pipeline_exists' }) })
 tela.disparar(tela.achar(n => n.tag === 'form')[0], 'onSubmit', {})
 await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0)); tela.sincronizar()
 assert(tela.texto.includes('Já existe um pipeline publicado com este identificador.')); assert.equal(router.__navegacoes.length, 0)
 assert(tela.achar(n => n.tag === 'a').some(a => a.props.href === '/pipelines?busca=ja_existe'))
 assert.equal(campo('Nome').props.value, 'Já existe')
 // Falha sem status (rede): mensagem em português, sem texto cru do navegador, formulário intacto.
 tela = mini.montar(jsx(PipelineCreate, {}))
 tela.disparar(campo('Nome'), 'onChange', { target: { value: 'Sem rede' } })
 api.__responder(() => { throw new Error('Failed to fetch') })
 tela.disparar(tela.achar(n => n.tag === 'form')[0], 'onSubmit', {})
 await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0)); tela.sincronizar()
 assert(tela.texto.includes('Não foi possível criar o rascunho agora. Seus dados continuam no formulário.')); assert(!tela.texto.includes('Failed to fetch'))
 assert.equal(campo('Nome').props.value, 'Sem rede'); assert.equal(router.__navegacoes.length, 0)
 resultado.criacao = 'ok'
 // Leitor sem edição não cria.
 caps(READER); tela = mini.montar(jsx(PipelineCreate, {})); assert(tela.texto.includes('Criação de rascunho indisponível'))

 fs.rmSync(tmp, { recursive: true, force: true })
 console.log(JSON.stringify(resultado))
})().catch(e => { console.error(e); process.exit(1) })
