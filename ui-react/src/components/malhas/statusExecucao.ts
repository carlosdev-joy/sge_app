// Visão de execução da malha (F9, spec §4b): tipos do endpoint
// GET /malhas/{name}/execucao e estilos por status de etl_pipeline_execucao.
// O status vem CRU da tabela — o mapa cobre os seis conhecidos e degrada para
// neutro em status desconhecido (nunca esconde uma linha que o banco tem).
//
// F4 (spec-malha-execucao §9.1/§9.3): entra o domínio da CORRIDA — o CICLO da
// malha, que é outra pergunta e por isso ganha um mapa PARALELO
// (`STATUS_CORRIDA`), nunca um reuso de `STATUS_EXECUCAO` (Decisão 46):
// reusar faria `ABERTA` herdar o estilo de `EXECUTANDO` e `EXPIRADA` /
// `SEM_TRABALHO` caírem no cinza do `default`, que é mentira de domínio.
import type { LucideIcon } from 'lucide-react'
import {
  Activity, AlertTriangle, Ban, CalendarX, CheckCircle2, CircleSlash, Clock,
  Hourglass, Moon, TimerOff, XCircle,
} from 'lucide-react'
import type {
  CorridaApi, CorridaCabecalho, CorridaEsperadaApi, HistoricoCorridas,
  PendenteCorrida, TipicosApi,
} from '../../types'
import {
  diaCurto, duracaoEntre, decorridoMin, horaCurta, carimboLongo, textoDuracao,
} from './tempoCorrida'
// F12 (Decisão 68) — o histórico factual vive num módulo PURO próprio, e este
// arquivo só o consome. `motivoLimpo` e `textoOrigem` mudaram de casa junto:
// eles são lidos também pelo `title` dos blocos da faixa, e duas cópias da
// mesma limpeza de texto é como a faixa e o card passam a transcrever motivos
// diferentes da mesma corrida.
import {
  motivoLimpo, pessoaQueFechou, textoCorridaAnterior, textoDiaAtipico,
  textoFalhasRecentes, textoOrigem,
} from './historicoCorridas'

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

/** F10 — o estado da FILA DE AVISO de um evento (`notificado_em`, coluna que
 *  existe desde a 067 e nunca foi lida pela tela). Três leituras, e as três
 *  precisam continuar distinguíveis:
 *
 *    • chave AUSENTE (`undefined`) — o banco não tem a coluna: "não perguntei";
 *    • `null` — o evento está na fila e **ninguém foi avisado ainda**;
 *    • texto  — avisado naquele instante.
 *
 *  Confundir `undefined` com `null` acenderia o banner vermelho da Decisão 66
 *  em toda malha de um banco antigo, que é o alarme falso da Decisão 26 com
 *  roupa nova. */
export interface ComNotificacao {
  notificado_em?: string | null
}

export interface EventoGuardia extends ComNotificacao {
  pipeline_name: string
  tipo: string
  criado_em: string
  mensagem: string | null
}

// F14/F15: evento de NÓ observador (marcador '#no:{id}' RESOLVIDO pelo
// servidor — o front nunca interpreta o marcador). tipo_no diz qual
// componente emitiu (notificacao | fim).
export interface EventoNo extends ComNotificacao {
  no_id: number
  tipo_no: string
  tipo: string
  criado_em: string
  mensagem: string | null
}

export interface MalhaExecucaoApi {
  // A data efetivamente usada: a pedida, ou o ODATE corrente calculado no
  // servidor com a virada global (etl_app_config['dependencia_hora_virada']).
  // Com a lente `?corrida={id}` (F4) ela passa a ser a da PRÓPRIA corrida — e
  // é aí que some a divergência entre o que o painel mostra e o que o disparo
  // usou.
  data_referencia: string
  execucoes: ExecucaoPipeline[]
  eventos: EventoGuardia[]
  // F4: o CICLO desta lente. Ausente = malha sem corrida registrada, banco sem
  // a 085 ou API anterior à fase — os três degradam no MESMO lugar (D41).
  corrida?: CorridaApi
  // F4: a 085 não está neste banco. É o que faz o painel calar JUNTO com o
  // card: sem ela, nem um nem outro pode afirmar "concluída".
  migration_085_pendente?: boolean
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
  // F7: os eventos DO CICLO (MALHA_ATRASADA, MALHA_EXPIRADA, o crédito de
  // retenção…). Até a F7 eles eram gravados e nunca chegavam à tela — a
  // tabela de eventos é chaveada por pipeline e a corrida não é um pipeline.
  // Chave ausente (API anterior, ou lente sem corrida) degrada como vazio.
  eventos_corrida?: EventoCorrida[]
  /** F4/F10 — o operador navegou por DATA e aquele dia teve mais de uma
   *  corrida. Nesse caso o bloco `corrida` é OMITIDO de propósito (descrever
   *  uma corrida sobre a lista do dia inteiro é a mesma mentira que a fase
   *  mata) e esta chave diz quantas foram. A tela não pode se limitar a calar:
   *  ela diz "este dia teve N corridas — escolha uma" e oferece o seletor. */
  corridas_no_dia?: number
  /** F10 — existe canal do Teams configurado? Separa as DUAS leituras de
   *  `notificado_em` nulo: "o webhook falhou e o aviso está preso" (vermelho,
   *  alguém precisa agir) e "não há destino, então nunca houve fila" (nada a
   *  fazer). Sem ela, toda instalação sem webhook acende o banner vermelho
   *  para sempre — o alarme falso crônico da Decisão 26. Chave ausente = a API
   *  não respondeu; mantém o comportamento anterior. */
  teams_configurado?: boolean
  /** F12 (Decisão 64) — a duração TÍPICA de cada membro do snapshot, com o `n`
   *  junto e o piso `n ≥ 5` já aplicado no servidor. Chave AUSENTE = não
   *  apurei (API anterior à fase, erro de leitura, ou lente sem corrida): o
   *  painel volta a mostrar só o decorrido, que é o que ele mostra hoje. */
  tipicos?: TipicosApi
  /** F12 (Decisão 68) — o histórico FACTUAL desta malha, RELATIVO À LENTE: a
   *  corrida anterior é a anterior à que esta resposta descreve. Chave
   *  AUSENTE = dia 1 (nenhuma corrida fechada antes desta), API anterior à
   *  fase, ou erro de leitura — e aí nenhuma frase de histórico existe. */
  historico?: HistoricoCorridas
}

/** Evento do CICLO — sem `pipeline_name`, porque o sujeito é a corrida. */
export interface EventoCorrida extends ComNotificacao {
  tipo: string
  criado_em: string
  mensagem: string | null
}

/** GET /malhas/{name}/corridas (F3/F4) — os ciclos, do mais recente para o
 *  mais antigo. `aberta` vem SEPARADO porque a corrida em voo é a única sobre
 *  a qual existe um gesto possível, e ela pode ser de um ODATE antigo (ou cair
 *  fora da página) — escondê-la seria esconder o botão que destrava a malha. */
export interface CorridasResposta {
  malha_name: string
  corridas: CorridaCabecalho[]
  aberta: CorridaCabecalho | null
  total?: number
  data_referencia?: string | null
  migration_085_pendente?: boolean
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
    // F4 (Decisão 47) — os desfechos da CORRIDA. Sem estes casos o evento mais
    // grave do produto cairia no `default` cinza do painel, com a mesma cor de
    // um aviso informativo. A partição é a MESMA do card do Teams
    // (dags/utils/ds_teams.py:64-74) e a MESMA da Decisão 59: o painel não
    // pode discordar do celular.
    case 'MALHA_FALHOU':
    case 'MALHA_EXPIRADA':
    case 'MALHA_ABORTADA':
      return 'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700'
    case 'MALHA_ATRASADA':
    case 'MALHA_CANCELADA':
    case 'MALHA_REPROCESSO':
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800'
    // Sem trabalho hoje não é incidente (Decisões 26/27: alarme falso semanal
    // treina o operador a ignorar o alarme) — e é o ÚNICO slate desta camada.
    case 'MALHA_SEM_TRABALHO':
      return 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'
    // F7 — o crédito de retenção. Azul e não âmbar: nada aconteceu de errado;
    // é o REGISTRO de por que o limite mudou de lugar. Ele existe exatamente
    // para que a barra que anda para trás tenha uma explicação nomeada
    // (Decisão 61), e pintá-lo de alarme diria o contrário do que ele é.
    case 'MALHA_TETO_CREDITADO':
      return 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800'
    default:
      return 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'
  }
}

// ═══════════════ A CORRIDA — o CICLO da malha (F4, §9.1/§9.3) ═══════════════
// O card parava de mentir aqui: até esta fase o status da malha era "a execução
// mais recente entre os membros", e por isso `CARGA_A` falhando às 03:00 com
// `CARGA_B` concluindo às 03:40 aparecia como **sucesso · CARGA_B**. Agora o
// status é o do CICLO, e o eixo de SAÚDE (Decisão 11) manda na cor enquanto ele
// está aberto: "em andamento" com falha já detectada é VERMELHO, não azul —
// descobrir a falha só no fechamento, às 05:00, é depois do SLA.

export interface EstiloCorrida {
  /** Rótulo pt-BR — a única fonte da palavra "concluída" na tela (D75/#15). */
  rotulo: string
  /** Pill de estado, par claro+escuro obrigatório (docs/ui-temas-cores.md). */
  chip: string
  /** Bolinha — o canal redundante à cor, que a casa exige (SupervisaoCard). */
  dot: string
  /** Ícone: o terceiro canal. Os três vermelhos têm ícones DIFERENTES, para
   *  quem não distingue vermelho de âmbar continuar distinguindo os estados. */
  Icone: LucideIcon
  /** `animate-pulse` — só o dot de ABERTA (Decisão 75/#13). */
  animado?: boolean
}

// A partição de cor é "isso me chama às 3h?" (Decisão 59):
//   vermelho CHEIO    = acabou mal, ação agora     (FALHA, EXPIRADA, ABORTADA)
//   vermelho CONTORNO = falha dentro de corrida VIVA, com "ainda rodando"
//   âmbar             = prazo / atípico / humano   (ATRASADA, SEM_PROGRESSO,
//                                                   CANCELADA)
//   slate             = não havia trabalho         (SEM_TRABALHO) — e só ele
const CHIP_VERMELHO_CHEIO =
  'bg-red-100 text-red-700 border-red-300 dark:bg-red-900/60 dark:text-red-300 dark:border-red-700'
const CHIP_VERMELHO_CONTORNO =
  'bg-red-50 text-red-700 border-red-400 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700'
const CHIP_AMBAR =
  'bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800'
const CHIP_SLATE =
  'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600'

export const STATUS_CORRIDA: Record<string, EstiloCorrida> = {
  ABERTA: {
    rotulo: 'em andamento',
    chip: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/60 dark:text-blue-300 dark:border-blue-700',
    dot: 'bg-blue-500',
    Icone: Activity,
    animado: true,
  },
  CONCLUIDA: {
    rotulo: 'concluída',
    chip: 'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/60 dark:text-green-300 dark:border-green-700',
    dot: 'bg-green-500',
    Icone: CheckCircle2,
  },
  FALHA: {
    rotulo: 'falhou',
    chip: CHIP_VERMELHO_CHEIO,
    dot: 'bg-red-500',
    Icone: XCircle,
  },
  EXPIRADA: {
    rotulo: 'encerrada sem terminar',
    chip: CHIP_VERMELHO_CHEIO,
    dot: 'bg-red-500',
    Icone: TimerOff,
  },
  ABORTADA: {
    rotulo: 'não chegou a começar',
    chip: CHIP_VERMELHO_CHEIO,
    dot: 'bg-red-500',
    Icone: CircleSlash,
  },
  SEM_TRABALHO: {
    rotulo: 'sem trabalho hoje',
    chip: CHIP_SLATE,
    dot: 'bg-slate-400',
    Icone: Moon,
  },
  CANCELADA: {
    // Âmbar de CONTORNO, nunca cinza: é ação humana, e ela precisa ser
    // explicável no fechamento do mês (Decisão 67).
    rotulo: 'encerrada pelo operador',
    chip: CHIP_AMBAR,
    dot: 'bg-amber-500',
    Icone: Ban,
  },
}

/** F9 (Decisão 58) — o estado DERIVADO `não abriu`.
 *
 *  Fica FORA de `STATUS_CORRIDA` de propósito: aquele mapa é o domínio da
 *  coluna `status` de `etl_malha_execucao`, e "não abriu" é a ausência de
 *  linha, não um valor dela. Misturá-los convidaria alguém a procurar
 *  `'nao_abriu'` no banco — onde ele nunca vai estar.
 *
 *  Âmbar, e não vermelho: pela partição da Decisão 59, vermelho CHEIO é
 *  "acabou mal" e este ciclo não chegou a começar. Âmbar é a faixa de
 *  "prazo/atípico/humano", que é exatamente onde este estado mora. */
export const ESTILO_NAO_ABRIU: EstiloCorrida = {
  rotulo: 'não abriu',
  chip: CHIP_AMBAR,
  dot: 'bg-amber-500',
  Icone: CalendarX,
}

/** A SAÚDE manda na cor quando o ciclo está ABERTO (Decisão 11). O rótulo é
 *  COMPOSTO — "em andamento · com falha (ainda rodando)" —, porque o estado do
 *  ciclo e o do trabalho são duas afirmações, e omitir a segunda é o card
 *  esperando o fechamento para contar o incêndio. */
export const SAUDE_CORRIDA: Record<string, Omit<EstiloCorrida, 'rotulo'> & {
  sufixo: string
}> = {
  OK: {
    sufixo: '',
    chip: STATUS_CORRIDA.ABERTA.chip,
    dot: STATUS_CORRIDA.ABERTA.dot,
    Icone: Activity,
    animado: true,
  },
  COM_FALHA: {
    sufixo: 'com falha (ainda rodando)',
    chip: CHIP_VERMELHO_CONTORNO,
    dot: 'bg-red-500',
    Icone: AlertTriangle,
  },
  ATRASADA: {
    sufixo: 'fora do prazo',
    chip: CHIP_AMBAR,
    dot: 'bg-amber-500',
    Icone: Clock,
  },
  SEM_PROGRESSO: {
    // Nunca slate: "nada se moveu há 40 min" com membro vivo é o sintoma nº 1
    // da execução órfã, a classe de defeito mais cara do produto.
    sufixo: 'sem sinal',
    chip: CHIP_AMBAR,
    dot: 'bg-amber-500',
    Icone: Hourglass,
  },
}

/** Status + saúde → estilo. Status fora do domínio degrada para neutro com o
 *  próprio texto: o banco pode ganhar um desfecho antes desta tela. */
export function estiloCorrida(status: string,
                              saude?: string | null): EstiloCorrida {
  const base = STATUS_CORRIDA[status] ?? {
    rotulo: String(status || '').toLowerCase().replace(/_/g, ' '),
    chip: CHIP_SLATE,
    dot: 'bg-slate-400',
    Icone: Activity,
  }
  if (status !== 'ABERTA' || !saude) return base
  const s = SAUDE_CORRIDA[saude]
  if (!s) return base
  return {
    rotulo: s.sufixo ? `${base.rotulo} · ${s.sufixo}` : base.rotulo,
    chip: s.chip,
    dot: s.dot,
    Icone: s.Icone,
    animado: s.animado,
  }
}

/** O ESTADO da corrida como a tela o anuncia: status + saúde + o "há 40 min"
 *  do sinal perdido, num objeto só.
 *
 *  Existe como função exportada porque DOIS consumidores precisam da mesma
 *  frase — o `CorridaBadge` (que só recebe a corrida) e o `resumoCorrida` (que
 *  monta o card inteiro). Duas derivações do mesmo estado divergiriam no dia em
 *  que alguém mexesse numa delas, e o defeito apareceria como a pílula dizendo
 *  "em andamento" ao lado de um texto dizendo "sem sinal há 40 min".
 *
 *  Os minutos vêm do BANCO (`sem_sinal_min`, já subtraído lá): é medida de
 *  relógio, e nenhum relógio local participa. */
export function estadoDaCorrida(c: CorridaApi): EstiloCorrida {
  const estilo = estiloCorrida(c.status, c.saude)
  if (c.status !== 'ABERTA' || c.saude !== 'SEM_PROGRESSO' || !c.sem_sinal_min) {
    return estilo
  }
  return { ...estilo, rotulo: `${estilo.rotulo} há ${textoDuracao(c.sem_sinal_min)}` }
}

/** Rótulo curto de uma corrida da LISTA (`GET /corridas`) — o que o ◀ ▶ diz
 *  antes de o operador clicar. Só o cabeçalho: a lista não traz saúde nem
 *  denominador, e inventar "0 de 0" aqui seria o card mentindo com dado que
 *  não veio. */
export function rotuloCorrida(c: CorridaCabecalho): string {
  const dia = diaCurto(c.data_referencia) ?? c.data_referencia
  const nome = c.sequencia > 1 ? `${c.sequencia}ª corrida de ${dia}`
    : `corrida de ${dia}`
  const estado = estiloCorrida(c.status).rotulo
  const hora = horaCurta(c.aberta_em)
  return `${nome} · ${estado}${hora ? ` · aberta ${hora}` : ''}`
}

/** `aberta_por` / `fechada_por` são formato de MÁQUINA — `'inicio:#12'`,
 *  `'manual:C123456'`, `'guardia'`, `'no_fim'`. Nenhum deles chega cru à tela
 *  (Decisão 74), e o `#` não aparece na interface: numa malha diária "#12"
 *  lê-se como "12ª tentativa hoje", que é falso.
 *
 *  A tradução DEFINITIVA é do servidor (Decisão 43) e chega com a faixa da
 *  F10; até lá o front traduz o que ele próprio exibe, porque a alternativa é
 *  publicar o nome de máquina agora. */
export function quemFez(v: string | null | undefined): string | null {
  const s = String(v ?? '').trim()
  if (!s) return null
  if (s.startsWith('manual:')) return s.slice('manual:'.length).trim() || null
  if (s.startsWith('inicio')) return 'o agendamento do Início'
  if (s.startsWith('guardia')) return 'o monitor automático'
  if (s === 'no_fim') return 'o nó Fim'
  if (s.startsWith('implicita')) return 'a primeira raiz a partir'
  // Valor que esta tela não conhece: mostra o que o banco tem, sem o `#`.
  return s.split('#')[0].replace(/[:_\s]+$/, '').trim() || null
}

/** Decisão 68 — o `SEM_TRABALHO` que sobe para ÂMBAR, e só ele.
 *
 *  O estado continua sendo "sem trabalho hoje": o que muda é a COR e a frase
 *  ao lado ("as últimas 4 terças tiveram trabalho"). O ícone segue sendo a lua
 *  de propósito — o fato é o mesmo, e trocar o ícone diria que aconteceu outra
 *  coisa. Quem carrega o segundo canal (a regra da casa: cor nunca é canal
 *  único) é a frase, que o card e a faixa escrevem logo abaixo.
 *
 *  ⚠️ Isto NÃO acontece no sábado da mesma malha, e é a metade que importa:
 *  um alarme de sábado toda semana treina o operador a ignorar o alarme
 *  (Decisão 26) — e aí ele ignora também a terça. Quem separa os dois casos é
 *  o `atipico` do servidor, comparando com o MESMO dia da semana. */
export function estiloDiaAtipico(base: EstiloCorrida): EstiloCorrida {
  return { ...base, chip: CHIP_AMBAR, dot: 'bg-amber-500' }
}

/** Classe de pendência → português de reunião (Decisão 74). Nenhum nome de
 *  máquina sobrevive à tradução: "a malha expirou por quiescência com 2
 *  membros dispensados" não é frase que alguém leve para uma reunião. */
export const ROTULO_PENDENCIA: Record<string, string> = {
  falhou: 'falhou',
  orfa: 'terminou sem registrar o fim',
  nao_liberou: 'esperando outro pipeline',
  nao_partiu: 'não chegou a iniciar',
}

// ═════════════════ F10 — o painel que responde "o que está travando" ═════════

/** As classes que ENTRAM na aba `Travando` — as mesmas que o servidor conta em
 *  `membros_travados` (Decisão 54). `nao_partiu` fica FORA de propósito: às
 *  01:10 ele é o estado normal de todo membro de toda corrida recém-aberta, e
 *  chipá-lo de vermelho seria um alarme falso por noite, em toda malha. Ele
 *  aparece na aba como linha quieta, com o número e sem cor. */
export const CLASSES_TRAVADAS = new Set(['falhou', 'orfa', 'nao_liberou'])

/** A aba com que o painel ABRE (Decisão 62).
 *
 *  Quando o operador abre o painel às 3h, as perguntas "está rodando?" e "em
 *  que pé está?" já foram respondidas pelo card ou pelo alarme que o trouxe
 *  até aqui — obrigá-lo a clicar em `Travando` é um clique a mais na única
 *  coisa que ele veio fazer. Corrida fechada não tem "agora" nem "travando":
 *  o que resta a ler é o histórico do ciclo. */
export function abaInicialDaCorrida(
  c: CorridaApi | null | undefined,
): 'agora' | 'travando' | 'eventos' {
  if (!c || c.status !== 'ABERTA') return 'eventos'
  if (c.saude === 'COM_FALHA' || c.saude === 'ATRASADA'
      || c.saude === 'SEM_PROGRESSO') return 'travando'
  return 'agora'
}

/** O RAIO DE ALCANCE de um travado, em texto (Decisão 63).
 *
 *  `↳ falhou: CARGA_A` não diz se atrás dela há 1 ou 17 pipelines parados, nem
 *  se algum é `ALTA` — e é exatamente isso que decide acordar alguém. Os dois
 *  números vêm do SERVIDOR (o fecho é sobre a dependência COMPILADA, não sobre
 *  as arestas do desenho), e `null` ali significa "não apurei": nesse caso a
 *  frase some inteira, em vez de publicar "0 parados atrás" como se fosse
 *  medida. */
export function textoAlcance(p: PendenteCorrida): string | null {
  if (p.alcance === null || p.alcance === undefined) return null
  if (p.alcance === 0) return 'nenhum pipeline parado atrás'
  const base = `${p.alcance} ${p.alcance === 1 ? 'pipeline parado' : 'pipelines parados'} atrás`
  return p.alcance_alta ? `${base} (${p.alcance_alta} de criticidade alta)` : base
}

/** Quanto tempo um aviso pode ficar na fila antes de virar banner vermelho.
 *
 *  A guardiã drena a fila a cada ciclo (5 min). SEM esta carência, toda falha
 *  de malha acenderia "ninguém foi avisado" por alguns minutos e apagaria
 *  sozinha — o alarme falso que a Decisão 26 proíbe, e que treinaria o
 *  operador a ignorar justamente o banner que existe para o caso em que o
 *  webhook está com 401 e a malha falha em silêncio para todo mundo. */
export const CARENCIA_FILA_AVISO_MIN = 10

/** Os tipos que a guardiã SEMPRE notifica (Decisão 48). `MALHA_CONCLUIDA` é
 *  opt-in e `MALHA_SEM_TRABALHO` nem vira card — nenhum dos dois pendurado na
 *  fila é notícia, e acusá-los aqui produziria banner vermelho por sucesso. */
const TIPOS_QUE_SEMPRE_AVISAM = new Set([
  'MALHA_FALHOU', 'MALHA_EXPIRADA', 'MALHA_ABORTADA', 'MALHA_ATRASADA',
  'MALHA_CANCELADA', 'MALHA_REPROCESSO',
])

/** Decisão 66 — o aviso que está preso na fila do Teams.
 *
 *  É o PIOR cenário de plantão: webhook com 401 por URL rotacionada, a guardiã
 *  loga e segue, e a malha falha em silêncio para todo mundo menos para quem
 *  já está com esta tela aberta.
 *
 *  ⚠️ Relógios: a carência é medida entre `criado_em` e `apurado_em`, que são
 *  os DOIS do banco (Decisão 60) — comparar `criado_em` com `Date.now()` daria
 *  "preso há -3h" com o desvio medido no dev, e o banner nunca acenderia. */
export function avisoPresoNaFila(
  eventos: (ComNotificacao & { tipo: string; criado_em: string })[],
  apuradoEm: string | null | undefined,
  /** Existe canal do Teams configurado? `false` = não há destino, então nunca
   *  houve fila — e sem isto QUALQUER instalação sem webhook (o dev inclusive)
   *  acenderia o banner vermelho permanentemente. `undefined` = a API não
   *  respondeu; mantém o comportamento anterior em vez de calar por suposição. */
  temCanal?: boolean,
): { desde: string; quantos: number } | null {
  // Sem destino não há fila: o que está sem carimbo nunca foi enfileirado, e
  // acusar isso todo dia é o alarme falso que a Decisão 26 proíbe — na primeira
  // semana o operador aprende a ignorar o banner, e aí ele deixa de servir para
  // o webhook que quebrou de verdade.
  if (temCanal === false) return null
  let desde: string | null = null
  let quantos = 0
  for (const ev of eventos) {
    // `undefined` = a coluna não veio (banco sem ela): não se acusa o que não
    // se perguntou. Só `null` é "está na fila".
    if (ev.notificado_em !== null) continue
    if (!TIPOS_QUE_SEMPRE_AVISAM.has(ev.tipo)) continue
    const idade = duracaoEntre(ev.criado_em, apuradoEm)
    if (idade === null || idade < CARENCIA_FILA_AVISO_MIN) continue
    quantos += 1
    if (desde === null || ev.criado_em < desde) desde = ev.criado_em
  }
  return desde === null ? null : { desde, quantos }
}

/** O que a `ui/Progress` desenha, já resolvido — segmentos, denominador e os
 *  dois textos acessíveis. Sai daqui (e não do JSX) pela mesma razão que a
 *  cor da faixa: card e painel têm de desenhar a MESMA barra a partir do
 *  MESMO agregado (D75/#5). */
export interface BarraCorrida {
  segmentos: {
    chave: string
    valor: number
    cor: string
    rotulo: string
    animado?: boolean
    hachurado?: boolean
  }[]
  /** Denominador: `membros_total` do snapshot, que NÃO ENCOLHE (Decisão 52). */
  total: number
  /** O `x` do `x de y` — o mesmo número que o olho lê ao lado da barra. */
  valorAtual: number
  ariaLabel: string
  /** O que o leitor de tela ANUNCIA. Existe para calar o cálculo automático de
   *  `valuenow/valuemax`, que anunciaria "57%" — o percentual de CONTAGEM que a
   *  Decisão 56 proíbe em toda superfície, entrando pela porta da
   *  acessibilidade. Nenhuma das duas metades pode produzir "%". */
  valorTexto: string
}

// A ordem dos segmentos é FIXA (§9.2) e nunca reordena entre refreshes: o olho
// aprende o desenho, e uma barra que troca a ordem dos pedaços a cada 20 s
// destrói a leitura periférica que ela existe para servir.
//
// Só DUAS cores preenchidas — verde (feito) e azul (rodando) — mais o trilho
// hachurado de "não roda hoje". O que travou fica FORA (Decisão 54): vermelho
// ocupando comprimento é lido como "quase pronto" a 1,5 m, e a barra responde
// UMA coisa só — quanto já ficou pronto.
function barraDaCorrida(c: CorridaApi, ok: number, total: number): BarraCorrida {
  const vivos = c.membros_vivos ?? 0
  const dispensados = c.membros_dispensados ?? 0
  const segmentos = [
    { chave: 'ok', valor: ok, cor: 'bg-green-500 dark:bg-green-500',
      rotulo: total === 1 ? 'concluído' : 'concluídos' },
    // O ÚNICO animado desta camada, junto do dot de ABERTA e da aresta ativa
    // (Decisão 75/#13) — animação em tudo viraria ruído e o olho perderia a
    // frente da corrida.
    { chave: 'vivo', valor: vivos, cor: 'bg-blue-500 dark:bg-blue-500',
      rotulo: 'em execução', animado: true },
    // Hachura significa UMA coisa nesta camada: "não roda hoje" (§9.15/#16).
    // Corrida congelada usa `opacity-60` + a palavra "parou em", nunca hachura.
    { chave: 'dispensado', valor: dispensados, cor: '',
      rotulo: 'não rodam hoje (regra de dia)', hachurado: true },
  ].filter(s => s.valor > 0)
  return {
    segmentos,
    total,
    valorAtual: ok,
    ariaLabel: 'progresso da corrida, em pipelines concluídos',
    // Sem "%" em lugar nenhum, nem para o leitor de tela. O plural acompanha o
    // denominador, como no texto visível: "1 de 1 pipelines concluídos" seria
    // a única frase da tela em português errado, e ela é justamente a que só
    // quem não enxerga a barra ouve.
    valorTexto: `${ok} de ${total} pipeline${total === 1 ? '' : 's'} `
      + `concluído${total === 1 ? '' : 's'}`
      + (vivos ? `, ${vivos} em execução` : '')
      + (dispensados ? `, ${dispensados} não ${dispensados === 1 ? 'roda' : 'rodam'} hoje` : ''),
  }
}

/** O que o card e a faixa escrevem sobre a corrida. Derivação PURA — é ela que
 *  garante que as duas superfícies contem a MESMA história (D75/#5: um
 *  agregado, uma fonte), e é ela que o teste com relógio deslocado exercita. */
export interface ResumoCorrida {
  estilo: EstiloCorrida
  /** Fundo+borda da FAIXA do painel, na mesma partição de cor do chip
   *  (Decisão 59). Sai daqui, e não do JSX, para o card e a faixa não
   *  divergirem de cor com o mesmo estado na tela. */
  faixa: string
  /** "corrida de 05/08" — e "2ª corrida de 05/08" só quando houve mais de uma
   *  no dia (Decisão 74: `#` não aparece na interface). */
  identidade: string
  /** Relativo enquanto aberta ("há 42 min"); ABSOLUTO quando fechada
   *  ("01:10 → 04:02 · 2h52"). Nunca os dois formatos no mesmo card. */
  tempo: string | null
  /** "1 de 4 pipelines concluídos" · "parou em 2 de 4" · "4 de 4 · fechando" ·
   *  null em SEM_TRABALHO (Decisão 57: nem 0, nem 4 de 4 — nenhum dos dois é
   *  verdade). */
  contagem: string | null
  /** A subtração da Decisão 53, obrigatória sempre que há contagem. */
  membros: string | null
  // ── F9: a barra, o fechamento e o "nada previsto" ────────────────────────
  /** Todos os membros que podiam concluir já concluíram, e a corrida CONTINUA
   *  ABERTA. Barra cheia — mas **não** é "concluída" nem "100%": o ciclo ainda
   *  está fechando, e chamar isso de concluído é a mentira de sempre, agora
   *  antecipada em 15 minutos. */
  fechando: boolean
  /** O que FALTA para ela fechar (Decisão 45), dizendo a REGRA antes da hora:
   *  "fecha 15 min após o último movimento; se nada mais mexer, por volta de
   *  04:17". Anunciar só a hora produziria o chamado falso das 04:18 quando
   *  alguém se mexeu às 04:16 — o relógio REINICIA a cada movimento. */
  fechamento: string | null
  /** Os segmentos da barra, na ORDEM FIXA da §9.2, ou `null` quando não há
   *  barra: `SEM_TRABALHO` (Decisão 57) e "não consegui apurar"
   *  (`membros_total` nulo) não desenham barra nenhuma. */
  barra: BarraCorrida | null
  /** "nada previsto" — o traço neutro que substitui a barra em `SEM_TRABALHO`.
   *  Nem 0, nem "4 de 4": 0 leria como "falhou tudo" e a barra cheia como
   *  "rodou tudo", e nenhum dos dois aconteceu. */
  nadaPrevisto: string | null
  /** Chip FORA do que a barra preencheria (Decisão 54). */
  travados: string | null
  /** O nome do problema mais grave, com a classe dele. */
  culpado: string | null
  vivos: string | null
  /** Auditoria (Decisão 67): quem encerrou, quando e por quê. */
  encerramento: string | null
  motivo: string | null
  // ── F12: a auditoria que faltava no CARD, e o histórico factual ──────────
  /** Decisão 44/67 — `sem nó Início` · `início manual (C123456)`. `null` na
   *  corrida agendada, que é o caso normal: uma linha em todo card para dizer
   *  "abriu como sempre abre" é ruído em 40 cards. */
  origemCurta: string | null
  /** Decisão 67 — `reaberta 1x por C123456`. A faixa já dizia isto dentro do
   *  `diagnostico`; o CARD não dizia, e "já mexeram aqui?" é uma das três
   *  primeiras perguntas de plantão. */
  reaberta: string | null
  /** Decisão 68 — `falhou 2 das últimas 7 corridas`. `null` sem histórico
   *  (dia 1) e `null` sem falha nenhuma: o histórico só fala quando tem
   *  notícia. */
  historicoFalhas: string | null
  /** Decisão 68 — `corrida anterior: 03/08 · concluída · 01:10 → 04:02`. */
  anterior: string | null
  /** Decisão 68 — `as últimas 4 terças tiveram trabalho`. Quando existe, o
   *  `estilo` e a `faixa` já vieram em ÂMBAR: os dois saem juntos daqui, para
   *  ser impossível pintar sem dizer por quê. */
  diaAtipico: string | null
  /** Banner do incidente que originou a spec (Decisão 66). */
  foraDoOdate: string | null
  // ── F7: os relógios ──────────────────────────────────────────────────────
  /** "limite de segurança (6h)" · "limite de segurança VENCIDO (6h)". Só
   *  existe quando a MALHA configurou o teto (Decisão 61) — o global de 24h é
   *  anti-travamento, e uma barra em 80% às 20h numa malha que sempre fecha em
   *  3h faria escalar por nada. */
  prazo: string | null
  /** 0–100 do limite, e `null` quando não há barra. Nunca passa de 100: a
   *  barra cheia diz "venceu", e um número acima disso não diria mais nada. */
  prazoPct: number | null
  /** "+6h de limite creditados por retenção" — a EXPLICAÇÃO da barra que andou
   *  para trás. Sem ela o recuo é silencioso, e uma barra de prazo que recua
   *  sem explicação destrói a confiança em todas as outras (Decisão 61). */
  credito: string | null
  /** "2 nós segurados desde 02:40 (C123456) — os relógios estão parados". */
  hold: string | null
  /** Decisão 43 — o diagnóstico numa linha: quem abriu, se foi reaberta e como
   *  esta malha fecha. As três primeiras perguntas de plantão, todas
   *  respondíveis pelo banco e nenhuma pela tela até esta fase. */
  diagnostico: string | null
  /** Tooltip — o único lugar em que `apurado_em` (relógio do BANCO) aparece. */
  titulo: string
}

/** Tipo de evento do CICLO → português de reunião (Decisão 74). Nome de
 *  máquina não vai à tela, e `MALHA_TETO_CREDITADO` é o pior deles: ele existe
 *  justamente para EXPLICAR um número que mudou. */
export const ROTULO_EVENTO_CORRIDA: Record<string, string> = {
  MALHA_FALHOU: 'falha na corrida',
  MALHA_ATRASADA: 'fora do prazo',
  MALHA_EXPIRADA: 'encerrada sem terminar',
  MALHA_ABORTADA: 'não chegou a começar',
  MALHA_CANCELADA: 'encerrada pelo operador',
  MALHA_CONCLUIDA: 'corrida concluída',
  MALHA_SEM_TRABALHO: 'sem trabalho hoje',
  MALHA_REPROCESSO: 'reprocesso',
  MALHA_TETO_CREDITADO: 'limite adiado por retenção',
}

/** Os desfechos em que a corrida foi INTERROMPIDA: o número que ficou não é
 *  progresso, é onde ela parou (Decisão 57) — o rótulo vira "parou em 4 de 7" e
 *  a barra CONGELA com `opacity-60`. Exportado porque quem escreve o texto
 *  (aqui) e quem apaga a barra (o card) precisam da MESMA lista: um desfecho de
 *  fora dela sairia com barra viva embaixo de "parou em". */
export const CORRIDA_INTERROMPIDA = new Set(['EXPIRADA', 'ABORTADA', 'CANCELADA'])
const INTERROMPIDA = CORRIDA_INTERROMPIDA

const FAIXA_VERMELHA =
  'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200'
const FAIXA_AMBAR =
  'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200'
const FAIXA_AZUL =
  'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200'
const FAIXA_VERDE =
  'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-200'
const FAIXA_NEUTRA =
  'border-edge bg-panel text-dim'

/** A partição de cor da FAIXA — a MESMA pergunta do chip ("isso me chama às
 *  3h?"), para o painel nunca discordar do card sobre o mesmo ciclo. */
function faixaDaCorrida(status: string, saude?: string | null): string {
  if (status === 'ABERTA') {
    if (saude === 'COM_FALHA') return FAIXA_VERMELHA
    if (saude === 'ATRASADA' || saude === 'SEM_PROGRESSO') return FAIXA_AMBAR
    return FAIXA_AZUL
  }
  if (status === 'CONCLUIDA') return FAIXA_VERDE
  if (status === 'FALHA' || status === 'EXPIRADA' || status === 'ABORTADA') {
    return FAIXA_VERMELHA
  }
  if (status === 'CANCELADA') return FAIXA_AMBAR
  return FAIXA_NEUTRA        // SEM_TRABALHO e o desconhecido: e só eles
}

function plural(n: number, s: string, p: string): string {
  return `${n} ${n === 1 ? s : p}`
}

export function resumoCorrida(
  c: CorridaApi,
  tempo: { respostaEm: number; agora: number },
  qtdCadastro?: number,
  /** F12/Decisão 68 — o histórico FACTUAL desta malha. Opcional, e a ausência
   *  é o contrato: dia 1 (nenhuma corrida fechada), API anterior à fase e erro
   *  de leitura caem todos no mesmo lugar — nenhuma frase desta fase é
   *  renderizada e o resumo é, byte a byte, o da F11. */
  historico?: HistoricoCorridas | null,
): ResumoCorrida {
  const atipico = textoDiaAtipico(historico, c.data_referencia)
  // A cor sai daqui já corrigida, e não do JSX: o chip, a faixa e a pílula do
  // card têm de concordar sobre a MESMA corrida. Um âmbar aplicado só numa das
  // superfícies seria "sem trabalho hoje" cinza no card e âmbar no painel.
  const estilo = atipico
    ? estiloDiaAtipico(estadoDaCorrida(c))
    : estadoDaCorrida(c)
  const rotulo = estilo.rotulo
  const aberta = c.status === 'ABERTA'

  const dia = diaCurto(c.data_referencia) ?? c.data_referencia
  const identidade = c.sequencia > 1
    ? `${c.sequencia}ª corrida de ${dia}`
    : `corrida de ${dia}`

  let texto: string | null = null
  // O decorrido do ciclo em voo, reusado pela BARRA DE LIMITE da F7: os dois
  // números têm de sair do mesmo lugar, senão o texto diz "há 3h50" enquanto a
  // barra desenha outra coisa na mesma linha.
  const decorridoAgora = aberta
    ? decorridoMin(c.decorrido_min, tempo.respostaEm, tempo.agora)
    : null
  if (aberta) {
    texto = decorridoAgora === null ? null : `há ${textoDuracao(decorridoAgora)}`
  } else if (c.aberta_em && c.fechada_em) {
    const dur = textoDuracao(duracaoEntre(c.aberta_em, c.fechada_em))
    texto = `${horaCurta(c.aberta_em)} → ${horaCurta(c.fechada_em)}`
      + (dur ? ` · ${dur}` : '')
  }

  const total = c.membros_total
  const ok = c.membros_ok
  let contagem: string | null = null
  let membros: string | null = null
  let barra: BarraCorrida | null = null
  let nadaPrevisto: string | null = null
  let fechando = false
  let fora = 0
  if (total !== null && total !== undefined && ok !== null && ok !== undefined) {
    if (c.status === 'SEM_TRABALHO') {
      // Sem barra e sem "x de y": 0 leria como "falhou tudo" e 4 de 4 como
      // "rodou tudo", e nenhum dos dois aconteceu.
      membros = `os ${total} membros não rodam hoje (regra de dia)`
      nadaPrevisto = 'nada previsto'
    } else {
      // SNAPSHOT VAZIO (§9.9): a corrida abriu e NENHUM membro estava ativo.
      // Não é falha de leitura (essa é `membros_total` nulo, alguns blocos
      // acima) — é um fato sobre o CADASTRO, e ele pede outra ação: alguém tem
      // de olhar a malha, não tentar de novo. "0 de 0 pipelines concluídos"
      // publicaria zero como se fosse medida de um trabalho que não existiu, e
      // essa frase chegava ao tooltip do card.
      const vazio = total === 0
      // TODOS os que podiam concluir já concluíram — e a corrida continua
      // ABERTA. É o estado em que a barra fica CHEIA sem que nada tenha
      // acabado: o ciclo está fechando, e a palavra "concluída" só existe com
      // `status = 'CONCLUIDA'` vindo do banco (§9.15/#15).
      fechando = aberta && !vazio
        && ok === total - (c.membros_dispensados ?? 0)
      if (!vazio) {
        contagem = INTERROMPIDA.has(c.status)
          ? `parou em ${ok} de ${total}`
          : fechando
            ? `${ok} de ${total} · fechando`
            : `${ok} de ${total} pipeline${total === 1 ? '' : 's'} concluído${total === 1 ? '' : 's'}`
        // A barra existe sempre que há denominador — inclusive nos desfechos
        // interrompidos, onde ela CONGELA (o `opacity-60` é do componente) e o
        // rótulo já mudou para "parou em".
        barra = barraDaCorrida(c, ok, total)
      }
      // Decisão 53: a subtração é FATO VISÍVEL, nunca nota de rodapé — é ela
      // que impede "2 de 2 · concluída, verde" numa malha de 7 em que alguém
      // inativou 5 na sexta-feira.
      const partes = [vazio
        ? 'a corrida abriu sem membros ativos'
        : plural(total, 'membro nesta corrida', 'membros nesta corrida')]
      if (c.membros_dispensados) {
        partes.push(`${c.membros_dispensados} não `
          + `${c.membros_dispensados === 1 ? 'roda' : 'rodam'} hoje (regra de dia)`)
      }
      // `membros_total < qtd_cadastro` é FATO VISÍVEL, nunca nota de rodapé —
      // é o caso do membro inativado na sexta que faria o sábado dizer "2 de 2,
      // concluída". Sem a palavra "inativos" no rótulo curto porque a causa
      // pode ser outra (entrou na malha DEPOIS da abertura); o tooltip abre.
      //
      // Duas fontes, e o MAIOR vence, porque cada uma enxerga metade do fato e
      // uma delas nem sempre está à mão: `qtd_cadastro` (o cadastro de hoje)
      // pega também quem ENTROU na malha depois da abertura, mas só o CARD o
      // tem; `membros_inativos` (a linha `ativo_na_abertura = 0` do snapshot)
      // viaja no payload da corrida e é o que a FAIXA do painel enxerga. Sem
      // o `??`, a faixa calava justamente sobre "2 de 2, concluída" — a mesma
      // omissão que a Decisão 53 existe para matar, um andar acima.
      fora = Math.max(0, (qtdCadastro ?? 0) - total, c.membros_inativos ?? 0)
      if (fora > 0) partes.push(`${fora} fora desta corrida`)
      membros = partes.join(' · ')
    }
  }

  // O servidor entrega `pendentes[]` ordenado por GRAVIDADE, então `[0]` é
  // sempre o nome que a tela deve dizer. Uma exceção, e ela é de relógio: com
  // a corrida ABERTA, `nao_partiu` significa só "ainda não começou" — é o
  // estado de TODO membro nos primeiros segundos de TODA corrida, e escrever
  // "↳ não chegou a iniciar: A" às 01:10 seria acusar por ordem alfabética
  // um pipeline que está apenas na fila. Fechada a corrida, o mesmo dado vira
  // veredito e volta a aparecer.
  const pendente = c.pendentes?.[0] ?? null
  const soFaltaComecar = aberta && pendente?.classe === 'nao_partiu'
  const culpado = (pendente && !soFaltaComecar)
    ? `${ROTULO_PENDENCIA[pendente.classe] ?? pendente.classe}: ${pendente.pipeline}`
    : null

  const abriu = quemFez(c.aberta_por)
  // ⚠️ Quem encerrou só vira texto quando quem encerrou foi GENTE (Decisão
  // 67 + Decisão 74). Fechador automático grava um `motivo` que é o texto do
  // MOTOR ("3 pipeline(s) sem concluir: …") — vocabulário de máquina, cuja
  // casa é a aba de eventos. O critério é o SUJEITO, não o status: por isso
  // isto deixou de ser `status === 'CANCELADA'` e passou a ser "fechada por
  // uma matrícula", que é o que a frase de fato afirma.
  const fechou = pessoaQueFechou(c, quemFez)
  const linhas: string[] = [`${rotulo} · ${identidade}`]
  if (texto) linhas.push(texto)
  if (contagem) linhas.push(contagem)
  if (abriu) linhas.push(`aberta por ${abriu}`)
  // "não foi reaberta" nunca vira "1ª tentativa" (Decisão 74).
  if (c.tentativas > 1) {
    linhas.push(`reaberta ${c.tentativas - 1}x`
      + (quemFez(c.reaberta_por) ? ` por ${quemFez(c.reaberta_por)}` : ''))
  }
  // As classes NUNCA viram "3 pendentes" (Decisão 21/D75#10): são problemas
  // com donos diferentes, e o tooltip nomeia cada um com a sua.
  for (const p of c.pendentes ?? []) {
    linhas.push(`${p.pipeline} — ${ROTULO_PENDENCIA[p.classe] ?? p.classe}`
      + (p.desde ? ` desde ${horaCurta(p.desde)}` : ''))
  }
  if (fora > 0) {
    linhas.push(`${fora} pipeline(s) da malha ficaram fora desta corrida — `
      + 'inativos quando ela abriu, ou adicionados à malha depois')
  }
  const fechamento = fechando ? textoFechamento(c) : null
  if (fechamento) linhas.push(fechamento)
  // F12 — o histórico no TOOLTIP também: quem passa o mouse no card já viu a
  // frase curta e quer o resto (a corrida anterior, com hora), sem precisar
  // abrir a malha.
  const historicoFalhas = textoFalhasRecentes(historico)
  const anterior = textoCorridaAnterior(historico,
                                        s => estiloCorrida(s).rotulo)
  if (atipico) linhas.push(atipico)
  if (historicoFalhas) linhas.push(historicoFalhas)
  if (anterior) linhas.push(anterior)
  const apurado = carimboLongo(c.apurado_em)
  if (apurado) linhas.push(`apurado em ${apurado}`)

  return {
    estilo: { ...estilo, rotulo },
    // A faixa segue a MESMA correção de cor do chip: sem isto, o painel
    // pintaria de cinza a mesma corrida que o card acabou de pintar de âmbar.
    faixa: atipico ? FAIXA_AMBAR : faixaDaCorrida(c.status, c.saude),
    identidade,
    tempo: texto,
    contagem,
    membros,
    fechando,
    fechamento,
    barra,
    nadaPrevisto,
    travados: c.membros_travados
      ? plural(c.membros_travados, 'travado', 'travados')
      : null,
    culpado,
    vivos: c.membros_vivos ? `${c.membros_vivos} rodando` : null,
    // Auditoria (Decisão 67): quem encerrou, quando e por quê — no fechamento
    // do mês, três corridas canceladas precisam ser explicáveis sem abrir o
    // banco.
    encerramento: fechou
      ? `encerrada por ${fechou}`
        + (c.fechada_em ? ` às ${horaCurta(c.fechada_em)}` : '')
      : null,
    motivo: (fechou && motivoLimpo(c.motivo))
      ? `motivo: "${motivoLimpo(c.motivo)}"`
      : null,
    // Decisão 44/67 — a origem e a reabertura, agora também no CARD. A faixa
    // já as dizia dentro do `diagnostico`; o card calava sobre as duas.
    origemCurta: textoOrigem(c, quemFez),
    reaberta: c.tentativas > 1
      ? `reaberta ${c.tentativas - 1}x`
        + (quemFez(c.reaberta_por) ? ` por ${quemFez(c.reaberta_por)}` : '')
      : null,
    historicoFalhas,
    anterior,
    diaAtipico: atipico,
    foraDoOdate: c.membros_fora_do_odate
      ? `${plural(c.membros_fora_do_odate, 'pipeline', 'pipelines')} de outra `
        + 'data de referência'
      : null,
    ...prazoDaCorrida(c, aberta, decorridoAgora),
    diagnostico: diagnosticoDaCorrida(c, abriu),
    titulo: linhas.join('\n'),
  }
}

/** O que falta para a corrida CHEIA fechar (Decisão 45) — a REGRA antes da
 *  hora, sempre nessa ordem.
 *
 *  O defeito que este texto evita tem duas caras opostas, e é preciso escapar
 *  das duas na mesma frase:
 *    • **calar** — o último pipeline fica verde às 04:02, o card continua "em
 *      andamento" até 04:17 e o operador reporta bug (ou, pior, dispara coisa
 *      na mão às 04:05);
 *    • **prometer a hora** — anunciar "fecha às 04:17" como horário exato
 *      produz o MESMO chamado falso às 04:18, porque a carência REINICIA a cada
 *      movimento: bastou alguém se mexer às 04:16.
 *
 *  Por isso: primeiro a regra ("fecha 15 min após o último movimento"), depois
 *  a hora sob condição explícita ("se nada mais mexer, por volta de 04:17").
 *
 *  As duas degradações são de payload, não de estado: API anterior à F9 não
 *  manda `quiescencia_min` nem `quiescencia_ate`, e a frase encolhe até o que
 *  ainda for verdade — nunca inventa o minuto que não veio. */
function textoFechamento(c: CorridaApi): string {
  // Malha com nó Fim não fecha por carência: quem fecha é o Fim. Dizer "fecha
  // 15 min após o último movimento" ali seria descrever o mecanismo errado —
  // e o operador esperaria por um relógio que não está correndo.
  if (c.modo_fechamento === 'fim') {
    return 'aguarda o nó Fim registrar a conclusão'
  }
  // ⚠️ HOLD — o relógio de fechamento NÃO ESTÁ CORRENDO (§6.7/Decisão 30: com
  // nó segurado "o teto não corre, a quiescência não avalia"). `quiescencia_ate`
  // continua sendo `último movimento + carência`, e é um carimbo que o hold
  // deixa para trás: com a retenção posta às 02:40 sobre um movimento das
  // 02:30, a frase honesta de sempre anunciaria "por volta de 02:45" às 13h —
  // uma hora que já passou, para um fechamento que não vai acontecer.
  //
  // É o mesmo defeito que a F7 já pagou na barra de limite (ela enchia durante
  // o hold, chegava ao vermelho e contradizia o texto ao lado). A linha que se
  // contradiz sozinha leva junto a confiança em todas as outras — por isso aqui
  // ela diz o FATO ("está parado") e a CAUSA, e nenhuma hora.
  const retidos = c.retido_nos ?? 0
  if (retidos > 0) {
    return `o fechamento está parado — ${plural(retidos, 'nó segurado', 'nós segurados')}`
      + (c.retido_desde ? ` desde ${horaCurta(c.retido_desde)}` : '')
  }
  const min = c.quiescencia_min
  const regra = (min && min > 0)
    ? `fecha ${min} min após o último movimento`
    : 'fecha alguns minutos após o último movimento'
  const hora = horaCurta(c.quiescencia_ate)
  return hora ? `${regra}; se nada mais mexer, por volta de ${hora}` : regra
}

/** F9 (Decisão 58) — o texto do estado que não tem registro: a corrida que
 *  DEVERIA ter aberto e não abriu.
 *
 *  `esperada.atrasada_min` foi medido no SERVIDOR, entre o horário previsto e o
 *  relógio do BANCO. Aqui ele só ganha o que passou no relógio LOCAL desde a
 *  resposta — exatamente como o decorrido da corrida em voo (Decisão 60), e
 *  nunca subtraindo `atrasada_desde` de `Date.now()`. */
export interface ResumoEsperada {
  estilo: EstiloCorrida
  faixa: string
  /** "previsto para 01:00 · há 7h12" — o "há" é o atraso, não o relógio de
   *  parede: dizer "já são 08:12" exibiria a hora do BANCO, que no dev está 3h
   *  à frente do relógio do próprio operador. */
  cabecalho: string
  /** "nenhuma corrida de 06/08" — o lugar onde a barra estaria. */
  semCorrida: string
  /** A consequência, quando ela existe: a corrida anterior continua aberta e é
   *  ELA que está segurando a porta (o índice de corrida única). Muda a ação —
   *  não é "o Airflow morreu", é "alguém precisa fechar a de ontem". */
  bloqueio: string | null
  titulo: string
}

export function resumoEsperada(
  e: CorridaEsperadaApi,
  tempo: { respostaEm: number; agora: number },
): ResumoEsperada {
  const atraso = decorridoMin(e.atrasada_min, tempo.respostaEm, tempo.agora)
  const dia = diaCurto(e.data_referencia)
  const cabecalho = `previsto para ${e.previsto_para}`
    + (atraso === null ? '' : ` · há ${textoDuracao(atraso)}`)
  const bloqueio = e.bloqueada_por_corrida_aberta
    ? 'a corrida anterior continua aberta — enquanto ela não fechar, a próxima '
      + 'não abre'
    : null
  const linhas = [
    `não abriu · ${cabecalho}`,
    dia ? `nenhuma corrida de ${dia} foi registrada` : 'nenhuma corrida registrada',
    `horário previsto: ${e.atrasada_desde ?? e.previsto_para}`,
  ]
  if (bloqueio) linhas.push(bloqueio)
  linhas.push('O gatilho desta malha já venceu e nenhuma corrida abriu — '
    + 'verifique se a DAG do Início está ativa no Airflow.')
  return {
    estilo: ESTILO_NAO_ABRIU,
    faixa: FAIXA_AMBAR,
    cabecalho,
    semCorrida: dia ? `nenhuma corrida de ${dia}` : 'nenhuma corrida registrada',
    bloqueio,
    titulo: linhas.join('\n'),
  }
}

/** O bloco de PRAZO da faixa (F7 — §6.6/§6.7, Decisões 30 e 61).
 *
 *  Três fatos, e a ordem em que eles aparecem é a ordem em que o operador
 *  precisa deles: onde o limite está, por que ele mudou de lugar, e por que os
 *  relógios estão parados.
 *
 *  Nenhuma conta de tempo entre relógios diferentes: `decorrido` já é o do
 *  servidor somado ao relógio LOCAL desde a resposta (Decisão 60), e
 *  `teto_total_min` é `aberta_em → teto_em` subtraído NO BANCO. A razão entre
 *  os dois é adimensional — é o único jeito honesto de desenhar esta barra. */
function prazoDaCorrida(c: CorridaApi, aberta: boolean, decorrido: number | null) {
  const total = c.teto_total_min ?? null
  // A barra só existe com teto CONFIGURADO na malha (Decisão 61): o default
  // global é anti-travamento, não SLA.
  const temBarra = !!c.teto_configurado && !!total && total > 0
  // ⚠️ A BARRA TAMBÉM PARA no hold (Decisão 30) — e isto não é cosmético.
  // `decorrido` é relógio de parede desde `aberta_em`: ele continua andando com
  // a malha segurada, e `teto_em` só se move no CRÉDITO, que só acontece ao
  // soltar. Sem congelar, o operador leria "os relógios estão parados" ao lado
  // de uma barra que enche, chega a 100% e fica VERMELHA — enquanto o texto ao
  // lado dela diz que o limite não venceu. Uma linha que se contradiz sozinha
  // destrói a confiança em todas as outras barras da tela, que é exatamente o
  // que a Decisão 61 existe para impedir.
  //
  // O numerador congelado é `aberta_em → retido_desde`: os DOIS são carimbos do
  // BANCO (mesmo relógio), e essa é a única subtração honesta possível aqui —
  // comparar `retido_desde` com o relógio do navegador daria "parado há -3h"
  // com o desvio de 3h medido no dev.
  const decorridoNaBarra = c.retido_desde
    ? duracaoEntre(c.aberta_em, c.retido_desde)
    : decorrido
  let prazo: string | null = null
  let prazoPct: number | null = null
  if (temBarra) {
    const horas = textoDuracao(total)
    prazo = c.teto_vencido
      ? `limite de segurança VENCIDO (${horas})`
      : `limite de segurança ${horas}`
    if (aberta && decorridoNaBarra !== null) {
      prazoPct = Math.max(0, Math.min(100,
        Math.round((decorridoNaBarra / total) * 100)))
    } else if (c.teto_vencido) {
      prazoPct = 100
    }
  }
  const creditado = c.teto_creditado_min ?? 0
  return {
    prazo,
    prazoPct,
    // Aparece mesmo SEM barra: o crédito é fato do ciclo, e quem não configurou
    // teto próprio também precisa saber que o limite global foi adiado.
    credito: creditado > 0
      ? `+${textoDuracao(creditado)} de limite creditados por retenção`
      : null,
    hold: (c.retido_nos ?? 0) > 0
      ? `${plural(c.retido_nos ?? 0, 'nó segurado', 'nós segurados')}`
        + (c.retido_desde ? ` desde ${horaCurta(c.retido_desde)}` : '')
        + (c.retido_por ? ` (${c.retido_por})` : '')
        + ' — os relógios estão parados'
      : null,
  }
}

/** Decisão 43 — o diagnóstico do ciclo em UMA linha.
 *
 *  "quem começou isto?", "é a primeira tentativa ou já mexeram aqui?" e "por
 *  que esta malha fecha sem passar pelo Fim?" são as três primeiras perguntas
 *  às 3h. Todas respondíveis pelo banco desde a F1, e nenhuma pela tela até
 *  aqui — seis campos gravados e nenhum mostrado.
 *
 *  Decisão 44: corrida `implicita` DIZ que não há nó Início, em vez de
 *  apresentar o ODATE do primeiro membro com uma autoridade que ele não tem. */
function diagnosticoDaCorrida(c: CorridaApi, abriu: string | null): string | null {
  const partes: string[] = []
  if (c.origem === 'inicio') {
    partes.push('aberta pelo agendamento do Início'
      + (c.ancora_pipeline ? ` (${c.ancora_pipeline})` : ''))
  } else if (c.origem === 'manual') {
    partes.push(`aberta manualmente${abriu ? ` por ${abriu}` : ''}`)
  } else if (c.origem === 'implicita') {
    partes.push('data de referência definida pela primeira raiz a partir'
      + (c.ancora_pipeline ? ` (${c.ancora_pipeline})` : '')
      + ' — esta malha não tem nó Início')
  }
  if (c.aberta_em) partes.push(`às ${horaCurta(c.aberta_em)}`)
  // "não foi reaberta" nunca vira "1ª tentativa" (Decisão 74).
  if (c.tentativas > 1) {
    partes.push(`reaberta ${c.tentativas - 1}x`
      + (quemFez(c.reaberta_por) ? ` por ${quemFez(c.reaberta_por)}` : ''))
  }
  // Decisão 45 — a REGRA antes da hora. Anunciar "até 04:17" como horário
  // exato produz o mesmo chamado falso pela forma do texto: o relógio da
  // quiescência REINICIA a cada movimento.
  if (c.status === 'ABERTA' && c.modo_fechamento === 'quiescencia') {
    partes.push('fecha sozinha alguns minutos após o último movimento')
  }
  return partes.length ? partes.join(' · ') : null
}
