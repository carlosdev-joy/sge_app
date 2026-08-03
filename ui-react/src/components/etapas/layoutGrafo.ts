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

// Conectar source→target criaria um ciclo? Anda pelos SUCESSORES de `target`
// (arestas normais E de ramo — ambas são ordem de execução) procurando `source`.
// Espelho client-side do _check_circular do backend (BFS da F1): feedback na
// hora da conexão, em vez de só no 4xx do save (o backend segue como autoridade).
export function criaCiclo(edges: ArestaGrafo[], source: string, target: string): boolean {
  if (source === target) return true
  const succ = new Map<string, string[]>()
  for (const e of edges) {
    if (!succ.has(e.source)) succ.set(e.source, [])
    succ.get(e.source)!.push(e.target)
  }
  const stack = [target]
  const seen = new Set<string>()
  while (stack.length) {
    const cur = stack.pop()!
    if (cur === source) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const nxt of succ.get(cur) ?? []) stack.push(nxt)
  }
  return false
}
