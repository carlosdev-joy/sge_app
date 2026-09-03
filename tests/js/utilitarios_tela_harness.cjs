// Bancada da tela Utilitários › Ver arquivo (spec docs/spec-utilitarios-arquivos.md, F3).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F3 é comportamento: o Iniciar só liga com pasta abaixo de uma
// raiz e nome válido; o campo diz "abaixo de /dados/bi" ou "fora dos
// diretórios" ANTES de chamar a API; o modal abre em "buscando", vira
// conteúdo com o rodapé, e o Copiar diz o que aconteceu (copiado / use
// Ctrl+C); o 413 oferece "últimas N linhas" sem fechar o modal. Nada disso
// se prova lendo o `.tsx`. Os dois componentes de apresentação rodam aqui no
// React mínimo da casa (minireact.cjs), byte a byte como estão no `src/`.
//
// A página (container com react-query) fica de fora: é rede; a prova dela é
// tsc + build + a tela no DEV.
//
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_tela_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/utilitarios/FormVerArquivo.tsx',
  'components/utilitarios/ModalConteudoArquivo.tsx',
  'lib/utilitariosArquivo.ts',
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

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-tela-'))
preparar(tmp)
shims(tmp)
const { FormVerArquivo } = require(path.join(tmp, 'components/utilitarios/FormVerArquivo.js'))
const { ModalConteudoArquivo } = require(path.join(tmp, 'components/utilitarios/ModalConteudoArquivo.js'))
const puras = require(path.join(tmp, 'lib/utilitariosArquivo.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no
  : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const inputs = (tela) => tela.achar(n => n.tag === 'input')
const digitar = (tela, input, value) => tela.disparar(input, 'onChange', { target: { value } })
const tick = () => new Promise(r => setImmediate(r))

// ⚠️ `globalThis.navigator` é um GETTER sem setter no Node 22 (ver
// tabela_copiar_harness.cjs): definir por propriedade, não por atribuição.
function porNavigator(valor) {
  Object.defineProperty(globalThis, 'navigator', { value: valor, configurable: true, writable: true })
}

const saida = {}

// ── 1. funções puras ───────────────────────────────────────────────────────
const RAIZES = ['/dados/bi', '/dados/param']
saida.puras = {
  raizDe: {
    dentro: puras.raizDe('/dados/bi/2026/x.txt', RAIZES),
    igual: puras.raizDe('/dados/param', RAIZES),
    prefixoEnganoso: puras.raizDe('/dados/bi2/x', RAIZES),
    fora: puras.raizDe('/etc/passwd', RAIZES),
    raizBarra: puras.raizDe('/etc/passwd', ['/']),
  },
  avisoPasta: {
    vazio: puras.avisoPasta('', RAIZES),
    relativa: puras.avisoPasta('dados/bi', RAIZES),
    fora: puras.avisoPasta('/etc', RAIZES),
    traversal: puras.avisoPasta('/dados/bi/../../etc', RAIZES),
    dentro: puras.avisoPasta('/dados/bi//2026/', RAIZES),
    semRaizes: puras.avisoPasta('/dados/bi', []),
    longa: puras.avisoPasta('/' + 'a'.repeat(1001), RAIZES),
  },
  avisoNome: {
    vazio: puras.avisoNome(''), barra: puras.avisoNome('a/b'), ponto: puras.avisoNome('..'),
    longo: puras.avisoNome('ç'.repeat(128)), ok: puras.avisoNome('carga.txt'),
  },
  ultimasLinhas: {
    vazio: puras.ultimasLinhas(''), ok: puras.ultimasLinhas(' 200 '), zero: puras.ultimasLinhas('0'),
    acima: puras.ultimasLinhas('100001'), texto: puras.ultimasLinhas('abc'), decimal: puras.ultimasLinhas('1.5'),
  },
  pedidoPronto: {
    ok: puras.pedidoPronto('/dados/bi', 'x.txt', '', RAIZES),
    semNome: puras.pedidoPronto('/dados/bi', '', '', RAIZES),
    fora: puras.pedidoPronto('/etc', 'passwd', '', RAIZES),
    nomeRuim: puras.pedidoPronto('/dados/bi', 'a/b', '', RAIZES),
    ultimasRuim: puras.pedidoPronto('/dados/bi', 'x', 'abc', RAIZES),
  },
  formatarTamanho: [puras.formatarTamanho(512), puras.formatarTamanho(1536), puras.formatarTamanho(5040000)],
  erroLeitura: {
    detail: puras.erroLeitura({ status: 403, message: 'Fora dos diretórios liberados.', detail: 'Fora dos diretórios liberados.' }),
    lista: puras.erroLeitura({ status: 422, message: '422 Unprocessable', detail: [{ msg: "'ultimas_linhas' precisa ser um inteiro." }] }),
    semDetail413: puras.erroLeitura({ status: 413, message: '413 Payload Too Large' }),
    nginx502: puras.erroLeitura({ status: 502, message: '502 Bad Gateway' }),
    apiSsh502: puras.erroLeitura({ status: 502, message: 'Falha ao conectar ao servidor por SSH — detalhe registrado no log da API.',
      detail: 'Falha ao conectar ao servidor por SSH — detalhe registrado no log da API.' }),
    rede: puras.erroLeitura(new TypeError('Failed to fetch')),
    nada: puras.erroLeitura(null),
  },
  resumo: puras.resumoConteudo({ caminho: '/x', tamanho_bytes: 1536, linhas: 1, codificacao: 'latin-1',
    truncado: true, modificado_em: '2026-09-03 10:00:00', conteudo: 'a', duracao_ms: 1234 }),
}

// ── 2. formulário ──────────────────────────────────────────────────────────
const SERVIDORES = [{ id: 'datastage', label: 'Servidor DataStage', configurado: true }]
function montarForm(props) {
  const pedidos = []
  const tela = mini.montar(el(FormVerArquivo, Object.assign({
    servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES }, iniciando: false,
    onIniciar: (p) => pedidos.push(p),
  }, props)))
  return { tela, pedidos }
}
// Com raiz o placeholder é "<raiz>/…"; sem raiz é o genérico.
const campoPasta = (tela) => inputs(tela).find(n => n.props.placeholder
  && (n.props.placeholder.endsWith('/…') || n.props.placeholder === '/caminho/da/pasta'))
const campoNome = (tela) => inputs(tela).find(n => n.props.placeholder === 'carga_20260903.txt')
const campoUltimas = (tela) => inputs(tela).find(n => n.props.inputMode === 'numeric')
const formVer = (tela) => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'ver-arquivo')

{
  const { tela, pedidos } = montarForm({})
  const botao = () => porAcao(tela, 'iniciar')[0]
  const r = { desligadoNoInicio: !!botao().props.disabled, placeholderPasta: campoPasta(tela).props.placeholder }
  digitar(tela, campoPasta(tela), 'dados/bi')
  r.relativa = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('caminho absoluto') }
  digitar(tela, campoPasta(tela), '/etc')
  r.fora = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('Fora dos diretórios liberados') }
  digitar(tela, campoPasta(tela), '/dados/bi/2026')
  r.dentro = { raizDe: porAttr(tela, 'data-raiz-de').map(textoDe), desligadoSemNome: !!botao().props.disabled }
  digitar(tela, campoNome(tela), 'a/b')
  r.nomeRuim = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('Sem barra') }
  digitar(tela, campoNome(tela), ' carga.txt ')
  r.valido = { desligado: !!botao().props.disabled }
  digitar(tela, campoUltimas(tela), 'abc')
  r.ultimasRuim = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('Inteiro entre 1 e 100000') }
  digitar(tela, campoUltimas(tela), '200')
  tela.disparar(formVer(tela), 'onSubmit', {})
  digitar(tela, campoUltimas(tela), '')
  tela.disparar(formVer(tela), 'onSubmit', {})
  r.pedidos = pedidos
  // Sem raiz: tudo fora, com o aviso apontando o Admin.
  const semRaiz = montarForm({ raizesPorServidor: {} }).tela
  digitar(semRaiz, campoPasta(semRaiz), '/dados/bi')
  r.semRaiz = { desligado: !!porAcao(semRaiz, 'iniciar')[0].props.disabled,
                aviso: semRaiz.texto.includes('Nenhum diretório liberado'),
                placeholder: campoPasta(semRaiz).props.placeholder }
  // Iniciando: desligado mesmo com pedido válido.
  const ocupado = montarForm({ iniciando: true }).tela
  digitar(ocupado, campoPasta(ocupado), '/dados/bi'); digitar(ocupado, campoNome(ocupado), 'x.txt')
  r.ocupado = !!porAcao(ocupado, 'iniciar')[0].props.disabled
  saida.form = r
}

// ── 3. modal ───────────────────────────────────────────────────────────────
const PEDIDO = { servidor: 'datastage', diretorio: '/dados/bi/', nome: 'consulta.sql' }
const RESULTADO = {
  caminho: '/dados/bi/consulta.sql', tamanho_bytes: 15, linhas: 1, codificacao: 'utf-8',
  truncado: false, modificado_em: '2026-09-03 00:57:23', conteudo: 'SELECT 1 AS x;\n', duracao_ms: 166,
}
function montarModal(props) {
  const chamadas = { fechar: 0, retentar: [] }
  const tela = mini.montar(el(ModalConteudoArquivo, Object.assign({
    aberto: true, pedido: PEDIDO, estado: 'buscando', resultado: null, erro: null,
    onFechar: () => { chamadas.fechar++ },
    onRetentar: (n) => chamadas.retentar.push(n),
  }, props)))
  return { tela, chamadas }
}

async function modal() {
  const r = {}
  {
    const { tela, chamadas } = montarModal({})
    r.buscando = {
      estado: porAttr(tela, 'data-estado')[0].props['data-estado'],
      caminho: textoDe(porAttr(tela, 'data-caminho')[0]),
      spinner: porAttr(tela, 'data-buscando').length,
      conteudo: porAttr(tela, 'data-conteudo').length,
    }
    tela.clicar(porAcao(tela, 'fechar')[0])
    r.buscando.fechou = chamadas.fechar
  }
  {
    const { tela } = montarModal({ estado: 'pronto', resultado: RESULTADO })
    r.pronto = {
      caminhoReal: textoDe(porAttr(tela, 'data-caminho')[0]),
      texto: textoDe(porAttr(tela, 'data-texto')[0]),
      resumo: porAttr(tela, 'data-resumo').map(textoDe)[0],
      truncadoBadge: tela.texto.includes('truncado'),
      spinner: porAttr(tela, 'data-buscando').length,
    }
    // Copiar com clipboard disponível → "copiado" e o ícone de confirmação.
    const escritos = []
    porNavigator({ clipboard: { writeText: async (t) => { escritos.push(t) } } })
    tela.clicar(porAcao(tela, 'copiar')[0])
    await tick(); await tick(); tela.sincronizar()
    r.copiarOk = {
      escritos, aviso: porAttr(tela, 'data-aviso').map(textoDe),
      check: tela.achar(n => n.props && n.props['data-icone'] === 'Check').length,
    }
  }
  {
    // Sem clipboard e sem document (o Node): cai no legado, que não existe → "use Ctrl+C".
    const { tela } = montarModal({ estado: 'pronto', resultado: RESULTADO })
    porNavigator(undefined)
    tela.clicar(porAcao(tela, 'copiar')[0])
    await tick(); await tick(); tela.sincronizar()
    r.copiarSemApi = { aviso: porAttr(tela, 'data-aviso').map(textoDe) }
  }
  {
    const { tela } = montarModal({ estado: 'pronto', resultado: Object.assign({}, RESULTADO, { truncado: true, conteudo: '' }) })
    r.truncadoVazio = { badge: tela.texto.includes('truncado'), vazio: tela.texto.includes('(arquivo vazio)'),
                        copiarDesligado: !!porAcao(tela, 'copiar')[0].props.disabled }
  }
  {
    // 413: mensagem + formulário "últimas N linhas" com 200 por padrão.
    const { tela, chamadas } = montarModal({ estado: 'erro',
      erro: { status: 413, mensagem: 'Arquivo de 4,8 MB, acima do teto de 64,0 KB. Use \'últimas N linhas\' para ver o fim dele.' } })
    const form = () => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'ultimas-linhas')
    const campo = () => inputs(tela).find(n => n.props.inputMode === 'numeric')
    r.erro413 = {
      mensagem: tela.texto.includes('acima do teto'), form: !!form(), valorInicial: campo().props.value,
      botaoLigado: !porAcao(tela, 'ver-fim')[0].props.disabled,
    }
    tela.disparar(form(), 'onSubmit', {})
    digitar(tela, campo(), 'abc')
    r.erro413.invalido = !!porAcao(tela, 'ver-fim')[0].props.disabled
    tela.disparar(form(), 'onSubmit', {})
    r.erro413.retentar = chamadas.retentar
  }
  {
    // 403: só a mensagem, sem o formulário.
    const { tela } = montarModal({ estado: 'erro', erro: { status: 403, mensagem: 'Fora dos diretórios liberados.' } })
    r.erro403 = { mensagem: tela.texto.includes('Fora dos diretórios'), form: porAttr(tela, 'data-form').length,
                  atributo: porAttr(tela, 'data-erro')[0].props['data-erro'] }
  }
  {
    const { tela } = montarModal({ aberto: false })
    r.fechado = { nos: porAttr(tela, 'data-estado').length }
  }
  saida.modal = r
}

;(async () => {
  try {
    await modal()
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  // ⚠️ Sai EXPLICITAMENTE: o aviso "copiado" some por `setTimeout` de 2,5 s, e
  // esse timer dispararia depois que a bancada descartou a árvore (o setState
  // de um componente já "desmontado" não existe no minireact) — o Node ficaria
  // vivo esperando o timer e morreria com exit 1 depois do JSON já escrito.
  process.stdout.write(JSON.stringify(saida), () => process.exit(0))
})().catch(e => { console.error(e); process.exit(1) })
