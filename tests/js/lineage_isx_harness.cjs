// Bancada da aba "Job DataStage" (spec docs/spec-lineage-isx.md, F4).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F4 é comportamento: a lista mostra o estado de cada job e o botão
// Extrair só com acao_editar (Atualizar = force quando já há lineage); o cabeçalho
// diz cache × extraído agora e mostra o erro da última tentativa sem esconder o
// lineage bom; a sequence lista os filhos e só oferece Extrair ao que está no
// pipeline; a tabela e o painel do stage mostram SQL, colunas, expressões, APT
// colapsado e o `#PSet.X#` como badge. Os componentes de apresentação rodam aqui
// no React mínimo da casa (minireact.cjs), byte a byte como estão no `src/`.
//
// O container (react-query) e o grafo (@xyflow/react) ficam de fora: são rede e
// canvas; a prova deles é tsc + build + a tela no DEV. O LEIAUTE do grafo é puro
// (lib/lineageIsx.leiaute) e é testado aqui.
//
// Saída: um JSON só no stdout, lido por tests/test_lineage_isx_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/governanca/isx/ListaJobsIsx.tsx',
  'components/governanca/isx/CabecalhoJobIsx.tsx',
  'components/governanca/isx/FilhosSequenceIsx.tsx',
  'components/governanca/isx/TabelaStagesIsx.tsx',
  'components/governanca/isx/ConteudoStageIsx.tsx',
  'components/governanca/isx/TextoComParametros.tsx',
  'lib/lineageIsx.ts',
]

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
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'lineage-isx-'))
preparar(tmp)
shims(tmp)
const { ListaJobsIsx } = require(path.join(tmp, 'components/governanca/isx/ListaJobsIsx.js'))
const { CabecalhoJobIsx } = require(path.join(tmp, 'components/governanca/isx/CabecalhoJobIsx.js'))
const { FilhosSequenceIsx } = require(path.join(tmp, 'components/governanca/isx/FilhosSequenceIsx.js'))
const { TabelaStagesIsx } = require(path.join(tmp, 'components/governanca/isx/TabelaStagesIsx.js'))
const { ConteudoStageIsx } = require(path.join(tmp, 'components/governanca/isx/ConteudoStageIsx.js'))
const { TextoComParametros } = require(path.join(tmp, 'components/governanca/isx/TextoComParametros.js'))
const L = require(path.join(tmp, 'lib/lineageIsx.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()

// ── dados de amostra (os mesmos da bancada do engine, no shape da API) ──────
const STAGES = [
  { direction: 'origem', object_type: 'Banco de Dados ODBC', object_name: 'DM_119_INFO', stage_name: 'DM_119_INFO', stage_type_raw: 'ODBCConnectorPX', stage_internal_id: 'V0S185',
    database_name: 'Ssd', sql_expression: "select distinct\n  b.COD_CPF_CNPJ AS CPF_CNPJ\nfrom DM_003_PROPOSTA a\nwhere IND_NLIST <> 'N'", file_path: null,
    output_columns: [{ name: 'CPF_CNPJ', type: 'string', length: 20 }], input_columns: [], apt_code: null, expressions: [], extracted_at: '2026-09-08 01:00:00' },
  { direction: 'transformacao', object_type: 'Transformer', object_name: 'TrfNlist', stage_name: 'TrfNlist', stage_type_raw: 'CTransformerStage', stage_internal_id: 'V0S169',
    database_name: null, sql_expression: null, file_path: null,
    output_columns: [{ name: 'IND_PESSOA_NLIST', type: 'string', length: 20 }, { name: 'CHAVE_NLIST', type: 'int32', length: null }],
    input_columns: [{ name: 'CPF_CNPJ', type: 'string', length: 20 }],
    apt_code: 'mainloop {\n  LnkDadosNlist.CHAVE_NLIST = 1;\n}',
    expressions: [{ output_col: 'IND_PESSOA_NLIST', expression: "trim(Right(STR('0',20):LnkNlist.CPF_CNPJ,20))", source_col: 'LnkNlist.CPF_CNPJ' }, { output_col: 'CHAVE_NLIST', expression: '1', source_col: '' }],
    extracted_at: '2026-09-08 01:00:00' },
  { direction: 'destino', object_type: 'Arquivo', object_name: '#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds', stage_name: 'DST_FTP_NLIST', stage_type_raw: 'PxDataSet', stage_internal_id: 'V0S200',
    database_name: null, sql_expression: null, file_path: '#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds',
    output_columns: [], input_columns: [{ name: 'IND_PESSOA_NLIST', type: 'string', length: 20 }], apt_code: null, expressions: [], extracted_at: '2026-09-08 01:00:00' },
  { direction: 'destino', object_type: 'Banco de Dados ODBC', object_name: 'dbo.TB_DESTINO', stage_name: 'TB_DEST', stage_type_raw: 'ODBCConnectorPX', stage_internal_id: 'V0S210',
    database_name: 'DSN_STG', sql_expression: 'dbo.TB_DESTINO', file_path: null, output_columns: [], input_columns: [], apt_code: null, expressions: [], extracted_at: null },
  { direction: 'destino', object_type: 'PxAlienStage', object_name: 'Misterio', stage_name: 'Misterio', stage_type_raw: 'PxAlienStage', stage_internal_id: 'V0S300',
    database_name: null, sql_expression: null, file_path: null, output_columns: [], input_columns: [], apt_code: null, expressions: [], extracted_at: null },
]
const FLOW = [
  { from: 'DM_119_INFO', from_type: 'ODBCConnectorPX', link: 'LnkNlist', to: 'TrfNlist', to_type: 'CTransformerStage' },
  { from: 'TrfNlist', from_type: 'CTransformerStage', link: 'LnkDadosNlist', to: 'DST_FTP_NLIST', to_type: 'PxDataSet' },
  { from: 'TrfNlist', from_type: 'CTransformerStage', link: 'LnkDadosNlist', to: 'DST_FTP_NLIST', to_type: 'PxDataSet' },   // duplicada
  { from: 'TrfNlist', from_type: 'CTransformerStage', link: 'LnkX', to: 'Fantasma', to_type: '' },                           // alvo inexistente
]
const JOB = {
  pipeline_name: 'PIPE_VIDA', job_name: 'SsdVidaDimePessoa02Ftp', ds_project: 'BI_VIDA', ds_folder_path: '\\Jobs\\SsdVida\\_Dime', job_type: 'PARALLEL',
  ds_last_modified: '2026-08-04T03:37:15.253+0000', job_description: 'ETL de amostra', job_long_description: 'Homologado em 19/11/2011.\nSegunda linha.',
  status: 'ok', erro: null, extracted_at: '2026-09-08 01:00:00', extracted_by: 'C012345', duracao_ms: 217, isx_sha256: 'x', isx_bytes: 1622,
  parameters: [], flow: FLOW, children: [], nao_reconhecidos: [{ stage: 'Misterio', stage_type: 'PxAlienStage', motivo: 'tipo fora do mapa' }], stages: STAGES,
}
const JOBS = [
  { job_name: 'SsdVidaDimePessoa02Ftp', execution_order: 1, job_type: 'datastage', isx: { status: 'ok', ds_job_type: 'PARALLEL', ds_last_modified: 'x', extracted_at: '2026-09-08 01:00:00', extracted_by: 'C012345', erro: null, ds_folder_path: '\\Jobs', linhas: 5 } },
  { job_name: 'SeqSsdVidaDime', execution_order: 2, job_type: 'datastage', isx: null },
  { job_name: 'JobRaiz', execution_order: 3, job_type: 'datastage', isx: { status: 'erro', ds_job_type: null, ds_last_modified: null, extracted_at: '2026-09-08 01:05:00', extracted_by: 'ADMIN (dag:etl_lineage_extract_isx)', erro: 'Job não encontrado no repositório do DataStage pelo istool', ds_folder_path: null, linhas: 0 } },
  { job_name: 'http_saude', execution_order: 4, job_type: 'http', isx: null },
]

const saida = {}

// ── 1. puras ─────────────────────────────────────────────────────────────────
const lei = L.leiaute(STAGES, FLOW)
const soIsolados = L.leiaute(STAGES.map(s => ({ ...s })), [])
const ciclo = L.leiaute([STAGES[0], STAGES[1]], [
  { from: 'DM_119_INFO', from_type: '', link: 'a', to: 'TrfNlist', to_type: '' }, { from: 'TrfNlist', from_type: '', link: 'b', to: 'DM_119_INFO', to_type: '' }])
saida.puras = {
  direcaoDe: ['origem', 'INPUT', 'OUTPUT', 'destino', null, 'xyz'].map(L.direcaoDe),
  leiaute: { camadas: lei.camadas, nos: lei.nos.map(n => [n.id, n.camada, n.direcao, n.x]), arestas: lei.arestas.map(a => [a.de, a.rotulo, a.para]) },
  isolados: soIsolados.nos.map(n => [n.id, n.camada]),
  ciclo: { camadas: ciclo.camadas, nos: ciclo.nos.map(n => [n.id, n.camada]) },
  partes: [L.partesParametro('#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds'), L.partesParametro('dbo.TB'), L.partesParametro(''), L.partesParametro('#A#x#B#')],
  ehParametro: [L.ehParametro('#PSet.X#'), L.ehParametro('dbo.TB'), L.ehParametro('a # b # c'), L.ehParametro(null)],
  resumo: STAGES.map(L.resumoStage),
  rotulo: [L.rotuloEstado(null), L.rotuloEstado(JOBS[0].isx), L.rotuloEstado({ ...JOBS[0].isx, linhas: 0 }), L.rotuloEstado(JOBS[2].isx)],
  erro: [L.erroIsx({ status: 403 }), L.erroIsx({ status: 422, detail: 'O job X não está mapeado no pipeline P' }), L.erroIsx({ status: 502 }),
         L.erroIsx({ status: 502, detail: 'O istool falhou ao exportar o job' }), L.erroIsx({}), L.erroIsx({ status: 504 }), L.erroIsx({ status: 409 })],
  frases: [L.fraseResumoLote(null, 'queued'), L.fraseResumoLote({ total: 3, extraidos: 2, cache: 0, erros: [{ pipeline_name: 'P', job_name: 'JobRaiz', status: 404, detail: 'x' }], duracao_s: 4.2 }, 'success'),
           L.fraseResumoLote(null, 'failed'), L.fraseResumoLote({ total: 2, extraidos: 0, cache: 2, erros: [] }, 'success')],
  formatos: [L.formatarDuracao(217), L.formatarDuracao(4210), L.formatarBytes(1622), L.formatarBytes(3 * 1024 * 1024), L.formatarDuracao(null)],
  base: [L.baseDoCaminho('/dados/dst/NLIST.ds'), L.baseDoCaminho('C:\\x\\y.txt'), L.baseDoCaminho('')],
}

// ── 2. lista de jobs ─────────────────────────────────────────────────────────
{
  const sel = [], ext = []
  const tela = mini.montar(el(ListaJobsIsx, { jobs: JOBS, selecionado: 'SsdVidaDimePessoa02Ftp', onSelecionar: j => sel.push(j), onExtrair: (j, f) => ext.push([j, f]), podeEditar: true, extraindo: null }))
  const itens = porAttr(tela, 'data-job')
  const botoes = porAcao(tela, 'extrair')
  tela.clicar(botoes.find(b => textoDe(b) === 'Atualizar'))
  tela.clicar(botoes.find(b => textoDe(b) === 'Extrair'))
  tela.clicar(porAcao(tela, 'selecionar')[1])
  saida.lista = {
    itens: itens.map(i => i.props['data-job']),
    selecionado: itens.filter(i => i.props['data-selecionado'] === '1').map(i => i.props['data-job']),
    textos: itens.map(textoDe),
    botoes: botoes.map(b => [textoDe(b), b.props['data-forcar'], !!b.props.disabled]),
    chamadasExtrair: ext, chamadasSelecionar: sel,
  }
  const semPermissao = mini.montar(el(ListaJobsIsx, { jobs: JOBS, selecionado: '', onSelecionar: () => {}, onExtrair: () => {}, podeEditar: false, extraindo: null }))
  saida.lista.semPermissaoBotoes = porAcao(semPermissao, 'extrair').length
  const ocupada = mini.montar(el(ListaJobsIsx, { jobs: JOBS, selecionado: '', onSelecionar: () => {}, onExtrair: () => {}, podeEditar: true, extraindo: 'SeqSsdVidaDime' }))
  saida.lista.ocupada = porAcao(ocupada, 'extrair').map(b => [textoDe(b), !!b.props.disabled])
  saida.lista.vazia = porAttr(mini.montar(el(ListaJobsIsx, { jobs: [], selecionado: '', onSelecionar: () => {}, onExtrair: () => {}, podeEditar: true, extraindo: null })), 'data-lista-vazia').length
}

// ── 3. cabeçalho ─────────────────────────────────────────────────────────────
{
  const cache = mini.montar(el(CabecalhoJobIsx, { job: JOB, cacheHit: true }))
  const agora = mini.montar(el(CabecalhoJobIsx, { job: JOB, cacheHit: false }))
  const soBanco = mini.montar(el(CabecalhoJobIsx, { job: JOB }))
  const comErro = mini.montar(el(CabecalhoJobIsx, { job: { ...JOB, status: 'erro', erro: 'O istool falhou ao exportar o job' } }))
  const antes = porAttr(cache, 'data-descricao-longa').length
  cache.clicar(porAcao(cache, 'descricao-longa')[0])
  saida.cabecalho = {
    badgeCache: porAttr(cache, 'data-badge-cache').length, badgeExtraido: porAttr(agora, 'data-badge-extraido').length,
    soBanco: porAttr(soBanco, 'data-badge-cache').length + porAttr(soBanco, 'data-badge-extraido').length,
    texto: soBanco.texto, erro: textoDe(porAttr(comErro, 'data-erro-job')[0]),
    descricaoLongaAntes: antes, descricaoLongaDepois: porAttr(cache, 'data-descricao-longa').length,
    naoReconhecidos: textoDe(porAttr(cache, 'data-nao-reconhecidos')[0]),
  }
}

// ── 4. filhos da sequence ─────────────────────────────────────────────────────
{
  const sel = [], ext = []
  const filhos = [{ job_name: 'SsdVidaDimePessoa02Ftp', activity: 'Act_Pessoa' }, { job_name: 'JobDeOutroPipeline', activity: 'Act_Outro' }]
  const tela = mini.montar(el(FilhosSequenceIsx, { filhos, jobsDoPipeline: new Set(['ssdvidadimepessoa02ftp', 'SeqSsdVidaDime']), onSelecionar: j => sel.push(j), onExtrair: j => ext.push(j), podeEditar: true, extraindo: null }))
  tela.clicar(porAcao(tela, 'ver-filho')[0])
  tela.clicar(porAcao(tela, 'extrair-filho')[0])
  saida.filhos = {
    mapeados: porAttr(tela, 'data-filho').map(n => [n.props['data-filho'], n.props['data-mapeado']]),
    verFilho: porAcao(tela, 'ver-filho').length, extrairFilho: porAcao(tela, 'extrair-filho').length,
    texto: tela.texto, sel, ext,
    vazio: porAttr(mini.montar(el(FilhosSequenceIsx, { filhos: [], jobsDoPipeline: new Set(), onSelecionar: () => {}, onExtrair: () => {}, podeEditar: true, extraindo: null })), 'data-filhos-vazio').length,
    semPermissao: porAcao(mini.montar(el(FilhosSequenceIsx, { filhos, jobsDoPipeline: new Set(['SsdVidaDimePessoa02Ftp']), onSelecionar: () => {}, onExtrair: () => {}, podeEditar: false, extraindo: null })), 'extrair-filho').length,
  }
}

// ── 5. tabela de stages ──────────────────────────────────────────────────────
{
  const sel = []
  const tela = mini.montar(el(TabelaStagesIsx, { stages: STAGES, selecionado: 'TrfNlist', onSelecionar: s => sel.push(s) }))
  const linhas = porAttr(tela, 'data-stage')
  tela.clicar(linhas[2])
  saida.tabela = {
    linhas: linhas.map(l => l.props['data-stage']),
    selecionada: linhas.filter(l => l.props['data-selecionado'] === '1').map(l => l.props['data-stage']),
    textos: linhas.map(textoDe), sel,
  }
}

// ── 6. conteúdo do stage ─────────────────────────────────────────────────────
{
  const origem = mini.montar(el(ConteudoStageIsx, { stage: STAGES[0] }))
  const trf = mini.montar(el(ConteudoStageIsx, { stage: STAGES[1] }))
  const destino = mini.montar(el(ConteudoStageIsx, { stage: STAGES[2] }))
  const aptAntes = porAttr(trf, 'data-apt-code').length
  trf.clicar(porAcao(trf, 'apt')[0])
  saida.stage = {
    origem: { sql: textoDe(porAttr(origem, 'data-sql')[0]), banco: textoDe(porAttr(origem, 'data-banco')[0]), colunasSaida: porAttr(origem, 'data-colunas').map(n => n.props['data-colunas']), texto: origem.texto },
    trf: { expressoes: porAttr(trf, 'data-expressao').map(n => n.props['data-expressao']), aptAntes, aptDepois: textoDe(porAttr(trf, 'data-apt-code')[0]), colunas: porAttr(trf, 'data-colunas').map(n => n.props['data-colunas']), sql: porAttr(trf, 'data-sql').length },
    destino: { arquivo: textoDe(porAttr(destino, 'data-arquivo')[0]), parametros: porAttr(destino, 'data-parametro').map(n => n.props['data-parametro']), colunas: porAttr(destino, 'data-colunas').map(n => n.props['data-colunas']) },
  }
  const texto = mini.montar(el(TextoComParametros, { texto: '#PSetSsdVida.ParmDbNameSsd#' }))
  saida.stage.textoSoParametro = { badges: porAttr(texto, 'data-parametro').map(n => n.props['data-parametro']), titulo: porAttr(texto, 'data-parametro')[0].props.title }
  saida.stage.textoVazio = mini.montar(el(TextoComParametros, { texto: null })).texto
}

process.stdout.write(JSON.stringify(saida))
