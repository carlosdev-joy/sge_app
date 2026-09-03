// Bancada do navegador de pastas (spec docs/spec-utilitarios-arquivos.md, F6).
//
// ⚠️ POR QUE RENDERIZA
// O aceite da F6 é comportamento: no nível zero a lista é das raízes; clicar
// numa pasta desce; clicar num arquivo devolve pasta + nome; link para fora
// fica inerte; Subir/Backspace seguem o `pai` e nunca sobem acima da raiz;
// "Usar esta pasta" só com uma pasta aberta; o filtro por nome não some com
// a lista. O componente de apresentação roda aqui no React mínimo da casa —
// e os dois formulários também, com um `onListar` falso: Navegar… abre na
// pasta digitada (ou nas raízes), o clique num arquivo preenche os campos, a
// pasta inválida mostra o erro e cai nas raízes.
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

const ENTRADAS = [
  'components/utilitarios/NavegadorPastas.tsx', 'lib/utilitariosNavegador.ts',
  'components/utilitarios/FormVerArquivo.tsx', 'components/utilitarios/FormEditarArquivo.tsx',
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
              puras.descricaoEntrada(E('l', 'link', { alvo: null })), puras.descricaoEntrada(E('l', 'link', { alvo: 'desconhecido' }))],
  erro: [puras.erroListagem({ status: 403, detail: 'Fora dos diretórios liberados.' }), puras.erroListagem({ status: 404 }),
         puras.erroListagem(new TypeError('Failed to fetch'))],
  inicio: [puras.inicioNavegacao('', ['/dados/bi', '/dados/param']), puras.inicioNavegacao('', ['/dados/bi/']),
           puras.inicioNavegacao(' /dados/bi/2026/ ', ['/dados/bi', '/dados/param']), puras.inicioNavegacao('/etc', ['/dados/bi', '/dados/param']),
           puras.inicioNavegacao('/etc', ['/dados/bi']), puras.inicioNavegacao('', [])],
}

// ── 2. o navegador ─────────────────────────────────────────────────────────
const NIVEL_ZERO = { caminho: null, caminho_real: null, raiz: null, pai: null, ocultos_omitidos: 0, truncado: false,
  entradas: [E('/dados/bi', 'raiz'), E('/dados/param', 'raiz')] }
const BI = { caminho: '/dados/bi', caminho_real: '/dados/bi', raiz: '/dados/bi', pai: null, ocultos_omitidos: 1, truncado: false,
  links_nao_resolvidos: 1,
  entradas: [E('2026', 'pasta', { modificado_em: '2026-09-03 00:57:23' }), E('logs', 'pasta'),
             E('consulta.sql', 'arquivo', { tamanho_bytes: 15 }), E('imagem.bin', 'arquivo', { tamanho_bytes: 4102 }),
             E('link_fora', 'link', { alvo: null }), E('atalho.param', 'link', { alvo: 'arquivo', tamanho_bytes: 15 }),
             E('l_desconhecido', 'link', { alvo: 'desconhecido' }), E('RELATORIO.TXT', 'arquivo', { tamanho_bytes: 3 }),
             E('README', 'arquivo', { tamanho_bytes: 2 })] }
// Raiz que é symlink: o caminho lexical é o que se navega; o real só aparece como nota.
const CARGAS = { caminho: '/dados/bi/2026/cargas', caminho_real: '/u01/dados/bi/2026/cargas', raiz: '/dados/bi', pai: '/dados/bi/2026',
  ocultos_omitidos: 0, truncado: true, entradas: [E('carga_utf8.txt', 'arquivo', { tamanho_bytes: 75 })] }

// O filtro é controlado (na página vive no hook useNavegadorPastas, que o zera ao
// abrir); esta caixa faz o papel do hook.
function Caixa({ props }) {
  const [filtro, setFiltro] = mini.hooks.useState('')
  return el(NavegadorPastas, Object.assign({}, props, { filtro, onFiltro: setFiltro }))
}
function montar(props) {
  const chamadas = { navegar: [], ocultos: [], usar: [], arquivo: [], fechar: 0 }
  const tela = mini.montar(el(Caixa, { props: Object.assign({
    aberto: true, listagem: NIVEL_ZERO, carregando: false, erro: null, mostrarOcultos: false,
    onNavegar: (c) => chamadas.navegar.push(c), onMostrarOcultos: (v) => chamadas.ocultos.push(v),
    onUsarPasta: (c) => chamadas.usar.push(c), onEscolherArquivo: (p, n) => chamadas.arquivo.push([p, n]),
    onFechar: () => { chamadas.fechar++ },
  }, props) }))
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
              desconhecidoAtivo: !botaoDaEntrada(tela, 'l_desconhecido').props.disabled,
              subirDesligado: !!porAcao(tela, 'subir')[0].props.disabled,
              rodape: textoDe(porAttr(tela, 'data-rodape')[0]),
              textoConsulta: textoDe(botaoDaEntrada(tela, 'consulta.sql')),
              real: porAttr(tela, 'data-real').length,
              // dentro de um <form>, qualquer botão sem type="button" submeteria o formulário
              todosTypeButton: tela.achar(n => n.tag === 'button').every(b => b.props.type === 'button') }
  tela.clicar(botaoDaEntrada(tela, '2026'))
  tela.clicar(botaoDaEntrada(tela, 'l_desconhecido'))
  tela.clicar(botaoDaEntrada(tela, 'consulta.sql'))
  tela.clicar(botaoDaEntrada(tela, 'atalho.param'))
  tela.clicar(porAcao(tela, 'usar-pasta')[0])
  tela.clicar(porAcao(tela, 'subir')[0])          // na raiz: volta ao nível zero
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Backspace', target: { tagName: 'DIV' } })
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Backspace', target: { tagName: 'INPUT' } })
  // Enter no filtro: prevenido (senão o <form> de fora submeteria)
  let prevenido = 0
  tela.disparar(porAttr(tela, 'data-navegador')[0], 'onKeyDown', { key: 'Enter', target: { tagName: 'INPUT' }, preventDefault: () => { prevenido++ } })
  r.enterNoFiltroPrevenido = prevenido
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
              rodape: textoDe(porAttr(tela, 'data-rodape')[0]),
              real: textoDe(porAttr(tela, 'data-real')[0]) }
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

// ── 3. os formulários com o navegador dentro ───────────────────────────────
// O navegador vive no formulário (hook useNavegadorPastas); a página só passa
// `onListar`. Aqui `onListar` é um fake por caminho — e é assim que se prova
// que o clique numa pasta desce, o clique num arquivo preenche os campos, a
// pasta digitada é o ponto de partida e uma pasta inválida cai nas raízes.
const { FormVerArquivo } = require(path.join(tmp, 'components/utilitarios/FormVerArquivo.js'))
const { FormEditarArquivo } = require(path.join(tmp, 'components/utilitarios/FormEditarArquivo.js'))
const tick = () => new Promise(r => setImmediate(r))
const inputs = (tela) => tela.achar(n => n.tag === 'input')
const digitar = (tela, no, value) => tela.disparar(no, 'onChange', { target: { value } })
const campoPasta = (tela) => inputs(tela).find(n => n.props.placeholder && (n.props.placeholder.endsWith('/…') || n.props.placeholder === '/caminho/da/pasta'))
const campoNome = (tela, placeholder) => inputs(tela).find(n => n.props.placeholder === placeholder)
const porCampo = (tela, campo) => tela.achar(n => n.props && n.props['data-campo'] === campo)[0]
const SERVIDORES = [{ id: 'datastage', label: 'Servidor DataStage', configurado: true }]
const RAIZES = ['/dados/bi', '/dados/param']
const LISTAGENS = { null: NIVEL_ZERO, '/dados/bi': BI, '/dados/bi/2026/cargas': CARGAS }
const listarFake = (registro) => async (servidor, caminho, ocultos) => {
  registro.push([servidor, caminho, ocultos])
  const l = LISTAGENS[caminho === null ? 'null' : caminho]
  if (!l) { const e = new Error('404'); e.status = 404; e.detail = 'Pasta não encontrada.'; throw e }
  return l
}
const esperar = async (tela) => { await tick(); await tick(); await tick(); tela.sincronizar() }
const navegadorAberto = (tela) => porAttr(tela, 'data-navegador').length
const entradas = (tela) => porAttr(tela, 'data-entrada').map(n => n.props['data-entrada'])

async function formularios() {
  // Ver arquivo
  {
    const pedidos = []
    const tela = mini.montar(el(FormVerArquivo, { servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES },
      iniciando: false, onIniciar: () => {}, onListar: listarFake(pedidos) }))
    const r = { botao: porAcao(tela, 'navegar').length, fechadoNoInicio: navegadorAberto(tela) }
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    r.abriuNoZero = { aberto: navegadorAberto(tela), pedidos: pedidos.slice(), entradas: entradas(tela) }
    tela.clicar(botaoDaEntrada(tela, '/dados/bi')); await esperar(tela)
    r.desceu = { entradas: entradas(tela).slice(0, 3), migalhas: porAttr(tela, 'data-migalha').map(n => n.props['data-migalha']) }
    tela.clicar(botaoDaEntrada(tela, 'consulta.sql')); await esperar(tela)
    r.escolheuArquivo = { pasta: campoPasta(tela).props.value, nome: campoNome(tela, 'carga_20260903.txt').props.value,
                          aberto: navegadorAberto(tela) }
    // Pasta digitada válida: o navegador abre nela; "Usar esta pasta" devolve o caminho LEXICAL
    // (a listagem CARGAS tem caminho_real diferente — raiz-symlink — e é o lexical que o ler aceita).
    digitar(tela, campoPasta(tela), '/dados/bi/2026/cargas/')
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    r.abriuNaDigitada = { ultimoPedido: pedidos[pedidos.length - 1], entradas: entradas(tela) }
    // Filtro digitado some ao fechar: reabrir mostra a lista inteira.
    digitar(tela, porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'filtro'), 'zzz')
    r.filtrouTudo = entradas(tela).length
    tela.clicar(porAcao(tela, 'usar-pasta')[0]); await esperar(tela)
    r.usouPasta = { pasta: campoPasta(tela).props.value, aberto: navegadorAberto(tela) }
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    r.reabriuSemFiltro = { entradas: entradas(tela).length, filtro: porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'filtro').props.value }
    tela.clicar(porAcao(tela, 'fechar')[0]); await esperar(tela)
    // Pasta digitada que não existe: erro na tela e a lista cai nas raízes.
    digitar(tela, campoPasta(tela), '/dados/bi/nao_existe')
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    r.pastaInvalida = { pedidos: pedidos.slice(-2), erro: porAttr(tela, 'data-erro').length, entradas: entradas(tela),
                        carregando: porAttr(tela, 'data-carregando').length }
    // Ocultos: no nível zero o interruptor fica desligado; dentro de uma pasta, relista com ele.
    r.ocultosDesligadoNoZero = !!porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'ocultos').props.disabled
    tela.clicar(botaoDaEntrada(tela, '/dados/bi')); await esperar(tela)
    tela.disparar(porAttr(tela, 'data-campo').find(n => n.props['data-campo'] === 'ocultos'), 'onChange', { target: { checked: true } })
    await esperar(tela)
    r.ocultos = pedidos[pedidos.length - 1]
    tela.clicar(porAcao(tela, 'fechar')[0]); await esperar(tela)
    r.fechou = navegadorAberto(tela)
    saida.formVer = r
    // Sem onListar: sem botão.
    const semNav = mini.montar(el(FormVerArquivo, { servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES }, iniciando: false, onIniciar: () => {} }))
    saida.formVerSemListar = porAcao(semNav, 'navegar').length
    // Sem raiz: botão desligado.
    const semRaiz = mini.montar(el(FormVerArquivo, { servidores: SERVIDORES, raizesPorServidor: {}, iniciando: false, onIniciar: () => {}, onListar: listarFake([]) }))
    saida.formVerSemRaiz = !!porAcao(semRaiz, 'navegar')[0].props.disabled
  }
  // Criar/editar arquivo
  {
    const pedidos = []
    const tela = mini.montar(el(FormEditarArquivo, { servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES },
      extensoes: ['txt', 'sql', 'param'], podeGravar: true, gravando: false, carregando: false, sujo: false, onSujo: () => {},
      onCarregar: async () => null, onGravar: () => {}, onListar: listarFake(pedidos) }))
    const r = { botao: porAcao(tela, 'navegar').length }
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    tela.clicar(botaoDaEntrada(tela, '/dados/bi')); await esperar(tela)
    tela.clicar(botaoDaEntrada(tela, 'consulta.sql')); await esperar(tela)
    r.sql = { pasta: campoPasta(tela).props.value, nome: campoNome(tela, 'parametros_carga').props.value,
              extensao: porCampo(tela, 'extensao').props.value, aberto: navegadorAberto(tela),
              gravar: !!porAcao(tela, 'gravar')[0].props.disabled, carregar: !!porAcao(tela, 'carregar')[0].props.disabled }
    // Extensão fora da lista (imagem.bin): nome e extensão separados, Gravar desligado com o aviso.
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    tela.clicar(botaoDaEntrada(tela, 'imagem.bin')); await esperar(tela)
    r.bin = { nome: campoNome(tela, 'parametros_carga').props.value, extensao: porCampo(tela, 'extensao').props.value,
              gravar: !!porAcao(tela, 'gravar')[0].props.disabled, aviso: tela.texto.includes('Extensão não liberada') }
    r.abriuNaPastaDoCampo = pedidos[pedidos.length - 1]
    // Nome que o editor não representa (RELATORIO.TXT em maiúscula, README sem extensão):
    // não deforma o nome — preenche só a pasta e avisa.
    const avisoEscolha = () => porAttr(tela, 'data-aviso').filter(n => n.props['data-aviso'] === 'arquivo-escolhido').length
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    tela.clicar(botaoDaEntrada(tela, 'RELATORIO.TXT')); await esperar(tela)
    r.maiuscula = { nome: campoNome(tela, 'parametros_carga').props.value, aviso: avisoEscolha(), cita: tela.texto.includes('"RELATORIO.TXT"') }
    tela.clicar(porAcao(tela, 'navegar')[0]); await esperar(tela)
    tela.clicar(botaoDaEntrada(tela, 'README')); await esperar(tela)
    r.semExtensao = { nome: campoNome(tela, 'parametros_carga').props.value, aviso: avisoEscolha() }
    digitar(tela, campoNome(tela, 'parametros_carga'), 'outro')
    r.avisoSomeAoDigitar = avisoEscolha()
    saida.formEditar = r
    // Operador (não grava): Navegar… desligado junto com o resto.
    const op = mini.montar(el(FormEditarArquivo, { servidores: SERVIDORES, raizesPorServidor: { datastage: RAIZES },
      extensoes: ['txt'], podeGravar: false, gravando: false, carregando: false, sujo: false, onSujo: () => {},
      onCarregar: async () => null, onGravar: () => {}, onListar: listarFake([]) }))
    saida.formEditarOperador = !!porAcao(op, 'navegar')[0].props.disabled
  }
}

;(async () => {
  try {
    await formularios()
  } catch (e) {
    fs.rmSync(tmp, { recursive: true, force: true })
    console.error(e && e.stack || e)
    process.exit(1)
  }
  fs.rmSync(tmp, { recursive: true, force: true })
  process.stdout.write(JSON.stringify(saida), () => process.exit(0))
})()
