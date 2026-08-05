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
export type EstadoElemento = 'concluido' | 'ativo' | 'esperando' | 'bloqueado' | null

/** Estado do TRECHO entre duas pontas. */
export type EstadoFluxo = 'concluido' | 'ativo' | 'esperando' | 'bloqueado' | 'inerte'

/** Status cru de etl_pipeline_execucao → estado da ponta.
 *
 *  PULADO fica NEUTRO de propósito: o dia foi barrado pela regra de agenda, o
 *  fluxo não passou por ali — mas também não quebrou, e pintá-lo de vermelho
 *  mandaria o plantonista investigar um sábado normal.
 *
 *  F4 (§9.9): `AGUARDANDO_DEPENDENCIA` ganha o estado próprio **esperando**.
 *  Até esta fase ele devolvia `null` e a linha ficava IDÊNTICA à de quem não
 *  rodou — a diferença entre "ninguém pediu" e "está parado esperando alguém"
 *  sumia justamente no desenho que existe para mostrar onde a corrida parou. */
export function estadoDoPipeline(status?: string | null): EstadoElemento {
  switch (status) {
    case 'SUCESSO':                 return 'concluido'
    case 'EXECUTANDO':              return 'ativo'
    case 'AGUARDANDO_DEPENDENCIA':  return 'esperando'
    case 'FALHA':
    case 'NAO_LIBEROU':             return 'bloqueado'
    default:                        return null   // PULADO, sem linha
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
  // F4: o destino REGISTROU que está esperando. Vem antes do `origem ===
  // 'concluido'` de propósito: com o predecessor pronto, aquele trecho era
  // pintado de azul-animado ("avançando") quando o que existe do outro lado é
  // um pipeline PARADO — animação em cima de espera é a tela prometendo
  // movimento que não está acontecendo.
  if (destino === 'esperando') return 'esperando'
  // Predecessor pronto e o destino ainda sem linha nenhuma: é onde a corrida
  // está avançando agora — a linha viva do painel.
  if (origem === 'concluido') return 'ativo'
  return 'inerte'
}

// Cores nos DOIS temas, alinhadas à legenda dos cards (verde = sucesso, azul =
// executando, vermelho = falha). Tons um passo mais escuros no claro para o
// traço fino manter contraste sobre o fundo do canvas.
const CORES: Record<Exclude<EstadoFluxo, 'inerte'>, { claro: string; escuro: string }> = {
  concluido: { claro: '#16a34a', escuro: '#4ade80' },
  ativo:     { claro: '#2563eb', escuro: '#60a5fa' },
  // Âmbar é o "prazo/espera" desta camada inteira (Decisão 59) — a mesma cor
  // do anel de AGUARDANDO_DEPENDENCIA no card do nó.
  esperando: { claro: '#d97706', escuro: '#fbbf24' },
  bloqueado: { claro: '#dc2626', escuro: '#f87171' },
}

// Tracejado do `esperando`. Padrão DIFERENTE do '6 3' que marca a linha
// compilada por nó de outra malha (o cadeado, `depEdge`): duas coisas
// tracejadas na mesma tela precisam de um segundo canal, e aqui ele é o
// desenho do traço somado à cor âmbar.
const TRACO_ESPERANDO = '4 4'

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
    // justamente a frente da corrida, que é o que o operador procura. O
    // `esperando` NÃO anda — ele é, por definição, o trecho parado.
    animated: estado === 'ativo',
    cor,
    style: {
      stroke: cor,
      strokeWidth: estado === 'ativo' ? 3 : 2.5,
      ...(estado === 'esperando' ? { strokeDasharray: TRACO_ESPERANDO } : {}),
    },
  }
}

/** Rótulo humano do trecho, para o rótulo acessível da linha e a legenda do
 *  rodapé. Português de operador (Decisão 74): nenhum nome de máquina. */
export const ROTULO_FLUXO: Record<EstadoFluxo, string> = {
  concluido: 'trecho percorrido',
  ativo: 'em andamento',
  esperando: 'esperando outro pipeline',
  bloqueado: 'parado',
  inerte: 'sem execução na data',
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
    // F4: `ROTULO_FLUXO` estava DECLARADO e não era consumido em lugar nenhum
    // do front — a cor da linha era a única coisa a dizer o que ela significa,
    // e cor sozinha nunca é canal único nesta casa. `ariaLabel` é o que o React
    // Flow expõe no elemento da aresta (o `<path>` do SVG não aceita `title`).
    ariaLabel: `${e.source} → ${e.target}: ${ROTULO_FLUXO[estado]}`,
  }
}
