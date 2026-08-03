// Realce de dependências no canvas — CAMADA de leitura compartilhada pelo
// FluxoEditor (nó = etapa) e pelo MalhaEditor (nó = pipeline ou componente).
// F1 da spec de operação no nível de etapa (§6, Bloco D; decisão 4 do §7).
//
// Contrato de não-regressão: o hook NÃO toca no estado `nodes`/`edges` dos
// editores. Ele recebe os arrays e devolve CÓPIAS decoradas só para o
// <ReactFlow>. Seleção, arrastar, conectar, excluir, layout salvo e o `dirty`
// continuam olhando para os arrays originais — o realce é pintura, não estado
// do desenho.
import { useCallback, useMemo, useState } from 'react'
import { useReactFlow, type Edge, type Node } from '@xyflow/react'
import {
  cadeiaRealce, type Cadeia, type FocoRealce, type SentidoCadeia,
} from './layoutGrafo'

// ── Paleta do realce ────────────────────────────────────────────────────────
// Índigo: distante do azul de identidade da casa (#1A5FA8, seleção), do âmbar
// (pendência) e do verde/vermelho (status de execução) — não briga com nenhuma
// camada existente. Contraste sobre o fundo do canvas: 6,0:1 no claro
// (#4f46e5 sobre #f8fafc) e 6,3:1 no escuro (#818cf8 sobre #0f1117) — bem
// acima do 3:1 do WCAG 1.4.11 para elemento gráfico.
const ACENTO_CLARO = '#4f46e5'
const ACENTO_ESCURO = '#818cf8'

// Esmaecido do que está FORA da cadeia. A opacidade foi escolhida pelo pior
// caso de legibilidade, não pelo efeito visual: o texto do nó (ink #1e293b no
// claro, #e2e8f0 no escuro) precisa continuar legível. Medido nesta
// combinação: 4,5:1 no claro e 6,0:1 no escuro — acima do 4,5:1 do WCAG 1.4.3
// para texto normal. O grayscale tira a COR dos chips/ícones (é ele que faz o
// nó "sair de cena") sem clarear o texto.
const NO_ESMAECIDO = { opacity: 0.65, filter: 'grayscale(0.8)' }
// Linha fora da cadeia some quase por completo — é traço, não texto.
const ARESTA_ESMAECIDA = 0.15
// O rótulo da linha (Link_7, "sim"/"não") é enfeite do traço e acompanha ele,
// num patamar mais alto para não virar borrão ilegível.
const ROTULO_ESMAECIDO = 0.35
const ARESTA_ACESA_W = 2.5

export interface RealceDependencias {
  foco: FocoRealce | null
  sentido: SentidoCadeia
  isolar: boolean
  /** null = nada aceso (sem foco, ou o foco sumiu do desenho) */
  cadeia: Cadeia | null
  /** rótulo do que está em foco — o id do nó ou "origem → destino" da linha */
  rotuloFoco: string | null
  focarNo: (id: string) => void
  focarAresta: (id: string) => void
  mudarSentido: (s: SentidoCadeia) => void
  alternarIsolar: () => void
  limpar: () => void
  /** nós decorados para o <ReactFlow> (idênticos ao original sem realce) */
  nodesRealce: Node[]
  /** arestas decoradas para o <ReactFlow> (idênticas ao original sem realce) */
  edgesRealce: Edge[]
}

export function useRealceDependencias(
  nodes: Node[],
  edges: Edge[],
  escuro: boolean,
): RealceDependencias {
  const rf = useReactFlow()
  const [foco, setFoco] = useState<FocoRealce | null>(null)
  const [sentido, setSentido] = useState<SentidoCadeia>('ambos')
  const [isolar, setIsolar] = useState(false)

  // Validade do foco em separado: nó/linha que saiu do desenho (exclusão,
  // refetch, troca de malha) apaga o realce em vez de deixar "tudo apagado e
  // nada aceso". Fica num memo próprio de propósito — arrastar um nó recria o
  // array `nodes` a cada frame, e um BOOLEAN estável impede que a travessia
  // seja refeita no meio do arrasto.
  const focoExiste = useMemo(() => {
    if (!foco) return false
    return foco.tipo === 'no'
      ? nodes.some((n) => n.id === foco.id)
      : edges.some((e) => e.id === foco.id)
  }, [foco, nodes, edges])

  const cadeia = useMemo(
    () => (foco && focoExiste ? cadeiaRealce(edges, foco, sentido) : null),
    [foco, focoExiste, sentido, edges],
  )

  const rotuloFoco = useMemo(() => {
    if (!foco || !cadeia) return null
    if (foco.tipo === 'no') return foco.id
    const a = edges.find((e) => e.id === foco.id)
    return a ? `${a.source} → ${a.target}` : null
  }, [foco, cadeia, edges])

  const limpar = useCallback(() => { setFoco(null); setIsolar(false) }, [])

  // Clicar de novo no MESMO item apaga (o gesto é o próprio interruptor). O
  // "isolar" nunca liga sozinho — decisão 4: esconder é sempre sob demanda.
  const focarNo = useCallback((id: string) => {
    setFoco((f) => (f && f.tipo === 'no' && f.id === id ? null : { tipo: 'no', id }))
  }, [])
  const focarAresta = useCallback((id: string) => {
    setFoco((f) => (f && f.tipo === 'aresta' && f.id === id ? null : { tipo: 'aresta', id }))
  }, [])
  const mudarSentido = useCallback((s: SentidoCadeia) => setSentido(s), [])

  // Ao ESCONDER o resto, reenquadra: numa malha grande a cadeia isolada pode
  // ficar fora da tela e o operador veria um canvas vazio. Ao voltar, reenquadra
  // de novo sobre o desenho inteiro.
  const alternarIsolar = useCallback(() => {
    setIsolar((v) => !v)
    setTimeout(() => rf.fitView({ padding: 0.25, duration: 300 }), 60)
  }, [rf])

  const acento = escuro ? ACENTO_ESCURO : ACENTO_CLARO

  const nodesRealce = useMemo(() => {
    if (!cadeia) return nodes
    return nodes.map((n) => {
      if (cadeia.nos.has(n.id)) return n            // aceso = intocado
      if (isolar) return { ...n, hidden: true }
      return { ...n, style: { ...n.style, ...NO_ESMAECIDO } }
    })
  }, [nodes, cadeia, isolar])

  const edgesRealce = useMemo(() => {
    if (!cadeia) return edges
    return edges.map((e) => {
      if (cadeia.arestas.has(e.id)) {
        // Linha acesa engrossa. A COR só é forçada quando a aresta não tem cor
        // própria (dependência simples): o ramo de decisão continua verde/slate
        // /cor do caso — aquela cor é significado, não enfeite.
        const temCor = !!e.style?.stroke
        const marcador = !temCor && e.markerEnd && typeof e.markerEnd === 'object'
          ? { ...e.markerEnd, color: acento }
          : e.markerEnd
        return {
          ...e,
          style: { ...e.style, strokeWidth: ARESTA_ACESA_W, ...(temCor ? {} : { stroke: acento }) },
          markerEnd: marcador,
          zIndex: 10,
        }
      }
      if (isolar) return { ...e, hidden: true }
      return {
        ...e,
        style: { ...e.style, opacity: ARESTA_ESMAECIDA },
        labelStyle: { ...e.labelStyle, opacity: ROTULO_ESMAECIDO },
        labelBgStyle: { ...e.labelBgStyle, opacity: ROTULO_ESMAECIDO },
      }
    })
  }, [edges, cadeia, isolar, acento])

  return {
    foco, sentido, isolar, cadeia, rotuloFoco,
    focarNo, focarAresta, mudarSentido, alternarIsolar, limpar,
    nodesRealce, edgesRealce,
  }
}
