// Módulo comum de layout e validação de grafo — extraído do FluxoEditor na F8
// (spec de dependências, §4b): o MalhaEditor (nó = pipeline) e o canvas de
// etapas (nó = job) compartilham as MESMAS funções puras. Tipos estruturais
// mínimos de propósito: Node/Edge do React Flow e os payloads da API satisfazem
// as interfaces sem cast.

// ── Tipos mínimos ───────────────────────────────────────────────────────────
// Nó do payload da API de fluxo (só o que o layout usa).
export interface NoAutoLayout {
  job_name: string
  execution_order?: number | null
}
// Nó/aresta do grafo vivo (subconjunto estrutural de Node/Edge do React Flow).
export interface NoGrafo { id: string }
export interface ArestaGrafo { source: string; target: string }

export type Posicoes = Record<string, { x: number; y: number }>

// Orientação do desenho (MalhaEditor): 'horizontal' = níveis topológicos em
// COLUNAS (esquerda → direita, o comportamento de sempre e o default de todas
// as funções — o FluxoEditor nem passa o parâmetro); 'vertical' = os níveis
// viram LINHAS (cima → baixo) e os irmãos se espalham no eixo x.
export type Orientacao = 'horizontal' | 'vertical'

// ── Layout automático em camadas por execution_order ────────────────────────
export const COL_W = 280
export const ROW_H = 140
// Modo vertical: espaçamento pensado para o card w-48 (192px) do MalhaEditor —
// irmãos lado a lado precisam de folga horizontal maior que o card (ROW_W) e
// os níveis empilham com respiro para as arestas (NIVEL_H).
export const ROW_W = 240
export const NIVEL_H = 150

// Converte (nível topológico, índice entre irmãos) em posição na orientação
// pedida — único ponto onde os eixos trocam; os algoritmos abaixo continuam
// raciocinando em níveis/irmãos, indiferentes à direção do desenho.
function posiciona(nivel: number, irmao: number, orientacao: Orientacao) {
  return orientacao === 'vertical'
    ? { x: irmao * ROW_W, y: nivel * NIVEL_H }
    : { x: nivel * COL_W, y: irmao * ROW_H }
}

export function autoLayout(
  apiNodes: NoAutoLayout[],
  orientacao: Orientacao = 'horizontal',
): Posicoes {
  const byOrder = new Map<number, NoAutoLayout[]>()
  for (const n of apiNodes) {
    const o = n.execution_order ?? 1
    if (!byOrder.has(o)) byOrder.set(o, [])
    byOrder.get(o)!.push(n)
  }
  const orders = Array.from(byOrder.keys()).sort((a, b) => a - b)
  const pos: Posicoes = {}
  orders.forEach((o, col) => {
    byOrder.get(o)!.forEach((n, i) => {
      pos[n.job_name] = posiciona(col, i, orientacao)
    })
  })
  return pos
}

// Layout sobre o grafo VIVO (nós + arestas atuais), não só os salvos: assim o
// "Reorganizar" reposiciona TAMBÉM os nós recém-adicionados (ex.: uma notificação
// que ainda não foi salva). Coluna = execution_order salvo, quando houver; para
// um nó novo, deriva de (maior coluna dos predecessores no grafo) + 1.
export function liveLayout(
  nodes: NoGrafo[],
  edges: ArestaGrafo[],
  savedOrder: Map<string, number>,
  orientacao: Orientacao = 'horizontal',
): Posicoes {
  const realEdges = edges.filter((e) => e && e.source && e.target)
  const pos: Posicoes = {}

  // Sem conectores no desenho → não há grafo: cai no layout por execution_order.
  if (realEdges.length === 0) {
    const byOrd = new Map<number, string[]>()
    for (const n of nodes) {
      const o = savedOrder.get(n.id) ?? 1
      if (!byOrd.has(o)) byOrd.set(o, [])
      byOrd.get(o)!.push(n.id)
    }
    Array.from(byOrd.keys()).sort((a, b) => a - b).forEach((o, ci) => {
      byOrd.get(o)!.forEach((id, ri) => { pos[id] = posiciona(ci, ri, orientacao) })
    })
    return pos
  }

  // COM conectores → a COLUNA segue o GRAFO (caminho mais longo a partir das
  // raízes, pelos conectores do desenho), NÃO o execution_order. Assim um nó
  // ligado ENTRE dois outros (ex.: notificação) fica inline, na coluna do meio,
  // em vez de empilhar na coluna de um vizinho.
  const preds = new Map<string, string[]>()
  for (const n of nodes) preds.set(n.id, [])
  for (const e of realEdges) {
    if (preds.has(e.target) && preds.has(e.source)) preds.get(e.target)!.push(e.source)
  }
  const col = new Map<string, number>()
  const visiting = new Set<string>()
  const resolve = (id: string): number => {
    const cached = col.get(id)
    if (cached != null) return cached
    if (visiting.has(id)) return 0   // guarda contra ciclo
    visiting.add(id)
    let c = 0
    for (const p of preds.get(id) ?? []) c = Math.max(c, resolve(p) + 1)
    visiting.delete(id)
    col.set(id, c)
    return c
  }
  for (const n of nodes) resolve(n.id)
  const byCol = new Map<number, string[]>()
  for (const n of nodes) {
    const c = col.get(n.id) ?? 0
    if (!byCol.has(c)) byCol.set(c, [])
    byCol.get(c)!.push(n.id)
  }
  const cols = Array.from(byCol.keys()).sort((a, b) => a - b)
  // Centraliza cada nível em torno do eixo médio dos irmãos — desenho
  // equilibrado (uma cadeia linear fica numa única linha/coluna; ramos saem
  // simétricos) em qualquer orientação.
  const maxRows = Math.max(1, ...cols.map((c) => byCol.get(c)!.length))
  cols.forEach((c, ci) => {
    const ids = byCol.get(c)!
    const offset = (maxRows - ids.length) / 2
    ids.forEach((id, ri) => {
      pos[id] = posiciona(ci, ri + offset, orientacao)
    })
  })
  return pos
}

// ── Travessia do grafo (base comum) ─────────────────────────────────────────
// Mapa de adjacência das arestas. `invertida = true` devolve PREDECESSORES.
// Não filtra ponta solta de propósito: é a mesma leitura crua que a detecção de
// ciclo sempre fez (o `liveLayout` tem regra própria — ver nota abaixo).
function adjacencia(edges: ArestaGrafo[], invertida = false): Map<string, string[]> {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    const de = invertida ? e.target : e.source
    const para = invertida ? e.source : e.target
    if (!adj.has(de)) adj.set(de, [])
    adj.get(de)!.push(para)
  }
  return adj
}

// Fecho transitivo a partir das sementes, andando por `adj`. DFS iterativo com
// Set de visitados (o mesmo desenho do detecção de ciclo — termina em grafo com
// ciclo). As SEMENTES não entram no resultado, a menos que um ciclo as devolva:
// "quem depende de mim" não me inclui, mas se eu dependo de mim mesmo, inclui.
function alcance(adj: Map<string, string[]>, sementes: string[]): Set<string> {
  const out = new Set<string>()
  const pilha = [...sementes]
  while (pilha.length) {
    const cur = pilha.pop()!
    for (const nxt of adj.get(cur) ?? []) {
      if (out.has(nxt)) continue
      out.add(nxt)
      pilha.push(nxt)
    }
  }
  return out
}

// Quem este nó ALIMENTA (sucessores diretos e indiretos) / de quem ele DEPENDE
// (predecessores diretos e indiretos). Funções puras — a base do realce de
// dependências dos dois canvas (spec de operação no nível de etapa, §6).
export function downstreamDe(edges: ArestaGrafo[], id: string): Set<string> {
  return alcance(adjacencia(edges), [id])
}
export function upstreamDe(edges: ArestaGrafo[], id: string): Set<string> {
  return alcance(adjacencia(edges, true), [id])
}

// Conectar source→target criaria um ciclo? Anda pelos SUCESSORES de `target`
// (arestas normais E de ramo — ambas são ordem de execução) procurando `source`.
// Espelho client-side do _check_circular do backend (BFS da F1): feedback na
// hora da conexão, em vez de só no 4xx do save (o backend segue como autoridade).
// Desde a F1 do realce usa o `alcance` comum — mesmo resultado da versão
// anterior (que também só achava `source` depois de ao menos uma aresta).
export function criaCiclo(edges: ArestaGrafo[], source: string, target: string): boolean {
  if (source === target) return true
  return alcance(adjacencia(edges), [target]).has(source)
}

// NOTA de propósito: o `liveLayout` NÃO passou a usar `adjacencia`. O mapa de
// predecessores dele é semeado com TODOS os nós do desenho e descarta aresta
// com ponta fora do desenho — regra de LAYOUT (nó novo, ainda sem aresta,
// precisa de coluna), não de travessia. Unificar mudaria o desenho salvo.

// ── Realce de dependências (spec de operação no nível de etapa, §6 — F1) ────
// Sentido do realce: o que ALIMENTA o foco ('tras'), o que DEPENDE dele
// ('frente') ou os dois lados ('ambos', o padrão da decisão 4 do §7).
export type SentidoCadeia = 'tras' | 'frente' | 'ambos'

// Aresta com identidade — o realce precisa acender a LINHA, não só as pontas.
export interface ArestaCadeia extends ArestaGrafo { id: string }

// O que o operador clicou: um nó ou uma linha.
export type FocoRealce = { tipo: 'no'; id: string } | { tipo: 'aresta'; id: string }

export interface Cadeia {
  /** ids dos nós ACESOS (inclui o foco) */
  nos: Set<string>
  /** ids das arestas ACESAS */
  arestas: Set<string>
  /** quantos itens o foco depende (para trás) — não conta o próprio foco */
  qtdTras: number
  /** quantos itens dependem do foco (para frente) — não conta o próprio foco */
  qtdFrente: number
}

// Cadeia acesa a partir do foco. Regras:
//  • nó em foco   → para trás parte dele, para frente também parte dele;
//  • linha em foco→ para trás parte da ORIGEM, para frente parte do DESTINO
//    (as duas pontas e a própria linha ficam acesas em qualquer sentido);
//  • aresta acesa é a que está DENTRO do cone (u→v com u no cone e v no cone),
//    nunca a que só encosta nele e vai embora para outro lado.
// Devolve null quando a aresta em foco não existe mais (refetch/exclusão) — o
// chamador trata como "sem realce", nunca como "tudo apagado".
export function cadeiaRealce(
  edges: ArestaCadeia[],
  foco: FocoRealce,
  sentido: SentidoCadeia,
): Cadeia | null {
  let origem: string
  let destino: string
  let arestaFoco: string | null = null
  if (foco.tipo === 'no') {
    origem = foco.id
    destino = foco.id
  } else {
    const a = edges.find((e) => e.id === foco.id)
    if (!a) return null
    arestaFoco = a.id
    origem = a.source
    destino = a.target
  }

  const tras = alcance(adjacencia(edges, true), [origem])
  const frente = alcance(adjacencia(edges), [destino])

  // Contadores HONESTOS do que está aceso: num nó, o próprio foco não conta
  // como dependência de si mesmo (ciclo não infla o número); numa linha, as
  // pontas contam — elas fazem parte do "antes"/"depois" daquela ligação.
  const qtdTras = foco.tipo === 'aresta'
    ? new Set([...tras, origem]).size
    : Array.from(tras).filter((id) => id !== origem).length
  const qtdFrente = foco.tipo === 'aresta'
    ? new Set([...frente, destino]).size
    : Array.from(frente).filter((id) => id !== destino).length

  const usaTras = sentido !== 'frente'
  const usaFrente = sentido !== 'tras'
  const coneTras = usaTras ? new Set([...tras, origem]) : new Set<string>()
  const coneFrente = usaFrente ? new Set([...frente, destino]) : new Set<string>()

  const nos = new Set<string>([...coneTras, ...coneFrente])
  // A linha clicada nunca apaga: as duas pontas dela ficam acesas mesmo quando
  // o sentido escolhido só olha para um lado.
  if (foco.tipo === 'aresta') { nos.add(origem); nos.add(destino) }

  const arestas = new Set<string>()
  for (const e of edges) {
    if (usaTras && tras.has(e.source) && coneTras.has(e.target)) arestas.add(e.id)
    if (usaFrente && frente.has(e.target) && coneFrente.has(e.source)) arestas.add(e.id)
  }
  if (arestaFoco) arestas.add(arestaFoco)

  return { nos, arestas, qtdTras, qtdFrente }
}
