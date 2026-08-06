// Bancada do DASHBOARD (F11 — `docs/spec-malha-execucao.md` §9.8, Decisão 70).
//
// POR QUE ELA EXISTE, e o que ela conserta
// ────────────────────────────────────────
// A F11 leva a corrida a TRÊS superfícies, e duas delas já tinham prova de
// comportamento: o card do Teams (dict entra, dict sai) e a lista de malhas
// (`f9_pagina_harness.cjs`). A terceira — o Dashboard, que é a tela em que o
// plantonista de fato cai — só tinha `grep` no `.tsx`.
//
// ⚠️ E o `grep` foi MEDIDO como insuficiente, por mutação: apagar
// `<CorridasDeMalhaCard />` do JSX (o bloco existe, compila e nunca é montado)
// e fazer `malhaDoDependente` devolver sempre `null` (o link volta a despejar
// o operador na lista, que é o defeito que a fase existe para consertar) —
// **as duas mutações sobreviveram à suíte inteira**. É o modo de falso verde
// que a F10 pagou nesta mesma spec: `grep` provando texto que nenhum ramo
// renderiza.
//
// Aqui a página é RENDERIZADA e os cliques são APERTADOS: o que sai do outro
// lado é a navegação — a URL para onde o operador de fato vai.
//
// Como roda: a mesma técnica de `f9_pagina_harness.cjs` — o `sucrase` que o
// Vite já traz transpila `pages/Dashboard.tsx` e, recursivamente, todo import
// relativo dele; o JSX clássico aponta para um `__h` que devolve a árvore como
// objeto puro e CHAMA os componentes de função na hora.
//
// O que é DUBLADO, e por quê (a lista é curta de propósito — cada stub é um
// pedaço da tela que deixa de ser provado):
//   • `react` / `@tanstack/react-query` / `react-router-dom` / `lucide-react`
//     — os mesmos hooks determinísticos da bancada da lista. O `useNavigate` é
//     ESPIÃO: é ele que recebe o efeito do clique;
//   • `lib/api` — fronteira de rede (levanta se alguém consultar no render);
//   • `components/dashboard/SupervisaoCard` e
//     `components/execucao/ExecucaoDetailModal` — outras fases, com bancada
//     própria; aqui só ocupariam a árvore.
// Tudo o mais é o código de produção, byte a byte: `Dashboard.tsx`,
// `corridasDaLista.ts`, `CorridaBadge`, `statusExecucao`, `tempoCorrida`,
// `ui/Progress`, `ui/Button`, `ui/Input`.
//
// Uso:  node f11_dashboard_harness.cjs <arquivo.json>
// Entrada: { "<cenário>": { agora_ms, malhas: <GET /malhas>,
//                           deps: <GET /pipelines/dependencias/estado> } }
// Saída (stdout): um JSON só, consumido por `tests/test_malhas_f11_aceite.py`.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const ENTRADA = 'pages/Dashboard.tsx'

const STUB_REL = new Set([
  'lib/api', 'components/dashboard/SupervisaoCard',
  'components/execucao/ExecucaoDetailModal',
])

// ── transpilação recursiva (idêntica à da bancada da lista) ─────────────────

function resolver(deRel, spec) {
  if (!spec.startsWith('.')) return { tipo: 'bare', chave: spec }
  const semExt = path.posix.normalize(
    path.posix.join(path.posix.dirname(deRel), spec))
  if (STUB_REL.has(semExt)) return { tipo: 'stub', chave: semExt }
  for (const ext of ['.tsx', '.ts', '/index.tsx', '/index.ts']) {
    if (fs.existsSync(path.join(SRC, semExt + ext))) {
      return { tipo: 'src', chave: semExt + ext }
    }
  }
  return { tipo: 'stub', chave: semExt }
}

const RE_FROM = /(from\s*|import\s*)(['"])([^'"]+)\2/g

function mapaDeImports(js) {
  const mapa = new Map()
  const re = /import\s+(?:type\s+)?([\s\S]*?)\s*from\s*(['"])([^'"]+)\2/g
  let m
  while ((m = re.exec(js)) !== null) {
    const [, clausula, , spec] = m
    if (!mapa.has(spec)) mapa.set(spec, new Set())
    const nomes = mapa.get(spec)
    const chaves = /\{([^}]*)\}/.exec(clausula)
    if (chaves) {
      for (const bruto of chaves[1].split(',')) {
        const nome = bruto.trim().split(/\s+as\s+/).pop().trim()
        if (nome) nomes.add(nome)
      }
    }
    const padrao = clausula.replace(/\{[^}]*\}/, '').replace(/,/g, '').trim()
    if (padrao && !padrao.startsWith('*')) nomes.add('default:' + padrao)
  }
  return mapa
}

function preparar(destino) {
  const fila = [ENTRADA]
  const feitos = new Set()
  const stubs = new Map()
  const arquivoDe = (chave) => path.join(destino, 'src', chave.replace(/\.tsx?$/, '') + '.mjs')
  const stubDe = (chave) => path.join(destino, 'stubs',
    chave.replace(/[^A-Za-z0-9]/g, '_') + '.mjs')

  while (fila.length) {
    const rel = fila.shift()
    if (feitos.has(rel)) continue
    feitos.add(rel)
    const fonte = fs.readFileSync(path.join(SRC, rel), 'utf8')
    let js = transform(fonte, {
      transforms: ['typescript', 'jsx'],
      jsxRuntime: 'classic',
      jsxPragma: '__h',
      jsxFragmentPragma: '__Frag',
      production: true,
      filePath: rel,
    }).code
    const importados = mapaDeImports(js)
    js = js.replace(RE_FROM, (todo, antes, q, spec) => {
      const alvo = resolver(rel, spec)
      if (alvo.tipo === 'src') {
        fila.push(alvo.chave)
        return `${antes}${q}${arquivoDe(alvo.chave)}${q}`
      }
      if (!stubs.has(alvo.chave)) stubs.set(alvo.chave, new Set())
      for (const nome of importados.get(spec) || []) stubs.get(alvo.chave).add(nome)
      return `${antes}${q}${stubDe(alvo.chave)}${q}`
    })
    const destinoArquivo = arquivoDe(rel)
    fs.mkdirSync(path.dirname(destinoArquivo), { recursive: true })
    const preambulo = rel.endsWith('.tsx')
      ? `import { __h, __Frag } from '${path.join(destino, 'jsx.mjs')}'\n` : ''
    fs.writeFileSync(destinoArquivo, preambulo + js)
  }

  fs.mkdirSync(path.join(destino, 'stubs'), { recursive: true })
  for (const [chave, nomes] of stubs) {
    fs.writeFileSync(stubDe(chave), corpoDoStub(chave, nomes, destino))
  }
  fs.writeFileSync(path.join(destino, 'jsx.mjs'), FONTE_JSX)
}

const FONTE_JSX = `
export const __Frag = 'fragmento'
export function __h(tipo, props, ...filhos) {
  const limpos = filhos.flat(Infinity)
    .filter(f => f !== null && f !== undefined && f !== false && f !== true)
  if (typeof tipo === 'function') {
    if (tipo.__icone) return { tipo: 'icone:' + tipo.__icone, props: props || {}, filhos: [] }
    const nome = tipo.name || 'anonimo'
    const entrada = Object.assign({}, props || {},
                                  limpos.length ? { children: limpos } : null)
    try {
      const saida = tipo(entrada)
      return {
        tipo: 'componente:' + nome, props: entrada,
        filhos: (saida === null || saida === undefined || saida === false)
          ? [] : [saida],
      }
    } catch (e) {
      return {
        tipo: 'erro:' + nome, props: entrada, filhos: [],
        erro: String((e && e.stack) || e),
      }
    }
  }
  return { tipo: String(tipo), props: props || {}, filhos: limpos }
}
`

function corpoDoStub(chave, nomes, destino) {
  const jsx = `import { __h } from '${path.join(destino, 'jsx.mjs')}'\n`
  if (chave === 'react') return jsx + STUB_REACT
  if (chave === '@tanstack/react-query') return jsx + STUB_QUERY
  if (chave === 'react-router-dom') return jsx + STUB_ROUTER
  if (chave === 'lucide-react') {
    return [...nomes].filter(n => !n.startsWith('default:')).map(n =>
      `export function ${n}() {}\n${n}.__icone = ${JSON.stringify(n)}`).join('\n') + '\n'
  }
  if (chave === 'lib/api') {
    return 'export function apiFetch() {\n'
      + '  throw new Error("apiFetch chamado no RENDER — a bancada não tem rede")\n}\n'
  }
  const nomeados = [...nomes].filter(n => !n.startsWith('default:'))
  const corpo = nomeados.map(n =>
    `export function ${n}(props) { return { tipo: 'stub:${n}', props: props || {}, filhos: [] } }`)
  if ([...nomes].some(n => n.startsWith('default:'))) {
    corpo.push("export default function padrao(props) "
      + "{ return { tipo: 'stub:default', props: props || {}, filhos: [] } }")
  }
  return jsx + corpo.join('\n') + '\n'
}

const STUB_REACT = `
export function useState(inicial) {
  return [typeof inicial === 'function' ? inicial() : inicial, () => {}]
}
export function useEffect() {}
export function useLayoutEffect() {}
export function useMemo(fn) { return fn() }
export function useCallback(fn) { return fn }
export function useRef(inicial) { return { current: inicial === undefined ? null : inicial } }
let seq = 0
export function useId() { return ':bancada' + (seq++) + ':' }
export function useContext() { return undefined }
export function createContext(v) { return { Provider: () => null, _valor: v } }
export function memo(c) { return c }
export function forwardRef(c) { return (props) => c(props, { current: null }) }
export const Fragment = 'fragmento'
export default {
  useState, useEffect, useLayoutEffect, useMemo, useCallback, useRef, useId,
  useContext, createContext, memo, forwardRef, Fragment,
}
`

// A consulta responde POR CHAVE, a partir do cenário. As que o cenário não
// preparou ficam CARREGANDO — devolver \`[]\` faria um painel desenhar "nada
// aqui" como se fosse fato apurado.
const STUB_QUERY = `
export function useQuery(opcoes) {
  const b = globalThis.__BANCADA
  const chave = JSON.stringify(opcoes && opcoes.queryKey)
  b.consultas.push(opcoes)
  const dado = b.respostas[chave]
  if (dado === undefined) {
    return { data: undefined, isLoading: true, isError: false, error: null,
             isFetching: true, dataUpdatedAt: 0, refetch: () => {} }
  }
  return { data: dado, isLoading: false, isError: false, error: null,
           isFetching: false, dataUpdatedAt: b.respostaEm, refetch: () => {} }
}
export function useMutation() {
  return { mutate: () => {}, mutateAsync: async () => {}, isPending: false }
}
export function useQueryClient() {
  return { invalidateQueries: () => {}, setQueryData: () => {}, getQueryData: () => undefined }
}
`

const STUB_ROUTER = `
export function useSearchParams() {
  const b = globalThis.__BANCADA
  return [b.searchParams, () => {}]
}
export function useNavigate() {
  return (destino) => { globalThis.__BANCADA.navegacoes.push(destino) }
}
export function useLocation() { return { pathname: '/', search: '' } }
export function Link(props) { return { tipo: 'stub:Link', props: props || {}, filhos: [] } }
`

// ── leitura da árvore ───────────────────────────────────────────────────────

function todosOsNos(no, saida = []) {
  if (!no || typeof no !== 'object') return saida
  saida.push(no)
  for (const f of no.filhos || []) todosOsNos(f, saida)
  return saida
}

function textoDe(no, partes = []) {
  if (no === null || no === undefined || typeof no === 'boolean') return partes
  if (typeof no !== 'object') {
    const t = String(no)
    if (t.trim()) partes.push(t)
    return partes
  }
  for (const f of no.filhos || []) textoDe(f, partes)
  return partes
}

function tudoQueSeLe(raiz) {
  const partes = [textoDe(raiz).join('')]
  for (const no of todosOsNos(raiz)) {
    for (const [k, v] of Object.entries(no.props || {})) {
      if (typeof v !== 'string') continue
      if (k === 'aria-hidden') continue
      if (k === 'title' || k === 'alt' || k === 'placeholder' || k.startsWith('aria-')) {
        partes.push(v)
      }
    }
  }
  return partes.join(' | ')
}

function acharComponentes(raiz, nome) {
  return todosOsNos(raiz).filter(n => n.tipo === 'componente:' + nome)
}

/** Aperta o nó e devolve PARA ONDE a página navegou. `null` = o clique não
 *  levou a lugar nenhum, que é o vermelho certo para uma linha decorativa. */
function clicarENavegar(no) {
  const b = globalThis.__BANCADA
  if (!no || typeof no.props.onClick !== 'function') return null
  const antes = b.navegacoes.length
  no.props.onClick()
  const novas = b.navegacoes.slice(antes)
  return novas.length ? novas[novas.length - 1] : null
}

/** As linhas clicáveis DENTRO de um card (o `<div>` com `onClick`). */
function linhasDe(no) {
  return todosOsNos(no).filter(
    n => n.tipo === 'div' && typeof n.props.onClick === 'function')
}

// ── execução ────────────────────────────────────────────────────────────────

async function main() {
  const cenarios = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f11dash-'))
  preparar(destino)
  const pagina = await import(path.join(destino, 'src', 'pages', 'Dashboard.mjs'))

  const saida = {}
  for (const [nome, cenario] of Object.entries(cenarios)) {
    try {
      saida[nome] = rodar(pagina.default, cenario)
    } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }
  process.stdout.write(JSON.stringify(saida, null, 1))
}

function rodar(Dashboard, cenario) {
  const agora = cenario.agora_ms
  Date.now = () => agora
  globalThis.__BANCADA = {
    respostas: {
      '["malhas"]': cenario.malhas,
      '["deps-estado-dashboard"]': cenario.deps,
    },
    respostaEm: agora,
    searchParams: new URLSearchParams(''),
    navegacoes: [],
    consultas: [],
  }
  const raiz = Dashboard({})
  const b = globalThis.__BANCADA

  // As linhas de CORRIDA, com o clique apertado: o destino é a URL para onde o
  // plantonista vai. `CorridaLinha` é componente próprio, então a leitura é
  // pelo nome — e não por classe de Tailwind, que muda com o tema.
  const corridas = acharComponentes(raiz, 'CorridaLinha').map(no => ({
    malha: (no.props.malha || {}).malha_name,
    texto: textoDe(no).join(' '),
    navegou: clicarENavegar(todosOsNos(no).find(
      n => n.tipo === 'div' && typeof n.props.onClick === 'function')),
  }))

  const cardCorridas = acharComponentes(raiz, 'CorridasDeMalhaCard')[0]
  const cardDeps = acharComponentes(raiz, 'AguardandoDependenciaCard')[0]

  const dependencias = cardDeps
    ? linhasDe(cardDeps).map(no => ({
        texto: textoDe(no).join(' '),
        title: no.props.title || null,
        navegou: clicarENavegar(no),
      }))
    : []

  // A CADÊNCIA, perguntada à função que o Dashboard registrou — não lida no
  // fonte. É o que prova "mesma chave, mesma cadência, zero consulta nova".
  const consultas = b.consultas.map(o => ({
    chave: o.queryKey,
    cadencia: typeof o.refetchInterval === 'function'
      ? o.refetchInterval({ state: { data: cenario.malhas } })
      : (o.refetchInterval === undefined ? null : o.refetchInterval),
  }))

  return {
    corridas,
    dependencias,
    consultas,
    // O card inteiro some quando não há nada a dizer (Decisões 26/27): um
    // painel "0 corridas" fixo no topo treina o olho a pular a região.
    tem_card_de_corrida: !!(cardCorridas && cardCorridas.filhos.length),
    cabecalho: cardCorridas ? textoDe(cardCorridas).join(' ') : null,
    lido: tudoQueSeLe(raiz),
    erros: todosOsNos(raiz).filter(n => n.tipo.startsWith('erro:'))
      .map(n => ({ componente: n.tipo, erro: n.erro })),
  }
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
