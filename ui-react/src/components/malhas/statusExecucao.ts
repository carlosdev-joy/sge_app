// Visão de execução da malha (F9, spec §4b): tipos do endpoint
// GET /malhas/{name}/execucao e estilos por status de etl_pipeline_execucao.
// O status vem CRU da tabela — o mapa cobre os seis conhecidos e degrada para
// neutro em status desconhecido (nunca esconde uma linha que o banco tem).

export interface ExecucaoPipeline {
  pipeline_name: string
  status: string
  inicio: string | null
  fim: string | null
  disparado_por: string | null
  motivo: string | null
  // F5 (D32) — aditivo, só em AGUARDANDO_DEPENDENCIA/NAO_LIBEROU: de QUEM a
  // corrida espera, pelo MESMO predicado do motor (port em api/services).
  faltantes?: string[]
}

export interface EventoGuardia {
  pipeline_name: string
  tipo: string
  criado_em: string
  mensagem: string | null
}

// F14/F15: evento de NÓ observador (marcador '#no:{id}' RESOLVIDO pelo
// servidor — o front nunca interpreta o marcador). tipo_no diz qual
// componente emitiu (notificacao | fim).
export interface EventoNo {
  no_id: number
  tipo_no: string
  tipo: string
  criado_em: string
  mensagem: string | null
}

export interface MalhaExecucaoApi {
  // A data efetivamente usada: a pedida, ou o ODATE corrente calculado no
  // servidor com a virada global (etl_app_config['dependencia_hora_virada']).
  data_referencia: string
  execucoes: ExecucaoPipeline[]
  eventos: EventoGuardia[]
  // F14 (aditivos): eventos dos nós observadores desta malha e a conclusão
  // da data (evento MALHA_CONCLUIDA do nó Fim). Chave ausente (API anterior)
  // degrada como array vazio/null — os componentes ficam neutros (F15).
  eventos_no?: EventoNo[]
  malha_concluida?: { em: string | null } | null
  // Deploy parcial (migration 067 ausente): arrays vazios + esta flag — a
  // malha continua abrindo e o aviso âmbar da F8 cobre a explicação.
  migration_067_pendente?: boolean
  // Deploy parcial (migration 075 ausente): eventos_no vazio + flag — o
  // resto da visão segue intacto (princípio 6 do desenho de componentes).
  migration_075_pendente?: boolean
}

export interface EstiloStatus {
  rotulo: string    // rótulo curto pt-BR (badge + legenda)
  anel: string      // anel de status por CIMA do nó (outline não briga com o
                    // ring azul de seleção do React Flow)
  badge: string     // pill pequena no canto do nó
  dot: string       // bolinha da legenda/badge
  animado?: boolean // EXECUTANDO pulsa
}

// Cores nos DOIS temas. Âmbar já é o warning do editor ("posições não
// salvas") — por isso o anel de AGUARDANDO_DEPENDENCIA é o mais discreto.
export const STATUS_EXECUCAO: Record<string, EstiloStatus> = {
  SUCESSO: {
    rotulo: 'sucesso',
    anel: 'outline outline-2 outline-offset-2 outline-green-500/70 dark:outline-green-400/60',
    badge: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-700',
    dot: 'bg-green-500',
  },
  FALHA: {
    rotulo: 'falha',
    anel: 'outline outline-2 outline-offset-2 outline-red-500/80 dark:outline-red-400/70',
    badge: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700',
    dot: 'bg-red-500',
  },
  EXECUTANDO: {
    rotulo: 'executando',
    anel: 'outline outline-2 outline-offset-2 outline-blue-500/80 dark:outline-blue-400/70',
    badge: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/60 dark:text-blue-300 dark:border-blue-700',
    dot: 'bg-blue-500',
    animado: true,
  },
  AGUARDANDO_DEPENDENCIA: {
    rotulo: 'aguardando dep.',
    anel: 'outline outline-2 outline-offset-2 outline-amber-400/50 dark:outline-amber-500/40',
    badge: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
    dot: 'bg-amber-500',
  },
  PULADO: {
    rotulo: 'pulado',
    anel: 'outline outline-2 outline-offset-2 outline-slate-400/60 dark:outline-slate-500/60',
    badge: 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600',
    dot: 'bg-slate-400',
  },
  NAO_LIBEROU: {
    rotulo: 'não liberou',
    anel: 'outline outline-2 outline-offset-2 outline-purple-500/70 dark:outline-purple-400/60',
    badge: 'bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-900/60 dark:text-purple-300 dark:border-purple-700',
    dot: 'bg-purple-500',
  },
  // F5 — a etapa está PARADA no portão, esperando um humano liberar. Existe só
  // no nível de ETAPA (nenhum status de etl_pipeline_execucao é este), por isso
  // fica FORA de ORDEM_LEGENDA: a legenda da malha não pode oferecer um estado
  // que nenhum pipeline dela vai ter. A legenda do canvas de Etapas o desenha
  // explicitamente.
  // Fúcsia porque as vizinhas já estão tomadas e a confusão sairia cara: azul é
  // "executando" (e em espera NÃO está executando), âmbar é "aguardando
  // dependência" (espera de máquina, não de gente) e roxo é "não liberou".
  // Pulsa como o "executando" — é o único jeito de a tela dizer, sem texto, que
  // aquilo está prendendo o processo AGORA.
  EM_ESPERA: {
    rotulo: 'em espera',
    anel: 'outline outline-2 outline-offset-2 outline-fuchsia-500/80 dark:outline-fuchsia-400/70',
    badge: 'bg-fuchsia-100 text-fuchsia-700 border-fuchsia-300 dark:bg-fuchsia-900/60 dark:text-fuchsia-300 dark:border-fuchsia-700',
    dot: 'bg-fuchsia-500',
    animado: true,
  },
}

// Ordem fixa da legenda no rodapé (leitura de painel: bons → ruins → neutros).
export const ORDEM_LEGENDA = [
  'SUCESSO', 'FALHA', 'EXECUTANDO', 'AGUARDANDO_DEPENDENCIA', 'PULADO', 'NAO_LIBEROU',
] as const

// Status desconhecido (o contrato manda o valor cru): estilo neutro com o
// próprio texto — o operador vê o que o banco tem, sem inventar cor.
export function estiloStatus(status: string): EstiloStatus {
  return STATUS_EXECUCAO[status] ?? {
    rotulo: status.toLowerCase(),
    anel: 'outline outline-2 outline-offset-2 outline-slate-400/60 dark:outline-slate-500/60',
    badge: 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600',
    dot: 'bg-slate-400',
  }
}

// Badge do tipo de evento da guardiã (JANELA_ESTOUROU / DATA_DIVERGENTE são os
// conhecidos da spec; MALHA_NOTIFICACAO / MALHA_CONCLUIDA são os POSITIVOS da
// F14 — os primeiros de conclusão, não de problema; tipo novo cai no neutro).
export function estiloEvento(tipo: string): string {
  switch (tipo) {
    case 'JANELA_ESTOUROU':
      return 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700'
    case 'DATA_DIVERGENTE':
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800'
    case 'MALHA_NOTIFICACAO':
      return 'bg-teal-100 text-teal-700 border-teal-300 dark:bg-teal-900/60 dark:text-teal-300 dark:border-teal-700'
    case 'MALHA_CONCLUIDA':
      return 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-700'
    // F5 — eventos da etapa em espera. Reusam esta tabela (e a fila do Teams da
    // guardiã) de propósito: nenhum canal novo. ESPERA_ESTOUROU é vermelho
    // porque o teto estourar interrompe a execução; os outros três são
    // informativos e não devem gritar no painel.
    case 'ESPERA_ETAPA':
      return 'bg-fuchsia-100 text-fuchsia-700 border-fuchsia-300 dark:bg-fuchsia-900/60 dark:text-fuchsia-300 dark:border-fuchsia-700'
    case 'ESPERA_LIBERADA':
      return 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-700'
    case 'ESPERA_CANCELADA':
      return 'bg-slate-200 text-slate-700 border-slate-400 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'
    case 'ESPERA_ESTOUROU':
      return 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700'
    // F5 — corrida que começou e cujo DagRun morreu sem fechar nada (órfã em
    // execução, detectada pela guardiã). Vermelho: enquanto ela existir, todos
    // os dependentes do dia ficam parados atrás dela.
    case 'EXECUCAO_ORFA':
      return 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700'
    default:
      return 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'
  }
}
