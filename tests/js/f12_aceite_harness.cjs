// Bancada de ACEITE da F12 — `docs/spec-malha-execucao.md` §10/### F12.
//
// ── O que ela faz que as outras duas bancadas da fase não fazem ─────────────
// `f12_tipicos_harness.cjs` e `f12_historico_harness.cjs` executam os módulos
// e chamam os componentes com objetos ESCRITOS À MÃO. São necessárias e não
// bastam, por duas razões que esta spec já pagou com defeito:
//
//   1. **dublê que fabrica dado que o servidor real nunca produz** (o modo de
//      falso verde da F8). Um `{ tipicos: { completo: true, itens: [...] } }`
//      escrito no teste casa com o componente porque a mesma pessoa escreveu
//      os dois. Aqui NADA é escrito à mão: cada cenário chega pronto de
//      `GET /malhas/{m}`, `GET /malhas/{m}/execucao` e
//      `GET /malhas/{m}/corridas`, serializados pelo pytest a partir do router
//      de verdade. Se o servidor renomear `p50_seg`, parar de mandar
//      `completo` ou publicar `historico` com outra forma, o texto muda AQUI;
//   2. **a FIAÇÃO.** O percentual da Decisão 56b, os `tipicos[]` da Decisão 64
//      e o `historico` da Decisão 68 são calculados/lidos no `MalhaEditor` e
//      DESCEM por prop. Uma bancada que chame `CabecalhoCorrida` já com
//      `percentualTempo` pronto prova o componente e não prova a tela: apagar
//      `percentualTempo={percentualTempo}` do editor deixaria a faixa muda com
//      a suíte verde. Por isso o que se renderiza aqui é o **`MalhaEditor`
//      inteiro**, byte a byte como está no `src/`, e o percentual aparece (ou
//      não) porque o editor o passou (ou não).
//
// ── O que é DUBLADO, e por quê (a lista é curta de propósito) ──────────────
//   • `@tanstack/react-query` — devolve o payload do cenário como resposta
//     pronta, indexado pela PRIMEIRA chave da `queryKey`. Nenhuma rede;
//   • `@xyflow/react` — o canvas. Nada do aceite desta fase mora nele (§9.15/11
//     proíbe explicitamente badge no nó), e um motor de grafo no Node seria a
//     bancada testando o React Flow;
//   • `lib/api`, `store/auth`, `ui/Toast` — rede, sessão e notificação;
//   • `lucide-react` — cada ícone vira o próprio nome, e é assim que se prova
//     que dois estados não compartilham ícone (cor nunca é canal único).
//
// Tudo o mais é código de produção: `MalhaEditor`, `CabecalhoCorrida`,
// `PainelCorridaLateral`, `SeletorCorrida`, `CorridaProgresso`, `ui/Progress`,
// `ui/Banner`, `statusExecucao`, `duracaoTipica`, `historicoCorridas`,
// `tempoCorrida`.
//
// ⚠️ O RELÓGIO. `Date.now` é fixado no relógio LOCAL do cenário e o payload
// carrega os carimbos do BANCO, que o dublê do pytest põe 3h à frente (o desvio
// MEDIDO no dev). Nenhum número desta bancada pode sair de subtrair um do
// outro — Decisão 60, e é o que faz `há 12 min` ser 12 e não −2h48.
//
// Uso:  node f12_aceite_harness.cjs <arquivo.json>
// Entrada: { "<cenário>": { "malha": …, "malha-execucao": …,
//                           "malha-corridas": …, agora_ms, corrida, aba? } }
// Saída (stdout): um JSON só, consumido por `tests/test_malhas_f12_aceite.py`.
'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADA = 'components/malhas/MalhaEditor.tsx'

// Fronteiras: os módulos relativos que NÃO são transpilados, porque o que há
// atrás deles é rede, sessão ou notificação. Cada um é um pedaço da tela que
// deixa de ser provado, e é por isso que a lista tem três nomes.
const FRONTEIRAS = {
  'lib/api': 'exports.apiFetch = async () => { throw new Error('
    + '"apiFetch chamado na bancada — nao ha rede aqui") }\n'
    + 'exports.API_BASE = ""\n',
  'store/auth': `
// Operador de plantão: é o perfil de quem abre esta tela às 3h, e é o que
// mantém os gestos na tela (um perfil de consulta esconderia botões e o
// cenário mediria a permissão em vez do aceite).
const ESTADO = {
  user: { matricula: 'OPER1', perfil: 'operador',
          permissoes: ['editar_pipeline', 'executar_pipeline', 'tela_malha'] },
  token: 'bancada',
  temPermissao: () => true,
  isAdmin: () => false,
}
exports.useAuthStore = (sel) => (typeof sel === 'function' ? sel(ESTADO) : ESTADO)
`,
  'components/ui/Toast': `
const registro = []
exports.toast = {
  success: (m) => registro.push(['success', m]),
  error: (m) => registro.push(['error', m]),
  info: (m) => registro.push(['info', m]),
  sucesso: (m) => registro.push(['success', m]),
  erro: (m) => registro.push(['error', m]),
}
exports.ToastHost = () => null
exports.__registro = registro
`,
}

// ── transpilação com fecho transitivo pelos imports RELATIVOS ───────────────

function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const tentativa of [base + '.tsx', base + '.ts',
                           path.join(base, 'index.tsx'),
                           path.join(base, 'index.ts')]) {
    if (fs.existsSync(tentativa)) return tentativa
  }
  return null
}

function preparar(destino) {
  const feitos = new Set()
  const icones = new Set()
  const fila = [path.join(SRC, ENTRADA)]
  while (fila.length) {
    const arquivo = fila.pop()
    if (feitos.has(arquivo)) continue
    feitos.add(arquivo)
    const rel = path.relative(SRC, arquivo).replace(/\.tsx?$/, '')
    const alvo = path.join(destino, rel + '.js')
    fs.mkdirSync(path.dirname(alvo), { recursive: true })
    if (FRONTEIRAS[rel] !== undefined) {
      fs.writeFileSync(alvo, FRONTEIRAS[rel])
      continue
    }
    const fonte = fs.readFileSync(arquivo, 'utf8')
    fs.writeFileSync(alvo, transform(fonte, {
      transforms: ['typescript', 'jsx', 'imports'],
      jsxRuntime: 'automatic', production: true, filePath: arquivo,
    }).code)
    for (const m of fonte.matchAll(
      /import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/g)) {
      for (const nome of m[1].split(',')) {
        const limpo = nome.trim()
        if (limpo) icones.add(limpo)
      }
    }
    for (const m of fonte.matchAll(/from\s*['"](\.[^'"]+)['"]/g)) {
      const destinoRel = resolverRelativo(path.dirname(arquivo), m[1])
      if (destinoRel) fila.push(destinoRel)
    }
  }
  return icones
}

function shims(destino, icones) {
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
  // \`memo\`/\`forwardRef\` são identidade: a bancada renderiza uma vez por
  // cenário, e memoizar mudaria o que se mede sem mudar o que a tela mostra.
  memo: (f) => f, forwardRef: (f) => f,
  createContext: (v) => ({ __ctx: true, valor: v, Provider: (p) => p.children }),
  useContext: (c) => c.valor,
  useId: () => ':bancada:',
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
  escrever('lucide-react', 'package.json',
           '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js',
    [...icones].map(n =>
      `exports.${n} = function ${n}(p){ return { __el: true, tipo: 'svg', `
      + `props: Object.assign({ 'data-icone': ${JSON.stringify(n)} }, p) } }`
    ).join('\n') + '\n')

  // O canvas. Nada do aceite da F12 mora nele — a Decisão 75/11 proíbe badge
  // no nó e texto no Fim de propósito, "o número já está na faixa a 3 cm".
  escrever('@xyflow/react', 'package.json',
           '{"name":"@xyflow/react","main":"index.js"}')
  escrever('@xyflow/react', 'index.js', `
const mini = require(${caminhoMini})
const caixa = (nome) => function (p) {
  return { __el: true, tipo: 'div',
           props: Object.assign({ 'data-xy': nome }, p) }
}
exports.ReactFlow = caixa('ReactFlow')
exports.ReactFlowProvider = caixa('ReactFlowProvider')
exports.Background = caixa('Background')
exports.Controls = caixa('Controls')
exports.MiniMap = caixa('MiniMap')
exports.Panel = caixa('Panel')
exports.Handle = caixa('Handle')
exports.BaseEdge = caixa('BaseEdge')
exports.EdgeLabelRenderer = caixa('EdgeLabelRenderer')
exports.Position = { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' }
exports.MarkerType = { ArrowClosed: 'arrowclosed', Arrow: 'arrow' }
exports.useReactFlow = () => ({
  fitView() {}, setCenter() {}, getNodes: () => [], getEdges: () => [],
  getNode: () => undefined, screenToFlowPosition: (p) => p,
  getViewport: () => ({ x: 0, y: 0, zoom: 1 }),
})
exports.useNodesInitialized = () => true
exports.useNodesState = (inicial) => {
  const [v, set] = mini.hooks.useState(inicial)
  return [v, set, () => {}]
}
exports.useEdgesState = (inicial) => {
  const [v, set] = mini.hooks.useState(inicial)
  return [v, set, () => {}]
}
exports.applyNodeChanges = (_m, nos) => nos
exports.applyEdgeChanges = (_m, arestas) => arestas
exports.addEdge = (_c, arestas) => arestas
exports.getBezierPath = () => ['', 0, 0]
exports.useStore = () => undefined
`)
  fs.mkdirSync(path.join(nm, '@xyflow', 'react', 'dist'), { recursive: true })
  fs.writeFileSync(path.join(nm, '@xyflow', 'react', 'dist', 'style.css'),
                   'module.exports = {}\n')

  escrever('@tanstack/react-query', 'package.json',
           '{"name":"@tanstack/react-query","main":"index.js"}')
  escrever('@tanstack/react-query', 'index.js', `
// A resposta do cenário, indexada pela PRIMEIRA chave da \`queryKey\` — que é
// o nome do endpoint. \`enabled: false\` devolve \`undefined\`, como o
// react-query de verdade: é o que faz o modo Montagem não ver a corrida.
//
// ⚠️ O dublê NÃO inventa dado: \`globalThis.__CENARIO\` é o que o pytest
// serializou do router. Uma chave que o servidor não manda não existe aqui.
exports.useQuery = (opcoes) => {
  const cenario = globalThis.__CENARIO || {}
  const nome = String((opcoes.queryKey || [])[0] || '')
  const habilitado = opcoes.enabled === undefined ? true : !!opcoes.enabled
  ;(cenario.__chaves || []).push(opcoes.queryKey)
  return {
    data: habilitado ? cenario[nome] : undefined,
    isLoading: false, isError: false, error: null, isFetching: false,
    dataUpdatedAt: cenario.agora_ms, refetch: () => {},
  }
}
exports.useMutation = () => ({
  mutate: () => {}, mutateAsync: async () => ({}), isPending: false,
  isError: false, reset: () => {},
})
exports.useQueryClient = () => ({
  invalidateQueries() {}, setQueryData() {}, getQueryData() {},
  cancelQueries() {}, removeQueries() {},
})
`)
}

// ── sondas de árvore ───────────────────────────────────────────────────────
//
// A árvore do `minireact` é `{ tag, props, filhos }` para nó de host e string
// para texto.

function todos(no, saida = []) {
  if (no === null || no === undefined || typeof no !== 'object') return saida
  saida.push(no)
  for (const f of no.filhos || []) todos(f, saida)
  return saida
}

function texto(no) {
  if (typeof no === 'string') return no
  if (!no || typeof no !== 'object') return ''
  return (no.filhos || []).map(texto).join(' ').replace(/\s+/g, ' ').trim()
}

/** Texto + TUDO o que é lido por quem não enxerga a tela.
 *
 *  É sobre este conjunto que se prova AUSÊNCIA: `title` e `aria-valuetext` são
 *  exatamente por onde um número escapa sem ninguém ver — foi assim que o
 *  percentual de CONTAGEM da Decisão 56 quase voltou pela porta da
 *  acessibilidade. */
function tudoQueSeLe(nos, textoDaTela) {
  const partes = [textoDaTela]
  for (const no of nos) {
    for (const [k, v] of Object.entries(no.props || {})) {
      if (typeof v !== 'string') continue
      if (k === 'title' || k.startsWith('aria-')) partes.push(v)
    }
  }
  return partes.join(' | ')
}

const LINHA_PAINEL =
  'rounded-md border border-edge bg-canvas px-2 py-1.5 transition-colors hover:border-blue-400'

/** Os tons do `ui/Banner`, pela classe que cada um pinta. Ler o TOM (e não só
 *  o texto) é o que separa "o aviso está na tela" de "o aviso está VERMELHO na
 *  faixa" — que é o aceite literal do webhook com 401. */
const TONS = [
  ['erro', 'bg-red-50'], ['alerta', 'bg-amber-50'],
  ['info', 'bg-blue-50'], ['sucesso', 'bg-green-50'],
]

// ⚠️ A âncora é o INÍCIO da classe do `ui/Banner` (`flex items-start gap-2 …`),
// e não um trecho solto. A FAIXA da corrida usa as mesmas quatro classes de
// caixa (`border-b px-3 py-2 text-[12px]`) e, numa corrida `COM_FALHA`, o
// `resumo.faixa` traz `bg-red-50` — um casamento frouxo classificaria a faixa
// inteira como "banner vermelho" e o aceite do webhook com 401 ficaria verde
// sem que o banner existisse.
const CAIXA_BANNER = /^flex items-start gap-2 border-b px-3 py-2 text-\[12px\]/

function bannersDe(nos) {
  const saida = []
  for (const no of nos) {
    const c = String((no.props || {}).className || '')
    if (!CAIXA_BANNER.test(c)) continue
    const tom = TONS.find(([, marca]) => c.includes(marca))
    saida.push({ tom: tom ? tom[0] : null, texto: texto(no) })
  }
  return saida
}

/** A linha da contagem, em PEDAÇOS e na ordem do DOM.
 *
 *  A ordem importa: "o `x de y` continua sendo o número primário e o primeiro a
 *  ser lido; o percentual é o SEGUNDO" (Decisão 56b). No DOM é a ordem em que
 *  o leitor de tela anuncia, então ela é o aceite, e não estética de CSS. */
function linhaDaContagem(nos) {
  // ⚠️ A busca é pelo pedaço EXATO (`\D*$`), e não por "começa com N de M".
  // Sem a âncora, o primeiro nó a casar seria o `div` de FORA, cujo único
  // filho é a linha inteira colada — e a sonda devolveria a frase toda como um
  // pedaço só, apagando justamente a ORDEM que se quer medir.
  for (const no of nos) {
    if (no.tag !== 'div') continue
    const pedacos = (no.filhos || []).map(texto).filter(Boolean)
    if (pedacos.some(p => /^\d+ de \d+\D*$/.test(p))) return pedacos
  }
  return null
}

function barrasDe(nos) {
  return nos.filter(n => (n.props || {}).role === 'progressbar').map(n => ({
    label: n.props['aria-label'] || null,
    valuetext: n.props['aria-valuetext'] || null,
    valuenow: n.props['aria-valuenow'],
    valuemax: n.props['aria-valuemax'],
  }))
}

/** As linhas da aba lateral (`Agora` / `Travando`), cada uma com a MARCA e o
 *  `title` dela — a marca `⚠ 2x` da Decisão 64. */
function linhasDoPainel(nos) {
  const saida = []
  for (const no of nos) {
    if (String((no.props || {}).className || '') !== LINHA_PAINEL) continue
    const marcas = todos(no).filter(n => {
      const c = String((n.props || {}).className || '')
      return c.includes('bg-amber-50') && c.includes('font-bold')
    })
    saida.push({
      texto: texto(no),
      marca: marcas.length ? texto(marcas[0]) : null,
      marca_title: marcas.length ? (marcas[0].props.title || null) : null,
      marca_classe: marcas.length ? marcas[0].props.className : null,
    })
  }
  return saida
}

/** Os blocos da faixa de corridas (`SeletorCorrida`), com o `title` de cada um
 *  — é ali que mora `travou: CARGA_A` e a auditoria da Decisão 67. */
function blocosDaFaixa(tela) {
  return tela.achar(n => n.tag === 'button'
      && /h-5 w-3\.5/.test(String(n.props.className || '')))
    .map(b => ({ title: b.props.title || null,
                 aria: b.props['aria-label'] || null,
                 classe: b.props.className }))
}

function main() {
  const cenarios = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f12aceite-'))
  const icones = preparar(destino)
  shims(destino, icones)

  // O `useColorMode` do editor lê `document.documentElement.classList` e
  // registra um `MutationObserver`. Nada disso muda o texto da faixa; o mínimo
  // aqui é o que impede a bancada de morrer por falta de DOM.
  globalThis.document = {
    documentElement: { classList: { contains: () => false } },
    addEventListener() {}, removeEventListener() {},
  }
  globalThis.MutationObserver = class { observe() {} disconnect() {} }

  const { MalhaEditor } = require(
    path.join(destino, 'components', 'malhas', 'MalhaEditor.js'))

  const saida = {}
  for (const [nome, cenario] of Object.entries(cenarios)) {
    try {
      // O relógio LOCAL do cenário. Fixá-lo é o que torna o texto
      // reprodutível — e é o ÚNICO relógio do frescor (Decisão 60).
      Date.now = () => cenario.agora_ms
      cenario.__chaves = []
      globalThis.__CENARIO = cenario
      const tela = mini.montar(mini.criar(MalhaEditor, {
        malha: cenario.malha_name,
        modoInicial: 'execucao',
        corridaInicial: cenario.corrida ?? null,
      }))
      // A aba pedida é aberta por CLIQUE no botão renderizado — não por prop.
      // Um botão de aba decorativo reprova aqui.
      let clicou = null
      if (cenario.aba) {
        const alvo = tela.botoes(cenario.aba)
        if (alvo.length) { tela.clicar(alvo[0]); clicou = cenario.aba }
      }
      // `achar` devolve TODOS os nós de host da árvore renderizada: é sobre
      // este conjunto que as sondas trabalham, e é ele que dá alcance de
      // PÁGINA às provas de ausência.
      const nos = tela.achar(() => true)
      saida[nome] = {
        texto: tela.texto,
        lido: tudoQueSeLe(nos, tela.texto),
        aba_clicada: clicou,
        abas: tela.botoes().map(b => texto(b)).filter(Boolean),
        linha_da_contagem: linhaDaContagem(nos),
        barras: barrasDe(nos),
        banners: bannersDe(nos),
        linhas: linhasDoPainel(nos),
        blocos: blocosDaFaixa(tela),
        chaves: cenario.__chaves,
      }
    } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }
  process.stdout.write(JSON.stringify(saida))
  // A árvore transpilada é lixo de bancada: sem esta linha cada execução da
  // suíte deixaria um diretório novo em `/tmp`.
  fs.rmSync(destino, { recursive: true, force: true })
}

main()
