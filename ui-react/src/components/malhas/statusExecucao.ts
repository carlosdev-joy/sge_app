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
  Activity, AlertTriangle, Ban, CheckCircle2, CircleSlash, Clock, Hourglass,
  Moon, TimerOff, XCircle,
} from 'lucide-react'
import type { CorridaApi, CorridaCabecalho } from '../../types'
import {
  diaCurto, duracaoEntre, decorridoMin, horaCurta, carimboLongo, textoDuracao,
} from './tempoCorrida'

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
}

/** Evento do CICLO — sem `pipeline_name`, porque o sujeito é a corrida. */
export interface EventoCorrida {
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

/** O `motivo` do encerramento manual é composto pelo servidor como
 *  `"encerrada por C123456: <texto>"`. O card já diz QUEM e QUANDO numa linha
 *  estruturada — repetir o prefixo na linha de baixo é ruído em cima da única
 *  frase que o operador escreveu com as próprias palavras. */
function motivoLimpo(v: string | null): string | null {
  if (!v) return null
  return v.replace(/^encerrada por [^:]{1,80}:\s*/i, '').trim() || null
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
  /** "1 de 4 pipelines concluídos" · "parou em 2 de 4" · null em SEM_TRABALHO
   *  (Decisão 57: nem 0, nem 4 de 4 — nenhum dos dois é verdade). */
  contagem: string | null
  /** A subtração da Decisão 53, obrigatória sempre que há contagem. */
  membros: string | null
  /** Chip FORA do que a barra preencheria (Decisão 54). */
  travados: string | null
  /** O nome do problema mais grave, com a classe dele. */
  culpado: string | null
  vivos: string | null
  /** Auditoria (Decisão 67): quem encerrou, quando e por quê. */
  encerramento: string | null
  motivo: string | null
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
 *  progresso, é onde ela parou (Decisão 57). */
const INTERROMPIDA = new Set(['EXPIRADA', 'ABORTADA', 'CANCELADA'])

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
): ResumoCorrida {
  const estilo = estiloCorrida(c.status, c.saude)
  const aberta = c.status === 'ABERTA'
  // "sem sinal há 40 min" — os minutos vêm do BANCO (`sem_sinal_min`, já
  // subtraído lá): é medida de relógio, e nenhum relógio local participa.
  const rotulo = (aberta && c.saude === 'SEM_PROGRESSO' && c.sem_sinal_min)
    ? `${estilo.rotulo} há ${textoDuracao(c.sem_sinal_min)}`
    : estilo.rotulo

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
  let fora = 0
  if (total !== null && total !== undefined && ok !== null && ok !== undefined) {
    if (c.status === 'SEM_TRABALHO') {
      // Sem barra e sem "x de y": 0 leria como "falhou tudo" e 4 de 4 como
      // "rodou tudo", e nenhum dos dois aconteceu.
      membros = `os ${total} membros não rodam hoje (regra de dia)`
    } else {
      contagem = INTERROMPIDA.has(c.status)
        ? `parou em ${ok} de ${total}`
        : `${ok} de ${total} pipeline${total === 1 ? '' : 's'} concluído${total === 1 ? '' : 's'}`
      // Decisão 53: a subtração é FATO VISÍVEL, nunca nota de rodapé — é ela
      // que impede "2 de 2 · concluída, verde" numa malha de 7 em que alguém
      // inativou 5 na sexta-feira.
      const partes = [plural(total, 'membro nesta corrida', 'membros nesta corrida')]
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
  const fechou = quemFez(c.fechada_por)
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
  const apurado = carimboLongo(c.apurado_em)
  if (apurado) linhas.push(`apurado em ${apurado}`)

  return {
    estilo: { ...estilo, rotulo },
    faixa: faixaDaCorrida(c.status, c.saude),
    identidade,
    tempo: texto,
    contagem,
    membros,
    travados: c.membros_travados
      ? plural(c.membros_travados, 'travado', 'travados')
      : null,
    culpado,
    vivos: c.membros_vivos ? `${c.membros_vivos} rodando` : null,
    // Auditoria (Decisão 67): quem encerrou, quando e por quê — no fechamento
    // do mês, três corridas canceladas precisam ser explicáveis sem abrir o
    // banco. Só em CANCELADA: nos outros desfechos quem "fecha" é o monitor
    // automático, e o diagnóstico dele é a linguagem do motor (a aba de
    // eventos é o lugar dela, não o card).
    encerramento: (c.status === 'CANCELADA' && fechou)
      ? `encerrada por ${fechou}`
        + (c.fechada_em ? ` às ${horaCurta(c.fechada_em)}` : '')
      : null,
    motivo: (c.status === 'CANCELADA' && motivoLimpo(c.motivo))
      ? `motivo: "${motivoLimpo(c.motivo)}"`
      : null,
    foraDoOdate: c.membros_fora_do_odate
      ? `${plural(c.membros_fora_do_odate, 'pipeline', 'pipelines')} de outra `
        + 'data de referência'
      : null,
    ...prazoDaCorrida(c, aberta, decorridoAgora),
    diagnostico: diagnosticoDaCorrida(c, abriu),
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
