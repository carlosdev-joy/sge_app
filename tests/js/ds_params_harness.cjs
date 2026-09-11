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

const ENTRADAS = ['lib/dsParams.ts', 'lib/rerunParams.ts', 'components/etapas/JobTypeFields.tsx',
                  'components/pipelines/ParametrosPipeline.tsx', 'components/etapas/ParametrosRerun.tsx',
                  'lib/maestro.ts', 'components/etapas/MaestroPainel.tsx', 'components/etapas/MaestroChat.tsx',
                  'lib/maestroAdmin.ts', 'lib/emailAdmin.ts']

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
  // react-dom: o MaestroChat leva o painel ao body por portal. O minireact não
  // tem portal (de propósito); aqui o portal rende NO LUGAR — o que a bancada
  // afirma é o conteúdo do painel, não onde ele mora no DOM.
  escrever('react-dom', 'package.json', '{"name":"react-dom","main":"index.js"}')
  escrever('react-dom', 'index.js', 'module.exports = { createPortal: (el) => el }; module.exports.default = module.exports')
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
// ui/Toast usa zustand (store global) — o "Importar do DataStage" só o chama no
// clique, que a bancada não exercita: um toast inerte no lugar.
fs.mkdirSync(path.join(tmp, 'components', 'ui'), { recursive: true })
fs.writeFileSync(path.join(tmp, 'components', 'ui', 'Toast.js'),
  'exports.toast = { success() {}, error() {}, info() {} };')
const D = require(path.join(tmp, 'lib/dsParams.js'))
const { JobTypeFields, jobTypeFieldsErrors } = require(path.join(tmp, 'components/etapas/JobTypeFields.js'))
const { ParametrosPipelineSecao } = require(path.join(tmp, 'components/pipelines/ParametrosPipeline.js'))
const R = Object.assign({}, require(path.join(tmp, 'lib/rerunParams.js')),
                        require(path.join(tmp, 'components/etapas/ParametrosRerun.js')))
const M = require(path.join(tmp, 'lib/maestro.js'))
const { MaestroPainel } = require(path.join(tmp, 'components/etapas/MaestroPainel.js'))
const { MaestroChat } = require(path.join(tmp, 'components/etapas/MaestroChat.js'))

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
function tela(params, previa, extra, jobName) {
  global.__q = Object.assign({}, previa ? { 'ds-params-preview': previa } : {}, extra || {})
  const value = { job_type: 'datastage', job_command: 'SeqCarga', ssh_conn_id: '', verbose_log: false,
    mssql_conn_id: '', mssql_database: '', params }
  return mini.montar(el(JobTypeFields, Object.assign({ value, onChange: () => {}, sshConns: [], mssqlConns: [] },
    extra && extra.__pipeline ? { pipeline: extra.__pipeline } : {},
    jobName ? { jobName } : {})))
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

// ── 6. F6: importar do lineage ISX ──────────────────────────────────────────
{
  const existentes = [{ id: 'a', param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'HML' }]
  const isx = [
    { name: 'pAmb', type: 'String', default: 'PRD' },                       // já existe → intocado
    { name: 'pData', type: 'Date', default: '2026-01-01', description: 'ref' },
    { name: 'pQtd', type: 'Integer', default: '10' },
    { name: 'ParmSenhaBanco', type: 'Encrypted', default: 'OFUSCADO' },     // Encrypted: default nunca vira valor
    { name: 'DbPassword', type: 'String', default: '***' },                 // sensível pelo parser → vazio
    { name: '$APT_NO_SORT_INSERTION', type: 'Stringlist', default: 'False' },
    { name: 'PSetSsdVida', type: 'Parameterset', default: '(As pre-defined)' },
    { name: 'pMisterio', type: 'Unicorn', default: 'x' },                   // desconhecido → String
    { name: '  ', type: 'String', default: 'x' },                           // sem nome → ignorado
  ]
  const r = D.importarDoIsx(existentes, isx)
  saida.isx = {
    novos: r.novos.map(p => [p.param_name, p.param_type, p.param_source, p.param_value, p.tem_valor === undefined ? null : p.tem_valor]),
    jaExistiam: r.jaExistiam, conjuntos: r.conjuntos, invalidos: r.invalidos,
    tipos: ['string', 'INTEGER', 'Stringlist', 'Parameterset', 'Encrypted', '', null].map(t => D.tipoDsDoIsx(t)),
  }
  const comBotao = tela([], null, { __pipeline: 'PIPE_VIDA' }, 'SeqCarga')
  const semJob = tela([], null, { __pipeline: 'PIPE_VIDA' })
  saida.isx.botao = porAttr(comBotao, 'data-importar-isx').length
  saida.isx.botaoSemJob = porAttr(semJob, 'data-importar-isx').length
}

// ── 5. F5: a seção do modal de rerun ────────────────────────────────────────
{
  const previa = [
    { job_name: 'SeqCarga', itens: [
      { param_name: 'pDataFim', param_type: 'Date', param_source: 'data_referencia', fonte: 'etapa', condicional: false,
        valor_efetivo: '2026-08-31', descricao: 'referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31', editavel: true },
      { param_name: 'pAmb', param_type: 'String', param_source: 'fixo', fonte: 'pipeline', condicional: true,
        valor_efetivo: 'PRD', descricao: 'fixo', editavel: true },
      { param_name: 'pSenha', param_type: 'Encrypted', param_source: 'fixo', fonte: 'etapa', condicional: false,
        valor_efetivo: '***', descricao: 'fixo (Encrypted — nunca exibido)', editavel: false },
    ] },
  ]
  const valores = {
    [R.chaveOverride('SeqCarga', 'pDataFim')]: '2026-09-01',
    [R.chaveOverride('SeqCarga', 'pAmb')]: 'PRD',
    [R.chaveOverride('SeqCarga', 'pSenha')]: 'x',
  }
  const tela = mini.montar(el(R.ParametrosRerun, { parametros: previa, valores, onChange: () => {} }))
  saida.rerun = {
    enviar: R.overridesParaEnviar(previa, valores),                    // só o que difere; Encrypted nunca
    enviarVazio: R.overridesParaEnviar(previa, {}),
    sobrepostos: porAttr(tela, 'data-sobrepostos').map(n => n.props['data-sobrepostos']),
    etapas: porAttr(tela, 'data-etapa-params').map(n => n.props['data-etapa-params']),
    inputs: porAttr(tela, 'data-override').map(n => [n.props['data-override'], n.props.value, n.props['data-mudou']]),
    naoEditaveis: porAttr(tela, 'data-nao-editavel').map(n => n.props['data-nao-editavel']),
    efetivos: porAttr(tela, 'data-valor-efetivo').map(n => n.props['data-valor-efetivo']),
    aviso: porAttr(tela, 'data-aviso-sobreposicao').length,
    texto: tela.texto,
    vazio: mini.montar(el(R.ParametrosRerun, { parametros: [], valores: {}, onChange: () => {} })).texto,
    indisponiveis: porAttr(mini.montar(el(R.ParametrosRerun, { parametros: [], valores: {}, onChange: () => {}, indisponiveis: true })),
                           'data-parametros-rerun').map(n => n.props['data-parametros-rerun']),
  }
}

// ── 7. Maestro (spec docs/spec-maestro-parametros.md, F2) ───────────────────
{
  const editor = [
    { id: 'a', param_name: 'pSenha', param_type: 'Encrypted', param_source: 'fixo', param_value: 'segredo!', tem_valor: true },
    { id: 'b', param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'PRD' },
    { id: 'c', param_name: 'pDataFim', param_type: 'Date', param_source: 'data_referencia', param_value: '',
      param_offset_meses: '-1', param_ancora: 'fim_mes', param_offset_dias: '', param_formato: '' },
    { id: 'd', param_name: '  ', param_type: 'String', param_source: 'fixo', param_value: 'x' },
  ]
  const propostaApi = [
    { param_name: 'pDataIni', param_type: 'Date', param_source: 'data_referencia', param_value: null,
      param_offset_meses: -1, param_ancora: 'inicio_mes', param_offset_dias: 0, param_formato: '%Y-%m-%d' },
    { param_name: 'pDataFim', param_type: 'Date', param_source: 'data_referencia', param_value: null,
      param_offset_meses: -1, param_ancora: 'fim_mes', param_offset_dias: 0, param_formato: '%Y-%m-%d' },
    { param_name: 'pSenha', param_type: 'Encrypted', param_source: 'fixo', param_value: '',
      param_offset_meses: null, param_ancora: null, param_offset_dias: null, param_formato: null, tem_valor: false },
  ]
  const novos = M.propostaParaEditor(propostaApi)
  const aplicado = M.aplicarProposta(editor, novos)
  // Encrypted sobre Encrypted com token GRAVADO (tela recém-carregada): o
  // "manter" sobrevive; e aplicar de novo com o mesmo nome não repete id.
  const aplicadoGravado = M.aplicarProposta(
    [{ id: 'g', param_name: 'pSenha', param_type: 'Encrypted', param_source: 'fixo', param_value: '', tem_valor: true }],
    M.propostaParaEditor(propostaApi))
  const idsDuasVezes = [...M.propostaParaEditor(propostaApi), ...M.propostaParaEditor(propostaApi)].map(p => p.id)
  const mensagens = [
    M.mensagemDeBoasVindas(),
    { id: 1, papel: 'user', texto: 'mensal do mês anterior' },
    { id: 2, papel: 'assistant', texto: 'erro do provedor', erro: true },
    { id: 3, papel: 'assistant', texto: 'Entendi. **pDataIni** e **pDataFim**.', resultado: {
      status: 'atendido', cenario: 'mensal_anterior', motivo: null, proposta: { params: propostaApi },
      previa: [{ param_name: 'pDataIni', valor: '2026-02-01', descricao: 'referência 2026-03-15 → -1 mês → início do mês → 2026-02-01' },
               { param_name: 'pDataFim', valor: '2026-02-28', descricao: 'd2' },
               { param_name: 'pSenha', valor: '***', descricao: 'fixo (Encrypted — nunca exibido)' }],
      avisos: ["o job não declara 'pDataFim' segundo o lineage ISX"], orientacao: null, referencia: '2026-03-15' } },
    { id: 4, papel: 'user', texto: 'e o último dia útil?' },
    { id: 5, papel: 'assistant', texto: 'Isso eu não atendo.', resultado: {
      status: 'nao_atendido', cenario: null, motivo: 'dia útil exige calendário', proposta: null, previa: null,
      avisos: [], orientacao: 'Procure o administrador do Orquestra.', referencia: '2026-03-15' } },
  ]
  const painelProps = (extra) => Object.assign({
    mensagens, carregando: false, sugestoes: ['carga mensal do mês anterior', 'D-1'], entrada: 'oi', onEntrada() {},
    onEnviar() {}, onSugestao() {}, onAplicar() {}, onFechar() {}, onNovaConversa() {}, historico: null,
    onHistorico() {}, onAbrirConversa() {}, referencia: '2026-06-10',   // o editor já mudou; a prévia foi com 2026-03-15
  }, extra || {})
  const painel = mini.montar(el(MaestroPainel, painelProps()))
  const aplicadaTela = mini.montar(el(MaestroPainel, painelProps({ mensagens: [Object.assign({}, mensagens[3], { aplicada: true })] })))
  const soBoasVindas = mini.montar(el(MaestroPainel, painelProps({ mensagens: [M.mensagemDeBoasVindas()] })))
  const pensando = mini.montar(el(MaestroPainel, painelProps({ carregando: true, mensagens: [M.mensagemDeBoasVindas()] })))
  const comHistorico = mini.montar(el(MaestroPainel, painelProps({ historico: [
    { conversa_id: 'c1', iniciado_em: '2026-09-10 10:00:00', pipeline_name: 'P', job_name: 'J',
      rodadas: [{ mensagem: 'antiga', resposta: 'r', status: 'atendido' }] }] })))

  // O botão no JobTypeFields: só datastage + backend dizendo enabled.
  const status = { enabled: true, sugestoes: ['carga mensal do mês anterior'] }
  const comMaestro = tela([], null, { 'maestro-status': status, __pipeline: 'PIPE_VIDA' }, 'SeqCarga')
  const desligado = tela([], null, { 'maestro-status': { enabled: false, sugestoes: [] }, __pipeline: 'PIPE_VIDA' }, 'SeqCarga')
  const semJobComMaestro = tela([], null, { 'maestro-status': status, __pipeline: 'PIPE_VIDA' })
  global.__q = { 'maestro-status': status }
  const storedprocComStatus = mini.montar(el(JobTypeFields, { value: { job_type: 'storedproc', job_command: 'dbo.p', ssh_conn_id: '',
    verbose_log: false, mssql_conn_id: '', mssql_database: '', params: [] }, onChange: () => {}, sshConns: [], mssqlConns: [] }))
  // Abrir o chat pelo botão: o painel (portal → inline na bancada) aparece.
  // O MaestroChat só monta o portal com `document` presente (guarda contra
  // ambiente sem DOM): um `document.body` mínimo faz o papel do browser.
  global.document = { body: {} }
  const chat = mini.montar(el(MaestroChat, { pipeline: 'PIPE_VIDA', jobName: 'SeqCarga', params: editor, referencia: '2026-03-15',
    sugestoes: ['x'], onAplicar() {} }))
  const antes = porAttr(chat, 'data-maestro-painel').length
  chat.clicar(porAttr(chat, 'data-maestro-botao')[0])
  const depois = porAttr(chat, 'data-maestro-painel').length
  delete global.document

  saida.maestro = {
    contexto: M.contextoDoEditor('PIPE_VIDA', ' SeqCarga ', editor, '2026-03-15'),
    contextoSemJob: M.contextoDoEditor(undefined, '', [], '2026-03-15'),
    historico: M.historicoParaEnvio(mensagens),
    historicoCorte: M.historicoParaEnvio(Array.from({ length: 30 }, (_, i) => ({ id: i, papel: i % 2 ? 'assistant' : 'user', texto: `m${i}` }))).map(m => m.content),
    novos: novos.map(p => [p.id, p.param_name, p.param_type, p.param_source, p.param_value, p.param_offset_meses, p.param_ancora, p.param_formato, p.tem_valor === undefined ? null : p.tem_valor]),
    aplicado: { ordem: aplicado.params.map(p => [p.id, p.param_name, p.param_value, p.tem_valor === undefined ? null : p.tem_valor]), substituidos: aplicado.substituidos, adicionados: aplicado.adicionados },
    aplicadoGravado: aplicadoGravado.params.map(p => [p.id, p.param_name, p.param_type, p.param_value, p.tem_valor === undefined ? null : p.tem_valor]),
    idsDuasVezes,
    resumo: M.resumoAplicacao(aplicado),
    resumoVazio: M.resumoAplicacao({ params: [], substituidos: [], adicionados: [] }),
    descricoes: propostaApi.map(M.descricaoDaLinha).concat([M.descricaoDaLinha({ param_name: 'pRun', param_type: 'String', param_source: 'run_id', param_value: null }),
      M.descricaoDaLinha({ param_name: 'pAmb', param_type: 'String', param_source: 'fixo', param_value: 'PRD' })]),
    erros: [[429], [402], [422, { errors: ['a', 'b'] }], [503, 'Maestro desligado'], [403], [500]].map(([s, d]) => M.mensagemDeErro({ status: s, detail: d, message: 'msg' })),
    idConversa: [M.novoConversaId(), M.novoConversaId()],
    painel: {
      msgs: porAttr(painel, 'data-maestro-msg').map(n => n.props['data-maestro-msg']),
      propostas: porAttr(painel, 'data-maestro-proposta').length,
      params: porAttr(painel, 'data-maestro-param').map(n => n.props['data-maestro-param']),
      previas: porAttr(painel, 'data-maestro-previa').map(n => n.props['data-maestro-previa']),
      referenciasDaPrevia: porAttr(painel, 'data-maestro-referencia').map(n => n.props['data-maestro-referencia']),
      botoesDesabilitadosPensando: ['data-maestro-nova', 'data-maestro-historico'].map(a => porAttr(pensando, a)[0].props.disabled),
      botoesHabilitadosOuvindo: ['data-maestro-nova', 'data-maestro-historico'].map(a => porAttr(painel, a)[0].props.disabled),
      avisos: porAttr(painel, 'data-maestro-aviso').length,
      aplicar: porAttr(painel, 'data-maestro-aplicar').length,
      naoAtendido: porAttr(painel, 'data-maestro-nao-atendido').length,
      sugestoesComConversa: porAttr(painel, 'data-maestro-sugestao').length,
      texto: painel.texto,
      aplicadaBotao: porAttr(aplicadaTela, 'data-maestro-aplicar').length,
      aplicadaMarca: porAttr(aplicadaTela, 'data-maestro-aplicada').length,
      sugestoesSoBoasVindas: porAttr(soBoasVindas, 'data-maestro-sugestao').length,
      estadoOuvindo: porAttr(soBoasVindas, 'data-maestro-estado').map(n => n.props['data-maestro-estado']),
      estadoPensando: porAttr(pensando, 'data-maestro-estado').map(n => n.props['data-maestro-estado']),
      digitando: porAttr(pensando, 'data-maestro-digitando').length,
      avatarPensando: porAttr(pensando, 'data-maestro-avatar').map(n => n.props['data-maestro-avatar']),
      historicoConversas: porAttr(comHistorico, 'data-maestro-conversa').map(n => n.props['data-maestro-conversa']),
      historicoSemEntrada: porAttr(comHistorico, 'data-maestro-entrada').length,
      modalExempt: porAttr(painel, 'data-modal-exempt').length,
    },
    botao: { comMaestro: porAttr(comMaestro, 'data-maestro-botao').length, desligado: porAttr(desligado, 'data-maestro-botao').length,
             semJob: porAttr(semJobComMaestro, 'data-maestro-botao').length, storedproc: porAttr(storedprocComStatus, 'data-maestro-botao').length,
             importarContinua: porAttr(comMaestro, 'data-importar-isx').length },
    // Nível pipeline (wizard): contexto com nivel, sem job; boas-vindas próprias; botão na seção do pipeline.
    pipeline: (() => {
      const ctx = M.contextoDoEditor('PIPE_VIDA', 'JobIgnorado', editor, '2026-03-15', 'pipeline')
      global.__q = { 'maestro-status': status }
      const secaoCom = mini.montar(el(ParametrosPipelineSecao, { params: [], onChange: () => {}, pipeline: 'PIPE_VIDA' }))
      global.__q = { 'maestro-status': { enabled: false, sugestoes: [] } }
      const secaoSem = mini.montar(el(ParametrosPipelineSecao, { params: [], onChange: () => {} }))
      // A conversa sobrevive à desmontagem (trocar de passo no wizard): guardada por chave.
      const chave = M.chaveDaConversa('pipeline', 'PIPE_VIDA', 'ignorado')
      M.esquecerConversa(chave)
      const antes = M.lerConversaGuardada(chave)
      M.guardarConversa(chave, { conversaId: 'c-1', mensagens: [M.mensagemDeBoasVindas('pipeline'), { id: 1, papel: 'user', texto: 'oi' }], aberto: true })
      const lida = M.lerConversaGuardada(chave)
      M.esquecerConversa(chave)
      const depois = M.lerConversaGuardada(chave)
      return { nivel: ctx.nivel, temJob: 'job_name' in ctx, etapaTemJob: 'job_name' in M.contextoDoEditor('P', 'J', [], '2026-03-15'),
               etapaNivel: M.contextoDoEditor('P', 'J', [], '2026-03-15').nivel,
               boasVindas: M.mensagemDeBoasVindas('pipeline').texto, boasVindasEtapa: M.mensagemDeBoasVindas().texto,
               botao: porAttr(secaoCom, 'data-maestro-botao').length, botaoDesligado: porAttr(secaoSem, 'data-maestro-botao').length,
               chaves: [chave, M.chaveDaConversa('etapa', 'P', 'J'), M.chaveDaConversa('etapa', 'P')],
               guardada: [antes === undefined, lida && lida.conversaId, lida && lida.mensagens.length, lida && lida.aberto, depois === undefined],
               resumo: [M.resumoAplicacao({ params: [], substituidos: ['a'], adicionados: [] }, 'pipeline'),
                        M.resumoAplicacao({ params: [], substituidos: [], adicionados: ['b'] })],
               alvo: [M.alvoDoSalvar('pipeline'), M.alvoDoSalvar()] }
    })(),
    abrir: { antes, depois, boasVindas: porAttr(chat, 'data-maestro-msg').length },
  }
}

// ── 8. Admin do Maestro (F3): a lib pura do formulário do cenário ────────────
{
  const A = require(path.join(tmp, 'lib/maestroAdmin.js'))
  const cenarioApi = {
    id: 5, codigo: 'mensal_anterior', titulo: 'Carga mensal', descricao: 'Primeiro e último dia.', ativo: true,
    criado_em: '2026-09-10 10:00:00', criado_por: 'migration_110', atualizado_em: null, atualizado_por: null,
    receita: { params: [
      { param_name: '<DATA_INICIAL>', param_type: 'Date', param_source: 'data_referencia', param_value: null,
        param_offset_meses: -1, param_ancora: 'inicio_mes', param_offset_dias: 0, param_formato: '%Y-%m-%d' },
      { param_name: '<CAMINHO>', param_type: 'Pathname', param_source: 'fixo', param_value: '/dados/entrada' },
    ], exemplos: ['carga mensal', 'mês passado'] },
  }
  const form = A.formDoCenario(cenarioApi)
  const corpo = A.cenarioParaApi(Object.assign({}, form, { codigo: ' Mensal_Anterior ', exemplosTexto: 'a\n\n a \nb' }))
  const semParams = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd', linhas: [] })
  const nomeRuim = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd',
    linhas: [Object.assign(A.linhaVazia(), { param_name: 'a b' })] })
  const dataComInteger = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd',
    linhas: [Object.assign(A.linhaVazia(), { param_name: '<D>', param_type: 'Integer' })] })
  const valido = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd',
    linhas: [Object.assign(A.linhaVazia(), { param_name: '<D>', param_offset_meses: '-1', param_ancora: 'fim_mes' })] })
  const encrypted = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd',
    linhas: [Object.assign(A.linhaVazia(), { param_name: '<SENHA>', param_type: 'Encrypted', param_source: 'fixo', param_value: 'vazou?' })] })
  const repetido = Object.assign(A.cenarioVazio(), { codigo: 'x1', titulo: 't', descricao: 'd',
    linhas: [Object.assign(A.linhaVazia(), { param_name: '<D>', param_ancora: 'inicio_mes' }),
             Object.assign(A.linhaVazia(), { param_name: '<D>', param_ancora: 'fim_mes' })] })
  saida.maestroAdmin = {
    form: { codigo: form.codigo, ativo: form.ativo, exemplosTexto: form.exemplosTexto,
            linhas: form.linhas.map(l => [l.param_name, l.param_type, l.param_source, l.param_value, l.param_offset_meses, l.param_ancora, l.param_offset_dias, l.param_formato]) },
    vazioTemUmaLinha: A.formDoCenario(Object.assign({}, cenarioApi, { receita: { params: [], exemplos: [] } })).linhas.length,
    corpo,
    exemplos: A.exemplosDoTexto(' x \n\nx\ny\n'),
    erros: {
      valido: A.errosDoCenario(valido),
      vazio: A.errosDoCenario(A.cenarioVazio()),
      semParams: A.errosDoCenario(semParams),
      nomeRuim: A.errosDoCenario(nomeRuim),
      dataComInteger: A.errosDoCenario(dataComInteger),
      codigoRuim: A.errosDoCenario(Object.assign({}, valido, { codigo: 'Ruim Demais' })),
      tituloLongo: A.errosDoCenario(Object.assign({}, valido, { titulo: 't'.repeat(121) })),
      exemplosDemais: A.errosDoCenario(Object.assign({}, valido, { exemplosTexto: Array.from({ length: 11 }, (_, i) => `e${i}`).join('\n') })),
      encrypted: A.errosDoCenario(encrypted),
      repetido: A.errosDoCenario(repetido),
    },
    encryptedNoCorpo: A.cenarioParaApi(encrypted).receita.params,
    mensagens: [
      A.mensagemErroAdmin({ status: 422, detail: { code: 'cenario_invalido', errors: ['a', 'b'] } }, 'p'),
      A.mensagemErroAdmin({ status: 409, detail: { code: 'codigo_existente', mensagem: 'Já existe' } }, 'p'),
      A.mensagemErroAdmin({ status: 503, detail: 'Maestro indisponível: migration 110 pendente' }, 'p'),
      A.mensagemErroAdmin({ status: 500, message: '500 Internal Server Error' }, 'padrão'),
    ],
    pendente110: [A.migration110Pendente({ status: 503, detail: 'Maestro indisponível: migration 110 pendente' }),
                  A.migration110Pendente({ status: 503, detail: 'outra coisa' }), A.migration110Pendente({ status: 500, detail: 'migration 110' })],
    idsUnicos: new Set([A.linhaVazia().id, A.linhaVazia().id, A.linhaVazia().id]).size,
  }
}

// ── 9. Admin › E-mail (F1 da spec docs/spec-notificacao-email.md): a lib pura ─
{
  const E = require(path.join(tmp, 'lib/emailAdmin.js'))
  const cfg = { enabled: true, remetente: 'orquestra@cvp.com.br', limite_mb: 5, raizes: ['/dados/saida', '/opt/IBM/dados'],
                dominios: ['cvp.com.br'], disponivel: true, ssh_configurado: true, ssh_host: 'lnxprd021' }
  const form = E.formDaConfig(cfg)
  const valido = Object.assign({}, form)
  saida.emailAdmin = {
    form,
    corpo: E.configParaApi(Object.assign({}, form, { remetente: ' Orq@CVP.com.br ', limite_mb: '10', raizesTexto: '/a\n\n/b, /a', dominiosTexto: '' })),
    listas: [E.listaDoTexto(' a@x.com ; b@y.org\n\na@x.com,c@z.io '), E.textoDaLista(['/a', '/b']), E.listaDoTexto('')],
    erros: {
      valido: E.errosDaConfig(valido),
      ligadoSemRemetente: E.errosDaConfig(Object.assign({}, valido, { remetente: '' })),
      desligadoSemRemetente: E.errosDaConfig(Object.assign({}, valido, { enabled: false, remetente: '' })),
      remetenteRuim: E.errosDaConfig(Object.assign({}, valido, { remetente: 'sem-arroba' })),
      limite: [E.errosDaConfig(Object.assign({}, valido, { limite_mb: '0' })).length, E.errosDaConfig(Object.assign({}, valido, { limite_mb: '26' })).length,
               E.errosDaConfig(Object.assign({}, valido, { limite_mb: '2.5' })).length, E.errosDaConfig(Object.assign({}, valido, { limite_mb: '25' })).length],
      raizes: E.errosDaConfig(Object.assign({}, valido, { raizesTexto: 'relativo\n/com espaco\n/a/../b\n/ok/' })),
      raizBarra: E.errosDaConfig(Object.assign({}, valido, { raizesTexto: '/' })),
      raizPonto: E.errosDaConfig(Object.assign({}, valido, { raizesTexto: '/a/./b' })),
      dominios: E.errosDaConfig(Object.assign({}, valido, { dominiosTexto: 'ruim\n@cvp.com.br' })),
      // teto de etl_app_config.config_value (VARCHAR(1000)) — a régua da API recusa
      longa: E.errosDaConfig(Object.assign({}, valido, {
        raizesTexto: Array.from({ length: 30 }, (_, i) => `/opt/IBM/InformationServer/Server/Projects/PROJ${i}/saida`).join('\n') })),
    },
    mensagens: [E.mensagemErroEmail({ status: 422, detail: { code: 'x', errors: ['a', 'b'] } }, 'p'),
                E.mensagemErroEmail({ status: 503, detail: 'E-mail indisponível: migration 111 pendente' }, 'p'),
                E.mensagemErroEmail({ status: 500, message: '500 Internal Server Error' }, 'padrão')],
    pendente111: [E.migration111Pendente({ status: 503, detail: 'E-mail indisponível: migration 111 pendente' }), E.migration111Pendente({ status: 503, detail: 'x' })],
    etapas: Object.keys(E.ETAPA_LAUDO),
  }
}

process.stdout.write(JSON.stringify(saida))
