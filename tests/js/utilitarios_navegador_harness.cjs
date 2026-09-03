// Bancada do navegador de pastas (spec docs/spec-utilitarios-arquivos.md, F6).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F6 é comportamento: no nível zero a lista é das raízes; clicar
// numa pasta desce; clicar num arquivo devolve pasta + nome; link para fora
// fica inerte; Subir/Backspace seguem o `pai` e nunca sobem acima da raiz;
// "Usar esta pasta" só com uma pasta aberta; o filtro por nome não some com
// a lista. O componente de apresentação roda aqui no React mínimo da casa.
//
// A página (container com react-query) fica de fora: tsc + build + DEV.
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_navegador_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = ['components/utilitarios/NavegadorPastas.tsx', 'lib/utilitariosNavegador.ts']

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

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-navegador-'))
preparar(tmp)
shims(tmp)
const { NavegadorPastas } = require(path.join(tmp, 'components/utilitarios/NavegadorPastas.js'))
const puras = require(path.join(tmp, 'lib/utilitariosNavegador.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const botaoDaEntrada = (tela, nome) => {
  const li = porAttr(tela, 'data-entrada').find(n => n.props['data-entrada'] === nome)
  return li && li.filhos.find(f => f.tag === 'button')
}

const saida = {}

// ── 1. puras ───────────────────────────────────────────────────────────────
const E = (nome, tipo, extra = {}) => Object.assign({ nome, tipo, tamanho_bytes: null, modificado_em: null }, extra)
saida.puras = {
  podeDescer: [puras.podeDescer(E('/dados/bi', 'raiz')), puras.podeDescer(E('x', 'pasta')),
               puras.podeDescer(E('l', 'link', { alvo: 'pasta' })), puras.podeDescer(E('l', 'link', { alvo: null })),
               puras.podeDescer(E('a', 'arquivo'))],
  ehArquivo: [puras.ehArquivo(E('a', 'arquivo')), puras.ehArquivo(E('l', 'link', { alvo: 'arquivo' })),
              puras.ehArquivo(E('x', 'pasta')), puras.ehArquivo(E('l', 'link', { alvo: null }))],
  caminho: [puras.caminhoDaEntrada(null, E('/dados/bi', 'raiz')), puras.caminhoDaEntrada('/dados/bi/', E('2026', 'pasta')),
            puras.caminhoDaEntrada('/dados/bi', E('x.txt', 'arquivo'))],
  migalhas: [puras.migalhas(null, null), puras.migalhas('/dados/bi', '/dados/bi'),
             puras.migalhas('/dados/bi/2026/cargas', '/dados/bi'), puras.migalhas('/u01/dados/x', '/dados')],
  descricao: [puras.descricaoEntrada(E('r', 'raiz')), puras.descricaoEntrada(E('p', 'pasta')),
              puras.descricaoEntrada(E('a', 'arquivo', { tamanho_bytes: 1536 })),
              puras.descricaoEntrada(E('l', 'link', { alvo: 'pasta' })), puras.descricaoEntrada(E('l', 'link', { alvo: 'arquivo', tamanho_bytes: 15 })),
              puras.descricaoEntrada(E('l', 'link', { alvo: null }))],
  erro: [puras.erroListagem({ status: 403, detail: 'Fora dos diretórios liberados.' }), puras.erroListagem({ status: 404 }),
         puras.erroListagem(new TypeError('Failed to fetch'))],
}

// ── 2. o navegador ─────────────────────────────────────────────────────────
const NIVEL_ZERO = { caminho_real: null, raiz: null, pai: null, ocultos_omitidos: 0, truncado: false,
  entradas: [E('/dados/bi', 'raiz'), E('/dados/param', 'raiz')] }
const BI = { caminho_real: '/dados/bi', raiz: '/dados/bi', pai: null, ocultos_omitidos: 1, truncado: false,
  entradas: [E('2026', 'pasta', { modificado_em: '2026-09-03 00:57:23' }), E('logs', 'pasta'),
             E('consulta.sql', 'arquivo', { tamanho_bytes: 15 }), E('imagem.bin', 'arquivo', { tamanho_bytes: 4102 }),
             E('link_fora', 'link', { alvo: null }), E('atalho.param', 'link', { alvo: 'arquivo', tamanho_bytes: 15 })] }
const CARGAS = { caminho_real: '/dados/bi/2026/cargas', raiz: '/dados/bi', pai: '/dados/bi/2026', ocultos_omitidos: 0, truncado: true,
  entradas: [E('carga_utf8.txt', 'arquivo', { tamanho_bytes: 75 })] }

function montar(props) {
  const chamadas = { navegar: [], ocultos: [], usar: [], arquivo: [], fechar: 0 }
  const tela = mini.montar(el(NavegadorPastas, Object.assign({
    aberto: true, listagem: NIVEL_ZERO, carregando: false, erro: null, mostrarOcultos: false,
    onNavegar: (c) => chamadas.navegar.push(c), onMostrarOcultos: (v) => chamadas.ocultos.push(v),
    onUsarPasta: (c) => chamadas.usar.push(c), onEscolherArquivo: (p, n) => chamadas.arquivo.push([p, n]),
    onFechar: () => { chamadas.fechar++ },
  }, props)))
  return { tela, chamadas }
}

{
  const { tela, chamadas } = montar({})
  const r = { entradas: porAttr(tela, 'data-entrada').map(n => n.props['data-entrada']),
              subirDesligado: !!porAcao(tela, 'subir')[0].props.disabled,
              usarDesligado: !!porAcao(tela, 'usar-pasta')[0].props.disabled,
              migalhas: porAttr(tela, 'data-migalha').map(n => n.props['data-migalha']) }
  tela.clicar(botaoDaEntrada(tela, '/dados/bi'))
  r.navegou = chamadas.navegar.slice()
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Backspace', target: { tagName: 'DIV' } })
  r.backspaceNoZero = chamadas.navegar.slice()
  saida.nivelZero = r
}
{
  const { tela, chamadas } = montar({ listagem: BI })
  const r = { migalhas: porAttr(tela, 'data-migalha').map(n => n.props['data-migalha']),
              entradas: porAttr(tela, 'data-entrada').map(n => [n.props['data-entrada'], n.props['data-tipo'], n.props['data-alvo'] ?? null]),
              linkForaInerte: !!botaoDaEntrada(tela, 'link_fora').props.disabled,
              atalhoAtivo: !botaoDaEntrada(tela, 'atalho.param').props.disabled,
              subirDesligado: !!porAcao(tela, 'subir')[0].props.disabled,
              rodape: textoDe(porAttr(tela, 'data-rodape')[0]),
              textoConsulta: textoDe(botaoDaEntrada(tela, 'consulta.sql')) }
  tela.clicar(botaoDaEntrada(tela, '2026'))
  tela.clicar(botaoDaEntrada(tela, 'consulta.sql'))
  tela.clicar(botaoDaEntrada(tela, 'atalho.param'))
  tela.clicar(porAcao(tela, 'usar-pasta')[0])
  tela.clicar(porAcao(tela, 'subir')[0])          // na raiz: volta ao nível zero
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Backspace', target: { tagName: 'DIV' } })
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Backspace', target: { tagName: 'INPUT' } })
  tela.disparar(porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'ocultos'), 'onChange', { target: { checked: true } })
  tela.clicar(porAttr(tela, 'data-migalha').find(n => n.props['data-migalha'] === 'raizes'))
  r.chamadas = chamadas
  // filtro por nome
  tela.disparar(porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'filtro'), 'onChange', { target: { value: 'CONS' } })
  r.filtrado = porAttr(tela, 'data-entrada').map(n => n.props['data-entrada'])
  tela.disparar(porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'filtro'), 'onChange', { target: { value: 'zzz' } })
  r.filtroVazio = porAttr(tela, 'data-vazio').length
  saida.raiz = r
}
{
  const { tela, chamadas } = montar({ listagem: CARGAS })
  const r = { migalhas: porAttr(tela, 'data-migalha').map(n => n.props['data-migalha']),
              rodape: textoDe(porAttr(tela, 'data-rodape')[0]) }
  tela.clicar(porAcao(tela, 'subir')[0])
  tela.clicar(porAttr(tela, 'data-migalha').find(n => n.props['data-migalha'] === '/dados/bi'))
  r.navegou = chamadas.navegar.slice()
  saida.fundo = r
}
{
  const { tela } = montar({ listagem: BI, carregando: true })
  saida.carregando = { spinner: porAttr(tela, 'data-carregando').length, entradas: porAttr(tela, 'data-entrada').length }
  const { tela: t2 } = montar({ listagem: NIVEL_ZERO, erro: 'Fora dos diretórios liberados.' })
  saida.erro = { caixa: porAttr(t2, 'data-erro').length, texto: t2.texto.includes('Fora dos diretórios') }
  const { tela: t3 } = montar({ aberto: false })
  saida.fechado = porAttr(t3, 'data-navegador').length
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(saida), () => process.exit(0))
