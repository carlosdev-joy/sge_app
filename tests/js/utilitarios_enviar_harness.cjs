// Bancada da aba Enviar arquivo (spec docs/spec-utilitarios-transferencia.md, F4).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F4 é comportamento: escolher um arquivo preenche o nome; extensão
// fora da lista, arquivo acima do teto e pasta fora das raízes desligam o
// Enviar ANTES de qualquer XHR; Enter num campo não envia; o Enviar manda o
// pedido e o `File`; o modal passa por enviando (barra + Cancelar, que some
// quando o corpo já subiu inteiro) → existe/pronto/cancelado/erro; e
// `enviarArquivo` monta o PUT cru com Authorization, traduz 409/502-HTML/504,
// e o cancelar rejeita com `cancelado`. Nada disso se prova lendo o `.tsx`.
// Componentes e libs rodam aqui byte a byte como estão no `src/`.
//
// A página (container) fica de fora: é rede; a prova dela é tsc + build + a
// tela no DEV. O XHR é injetado (`criarXhr`) — o Node não tem XMLHttpRequest.
//
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_enviar_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/utilitarios/FormEnviarArquivo.tsx',
  'components/utilitarios/ModalEnvioArquivo.tsx',
  'lib/utilitariosTransferencia.ts',
  'lib/utilitariosEnvio.ts',
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

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-enviar-'))
preparar(tmp)
shims(tmp)
const { FormEnviarArquivo } = require(path.join(tmp, 'components/utilitarios/FormEnviarArquivo.js'))
const { ModalEnvioArquivo } = require(path.join(tmp, 'components/utilitarios/ModalEnvioArquivo.js'))
const T = require(path.join(tmp, 'lib/utilitariosTransferencia.js'))
const E = require(path.join(tmp, 'lib/utilitariosEnvio.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const porCampo = (tela, campo) => tela.achar(n => n.props && n.props['data-campo'] === campo)[0]
const textoDe = (no) => typeof no === 'string' ? no : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const inputs = (tela) => tela.achar(n => n.tag === 'input')
const digitar = (tela, no, value) => tela.disparar(no, 'onChange', { target: { value } })
const todosTypeButton = (tela) => tela.achar(n => n.tag === 'button').every(b => b.props.type === 'button')
const tick = () => new Promise(r => setImmediate(r))

const saida = {}

// ── 1. puras ───────────────────────────────────────────────────────────────
const RAIZES = ['/dados/bi', '/dados/param']
const EXT = ['txt', 'sql', 'param']
const TETO_KB = 51200
saida.puras = {
  extensaoDe: ['Relatorio.TXT', 'dados.tar.gz', 'README', '.bashrc', 'x.', ' a.b '].map(T.extensaoDe),
  avisoEnvio: {
    vazio: T.avisoEnvio('', 10, EXT, TETO_KB),
    ok: T.avisoEnvio('Relatorio.TXT', 10, EXT, TETO_KB),
    barra: T.avisoEnvio('a/b.txt', 10, EXT, TETO_KB),
    controle: T.avisoEnvio('a\nb.txt', 10, EXT, TETO_KB),
    invisivel: T.avisoEnvio('‮txt.exe', 10, EXT, TETO_KB),
    longo: T.avisoEnvio('a'.repeat(212) + '.txt', 10, EXT, TETO_KB),
    semExt: T.avisoEnvio('README', 10, EXT, TETO_KB),
    foraDaLista: T.avisoEnvio('script.SH', 10, EXT, TETO_KB),
    dupla: T.avisoEnvio('x.txt.sh', 10, EXT, TETO_KB),
    teto: T.avisoEnvio('grande.txt', TETO_KB * 1024 + 1, EXT, TETO_KB),
    noTeto: T.avisoEnvio('grande.txt', TETO_KB * 1024, EXT, TETO_KB),
    semTamanho: T.avisoEnvio('x.txt', null, EXT, TETO_KB),
  },
  pronto: {
    ok: T.envioPronto('/dados/bi', 'x.txt', 10, RAIZES, EXT, TETO_KB, true),
    semPermissao: T.envioPronto('/dados/bi', 'x.txt', 10, RAIZES, EXT, TETO_KB, false),
    semArquivo: T.envioPronto('/dados/bi', 'x.txt', null, RAIZES, EXT, TETO_KB, true),
    fora: T.envioPronto('/etc', 'x.txt', 10, RAIZES, EXT, TETO_KB, true),
    extRuim: T.envioPronto('/dados/bi', 'x.exe', 10, RAIZES, EXT, TETO_KB, true),
    semPasta: T.envioPronto('', 'x.txt', 10, RAIZES, EXT, TETO_KB, true),
  },
  url: T.urlEnviar({ servidor: 'datastage', diretorio: ' /dados/bi ', nome: ' Relatório ção.TXT ', sobrescrever: true }),
  erro: {
    conflito: T.erroEnvio({ status: 409, detail: { mensagem: 'O arquivo já existe. Confirme para gravar por cima.', existente: { tamanho_bytes: 10, modificado_em: '2026-09-07 10:00:00' } } }),
    htmlNginx502: T.erroEnvio({ status: 502, message: '502', detail: undefined }),
    htmlNginx413: T.erroEnvio({ status: 413, message: '413', detail: undefined }),
    api413: T.erroEnvio({ status: 413, message: 'Arquivo de 60,0 MB (62914560 bytes), acima do teto de 50,0 MB para envio.', detail: 'Arquivo de 60,0 MB (62914560 bytes), acima do teto de 50,0 MB para envio.' }),
    timeout504: T.erroEnvio({ status: 504, message: 'O servidor não respondeu em 240 s.', detail: 'O servidor não respondeu em 240 s.' }),
    ocupado503: T.erroEnvio({ status: 503, detail: 'Há transferências em andamento — tente de novo em instantes.' }),
    parou408: T.erroEnvio({ status: 408, message: '408', detail: undefined }),
    rede: T.erroEnvio(new Error('Falha de rede no envio')),
  },
  resumo: T.resumoEnvio({ caminho: '/x', tamanho_bytes: 3145728, sha256: 'abcdef0123456789', criado: false, backup: '/x.bak-1', duracao_ms: 1234 }),
  chegouInteiro: [T.envioChegouInteiro(null), T.envioChegouInteiro({ enviado: 5, total: 15 }), T.envioChegouInteiro({ enviado: 15, total: 15 }), T.envioChegouInteiro({ enviado: 0, total: 0 })],
  cancelamento: [T.fraseCancelamento(false), T.fraseCancelamento(true)],
}

// ── 2. enviarArquivo com XHR falso ─────────────────────────────────────────
function xhrFalso(resposta) {
  const x = {
    chamadas: { open: [], headers: [], send: [], abort: 0 },
    upload: { onprogress: null }, onload: null, onerror: null, onabort: null, status: 0, responseText: '',
  }
  x.open = (m, u) => x.chamadas.open.push([m, u])
  x.setRequestHeader = (k, v) => x.chamadas.headers.push([k, v])
  x.abort = () => { x.chamadas.abort++; if (x.onabort) x.onabort() }
  x.send = (corpo) => {
    x.chamadas.send.push(corpo)
    setImmediate(() => {
      for (const [l, t] of resposta.progresso || []) if (x.upload.onprogress) x.upload.onprogress({ loaded: l, total: t, lengthComputable: true })
      if (resposta.evento === 'error') { x.onerror(); return }
      if (resposta.evento === 'abort') return   // fica esperando o cancelar()
      x.status = resposta.status; x.responseText = resposta.body; x.onload()
    })
  }
  return x
}
const PEDIDO = { servidor: 'datastage', diretorio: '/dados/bi', nome: 'Relatorio.TXT', sobrescrever: false }
const ARQUIVO = new Blob([new Uint8Array(15)])
async function enviar(resposta, extra = {}) {
  const x = xhrFalso(resposta)
  const progresso = []; const expirou = []
  const envio = E.enviarArquivo(PEDIDO, ARQUIVO, (e, t) => progresso.push([e, t]), Object.assign({
    criarXhr: () => x, token: () => 'tok', aoExpirar: () => expirou.push(1),
  }, extra))
  if (resposta.evento === 'abort') { await tick(); await tick(); envio.cancelar() }
  let resultado = null; let erro = null
  try { resultado = await envio.promessa } catch (e) {
    erro = { status: e.status === undefined ? null : e.status, detail: e.detail === undefined ? null : e.detail,
             message: e.message, cancelado: !!e.cancelado }
  }
  return { open: x.chamadas.open, headers: x.chamadas.headers, enviouBlob: x.chamadas.send.length === 1 && x.chamadas.send[0] === ARQUIVO,
           abort: x.chamadas.abort, progresso, expirou: expirou.length, resultado, erro }
}
async function transporte() {
  const r = {}
  r.ok = await enviar({ status: 200, body: JSON.stringify({ caminho: '/dados/bi/Relatorio.TXT', tamanho_bytes: 15, sha256: 'abc', criado: true, backup: null, duracao_ms: 12 }), progresso: [[5, 15], [15, 15]] })
  r.conflito = await enviar({ status: 409, body: JSON.stringify({ detail: { mensagem: 'O arquivo já existe. Confirme para gravar por cima.', existente: { tamanho_bytes: 10, modificado_em: '2026-09-07 10:00:00' } } }) })
  r.html502 = await enviar({ status: 502, body: '<html><body><h1>502 Bad Gateway</h1></body></html>' })
  r.api504 = await enviar({ status: 504, body: JSON.stringify({ detail: 'O servidor não respondeu em 240 s.' }) })
  r.rede = await enviar({ evento: 'error' })
  r.cancelado = await enviar({ evento: 'abort', progresso: [[5, 15]] })
  r.expirou = await enviar({ status: 401, body: JSON.stringify({ detail: 'Not authenticated' }) })
  r.semToken = await enviar({ status: 200, body: '{}' }, { token: () => null })
  saida.transporte = r
}

// ── 3. formulário ──────────────────────────────────────────────────────────
const SERVIDORES = [{ id: 'datastage', label: 'Servidor DataStage', configurado: true }]
function montarForm(props) {
  const chamadas = { enviar: [] }
  const tela = mini.montar(el(FormEnviarArquivo, Object.assign({
    servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES }, extensoes: EXT, tetoKb: TETO_KB,
    podeGravar: true, enviando: false, onEnviar: (p, a) => chamadas.enviar.push([p, a]),
  }, props)))
  return { tela, chamadas }
}
const campoPasta = (tela) => inputs(tela).find(n => n.props.placeholder && (n.props.placeholder.endsWith('/…') || n.props.placeholder === '/caminho/da/pasta'))
const campoNome = (tela) => inputs(tela).find(n => n.props.placeholder === 'relatorio.txt')
const seletor = (tela) => porCampo(tela, 'arquivo')
const formEnviar = (tela) => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'enviar-arquivo')
const escolhido = (tela) => porAttr(tela, 'data-arquivo-escolhido')[0]
const ARQ_LOCAL = { name: 'Relatorio.TXT', size: 3000 }
const ARQ_GRANDE = { name: 'grande.txt', size: TETO_KB * 1024 + 1 }
{
  const { tela, chamadas } = montarForm({})
  const botao = () => porAcao(tela, 'enviar')[0]
  const r = {
    inicio: { enviar: !!botao().props.disabled, escolhido: escolhido(tela).props['data-arquivo-escolhido'], texto: textoDe(escolhido(tela)),
              seletorTipo: seletor(tela).props.type, seletorSrOnly: /\bsr-only\b/.test(seletor(tela).props.className || ''),
              todosTypeButton: todosTypeButton(tela), teto: tela.texto.includes('Até 50,0 MB') },
  }
  tela.disparar(seletor(tela), 'onChange', { target: { files: [ARQ_LOCAL] } })
  r.escolheu = { nome: campoNome(tela).props.value, texto: textoDe(escolhido(tela)), enviar: !!botao().props.disabled }
  digitar(tela, campoPasta(tela), '/dados/bi/2026')
  r.comPasta = { enviar: !!botao().props.disabled }
  // Enter num campo: o <form> não envia.
  tela.disparar(formEnviar(tela), 'onSubmit', { preventDefault() {} })
  r.enterNoCampo = chamadas.enviar.length
  digitar(tela, campoNome(tela), 'x.exe')
  r.extRuim = { enviar: !!botao().props.disabled, aviso: tela.texto.includes('Extensão exe não está na lista') }
  digitar(tela, campoNome(tela), 'README')
  r.semExt = { enviar: !!botao().props.disabled, aviso: tela.texto.includes('sem extensão') }
  digitar(tela, campoNome(tela), 'Relatorio.TXT')
  digitar(tela, campoPasta(tela), '/etc')
  r.fora = { enviar: !!botao().props.disabled, aviso: tela.texto.includes('Fora dos diretórios liberados') }
  digitar(tela, campoPasta(tela), '/dados/bi/2026')
  tela.clicar(botao())
  r.enviou = chamadas.enviar.map(([p, a]) => [p, a.name])
  // Arquivo acima do teto: aviso e botão desligado antes de qualquer XHR.
  tela.disparar(seletor(tela), 'onChange', { target: { files: [ARQ_GRANDE] } })
  r.teto = { nome: campoNome(tela).props.value, enviar: !!botao().props.disabled, aviso: tela.texto.includes('acima do teto de 50,0 MB') }
  tela.clicar(botao()) // desligado: o minireact ainda chama o onClick; o handler tem o cinto `pronto`
  r.tetoNaoEnviou = chamadas.enviar.length
  saida.form = r

  const ocupado = montarForm({ enviando: true }).tela
  ocupado.disparar(seletor(ocupado), 'onChange', { target: { files: [ARQ_LOCAL] } }); digitar(ocupado, campoPasta(ocupado), '/dados/bi')
  saida.formEnviando = { enviar: !!porAcao(ocupado, 'enviar')[0].props.disabled, escolher: !!porAcao(ocupado, 'escolher')[0].props.disabled,
                         loading: !!porAcao(ocupado, 'enviar')[0].props.loading || textoDe(porAcao(ocupado, 'enviar')[0]).includes('⟳') }
  const semPerm = montarForm({ podeGravar: false }).tela
  saida.formSemPermissao = { aviso: porAttr(semPerm, 'data-aviso').map(n => n.props['data-aviso']),
                             enviar: !!porAcao(semPerm, 'enviar')[0].props.disabled, escolher: !!porAcao(semPerm, 'escolher')[0].props.disabled,
                             seletor: !!seletor(semPerm).props.disabled }
  const semExt = montarForm({ extensoes: [] }).tela
  semExt.disparar(seletor(semExt), 'onChange', { target: { files: [ARQ_LOCAL] } }); digitar(semExt, campoPasta(semExt), '/dados/bi')
  saida.formSemExtensoes = { aviso: porAttr(semExt, 'data-aviso').map(n => n.props['data-aviso']), enviar: !!porAcao(semExt, 'enviar')[0].props.disabled }
}

// ── 4. modal ───────────────────────────────────────────────────────────────
const RESULTADO = { caminho: '/dados/bi/Relatorio.TXT', tamanho_bytes: 3145728, sha256: 'abcdef0123456789', criado: true, backup: null, duracao_ms: 1234 }
function montarModal(props) {
  const chamadas = { fechar: 0, cancelar: 0, sobrescrever: 0 }
  const tela = mini.montar(el(ModalEnvioArquivo, Object.assign({
    aberto: true, pedido: PEDIDO, estado: 'enviando', progresso: null, resultado: null, erro: null, chegouInteiro: false,
    onFechar: () => { chamadas.fechar++ }, onCancelar: () => { chamadas.cancelar++ }, onSobrescrever: () => { chamadas.sobrescrever++ },
  }, props)))
  return { tela, chamadas }
}
{
  const r = {}
  {
    const { tela, chamadas } = montarModal({ progresso: { enviado: 5, total: 15 } })
    const barra = porAttr(tela, 'data-barra')[0]
    r.enviando = { caminho: textoDe(porAttr(tela, 'data-caminho')[0]), frase: textoDe(porAttr(tela, 'data-frase-envio')[0]),
                   valuenow: barra.props['aria-valuenow'], preenchido: String(porAttr(tela, 'data-preenchido')[0].props['data-preenchido']),
                   cancelar: porAcao(tela, 'cancelar-envio').length, fechar: porAcao(tela, 'fechar').length, todosTypeButton: todosTypeButton(tela) }
    tela.clicar(porAcao(tela, 'cancelar-envio')[0])
    r.enviando.cancelou = chamadas.cancelar
  }
  {
    const { tela } = montarModal({ progresso: { enviado: 15, total: 15 } })
    r.subiuTudo = { frase: textoDe(porAttr(tela, 'data-frase-envio')[0]), cancelar: porAcao(tela, 'cancelar-envio').length,
                    preenchido: String(porAttr(tela, 'data-preenchido')[0].props['data-preenchido']) }
  }
  {
    const { tela } = montarModal({ progresso: null })
    r.semProgresso = { frase: textoDe(porAttr(tela, 'data-frase-envio')[0]), preenchido: String(porAttr(tela, 'data-preenchido')[0].props['data-preenchido']) }
  }
  {
    const { tela, chamadas } = montarModal({ estado: 'cancelado', chegouInteiro: false })
    r.canceladoAntes = { atributo: porAttr(tela, 'data-cancelado')[0].props['data-cancelado'], frase: tela.texto.includes('antes de terminar'),
                         fechar: porAcao(tela, 'fechar').length, cancelar: porAcao(tela, 'cancelar-envio').length }
    tela.clicar(porAcao(tela, 'fechar')[0]); r.canceladoAntes.fechou = chamadas.fechar
    const chegou = montarModal({ estado: 'cancelado', chegouInteiro: true }).tela
    r.canceladoChegou = { atributo: porAttr(chegou, 'data-cancelado')[0].props['data-cancelado'], frase: chegou.texto.includes('confira na pasta') }
  }
  {
    const { tela, chamadas } = montarModal({ estado: 'existe', erro: { status: 409, mensagem: 'O arquivo já existe. Confirme para gravar por cima.',
      existente: { tamanho_bytes: 27, modificado_em: '2026-09-07 07:06:00' } } })
    r.existe = { mensagem: tela.texto.includes('já existe'), tamanho: tela.texto.includes('27 B'), data: tela.texto.includes('2026-09-07 07:06:00'),
                 fechar: porAcao(tela, 'fechar').length, todosTypeButton: todosTypeButton(tela) }
    tela.clicar(porAcao(tela, 'sobrescrever')[0]); r.existe.sobrescreveu = chamadas.sobrescrever
    tela.clicar(porAcao(tela, 'cancelar')[0]); r.existe.cancelouFecha = chamadas.fechar
  }
  {
    const { tela } = montarModal({ estado: 'pronto', resultado: RESULTADO })
    r.pronto = { caminho: textoDe(porAttr(tela, 'data-caminho')[0]), resumo: textoDe(porAttr(tela, 'data-resumo')[0]), fechar: porAcao(tela, 'fechar').length }
  }
  {
    const { tela } = montarModal({ estado: 'erro', erro: T.erroEnvio({ status: 504, detail: 'O servidor não respondeu em 240 s.' }) })
    r.erro504 = { atributo: porAttr(tela, 'data-erro')[0].props['data-erro'], confira: tela.texto.includes('Confira na pasta') }
  }
  {
    const { tela } = montarModal({ aberto: false })
    r.fechado = porAttr(tela, 'data-estado').length
  }
  saida.modal = r
}

;(async () => {
  try {
    await transporte()
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  process.stdout.write(JSON.stringify(saida), () => process.exit(0))
})().catch(e => { console.error(e); process.exit(1) })
