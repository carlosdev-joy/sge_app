// Bancada do download nos Utilitários (spec docs/spec-utilitarios-transferencia.md, F2).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F2 é comportamento: o Baixar aparece ao lado de Copiar e como
// saída do 415/413 (não do 403); no navegador, só em arquivo e só com
// `onBaixar`, e clicar nele NÃO escolhe o arquivo nem fecha; a faixa mostra
// conectando → progresso → pronto/erro com região `aria-live` que existe
// sempre; e `baixarArquivo` conta os bytes contra o Content-Length, entrega
// o Blob com o nome do cabeçalho e recusa download pela metade. Nada disso se
// prova lendo o `.tsx`. Componentes e libs rodam aqui byte a byte como estão
// no `src/`, no React mínimo da casa (minireact.cjs).
//
// A página (container com react-query) fica de fora: é rede; a prova dela é
// tsc + build + a tela no DEV. O ambiente do download (`buscar`, `entregar`)
// é injetado — o Node não tem fetch autenticado nem URL.createObjectURL.
//
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_transferencia_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/utilitarios/ModalConteudoArquivo.tsx',
  'components/utilitarios/NavegadorPastas.tsx',
  'components/utilitarios/BarraTransferencia.tsx',
  'lib/utilitariosTransferencia.ts',
  'lib/utilitariosDownload.ts',
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
    const js = transform(fonte, {
      transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true, filePath: arquivo,
    }).code
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
  createElement: mini.criar, Fragment: mini.FRAGMENT, forwardRef, useId: () => 'orq-id',
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

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-transferencia-'))
preparar(tmp)
shims(tmp)
const { ModalConteudoArquivo } = require(path.join(tmp, 'components/utilitarios/ModalConteudoArquivo.js'))
const { NavegadorPastas } = require(path.join(tmp, 'components/utilitarios/NavegadorPastas.js'))
const { BarraTransferencia } = require(path.join(tmp, 'components/utilitarios/BarraTransferencia.js'))
const T = require(path.join(tmp, 'lib/utilitariosTransferencia.js'))
const D = require(path.join(tmp, 'lib/utilitariosDownload.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const todosTypeButton = (tela) => tela.achar(n => n.tag === 'button').every(b => b.props.type === 'button')

const saida = {}

// ── 1. puras ───────────────────────────────────────────────────────────────
saida.puras = {
  url: [
    T.urlBaixar({ servidor: 'datastage', diretorio: ' /dados/bi/2026 ', nome: ' relatório ção.txt ' }),
    T.urlBaixar({ servidor: 'datastage', diretorio: '/dados/bi', nome: 'a+b&c%d.bin' }),
  ],
  nome: [
    T.nomeDoContentDisposition("attachment; filename=\"relat_rio __o.txt\"; filename*=UTF-8''relat%C3%B3rio%20%C3%A7%C3%A3o.txt", 'x'),
    T.nomeDoContentDisposition('attachment; filename="carga.bin"', 'x'),
    T.nomeDoContentDisposition('attachment; filename=carga.bin', 'x'),
    T.nomeDoContentDisposition(null, 'pedido.txt'),
    T.nomeDoContentDisposition("attachment; filename=\"res.txt\"; filename*=UTF-8''%E0%A4%A", 'x'),
    T.nomeDoContentDisposition('inline', 'pedido.txt'),
  ],
  progresso: [T.textoProgresso(1536, 40 * 1024 * 1024), T.textoProgresso(512, null)],
  percentual: [T.percentual(0, 100), T.percentual(50, 200), T.percentual(300, 200), T.percentual(5, null), T.percentual(1, 3)],
  oferece: [T.ofereceDownload(413), T.ofereceDownload(415), T.ofereceDownload(403), T.ofereceDownload(null)],
  emCurso: [T.emCurso(null), T.emCurso({ fase: 'conectando', nome: 'x' }), T.emCurso({ fase: 'baixando', nome: 'x', feito: 1, total: 2 }),
            T.emCurso({ fase: 'pronto', nome: 'x', total: 1 }), T.emCurso({ fase: 'erro', nome: 'x', status: 413, mensagem: 'm' })],
  erro: [
    T.erroTransferencia({ status: 413, message: '413 Payload Too Large' }),
    T.erroTransferencia({ status: 503, message: 'Há transferências em andamento — tente de novo em instantes.',
      detail: 'Há transferências em andamento — tente de novo em instantes.' }),
    T.erroTransferencia({ status: 502, message: '502 Bad Gateway' }),
    T.erroTransferencia(new TypeError('Failed to fetch')),
    T.erroTransferencia({ detail: 'O arquivo chegou incompleto (5 de 10 bytes) — tente de novo.' }),
  ],
  frases: [
    T.fraseTransferencia({ fase: 'conectando', nome: 'a.bin' }),
    T.fraseTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 5, total: 15 }),
    T.fraseTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 5, total: null }),
    T.fraseTransferencia({ fase: 'pronto', nome: 'a.bin', total: 15 }),
    T.fraseTransferencia({ fase: 'erro', nome: 'a.bin', status: 413, mensagem: 'acima do teto' }),
  ],
  // O leitor de tela só ouve marcos: 0–24 % sem número, depois 25/50/75/100.
  anuncio: [
    T.anuncioTransferencia(null),
    T.anuncioTransferencia({ fase: 'conectando', nome: 'a.bin' }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 0, total: 100 }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 24, total: 100 }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 25, total: 100 }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 74, total: 100 }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 100, total: 100 }),
    T.anuncioTransferencia({ fase: 'baixando', nome: 'a.bin', feito: 5, total: null }),
    T.anuncioTransferencia({ fase: 'pronto', nome: 'a.bin', total: 15 }),
    T.anuncioTransferencia({ fase: 'erro', nome: 'a.bin', status: 413, mensagem: 'acima do teto' }),
  ],
}

// ── 2. baixarArquivo com ambiente injetado ─────────────────────────────────
function respostaFake({ headers = {}, blocos = [], semStream = false }) {
  const h = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]))
  const res = { headers: { get: (k) => (h.has(k.toLowerCase()) ? h.get(k.toLowerCase()) : null) } }
  if (semStream) {
    res.blob = async () => new Blob(blocos)
  } else {
    let i = 0
    res.body = { getReader: () => ({
      read: async () => (i < blocos.length ? { done: false, value: blocos[i++] } : { done: true, value: undefined }),
    }) }
  }
  return res
}
const BLOCOS = [new Uint8Array([1, 2, 3, 4, 5]), new Uint8Array([6, 7, 8, 9, 10]), new Uint8Array([11, 12, 13, 14, 15])]
const PEDIDO = { servidor: 'datastage', diretorio: '/dados/bi', nome: ' imagem.bin ' }
const CABECALHOS = {
  'Content-Length': '15', 'X-Orquestra-Sha256': 'abc',
  'Content-Disposition': "attachment; filename=\"imagem.bin\"; filename*=UTF-8''imagem.bin",
}
async function baixar(resposta, extra = {}) {
  const urls = []; const progresso = []; const entregues = []
  let erro = null; let resultado = null
  try {
    resultado = await D.baixarArquivo(PEDIDO, (f, t) => progresso.push([f, t]), {
      buscar: async (u) => { urls.push(u); if (resposta instanceof Error) throw resposta; return resposta },
      entregar: (blob, nome) => entregues.push({ blob, nome }),
      ...extra,
    })
  } catch (e) {
    erro = { status: e.status === undefined ? null : e.status, detail: e.detail === undefined ? null : e.detail, message: e.message }
  }
  const bytes = entregues.length ? Array.from(new Uint8Array(await entregues[0].blob.arrayBuffer())) : null
  return { urls, progresso, entregues: entregues.map(e => ({ tamanho: e.blob.size, nome: e.nome })), bytes, erro, resultado }
}

async function download() {
  const r = {}
  r.ok = await baixar(respostaFake({ headers: CABECALHOS, blocos: BLOCOS }))
  r.incompleto = await baixar(respostaFake({ headers: Object.assign({}, CABECALHOS, { 'Content-Length': '20' }), blocos: BLOCOS }))
  r.semStream = await baixar(respostaFake({ headers: CABECALHOS, blocos: BLOCOS, semStream: true }))
  r.semTotal = await baixar(respostaFake({ headers: { 'Content-Disposition': 'attachment; filename="x.bin"' }, blocos: BLOCOS }))
  r.semCabecalho = await baixar(respostaFake({ headers: { 'Content-Length': '15' }, blocos: BLOCOS }))
  r.erroApi = await baixar(Object.assign(new Error('Arquivo de 60,0 MB, acima do teto'), { status: 413, detail: 'Arquivo de 60,0 MB, acima do teto de 50,0 MB para download.' }))
  r.vazio = await baixar(respostaFake({ headers: Object.assign({}, CABECALHOS, { 'Content-Length': '0' }), blocos: [] }))
  saida.download = r
}

// ── 3. modal de conteúdo ───────────────────────────────────────────────────
const PEDIDO_LEITURA = { servidor: 'datastage', diretorio: '/dados/bi/', nome: 'consulta.sql' }
const RESULTADO = {
  caminho: '/dados/bi/consulta.sql', tamanho_bytes: 15, linhas: 1, codificacao: 'utf-8',
  truncado: false, modificado_em: '2026-09-03 00:57:23', conteudo: 'SELECT 1 AS x;\n', duracao_ms: 166,
}
function montarModal(props) {
  const chamadas = { fechar: 0, retentar: [], baixar: 0 }
  const tela = mini.montar(el(ModalConteudoArquivo, Object.assign({
    aberto: true, pedido: PEDIDO_LEITURA, estado: 'buscando', resultado: null, erro: null,
    onFechar: () => { chamadas.fechar++ }, onRetentar: (n) => chamadas.retentar.push(n),
  }, props)))
  return { tela, chamadas }
}
{
  const r = {}
  {
    const { tela, chamadas } = montarModal({ estado: 'pronto', resultado: RESULTADO, onBaixar: () => { chamadas.baixar++ } })
    const b = porAcao(tela, 'baixar')
    r.pronto = { botoes: b.length, type: b[0] && b[0].props.type, desligado: !!(b[0] && b[0].props.disabled) }
    tela.clicar(b[0])
    r.pronto.chamou = chamadas.baixar
    r.pronto.copiarAindaExiste = porAcao(tela, 'copiar').length
  }
  {
    const { tela } = montarModal({ estado: 'pronto', resultado: RESULTADO, onBaixar: () => {}, baixando: true })
    r.prontoBaixando = { desligado: !!porAcao(tela, 'baixar')[0].props.disabled }
  }
  {
    const { tela } = montarModal({ estado: 'pronto', resultado: RESULTADO })
    r.prontoSemOnBaixar = { botoes: porAcao(tela, 'baixar').length }
  }
  {
    const { tela, chamadas } = montarModal({ estado: 'erro', erro: { status: 415, mensagem: 'O arquivo não é texto (parece binário) — os Utilitários só abrem texto.' },
      onBaixar: () => { chamadas.baixar++ } })
    const b = porAcao(tela, 'baixar-arquivo')
    r.erro415 = { botoes: b.length, type: b[0] && b[0].props.type, formUltimas: porAttr(tela, 'data-form').length,
                  texto: textoDe(porAttr(tela, 'data-saida')[0]) }
    tela.clicar(b[0])
    r.erro415.chamou = chamadas.baixar
  }
  {
    const { tela } = montarModal({ estado: 'erro', erro: { status: 413, mensagem: 'Arquivo de 4,8 MB, acima do teto de 64,0 KB.' }, onBaixar: () => {} })
    r.erro413 = { botoes: porAcao(tela, 'baixar-arquivo').length, formUltimas: porAttr(tela, 'data-form').length,
                  texto: textoDe(porAttr(tela, 'data-saida')[0]) }
  }
  {
    const { tela } = montarModal({ estado: 'erro', erro: { status: 403, mensagem: 'Fora dos diretórios liberados.' }, onBaixar: () => {} })
    r.erro403 = { botoes: porAcao(tela, 'baixar-arquivo').length, saida: porAttr(tela, 'data-saida').length }
  }
  {
    const { tela } = montarModal({ estado: 'erro', erro: { status: 415, mensagem: 'binário' } })
    r.erro415SemOnBaixar = { botoes: porAcao(tela, 'baixar-arquivo').length }
  }
  {
    const { tela } = montarModal({ estado: 'buscando', onBaixar: () => {} })
    r.buscando = { botoes: porAcao(tela, 'baixar').length + porAcao(tela, 'baixar-arquivo').length }
  }
  saida.modal = r
}

// ── 4. navegador ───────────────────────────────────────────────────────────
const E = (nome, tipo, extra = {}) => Object.assign({ nome, tipo, tamanho_bytes: null, modificado_em: null }, extra)
const NIVEL_ZERO = { caminho: null, caminho_real: null, raiz: null, pai: null, ocultos_omitidos: 0, truncado: false,
  entradas: [E('/dados/bi', 'raiz'), E('/dados/param', 'raiz')] }
const BI = { caminho: '/dados/bi', caminho_real: '/dados/bi', raiz: '/dados/bi', pai: null, ocultos_omitidos: 0, truncado: false,
  entradas: [E('2026', 'pasta'), E('consulta.sql', 'arquivo', { tamanho_bytes: 15 }), E('imagem.bin', 'arquivo', { tamanho_bytes: 4102 }),
             E('link_fora', 'link', { alvo: null }), E('atalho.param', 'link', { alvo: 'arquivo', tamanho_bytes: 15 }),
             E('l_desconhecido', 'link', { alvo: 'desconhecido' })] }
function Caixa({ props }) {
  const [filtro, setFiltro] = mini.hooks.useState('')
  return el(NavegadorPastas, Object.assign({}, props, { filtro, onFiltro: setFiltro }))
}
function montarNav(props) {
  const chamadas = { navegar: [], usar: [], arquivo: [], fechar: 0, baixar: [] }
  const tela = mini.montar(el(Caixa, { props: Object.assign({
    aberto: true, listagem: BI, carregando: false, erro: null, mostrarOcultos: false,
    onNavegar: (c) => chamadas.navegar.push(c), onMostrarOcultos: () => {},
    onUsarPasta: (c) => chamadas.usar.push(c), onEscolherArquivo: (p, n) => chamadas.arquivo.push([p, n]),
    onFechar: () => { chamadas.fechar++ },
  }, props) }))
  return { tela, chamadas }
}
const liDe = (tela, nome) => porAttr(tela, 'data-entrada').find(n => n.props['data-entrada'] === nome)
const baixarDe = (tela, nome) => { const li = liDe(tela, nome); return li && li.filhos.find(f => f.props && f.props['data-acao'] === 'baixar-linha') }
{
  const r = {}
  {
    const { tela, chamadas } = montarNav({ onBaixar: (p, n) => chamadas.baixar.push([p, n]) })
    r.comOnBaixar = {
      icones: porAcao(tela, 'baixar-linha').length,
      quem: BI.entradas.map(e => e.nome).filter(n => !!baixarDe(tela, n)),
      todosTypeButton: todosTypeButton(tela),
      ariaLabel: baixarDe(tela, 'consulta.sql').props['aria-label'],
    }
    tela.clicar(baixarDe(tela, 'consulta.sql'))
    tela.clicar(baixarDe(tela, 'atalho.param'))
    // Cópias: o clique seguinte (no botão principal) empurra em `arquivo`, e a
    // foto de "antes" não pode mudar junto.
    r.comOnBaixar.chamadas = { baixar: chamadas.baixar.slice(), arquivo: chamadas.arquivo.slice(),
                               fechar: chamadas.fechar, navegar: chamadas.navegar.slice() }
    // O botão principal da linha continua escolhendo o arquivo.
    tela.clicar(liDe(tela, 'consulta.sql').filhos.find(f => f.tag === 'button'))
    r.comOnBaixar.escolheu = chamadas.arquivo.slice()
  }
  {
    const { tela } = montarNav({ onBaixar: () => {}, baixando: true })
    r.baixando = { desligados: porAcao(tela, 'baixar-linha').every(b => !!b.props.disabled), total: porAcao(tela, 'baixar-linha').length }
  }
  {
    const { tela } = montarNav({})
    r.semOnBaixar = { icones: porAcao(tela, 'baixar-linha').length }
  }
  {
    const { tela } = montarNav({ listagem: NIVEL_ZERO, onBaixar: () => {} })
    r.nivelZero = { icones: porAcao(tela, 'baixar-linha').length }
  }
  saida.navegador = r
}

// ── 5. faixa de transferência ──────────────────────────────────────────────
function montarBarra(estado) {
  const chamadas = { fechar: 0 }
  const tela = mini.montar(el(BarraTransferencia, { estado, onFechar: () => { chamadas.fechar++ } }))
  const raiz = porAttr(tela, 'data-transferencia')[0]
  const live = porAttr(tela, 'aria-live')
  const painel = porAttr(tela, 'data-painel-transferencia')
  const barra = porAttr(tela, 'data-barra')[0]
  const preenchido = porAttr(tela, 'data-preenchido')[0]
  return {
    tela, chamadas,
    r: {
      fase: raiz && raiz.props['data-transferencia'],
      // UMA região viva, sempre presente, só para leitor de tela, sem role=status aninhado.
      live: live.length, liveSrOnly: !!(live[0] && /\bsr-only\b/.test(live[0].props.className || '')),
      anuncio: live[0] ? textoDe(live[0]) : null,
      roleStatus: tela.achar(n => n.props && n.props.role === 'status').length,
      painel: painel.length,
      // Acima do Modal (z-50) e fora do trap de foco do overlay.
      // (`\b` não vale depois de `]`: os dois lados são não-palavra)
      acimaDoModal: !!(painel[0] && /(^|\s)z-\[60\](\s|$)/.test(painel[0].props.className || '')),
      foraDoTrap: !!(painel[0] && painel[0].props['data-modal-exempt'] !== undefined),
      frase: porAttr(tela, 'data-frase').map(textoDe)[0] ?? null,
      barra: !!barra, valuenow: barra ? (barra.props['aria-valuenow'] ?? null) : null,
      preenchido: preenchido ? String(preenchido.props['data-preenchido']) : null,
      fechar: porAcao(tela, 'fechar-transferencia').length,
      todosTypeButton: todosTypeButton(tela),
    },
  }
}
{
  const r = {}
  r.nenhuma = montarBarra(null).r
  r.conectando = montarBarra({ fase: 'conectando', nome: 'a.bin' }).r
  r.baixando = montarBarra({ fase: 'baixando', nome: 'a.bin', feito: 5, total: 15 }).r
  r.baixandoSemTotal = montarBarra({ fase: 'baixando', nome: 'a.bin', feito: 5, total: null }).r
  {
    const m = montarBarra({ fase: 'pronto', nome: 'a.bin', total: 15 })
    m.tela.clicar(porAcao(m.tela, 'fechar-transferencia')[0])
    r.pronto = Object.assign(m.r, { fechou: m.chamadas.fechar })
  }
  r.erro = montarBarra({ fase: 'erro', nome: 'a.bin', status: 413, mensagem: 'Arquivo acima do teto de download.' }).r
  saida.barra = r
}

;(async () => {
  try {
    await download()
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  process.stdout.write(JSON.stringify(saida), () => process.exit(0))
})().catch(e => { console.error(e); process.exit(1) })
