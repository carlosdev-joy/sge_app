// Bancada do lib/dsParams.ts — parâmetros DataStage no front (spec
// docs/spec-parametros-job-datastage.md, F3).
//
// O módulo é PURO (sem React): transpila com o sucrase do ui-react e chama as
// funções direto. O que se prende aqui é o contrato draft ↔ API (origem sempre
// presente, cálculo só com origem de data, Encrypted vazio + tem_valor = `***`,
// segredo nunca vai para a prévia) e as réguas que espelham a API. E a tela
// que consome o editor (JobTypeFields em modo datastage) renderiza no React
// mínimo da casa para provar o que aparece por origem/tipo.
//
// Saída: um JSON só no stdout, lido por tests/test_ds_params_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = ['lib/dsParams.ts', 'components/etapas/JobTypeFields.tsx', 'components/pipelines/ParametrosPipeline.tsx']

function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const t of [base + '.tsx', base + '.ts', path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) {
    if (fs.existsSync(t)) return t
  }
  return null
}

function preparar(destino) {
  const feitos = new Set()
  const fila = ENTRADAS.map(e => path.join(SRC, e))
  while (fila.length) {
    const arquivo = fila.pop()
    if (feitos.has(arquivo)) continue
    feitos.add(arquivo)
    const fonte = fs.readFileSync(arquivo, 'utf8')
    const js = transform(fonte, { transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true, filePath: arquivo }).code
    const rel = path.relative(SRC, arquivo).replace(/\.tsx?$/, '.js')
    const alvo = path.join(destino, rel)
    fs.mkdirSync(path.dirname(alvo), { recursive: true })
    fs.writeFileSync(alvo, js)
    for (const m of fonte.matchAll(/from\s*['"](\.[^'"]+)['"]/g)) {
      const dep = resolverRelativo(path.dirname(arquivo), m[1])
      if (dep) fila.push(dep)
    }
  }
}

function shims(destino) {
  const nm = path.join(destino, 'node_modules')
  const escrever = (pacote, arquivo, conteudo) => {
    const dir = path.join(nm, pacote)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, arquivo), conteudo)
  }
  const caminhoMini = JSON.stringify(path.join(__dirname, 'minireact.cjs'))
  escrever('react', 'package.json', '{"name":"react","main":"index.js"}')
  escrever('react', 'index.js', `
const mini = require(${caminhoMini})
function forwardRef(render) {
  const C = (props) => render(props, null)
  Object.defineProperty(C, 'name', { value: render.name || 'forwardRef' })
  return C
}
module.exports = Object.assign({}, mini.hooks, {
  createElement: mini.criar, Fragment: mini.FRAGMENT,
  forwardRef, useId: () => 'orq-id',
  useDeferredValue: (v) => v,
})
module.exports.default = module.exports
`)
  const runtime = `
const mini = require(${caminhoMini})
const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key })
module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }
`
  escrever('react', 'jsx-runtime.js', runtime)
  escrever('react', 'jsx-dev-runtime.js', runtime)
  escrever('lucide-react', 'package.json', '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js', `
module.exports = new Proxy({}, { get: (_, nome) => {
  if (nome === '__esModule') return true
  const Icone = () => ({ __el: true, tipo: 'svg', props: { 'data-icone': String(nome) } })
  Object.defineProperty(Icone, 'name', { value: String(nome) })
  return Icone
} })
`)
  // react-query: a prévia e os defaults do pipeline vêm do servidor — aqui o
  // hook devolve o que a bancada injetar em global.__q[queryKey[0]] (ou nada),
  // sem rede. Query desabilitada não devolve nada.
  escrever('@tanstack/react-query', 'package.json', '{"name":"@tanstack/react-query","main":"index.js"}')
  escrever('@tanstack/react-query', 'index.js', `
module.exports = { useQuery: (opts) => ({
  data: (global.__q && opts.enabled !== false) ? global.__q[String(opts.queryKey[0])] : undefined,
  isLoading: false,
}) }
`)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-params-'))
preparar(tmp)
shims(tmp)
// lib/api.ts importa o store de auth — não é chamado aqui (useQuery é shim),
// mas precisa carregar: dá um módulo vazio no lugar.
fs.mkdirSync(path.join(tmp, 'lib'), { recursive: true })
fs.writeFileSync(path.join(tmp, 'lib', 'api.js'), 'exports.apiFetch = async () => ({});')
const D = require(path.join(tmp, 'lib/dsParams.js'))
const { JobTypeFields, jobTypeFieldsErrors } = require(path.join(tmp, 'components/etapas/JobTypeFields.js'))
const { ParametrosPipelineSecao } = require(path.join(tmp, 'components/pipelines/ParametrosPipeline.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()

const saida = {}

// ── 1. conversão draft ↔ API ────────────────────────────────────────────────
{
  const draft = [
    { param_name: 'pDataIni', param_type: 'Date', param_source: 'data_referencia', param_value: '',
      param_offset_meses: '-1', param_ancora: 'inicio_mes', param_offset_dias: '', param_formato: '' },
    { param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'PRD',
      param_offset_meses: '3', param_ancora: 'fim_mes', param_offset_dias: '1', param_formato: '%Y' },   // cálculo IGNORADO fora de origem de data
    { param_name: 'pSenhaMantida', param_type: 'Encrypted', param_source: 'fixo', param_value: '', tem_valor: true },
    { param_name: 'pSenhaNova', param_type: 'Encrypted', param_source: 'fixo', param_value: 'segredo!' },
    { param_name: 'pRun', param_type: 'String', param_source: 'run_id', param_value: 'lixo' },
    { param_name: '  ', param_type: 'String', param_source: 'fixo', param_value: '' },               // linha vazia
    { param_name: 'pSemOrigem', param_type: 'String', param_value: 'x' },                            // origem ausente → fixo
  ]
  saida.toApi = D.dsParamsToApi(draft)
  saida.previewItens = D.previewItens(draft)
  saida.despacho = {
    storedproc: D.paramsToApi('storedproc', [{ param_name: '@p', param_type: 'INT', param_value: '1' }]),
    shell: D.paramsToApi('shell', [{ param_name: 'x', param_type: 'String', param_value: '1' }]),
  }
  saida.fromApi = D.paramsFromApi([
    { param_name: 'pDataFim', param_type: 'Date', param_value: null, param_order: 0, param_source: 'data_referencia',
      param_offset_meses: -1, param_ancora: 'fim_mes', param_offset_dias: null, param_formato: '%Y%m%d' },
    { param_name: 'pSenha', param_type: 'Encrypted', param_value: '***', param_order: 1, param_source: 'fixo',
      param_offset_meses: null, param_ancora: null, param_offset_dias: null, param_formato: null, tem_valor: true },
    { param_name: '@p', param_type: 'VARCHAR', param_value: 'v', param_order: 0 },                       // storedproc sem a 107
  ])
}

// ── 2. réguas ───────────────────────────────────────────────────────────────
{
  const ok = (p) => D.dsParamErrors([Object.assign({ param_type: 'String', param_source: 'fixo', param_value: 'v' }, p)])
  saida.regras = {
    valido: ok({ param_name: 'pA' }),
    pset: ok({ param_name: 'PSet.pA' }),
    nomeRuim: ok({ param_name: 'a.b.c' }),
    nomeLongo: ok({ param_name: 'p'.repeat(129) }),
    semOrigem: ok({ param_name: 'pA', param_source: '' }),
    dataComInteger: ok({ param_name: 'pA', param_type: 'Integer', param_source: 'data_referencia' }),
    mesesFora: ok({ param_name: 'pA', param_source: 'data_referencia', param_offset_meses: '121' }),
    diasNaoInteiro: ok({ param_name: 'pA', param_source: 'data_referencia', param_offset_dias: 'x' }),
    formatoRuim: ok({ param_name: 'pA', param_source: 'data_referencia', param_formato: '%A' }),
    formatoLongo: ok({ param_name: 'pA', param_source: 'data_referencia', param_formato: '%Y' + '-'.repeat(39) }),
    runIdDate: ok({ param_name: 'pA', param_type: 'Date', param_source: 'run_id' }),
    integerRuim: ok({ param_name: 'pA', param_type: 'Integer', param_value: 'abc' }),
    pathRelativo: ok({ param_name: 'pA', param_type: 'Pathname', param_value: '~/x' }),
    dateRuim: ok({ param_name: 'pA', param_type: 'Date', param_value: '09/09/2026' }),
    encryptedVazio: ok({ param_name: 'pA', param_type: 'Encrypted', param_value: '' }),
    encryptedMantido: ok({ param_name: 'pA', param_type: 'Encrypted', param_value: '', tem_valor: true }),
    stringVazia: ok({ param_name: 'pA', param_value: '' }),
    duplicadoCaixaExata: D.dsParamErrors([
      { param_name: 'pA', param_type: 'String', param_source: 'fixo', param_value: '1' },
      { param_name: 'pa', param_type: 'String', param_source: 'fixo', param_value: '1' },
      { param_name: 'pA', param_type: 'String', param_source: 'fixo', param_value: '2' },
    ]),
    linhaVazia: D.dsParamErrors([{ param_name: '', param_type: 'String', param_source: 'fixo', param_value: '' }]),
    regexLiteral: [String(D.DS_PARAM_NAME_RE), String(D.DS_FORMATO_RE)],
  }
  saida.erroPorTipo = {
    datastage: jobTypeFieldsErrors({ job_type: 'datastage', job_command: 'J', ssh_conn_id: '', verbose_log: false,
      mssql_conn_id: '', mssql_database: '', params: [{ param_name: 'pA', param_type: 'Integer', param_source: 'fixo', param_value: 'x' }] }),
    storedprocIntocado: jobTypeFieldsErrors({ job_type: 'storedproc', job_command: 'dbo.p', ssh_conn_id: '', verbose_log: false,
      mssql_conn_id: 'c', mssql_database: '', params: [{ param_name: '@p', param_type: 'INT', param_value: '' }] }),
  }
}

// ── 3. a tela: JobTypeFields em modo datastage ──────────────────────────────
function tela(params, previa, extra) {
  global.__q = Object.assign({}, previa ? { 'ds-params-preview': previa } : {}, extra || {})
  const value = { job_type: 'datastage', job_command: 'SeqCarga', ssh_conn_id: '', verbose_log: false,
    mssql_conn_id: '', mssql_database: '', params }
  return mini.montar(el(JobTypeFields, Object.assign({ value, onChange: () => {}, sshConns: [], mssqlConns: [] },
    extra && extra.__pipeline ? { pipeline: extra.__pipeline } : {})))
}
{
  const semParams = tela([])
  const comParams = tela([
    { id: 'a', param_name: 'pDataFim', param_type: 'Date', param_source: 'data_referencia', param_value: '',
      param_offset_meses: '-1', param_ancora: 'fim_mes', param_offset_dias: '', param_formato: '' },
    { id: 'b', param_name: 'pSenha', param_type: 'Encrypted', param_source: 'fixo', param_value: '', tem_valor: true },
    { id: 'c', param_name: 'pRun', param_type: 'String', param_source: 'run_id', param_value: '' },
    { id: 'd', param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'PRD' },
  ], { referencia: '2026-09-09', itens: [
    { param_name: 'pDataFim', valor: '2026-08-31', descricao: 'referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31' },
    { param_name: 'pAmb', valor: 'PRD', descricao: 'fixo' },
  ], erros: ["parâmetro #3 'pRun': algo"] })
  const storedproc = mini.montar(el(JobTypeFields, { value: { job_type: 'storedproc', job_command: 'dbo.p', ssh_conn_id: '',
    verbose_log: false, mssql_conn_id: '', mssql_database: '', params: [{ param_name: '@p', param_type: 'INT', param_value: '1' }] },
    onChange: () => {}, sshConns: [], mssqlConns: [] }))
  // Lista que ESVAZIOU depois de uma prévia com erro: a caixa âmbar e as
  // prévias velhas não podem ficar (placeholderData da query desabilitada).
  const esvaziada = tela([], { referencia: '2026-09-09', itens: [{ param_name: 'pA', valor: '1', descricao: 'fixo' }],
    erros: ["parâmetro #1 'pA': valor 'x' não é um Integer válido"] })
  saida.tela = {
    esvaziadaErros: porAttr(esvaziada, 'data-previa-erros').length,
    esvaziadaPrevias: porAttr(esvaziada, 'data-previa').length,
    secaoSemParams: porAttr(semParams, 'data-secao-params-ds').length,
    referenciaSemParams: porAttr(semParams, 'data-referencia-previa').length,
    referenciaComParams: porAttr(comParams, 'data-referencia-previa').length,
    linhas: porAttr(comParams, 'data-param-linha').map(n => n.props['data-param-linha']),
    origens: porAttr(comParams, 'data-origem').map(n => n.props['data-origem']),
    calculos: porAttr(comParams, 'data-calculo').length,
    encrypted: porAttr(comParams, 'data-encrypted').map(n => [n.props['data-encrypted'], n.props.type, n.props.placeholder]),
    previas: porAttr(comParams, 'data-previa').map(n => [n.props['data-previa'], n.props.title]),
    errosPrevia: porAttr(comParams, 'data-previa-erros').length,
    texto: comParams.texto,
    storedprocSemSecaoDs: porAttr(storedproc, 'data-secao-params-ds').length,
    storedprocSemEditorDs: porAttr(storedproc, 'data-editor-params').length,
  }
}

// ── 4. F4: defaults do pipeline na etapa + a seção do wizard ────────────────
{
  const defaults = { parametros: [
    { param_name: 'pAmb', param_type: 'String', param_value: 'PRD', param_order: 0, param_source: 'fixo' },
    { param_name: 'pSenha', param_type: 'Encrypted', param_value: '***', param_order: 1, param_source: 'fixo', tem_valor: true },
    { param_name: 'pDataFim', param_type: 'Date', param_value: null, param_order: 2, param_source: 'data_referencia',
      param_offset_meses: -1, param_ancora: 'fim_mes' },
  ], disponivel: true }
  // etapa sobrepõe pAmb
  const comDefaults = tela([{ id: 'a', param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'HML' }],
    null, { 'pipeline-parametros': defaults, __pipeline: 'PIPE_VIDA' })
  const semPipeline = tela([], null, { 'pipeline-parametros': defaults })   // sem prop pipeline → query desabilitada
  const semDefaults = tela([], null, { 'pipeline-parametros': { parametros: [], disponivel: true }, __pipeline: 'PIPE_VIDA' })
  saida.defaults = {
    linha: porAttr(comDefaults, 'data-defaults-pipeline').length,
    itens: porAttr(comDefaults, 'data-default').map(n => [n.props['data-default'], n.props['data-sobreposto']]),
    texto: textoDe(porAttr(comDefaults, 'data-defaults-pipeline')[0]),
    semPipeline: porAttr(semPipeline, 'data-defaults-pipeline').length,
    semDefaults: porAttr(semDefaults, 'data-defaults-pipeline').length,
  }

  global.__q = { 'ds-params-preview': { referencia: '2026-09-09', itens: [{ param_name: 'pAmb', valor: 'PRD', descricao: 'fixo' }], erros: [] } }
  const secaoVazia = mini.montar(el(ParametrosPipelineSecao, { params: [], onChange: () => {} }))
  const secao = mini.montar(el(ParametrosPipelineSecao, { params: [
    { id: 'a', param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'PRD' },
    { id: 'b', param_name: 'pDataFim', param_type: 'Date', param_source: 'data_referencia', param_value: '', param_offset_meses: '-1', param_ancora: 'fim_mes', param_offset_dias: '', param_formato: '' },
  ], onChange: () => {} }))
  saida.secaoPipeline = {
    vaziaEditor: porAttr(secaoVazia, 'data-editor-params').length,
    vaziaReferencia: porAttr(secaoVazia, 'data-referencia-previa').length,
    contagem: porAttr(secao, 'data-contagem').map(n => n.props['data-contagem']),
    linhas: porAttr(secao, 'data-param-linha').map(n => n.props['data-param-linha']),
    calculos: porAttr(secao, 'data-calculo').length,
    previas: porAttr(secao, 'data-previa').map(n => n.props['data-previa']),
    texto: secao.texto,
  }
}

process.stdout.write(JSON.stringify(saida))
