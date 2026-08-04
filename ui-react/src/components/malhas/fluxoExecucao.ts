// Camada de FLUXO da visão de Execução da malha — a leitura de Control-M:
// olhando o desenho, dá para ver por onde a corrida do dia já passou, onde ela
// está agora e onde parou.
//
// A cor mora na LINHA, não só no card: o card diz o estado de UM pipeline, a
// linha diz o que aconteceu ENTRE dois. São perguntas diferentes — "esse job
// terminou?" e "a corrida chegou até aqui?".
//
// Regra de honestidade da casa (a mesma dos anéis de status da F9): nada de cor
// inventada. Sem execução registrada na data, a linha fica exatamente como no
// modo Montagem — cinza neutra. Verde aqui significa "o predecessor concluiu
// nesta data de referência", nunca "está tudo bem".
import type { Edge } from '@xyflow/react'
import type { ExecComponente } from './MalhaComponenteNodes'

/** Estado de uma PONTA da linha (pipeline ou componente). null = sem dado. */
export type EstadoElemento = 'concluido' | 'ativo' | 'bloqueado' | null

/** Estado do TRECHO entre duas pontas. */
export type EstadoFluxo = 'concluido' | 'ativo' | 'bloqueado' | 'inerte'

/** Status cru de etl_pipeline_execucao → estado da ponta.
 *
 *  PULADO fica NEUTRO de propósito: o dia foi barrado pela regra de agenda, o
 *  fluxo não passou por ali — mas também não quebrou, e pintá-lo de vermelho
 *  mandaria o plantonista investigar um sábado normal. */
export function estadoDoPipeline(status?: string | null): EstadoElemento {
  switch (status) {
    case 'SUCESSO':      return 'concluido'
    case 'EXECUTANDO':   return 'ativo'
    case 'FALHA':
    case 'NAO_LIBEROU':  return 'bloqueado'
    default:             return null   // AGUARDANDO_DEPENDENCIA, PULADO, sem linha
  }
}

/** Estado de um COMPONENTE a partir da camada de execução que ele já recebe.
 *
 *  O Início nunca é 'bloqueado': uma raiz que falhou não impede as outras de
 *  terem partido, e o vermelho pertence ao trecho daquela raiz. */
export function estadoDoComponente(e: ExecComponente | null): EstadoElemento {
  if (!e) return null
  switch (e.kind) {
    case 'inicio':
      if (e.raizes > 0 && e.sucesso === e.raizes) return 'concluido'
      if (e.sucesso > 0 || e.emCurso > 0 || e.falha > 0) return 'ativo'
      return null
    case 'aguarde':
      if (e.estado === 'bloqueado')  return 'bloqueado'
      if (e.estado === 'satisfeito') return 'concluido'
      return 'ativo'                 // aguardando: a corrida está parada AQUI
    case 'notificacao':
      return e.emitidaEm ? 'concluido' : null
    case 'fim':
      return e.concluidaEm ? 'concluido' : null
    default:
      return null
  }
}

/** Estado do trecho, pelas duas pontas.
 *
 *  Quem manda é o DESTINO: a pergunta que a linha responde é "a corrida chegou
 *  do outro lado?". Olhar só a origem erra o trecho que sai do Início — ele
 *  não tem status próprio, e a aresta para uma raiz que já concluiu ficaria
 *  cinza (visto ao semear o cenário no dev). O bloqueio vem antes de tudo:
 *  vermelho é o que o plantonista precisa achar primeiro. */
export function estadoDaAresta(origem: EstadoElemento,
                               destino: EstadoElemento): EstadoFluxo {
  if (origem === 'bloqueado' || destino === 'bloqueado') return 'bloqueado'
  if (destino === 'concluido') return 'concluido'  // a corrida atravessou aqui
  if (destino === 'ativo') return 'ativo'          // a frente da corrida está aqui
  // Predecessor pronto e o destino ainda sem partir: é exatamente onde a
  // corrida está avançando agora — a linha viva do painel.
  if (origem === 'concluido') return 'ativo'
  return 'inerte'
}

// Cores nos DOIS temas, alinhadas à legenda dos cards (verde = sucesso, azul =
// executando, vermelho = falha). Tons um passo mais escuros no claro para o
// traço fino manter contraste sobre o fundo do canvas.
const CORES: Record<Exclude<EstadoFluxo, 'inerte'>, { claro: string; escuro: string }> = {
  concluido: { claro: '#16a34a', escuro: '#4ade80' },
  ativo:     { claro: '#2563eb', escuro: '#60a5fa' },
  bloqueado: { claro: '#dc2626', escuro: '#f87171' },
}

export interface DecoracaoAresta {
  style: Record<string, unknown>
  animated: boolean
  cor: string | null
}

/** Traço + animação do trecho. `inerte` devolve `cor: null` — a linha fica
 *  como na Montagem, sem estilo nenhum por cima. */
export function decorarAresta(estado: EstadoFluxo, escuro: boolean): DecoracaoAresta {
  if (estado === 'inerte') return { style: {}, animated: false, cor: null }
  const cor = escuro ? CORES[estado].escuro : CORES[estado].claro
  return {
    // Só o trecho ATIVO anda: animação em tudo viraria ruído e o olho perderia
    // justamente a frente da corrida, que é o que o operador procura.
    animated: estado === 'ativo',
    cor,
    style: { stroke: cor, strokeWidth: estado === 'ativo' ? 3 : 2.5 },
  }
}

/** Aplica a camada de fluxo a uma aresta do canvas, preservando o que ela já
 *  carrega (o tracejado da linha compilada por outra malha, o rótulo do
 *  cadeado). Trecho inerte devolve a aresta INTOCADA — nem uma cópia — para o
 *  React Flow não remontar o que não mudou. */
export function arestaComFluxo(e: Edge, estado: EstadoFluxo, escuro: boolean): Edge {
  const d = decorarAresta(estado, escuro)
  if (!d.cor) return e
  const marcador = (e.markerEnd && typeof e.markerEnd === 'object')
    ? { ...e.markerEnd, color: d.cor }
    : e.markerEnd
  return {
    ...e,
    animated: d.animated,
    style: { ...e.style, ...d.style },
    markerEnd: marcador,
  }
}

/** Rótulo humano do trecho, para o title da linha e a legenda do rodapé. */
export const ROTULO_FLUXO: Record<EstadoFluxo, string> = {
  concluido: 'trecho concluído',
  ativo: 'em andamento',
  bloqueado: 'parado',
  inerte: 'sem execução na data',
}
