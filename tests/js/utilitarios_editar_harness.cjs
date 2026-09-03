// Bancada da aba Utilitários › Criar/editar arquivo (spec docs/spec-utilitarios-arquivos.md, F5).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F5 é comportamento: Gravar só liga com pasta abaixo da raiz, nome
// válido, extensão da lista e (em Latin-1) sem caractere fora do repertório;
// quem não pode gravar vê o editor desabilitado com a explicação; Carregar
// existente preenche o editor e troca a codificação para a detectada; o modal
// abre em "gravando", vira resultado, ou o pedido de confirmação do 409 com o
// que será substituído. Os dois componentes de apresentação rodam aqui no React
// mínimo da casa, byte a byte como estão no `src/`.
//
// A página (container com react-query) fica de fora: tsc + build + a tela no DEV.
//
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_editar_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/utilitarios/FormEditarArquivo.tsx',
  'components/utilitarios/ModalGravacaoArquivo.tsx',
  'lib/utilitariosGravacao.ts',
]

function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const t of [base + '.tsx', base + '.ts',
                   path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) {
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
      transforms: ['typescript', 'jsx', 'imports'],
      jsxRuntime: 'automatic', production: true, filePath: arquivo,
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

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-editar-'))
preparar(tmp)
shims(tmp)
const { FormEditarArquivo } = require(path.join(tmp, 'components/utilitarios/FormEditarArquivo.js'))
const { ModalGravacaoArquivo } = require(path.join(tmp, 'components/utilitarios/ModalGravacaoArquivo.js'))
const puras = require(path.join(tmp, 'lib/utilitariosGravacao.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const porCampo = (tela, campo) => tela.achar(n => n.props && n.props['data-campo'] === campo)[0]
const textoDe = (no) => typeof no === 'string' ? no
  : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const inputs = (tela) => tela.achar(n => n.tag === 'input')
const digitar = (tela, no, value) => tela.disparar(no, 'onChange', { target: { value } })
const tick = () => new Promise(r => setImmediate(r))

const saida = {}

// ── 1. funções puras ───────────────────────────────────────────────────────
const RAIZES = ['/dados/bi', '/dados/param']
const EXT = ['txt', 'sql', 'param']
saida.puras = {
  nomeCompleto: puras.nomeArquivoCompleto(' carga ', 'TXT'),
  separar: [puras.separarNomeExtensao('carga.2026.txt'), puras.separarNomeExtensao('semext'), puras.separarNomeExtensao('.oculto')],
  pastaENome: [puras.pastaENomeDoCaminho('/dados/bi/2026/x.txt'), puras.pastaENomeDoCaminho('/x.txt'), puras.pastaENomeDoCaminho('x.txt')],
  avisoNomeBase: {
    vazio: puras.avisoNomeBase('', 'txt'), ok: puras.avisoNomeBase('carga', 'txt'), barra: puras.avisoNomeBase('a/b', 'txt'),
    controle: puras.avisoNomeBase('a\nb', 'txt'), longo: puras.avisoNomeBase('a'.repeat(212), 'txt'),
    noLimite: puras.avisoNomeBase('a'.repeat(211), 'txt'),
  },
  foraDoLatin1: [puras.foraDoLatin1('ação\n'), puras.foraDoLatin1('ok\nvalor 10€'), puras.foraDoLatin1('a\n😀')],
  contarLinhas: [puras.contarLinhas(''), puras.contarLinhas('a'), puras.contarLinhas('a\r\nb\r\n'), puras.contarLinhas('a\nb')],
  contarBytes: [puras.contarBytes('ação', 'utf-8'), puras.contarBytes('ação', 'latin-1')],
  extensaoValida: [puras.extensaoValida('txt', EXT), puras.extensaoValida('sh', EXT), puras.extensaoValida('TXT', EXT)],
  pronta: {
    ok: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'txt', conteudo: 'a', codificacao: 'utf-8' }, RAIZES, EXT, true),
    semPermissao: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'txt', conteudo: 'a', codificacao: 'utf-8' }, RAIZES, EXT, false),
    fora: puras.gravacaoPronta({ diretorio: '/etc', nome: 'x', extensao: 'txt', conteudo: 'a', codificacao: 'utf-8' }, RAIZES, EXT, true),
    extRuim: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'sh', conteudo: 'a', codificacao: 'utf-8' }, RAIZES, EXT, true),
    latin1Fora: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'txt', conteudo: '10€', codificacao: 'latin-1' }, RAIZES, EXT, true),
    latin1Ok: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'txt', conteudo: 'ação', codificacao: 'latin-1' }, RAIZES, EXT, true),
    vazioOk: puras.gravacaoPronta({ diretorio: '/dados/bi', nome: 'x', extensao: 'txt', conteudo: '', codificacao: 'utf-8' }, RAIZES, EXT, true),
  },
  erroGravacao: {
    conflito: puras.erroGravacao({ status: 409, message: '409 Conflict',
      detail: { mensagem: 'O arquivo já existe. Confirme para gravar por cima.', existente: { tamanho_bytes: 27, modificado_em: '2026-09-03 07:06:00' } } }),
    string: puras.erroGravacao({ status: 422, message: "Extensão 'sh' não liberada", detail: "Extensão 'sh' não liberada" }),
    rede: puras.erroGravacao(new TypeError('Failed to fetch')),
  },
  resumo: puras.resumoGravacao({ caminho: '/x', tamanho_bytes: 27, sha256: 'abcdef0123456789', criado: false,
    backup: '/x.bak-1', codificacao: 'utf-8', linhas: 2, duracao_ms: 248 }),
}

// ── 2. formulário ──────────────────────────────────────────────────────────
const SERVIDORES = [{ id: 'datastage', label: 'Servidor DataStage', configurado: true }]
function montarForm(props) {
  const chamadas = { gravar: [], carregar: [] }
  const tela = mini.montar(el(FormEditarArquivo, Object.assign({
    servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES }, extensoes: EXT, podeGravar: true,
    gravando: false, carregando: false,
    onCarregar: async (p) => { chamadas.carregar.push(p); return { conteudo: 'DESCRICAO=ação\n', codificacao: 'latin-1' } },
    onGravar: (p) => chamadas.gravar.push(p),
  }, props)))
  return { tela, chamadas }
}
const campoPasta = (tela) => inputs(tela).find(n => n.props.placeholder && (n.props.placeholder.endsWith('/…') || n.props.placeholder === '/caminho/da/pasta'))
const campoNome = (tela) => inputs(tela).find(n => n.props.placeholder === 'parametros_carga')
const editor = (tela) => porCampo(tela, 'conteudo')
const selectExt = (tela) => porCampo(tela, 'extensao')
const selectCod = (tela) => porCampo(tela, 'codificacao')
const formEditar = (tela) => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'editar-arquivo')

async function formulario() {
  const { tela, chamadas } = montarForm({})
  const botao = () => porAcao(tela, 'gravar')[0]
  const carregarBtn = () => porAcao(tela, 'carregar')[0]
  const r = {
    inicio: { gravar: !!botao().props.disabled, carregar: !!carregarBtn().props.disabled,
              extensao: selectExt(tela).props.value, codificacao: selectCod(tela).props.value,
              contador: textoDe(porAttr(tela, 'data-contador')[0]) },
  }
  digitar(tela, campoPasta(tela), '/dados/param')
  digitar(tela, campoNome(tela), 'parametros')
  r.semConteudo = { gravar: !!botao().props.disabled, carregar: !!carregarBtn().props.disabled }
  // Nome com extensão colada ("x.sql") separa e escolhe a extensão da lista.
  digitar(tela, campoNome(tela), 'consulta.sql')
  r.nomeComExtensao = { nome: campoNome(tela).props.value, extensao: selectExt(tela).props.value }
  digitar(tela, campoNome(tela), 'parametros')
  digitar(tela, selectExt(tela), 'param')
  // Carregar existente: preenche e troca a codificação para a detectada.
  tela.clicar(carregarBtn())
  await tick(); await tick(); tela.sincronizar()
  r.carregou = { pedido: chamadas.carregar, conteudo: editor(tela).props.value, codificacao: selectCod(tela).props.value,
                 contador: textoDe(porAttr(tela, 'data-contador')[0]) }
  // Em Latin-1, um € desliga o Gravar e avisa; em UTF-8 volta a ligar.
  digitar(tela, editor(tela), 'DESCRICAO=ação\nVALOR=10€\n')
  r.euroLatin1 = { gravar: !!botao().props.disabled, aviso: tela.texto.includes('fora do Latin-1'),
                   contador: textoDe(porAttr(tela, 'data-contador')[0]) }
  digitar(tela, selectCod(tela), 'utf-8')
  r.euroUtf8 = { gravar: !!botao().props.disabled, aviso: tela.texto.includes('fora do Latin-1') }
  // Ctrl+Enter grava com o pedido inteiro; sobrescrever começa false.
  tela.disparar(editor(tela), 'onKeyDown', { key: 'Enter', ctrlKey: true })
  r.ctrlEnter = chamadas.gravar.slice()
  // Enter sem Ctrl NÃO grava.
  tela.disparar(editor(tela), 'onKeyDown', { key: 'Enter', ctrlKey: false })
  r.enterSozinho = chamadas.gravar.length
  // Extensão fora da lista desliga.
  digitar(tela, selectExt(tela), 'sh')
  r.extRuim = { gravar: !!botao().props.disabled }
  saida.form = r

  // Sem permissão: tudo desabilitado e o aviso no lugar.
  const semPerm = montarForm({ podeGravar: false }).tela
  saida.formSemPermissao = {
    aviso: porAttr(semPerm, 'data-aviso').map(n => n.props['data-aviso']),
    editorDesabilitado: !!editor(semPerm).props.disabled,
    gravar: !!porAcao(semPerm, 'gravar')[0].props.disabled,
  }
  // Sem extensões: aviso apontando o Admin e Gravar desligado.
  const semExt = montarForm({ extensoes: [] }).tela
  digitar(semExt, campoPasta(semExt), '/dados/bi'); digitar(semExt, campoNome(semExt), 'x'); digitar(semExt, editor(semExt), 'a')
  saida.formSemExtensoes = {
    aviso: porAttr(semExt, 'data-aviso').map(n => n.props['data-aviso']),
    gravar: !!porAcao(semExt, 'gravar')[0].props.disabled,
  }
  // Carregar que falhou (null): o editor não muda.
  const { tela: t3 } = montarForm({ onCarregar: async () => null })
  digitar(t3, campoPasta(t3), '/dados/bi'); digitar(t3, campoNome(t3), 'x'); digitar(t3, editor(t3), 'meu texto')
  t3.clicar(porAcao(t3, 'carregar')[0])
  await tick(); await tick(); t3.sincronizar()
  saida.formCarregarFalhou = { conteudo: editor(t3).props.value }
}

// ── 3. modal ───────────────────────────────────────────────────────────────
const PEDIDO = { servidor: 'datastage', diretorio: '/dados/bi/2026/', nome: 'prova', extensao: 'txt',
                 conteudo: 'v2', codificacao: 'utf-8', sobrescrever: false }
const RESULTADO = { caminho: '/dados/bi/2026/prova.txt', tamanho_bytes: 3, sha256: '81db67b6a5702b9b68f0', criado: false,
                    backup: '/dados/bi/2026/prova.txt.bak-20260903072032-797', codificacao: 'utf-8', linhas: 1, duracao_ms: 197 }
function montarModal(props) {
  const chamadas = { fechar: 0, sobrescrever: 0, ver: [] }
  const tela = mini.montar(el(ModalGravacaoArquivo, Object.assign({
    aberto: true, pedido: PEDIDO, estado: 'gravando', resultado: null, erro: null,
    onFechar: () => { chamadas.fechar++ },
    onSobrescrever: () => { chamadas.sobrescrever++ },
    onVerArquivo: (c) => chamadas.ver.push(c),
  }, props)))
  return { tela, chamadas }
}

function modal() {
  const r = {}
  {
    const { tela, chamadas } = montarModal({})
    r.gravando = { caminho: textoDe(porAttr(tela, 'data-caminho')[0]), spinner: porAttr(tela, 'data-gravando').length,
                   sobrescrever: porAcao(tela, 'sobrescrever').length }
    tela.clicar(porAcao(tela, 'fechar')[0])
    r.gravando.fechou = chamadas.fechar
  }
  {
    const { tela, chamadas } = montarModal({ estado: 'existe', erro: { status: 409, mensagem: 'O arquivo já existe. Confirme para gravar por cima.',
      existente: { tamanho_bytes: 27, modificado_em: '2026-09-03 07:06:00' } } })
    r.existe = { mensagem: tela.texto.includes('já existe'), tamanho: tela.texto.includes('27 B'), data: tela.texto.includes('2026-09-03 07:06:00'),
                 fechar: porAcao(tela, 'fechar').length, ver: porAcao(tela, 'ver-arquivo').length }
    tela.clicar(porAcao(tela, 'sobrescrever')[0])
    r.existe.sobrescreveu = chamadas.sobrescrever
    tela.clicar(porAcao(tela, 'cancelar')[0])
    r.existe.cancelou = chamadas.fechar
  }
  {
    const { tela, chamadas } = montarModal({ estado: 'pronto', resultado: RESULTADO })
    r.pronto = { caminho: textoDe(porAttr(tela, 'data-caminho')[0]), resumo: textoDe(porAttr(tela, 'data-resumo')[0]),
                 sobrescrever: porAcao(tela, 'sobrescrever').length }
    tela.clicar(porAcao(tela, 'ver-arquivo')[0])
    r.pronto.ver = chamadas.ver
  }
  {
    const { tela } = montarModal({ estado: 'erro', erro: { status: 413, mensagem: 'Conteúdo de 70,0 KB, acima do teto de 64,0 KB.' } })
    r.erro = { mensagem: tela.texto.includes('acima do teto'), atributo: porAttr(tela, 'data-erro')[0].props['data-erro'],
               sobrescrever: porAcao(tela, 'sobrescrever').length }
  }
  {
    const { tela } = montarModal({ aberto: false })
    r.fechado = porAttr(tela, 'data-estado').length
  }
  saida.modal = r
}

;(async () => {
  try {
    await formulario()
    modal()
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  process.stdout.write(JSON.stringify(saida), () => process.exit(0))
})().catch(e => { console.error(e); process.exit(1) })
