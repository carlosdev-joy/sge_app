// Bancada da PÁGINA da F9 (spec-malha-execucao.md §9.1–§9.3, §9.9) — a lista
// de malhas INTEIRA, montada a partir do payload que a API de verdade devolve.
//
// POR QUE ESTA BANCADA EXISTE, se já há `f9_card_harness.cjs`
// ───────────────────────────────────────────────────────────
// Aquela prova as DERIVAÇÕES (`resumoCorrida`, `CorridaProgresso`, a pílula) a
// partir de objetos escritos à mão. Ela é necessária e não basta, por dois
// motivos que já custaram defeito ALTO nesta spec:
//
//   1. **dublê que fabrica um dado que o servidor nunca produz.** Um objeto de
//      corrida escrito no teste sempre casa com o componente que o teste está
//      exercitando — é o teste conversando consigo mesmo. Aqui o cenário chega
//      pronto de `GET /malhas`, serializado pelo pytest a partir do router de
//      verdade: se a API parar de mandar `quiescencia_ate`, ou mandá-lo com
//      outro nome, a frase de fechamento some e ESTE arquivo fica vermelho;
//   2. **teste que afirma a MENSAGEM e não o COMPORTAMENTO.** "`Acompanhar`
//      existe e funciona" não é `grep 'onClick={onAcompanhar}'` no fonte: é
//      achar o botão na árvore renderizada, APERTÁ-LO, e ver que parâmetro de
//      URL sai do outro lado — e depois abrir a página com aquele parâmetro e
//      ver o editor receber a lente. Os dois passos acontecem aqui.
//
// Também é aqui que as provas de AUSÊNCIA ganham o alcance que o aceite pede
// ("nem '100%' nem 'concluída' em lugar nenhum"): a varredura é da PÁGINA
// inteira — texto, `title` e todo `aria-*` —, não de um componente recortado.
//
// ── Como isto roda sem runner de JS ────────────────────────────────────────
// Mesma técnica de `f4_front_harness.cjs`/`f9_card_harness.cjs`, esticada de um
// componente para uma árvore de módulos: o `sucrase` que o Vite já traz
// transpila `pages/Malha.tsx` e, RECURSIVAMENTE, todo import relativo dele; o
// JSX clássico aponta para um `__h` nosso, que devolve a árvore como objeto
// puro e CHAMA os componentes de função na hora (é o que faz `MalhaCard`,
// `CorridaBadge`, `CorridaProgresso` e `ui/Progress` aparecerem expandidos, com
// os `aria-*` de verdade no nó de verdade).
//
// O que é DUBLADO, e por quê — a lista é curta de propósito, porque cada stub é
// um pedaço da tela que deixa de ser provado:
//   • `react`          — hooks determinísticos (sem agendador, sem efeito). O
//                        `Date.now` é fixado no relógio do cenário: o frescor e
//                        o decorrido são do relógio LOCAL (Decisão 60) e um
//                        relógio de verdade tornaria o texto irreprodutível;
//   • `@tanstack/react-query` — devolve o payload do cenário como resposta
//                        pronta, com `dataUpdatedAt` no relógio local;
//   • `react-router-dom`      — `setSearchParams` vira ESPIÃO: é ele que
//                        recebe o efeito do clique em `Acompanhar`;
//   • `lucide-react`   — cada ícone vira o próprio nome (é assim que se prova
//                        que estados diferentes não compartilham ícone);
//   • `lib/api`, `store/auth`, `ui/Toast`, `malhas/MalhaEditor` — fronteiras de
//                        rede, sessão, notificação e o editor de React Flow. O
//                        `MalhaEditor` vira nó com as props VISÍVEIS, porque o
//                        que esta fase precisa provar dele é exatamente qual
//                        lente ele recebe.
//
// Tudo o mais é o código de produção, byte a byte: `Malha.tsx`, `MalhaCard`,
// `statusExecucao.ts`, `tempoCorrida.ts`, `CorridaBadge`, `CorridaProgresso`,
// `ui/Progress`, `ui/Button`, `CritBadge`.
//
// Uso:  node f9_pagina_harness.cjs <arquivo.json>
// Entrada: { "<cenário>": { payload: <resposta de GET /malhas>,
//                           agora_ms: <epoch local>, url?: "malha=M1&modo=…" } }
// Saída (stdout): um JSON só, consumido por `tests/test_malhas_f9_aceite.py`.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const ENTRADA = 'pages/Malha.tsx'

// Fronteiras dubladas à mão (o comentário do cabeçalho diz por quê). Só os
// RELATIVOS precisam de lista: todo especificador de pacote (`react`,
// `lucide-react`, …) vira stub por definição, porque nada de `node_modules`
// entra nesta bancada — e é isso que garante que o que roda aqui é o `src/`.
const STUB_REL = new Set([
  'lib/api', 'store/auth', 'components/ui/Toast', 'components/malhas/MalhaEditor',
])

// ── transpilação recursiva ──────────────────────────────────────────────────

/** `pages/Malha.tsx` + './x' → 'components/x.tsx' (ou o rótulo do stub). */
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
  return { tipo: 'stub', chave: semExt }      // some do grafo: vira stub genérico
}

const RE_FROM = /(from\s*|import\s*)(['"])([^'"]+)\2/g

/** Especificador → nomes importados dele, lidos do texto do módulo.
 *
 *  É o que permite gerar um stub com a superfície EXATA que o código de
 *  produção consome — e o motivo de a varredura ser feita de uma vez só, com o
 *  `lastIndex` do regex global andando de um `import` para o próximo: um
 *  padrão por especificador casaria, num arquivo sem ponto e vírgula (o estilo
 *  desta casa), tudo o que estivesse ENTRE o primeiro `import` do arquivo e o
 *  `from` procurado — e o stub do `lucide-react` nascia exportando `useMemo`. */
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
  const stubs = new Map()          // chave → Set de nomes usados
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

// ── os stubs ────────────────────────────────────────────────────────────────

const FONTE_JSX = `
export const __Frag = 'fragmento'

/** Cria o nó, e CHAMA o componente de função na hora.
 *
 *  Chamar é o que faz esta bancada valer: sem isso \`MalhaCard\`,
 *  \`CorridaProgresso\` e \`ui/Progress\` ficariam como caixas opacas e os
 *  \`aria-*\` — que são metade do aceite — nunca apareceriam na árvore.
 *
 *  O resultado fica ENVOLVIDO num nó que guarda o nome e as props do
 *  componente: é assim que o teste acha "o MalhaCard da malha X" e "as props
 *  que o MalhaEditor recebeu", sem depender de texto.
 *
 *  Componente que LEVANTA não derruba a página: vira um nó \`erro:<nome>\`. O
 *  aceite "zero exceção no console" precisa que a exceção seja um DADO — se ela
 *  matasse o processo, o cenário inteiro sumiria e a suíte diria "sem cards"
 *  em vez de "o card explodiu". */
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
    // Cada ícone vira o PRÓPRIO NOME na árvore: é o único jeito de provar que
    // os três desfechos vermelhos e os dois âmbares não compartilham ícone —
    // cor nunca é canal único nesta casa.
    return [...nomes].filter(n => !n.startsWith('default:')).map(n =>
      `export function ${n}() {}\n${n}.__icone = ${JSON.stringify(n)}`).join('\n') + '\n'
  }
  if (chave === 'lib/api') {
    return 'export function apiFetch() {\n'
      + '  throw new Error("apiFetch chamado no RENDER — a bancada não tem rede;"\n'
      + '    + " se isto levantar, alguma consulta saiu do queryFn")\n}\n'
  }
  if (chave === 'store/auth') {
    // Operador (não `consulta`): é o perfil de quem está de plantão às 3h, e é
    // o que mantém os botões de ação na tela.
    return 'const ESTADO = { user: { matricula: "OPER1", perfil: "operador" } }\n'
      + 'export function useAuthStore(seletor) {\n'
      + '  return typeof seletor === "function" ? seletor(ESTADO) : ESTADO\n}\n'
  }
  if (chave === 'components/ui/Toast') {
    return 'const registro = []\n'
      + 'export const toast = {\n'
      + '  success: (m) => registro.push(["success", m]),\n'
      + '  error: (m) => registro.push(["error", m]),\n'
      + '  info: (m) => registro.push(["info", m]),\n'
      + '}\n'
      + 'export function ToastHost() { return null }\n'
      + 'export const __registro = registro\n'
  }
  // Genérico: componente-caixa que preserva as props (é assim que se lê a lente
  // com que o `MalhaEditor` foi aberto).
  const nomeados = [...nomes].filter(n => !n.startsWith('default:'))
  const corpo = nomeados.map(n =>
    `export function ${n}(props) { return { tipo: 'stub:${n}', props: props || {}, filhos: [] } }`)
  if ([...nomes].some(n => n.startsWith('default:'))) {
    corpo.push("export default function padrao(props) "
      + "{ return { tipo: 'stub:default', props: props || {}, filhos: [] } }")
  }
  return jsx + corpo.join('\n') + '\n'
}

// Hooks DETERMINÍSTICOS. Nenhum agenda nada: o relógio do cenário é fixo, e um
// `setInterval` de verdade tornaria a saída irreprodutível.
const STUB_REACT = `
export function useState(inicial) {
  // O setter é ESPIÃO, e o estado é SEMEÁVEL (F11).
  //
  // Por que as duas coisas: o aceite da fase é *"o filtro \`Rodando agora\`
  // responde da LISTA"* — e "responder" é a lista ENCOLHER, não o botão pedir
  // um valor. Só o espião provaria que o contador é clicável e inerte; só a
  // semente provaria que a lista filtra, mas não que o clique chega lá. A
  // bancada faz as duas metades: aperta o contador, ANOTA o que ele pediu e
  // redesenha a página com aquele estado — que é o que o React faria.
  //
  // A semente é por ÍNDICE de hook (a ordem de chamada, que é determinística
  // nesta árvore) e vem SEMPRE de um clique de verdade da passada anterior:
  // um índice escrito à mão no teste seria a bancada semeando o estado que ela
  // quer provar, e aí o botão poderia estar desligado que ninguém veria.
  const b = globalThis.__BANCADA
  const i = b ? b.hooks++ : -1
  const semeado = b && b.sementes && Object.prototype.hasOwnProperty.call(b.sementes, i)
  const valor = semeado
    ? b.sementes[i]
    : (typeof inicial === 'function' ? inicial() : inicial)
  return [valor, (v) => {
    if (!b) return
    const pedido = typeof v === 'function' ? '<fn>' : v
    b.estados.push(pedido)
    b.setados.push({ i, valor: pedido })
  }]
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

const STUB_QUERY = `
export function useQuery(opcoes) {
  const chave = JSON.stringify(opcoes && opcoes.queryKey)
  const b = globalThis.__BANCADA
  // TODA consulta montada pela página é anotada, e não só a da lista: é assim
  // que se mede "o filtro responde DA LISTA, sem abrir malha por malha"
  // (F11). Uma consulta por card apareceria aqui como 15 chaves distintas —
  // e nenhuma asserção de texto pegaria isso.
  b.chaves.push(opcoes && opcoes.queryKey)
  if (chave === JSON.stringify(['malhas'])) {
    b.consultas.push(opcoes)
    return {
      data: b.payload, isLoading: false, isError: false, error: null,
      isFetching: false, dataUpdatedAt: b.respostaEm, refetch: () => {},
    }
  }
  // Qualquer outra consulta (as dos modais) fica CARREGANDO: o cenário não a
  // preparou, e devolver \`[]\` faria um modal desenhar "nenhum membro" como se
  // fosse fato apurado.
  return {
    data: undefined, isLoading: true, isError: false, error: null,
    isFetching: true, dataUpdatedAt: 0, refetch: () => {},
  }
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
  return [b.searchParams, (p) => { b.navegacoes.push(paraObjeto(p)) }]
}
function paraObjeto(p) {
  if (p instanceof URLSearchParams) return Object.fromEntries(p.entries())
  return Object.assign({}, p)
}
export function useNavigate() {
  return (destino) => { globalThis.__BANCADA.navegacoes.push({ __to: destino }) }
}
export function useLocation() { return { pathname: '/malha', search: '' } }
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

/** Texto + tudo que é lido por quem não enxerga a tela. É sobre este conjunto
 *  que se prova ausência: sem os `aria-*`, o percentual entra pela porta da
 *  acessibilidade e nenhuma inspeção visual pega. */
function tudoQueSeLe(raiz) {
  // O texto é colado SEM separador, e os atributos vêm depois com um: uma
  // frase da tela nasce partida em vários nós (`↳ ` + `fecha 15 min…`), e
  // separá-los faria a busca por frase falhar justamente onde ela importa.
  const partes = [textoDe(raiz).join('')]
  for (const no of todosOsNos(raiz)) {
    for (const [k, v] of Object.entries(no.props || {})) {
      if (typeof v !== 'string') continue
      // `aria-hidden` fica FORA: ele marca o que o leitor de tela NÃO lê (os
      // segmentos da barra, o traço de "nada previsto"). Incluí-lo encheria a
      // prova de ausência de literais "true" e, pior, sugeriria que conteúdo
      // escondido é conteúdo lido.
      if (k === 'aria-hidden') continue
      if (k === 'title' || k === 'alt' || k === 'placeholder' || k.startsWith('aria-')) {
        partes.push(v)
      }
    }
  }
  return partes.join(' | ')
}

function classesDe(raiz) {
  return todosOsNos(raiz)
    .map(n => (typeof n.props.className === 'string' ? n.props.className : ''))
    .join(' ')
}

function acharComponentes(raiz, nome) {
  return todosOsNos(raiz).filter(n => n.tipo === 'componente:' + nome)
}

function acharBotao(raiz, rotulo) {
  return todosOsNos(raiz).find(
    n => n.tipo === 'button' && textoDe(n).join(' ').includes(rotulo))
}

/** A barra ACESSÍVEL, se ela existir: o nó com `role="progressbar"`. Prova de
 *  ausência de barra é a ausência DESTE nó — uma barra com `total = 0` passaria
 *  por qualquer teste de string. */
function barraDe(raiz) {
  const no = todosOsNos(raiz).find(n => n.props && n.props.role === 'progressbar')
  if (!no) return null
  return {
    role: no.props.role,
    ariaLabel: no.props['aria-label'],
    valuenow: no.props['aria-valuenow'],
    valuemin: no.props['aria-valuemin'],
    valuemax: no.props['aria-valuemax'],
    valuetext: no.props['aria-valuetext'],
    larguras: no.filhos.map(f => (f.props.style || {}).width),
    titles: no.filhos.map(f => f.props.title),
    classes: no.filhos.map(f => f.props.className || ''),
  }
}

// ── execução ────────────────────────────────────────────────────────────────

async function main() {
  const cenarios = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f9pag-'))
  preparar(destino)
  const pagina = await import(path.join(destino, 'src', 'pages', 'Malha.mjs'))

  const saida = {}
  for (const [nome, cenario] of Object.entries(cenarios)) {
    try {
      saida[nome] = cenario.apertar ? comClique(pagina.default, cenario)
                                    : rodar(pagina.default, cenario)
    } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }
  process.stdout.write(JSON.stringify(saida, null, 1))
}

/** Aperta o nó e devolve o que o clique PEDIU: os valores (como o teste da F9
 *  já os lê) e as sementes `{i, valor}` que a próxima passada aplica. `[]` = o
 *  clique não pediu nada (botão decorativo) ou nem havia `onClick`. */
function clicar(no) {
  const b = globalThis.__BANCADA
  if (!no || typeof no.props.onClick !== 'function') {
    return { valores: [], sementes: [] }
  }
  const antes = b.setados.length
  no.props.onClick()
  const novos = b.setados.slice(antes)
  return { valores: novos.map(s => s.valor), sementes: novos }
}

/** A página DEPOIS de o contador ser apertado — as duas passadas que o React
 *  faria: renderiza, aperta a pílula cujo texto contém `cenario.apertar`,
 *  anota o estado que o clique pediu e redesenha com ele.
 *
 *  ⚠️ A semente sai do CLIQUE, nunca do cenário. Se o `onClick` não existir,
 *  ou não pedir nada, a segunda passada é idêntica à primeira e o teste vê a
 *  lista inteira — que é exatamente o vermelho certo para um contador
 *  decorativo. A alternativa (o teste dizer "renderize com filtro=rodando")
 *  provaria o filtro e esconderia o botão desligado.
 *
 *  A saída é a da SEGUNDA passada, com o rastro da primeira em `antes`. */
function comClique(Malha, cenario) {
  const antes = rodar(Malha, cenario)
  const alvo = (antes.stats || []).find(
    s => s.texto.toLowerCase().includes(String(cenario.apertar).toLowerCase()))
  if (!alvo) {
    return Object.assign(antes, {
      __erro__: 'pílula não encontrada para apertar: ' + cenario.apertar
        + ' — na tela: ' + JSON.stringify((antes.stats || []).map(s => s.texto)),
    })
  }
  const sementes = {}
  for (const s of alvo.sementes) sementes[s.i] = s.valor
  const depois = rodar(Malha, cenario, sementes)
  return Object.assign(depois, {
    apertou: alvo.texto,
    pedido: alvo.clique,
    antes: { ordem: antes.ordem, chaves: antes.chaves },
  })
}

/** Uma passada de render, com o estado que a passada anterior semeou.
 *
 *  `sementes` é `{índice do hook: valor}` e vem SEMPRE de um clique real —
 *  ver o comentário do `useState` do stub. */
function rodar(Malha, cenario, sementes) {
  const agora = cenario.agora_ms
  // O relógio LOCAL do cenário — o único que o frescor e o decorrido consultam
  // (Decisão 60). Fixá-lo aqui é o que torna o texto reprodutível.
  Date.now = () => agora
  globalThis.__BANCADA = {
    payload: cenario.payload,
    respostaEm: cenario.resposta_em_ms === undefined ? agora : cenario.resposta_em_ms,
    searchParams: new URLSearchParams(cenario.url || ''),
    navegacoes: [],
    consultas: [],
    chaves: [],
    estados: [],
    setados: [],
    hooks: 0,
    sementes: sementes || null,
  }
  const raiz = Malha({})
  const b = globalThis.__BANCADA

  const cards = acharComponentes(raiz, 'MalhaCard').map((no, i) => {
    const malha = (no.props.malha || {}).malha_name
    const botoes = todosOsNos(no)
      .filter(n => n.tipo === 'button')
      .map(n => ({ rotulo: textoDe(n).join(' ').trim(), desabilitado: !!n.props.disabled,
                   title: n.props.title || null }))
    // O CLIQUE de verdade: o `onClick` do botão renderizado, chamado como o
    // navegador o chamaria. O que sai do outro lado é a navegação.
    const antes = b.navegacoes.length
    const alvo = acharBotao(no, 'Acompanhar')
    if (alvo && typeof alvo.props.onClick === 'function') alvo.props.onClick()
    return {
      ordem: i,
      malha,
      lido: tudoQueSeLe(no),
      // O texto do card em DUAS formas: colado (é como o olho lê a frase, que
      // nasce partida em vários nós JSX) e em pedaços (é como se afirma que um
      // rótulo existe sozinho, sem casar por acidente com o vizinho).
      texto: textoDe(no).join(''),
      textos: textoDe(no),
      classes: classesDe(no),
      barra: barraDe(no),
      botoes,
      acompanhar_existe: !!alvo,
      acompanhar_desabilitado: !!(alvo && alvo.props.disabled),
      acompanhar_navegou: b.navegacoes.slice(antes),
    }
  })

  // As props com que o editor foi aberto — é o outro lado do clique em
  // `Acompanhar`: a URL vira LENTE, ou o parâmetro é decoração.
  const editor = acharComponentes(raiz, 'MalhaEditor')
    .map(n => ({
      malha: n.props.malha, modoInicial: n.props.modoInicial,
      dataInicial: n.props.dataInicial, corridaInicial: n.props.corridaInicial,
    }))

  // O polling da Decisão 73, CHAMADO — não lido no fonte. `refetchInterval` é
  // função: dá para perguntar a ela, com o payload deste cenário, se a tela
  // vai se atualizar sozinha. `false` = a tela congela; e como o MESMO
  // predicado governa o alarme de dado velho, congelar em silêncio é o defeito
  // que este número pega.
  const opcoes = (b.consultas || []).find(
    o => JSON.stringify(o.queryKey) === JSON.stringify(['malhas']))
  let polling = null
  if (opcoes && typeof opcoes.refetchInterval === 'function') {
    polling = opcoes.refetchInterval({ state: { data: cenario.payload } })
  }

  return {
    cards,
    editor,
    polling,
    // A stats bar: cada pílula como o olho a lê ("1 não abriu"), com o tom.
    //
    // F11: as pílulas de CORRIDA são `<button>` (contador que age como filtro é
    // botão de estado, Decisão 75), então o extrator aceita os dois elementos —
    // filtrar só `div` faria os contadores novos sumirem daqui e o teste da F9
    // acusar a ausência de uma pílula que está na tela. `pressionado` é o
    // `aria-pressed`: `null` para as pílulas que não filtram nada.
    stats: todosOsNos(raiz)
      .filter(n => (n.tipo === 'div' || n.tipo === 'button')
        && /rounded px-3 py-1\.5/.test(n.props.className || ''))
      .map(n => {
        // O CLIQUE de verdade, como o navegador o faria: o que sai do outro
        // lado é o valor pedido ao `setState`. Contador clicável e inerte
        // (o `onClick` que não chama nada) sai daqui com `[]`.
        const apertado = clicar(n)
        return {
          texto: textoDe(n).join(' '),
          classes: n.props.className,
          pressionado: n.props['aria-pressed'] ?? null,
          clicavel: n.tipo === 'button',
          clique: apertado.valores,
          sementes: apertado.sementes,
        }
      }),
    // F11: os filtros da toolbar, com as opções como o olho as lê. `Ativas/
    // Inativas` é situação de CADASTRO e `Rodando agora/…` é estado de CICLO —
    // são dois <select>, e o aceite exige que o segundo exista ao lado do
    // primeiro (e não no lugar dele).
    filtros: todosOsNos(raiz)
      .filter(n => n.tipo === 'select')
      .map(n => ({
        aria: n.props['aria-label'] || null,
        valor: n.props.value,
        opcoes: todosOsNos(n).filter(o => o.tipo === 'option')
          .map(o => ({ valor: o.props.value, rotulo: textoDe(o).join('') })),
      })),
    lido: tudoQueSeLe(raiz),
    texto: textoDe(raiz).join(''),
    // Toda chave de consulta que a página montou nesta passada. Com 15 cards
    // na tela, uma chave por card seria N+1 na lista — e o aceite da F11 é
    // exatamente que o filtro responde SEM abrir malha por malha.
    chaves: b.chaves,
    // Ordem em que os cards aparecem na tela — o aceite da Decisão 58.
    ordem: cards.map(c => c.malha),
    // "zero exceção": qualquer componente que levantou vira dado, não crash.
    erros: todosOsNos(raiz).filter(n => n.tipo.startsWith('erro:'))
      .map(n => ({ componente: n.tipo, erro: n.erro })),
    navegacoes: globalThis.__BANCADA.navegacoes,
  }
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
