// Bancada do gesto que abre o conteúdo do chamado — `CabecalhoCard` (kanban) e
// `ListaDoBloco` (painel).
//
// ⚠️ POR QUE ISTO RENDERIZA E CLICA, E NÃO LÊ O FONTE
// O que estas telas entregam é uma AFFORDANCE: a promessa, visível sem passar o
// mouse, de que há algo para ver. Procurar `detalhes` no `.tsx` provaria só que
// a palavra foi digitada — não que ela aparece, nem que clicar nela abre coisa
// alguma. Foi assim que um teste desta mesma spec passou VERDE com o defeito de
// pé (`tests/test_kanban_rodape_card.py`).
//
// Saída: um JSON só no stdout.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/chamados/CabecalhoCard.tsx',
  'components/chamados/ListaDoBloco.tsx',
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
module.exports = Object.assign({}, mini.hooks, {
  createElement: mini.criar, Fragment: mini.FRAGMENT,
})
module.exports.default = module.exports
`)
  // ⚠️ `jsx(tipo, props, key)` monta o nó DIRETO, sem passar por `criar`: o
  // `criar` trata os filhos como variádicos e o jsx-runtime já manda `children`
  // DENTRO de props. Chamá-lo aqui punha a `key` no lugar dos filhos e a árvore
  // renderizava vazia — sem erro nenhum.
  const runtime = `
const mini = require(${caminhoMini})
const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key })
module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }
`
  escrever('react', 'jsx-runtime.js', runtime)
  escrever('react', 'jsx-dev-runtime.js', runtime)

  // Os ícones viram `<svg data-icone="FileText">`: a bancada precisa saber QUAL
  // ícone foi desenhado — parte do pedido é que o gesto tenha ícone E palavra.
  escrever('lucide-react', 'package.json',
    '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js', `
module.exports = new Proxy({}, { get: (_, nome) => {
  if (nome === '__esModule') return true
  const Icone = () => ({ __el: true, tipo: 'svg',
    props: { 'data-icone': String(nome) } })
  Object.defineProperty(Icone, 'name', { value: String(nome) })
  return Icone
} })
`)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gesto-'))
preparar(tmp)
shims(tmp)
const { CabecalhoCard } = require(path.join(tmp, 'components/chamados/CabecalhoCard.js'))
const { ListaDoBloco } = require(path.join(tmp, 'components/chamados/ListaDoBloco.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const marcado = (tela, atributo) =>
  tela.achar(n => n.props && n.props[atributo] !== undefined)

// ── 1. o cabeçalho do card do kanban ───────────────────────────────────────
function cabecalho(extra) {
  let aberturas = 0
  const props = Object.assign({
    numero: 'RITM0012345', titulo: 'Ajustar carga da malha',
    url: 'https://cvpsnprod.service-now.com/nav_to.do?uri=sc_req_item.do',
    aoAbrirDetalhe: () => { aberturas++ },
  }, extra)
  const tela = mini.montar(el(CabecalhoCard, props))
  const botao = marcado(tela, 'data-detalhe')[0]
  const titulo = marcado(tela, 'data-titulo')[0]
  const externo = marcado(tela, 'data-servicenow')[0]
  const textoDoBotao = botao
    ? tela.botoes('detalhes').map(n => n.props['data-detalhe'] !== undefined).length
    : 0
  if (botao) tela.clicar(botao)
  const depoisDoBotao = aberturas
  if (titulo) tela.clicar(titulo)
  return {
    texto: tela.texto,
    // O botão existe, mostra a PALAVRA e traz o ícone junto.
    temBotao: !!botao,
    botaoAchadoPeloTexto: textoDoBotao > 0,
    iconeDoBotao: botao
      ? (tela.achar(n => n.tag === 'svg' && n.props['data-icone'] === 'FileText').length > 0)
      : false,
    ajudaDoBotao: botao ? (botao.props.title || '') : '',
    // Clicar abre — no botão E no título (o alvo maior de quem já descobriu).
    abreNoBotao: depoisDoBotao === 1,
    abreNoTitulo: aberturas === 2,
    // O link do ServiceNow continua, e continua sendo um link de verdade.
    temLinkExterno: !!externo,
    linkExterno: externo ? {
      tag: externo.tag, href: externo.props.href,
      target: externo.props.target, rel: externo.props.rel,
      title: externo.props.title || '',
      icone: tela.achar(n => n.tag === 'svg'
        && n.props['data-icone'] === 'ExternalLink').length > 0,
    } : null,
  }
}

// ── 2. a lista do bloco aberto no painel ───────────────────────────────────
function lista(extra) {
  let abertos = []
  const chamado = Object.assign({
    sys_id: 'abc123', numero: 'RITM0099887', titulo: 'Carga Vida diária',
    estado_kanban: 'andamento', atribuido_a: 'Fulano',
    prazo: '2026-09-02 10:00:00', encerrado_em: null,
    atualizado_em: '2026-08-27 18:40:00',
    url: 'https://cvpsnprod.service-now.com/nav_to.do?uri=sc_req_item.do',
  }, extra.chamado || {})
  const tela = mini.montar(el(ListaDoBloco, {
    chamados: [chamado], resolvidos: !!extra.resolvidos,
    aoAbrir: (c) => { abertos.push(c.sys_id) },
  }))
  const numero = tela.botoes(chamado.numero)[0]
  if (numero) tela.clicar(numero)
  const externo = tela.achar(n => n.tag === 'a')[0]
  return {
    texto: tela.texto,
    // O número é BOTÃO (abre aqui), não âncora para outra aba.
    numeroEhBotao: !!numero,
    abre: abertos.join(','),
    // E o ServiceNow continua alcançável, dito por ícone próprio.
    temLinkExterno: !!externo,
    alvoDoLink: externo ? externo.props.target : null,
  }
}

const cenarios = {
  cabecalho: cabecalho({}),
  cabecalho_sem_url: cabecalho({ url: null }),
  cabecalho_sem_titulo: cabecalho({ titulo: null }),
  lista: lista({}),
  lista_resolvidos: lista({
    resolvidos: true,
    chamado: { estado_kanban: 'resolvido' },
  }),
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
