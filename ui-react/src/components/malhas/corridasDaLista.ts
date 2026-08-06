import { diaCurto, horaCurta } from './tempoCorrida'
import type { CorridaApi, CorridaEsperadaApi } from '../../types'

// ─────────────────────────────────────────────────────────────────────────────
// A lista de malhas VISTA PELA CORRIDA — spec docs/spec-malha-execucao.md
// §9.8/§10 "### F11".
//
// A pergunta que esta fase responde: hoje é **impossível** saber qual malha
// está rodando sem abrir uma a uma e trocar o modo. Uma tela ótima que ninguém
// alcança às 3h vale menos que uma tela boa com caminho até ela.
//
// POR QUE MÓDULO PRÓPRIO, e não JSX solto em `pages/Malha.tsx` (Decisão 71 —
// só se promove o que tem CHAMADOR PROVADO): são DOIS chamadores, e o segundo é
// o que torna esta fase útil. A lista (`pages/Malha.tsx`) filtra e conta; o
// Dashboard (`pages/Dashboard.tsx`) mostra a linha de corrida a partir do MESMO
// payload e com o MESMO predicado de polling. Duas cópias das mesmas regras é
// como duas telas passam a discordar sobre a mesma malha na mesma manhã —
// exatamente o defeito que esta spec inteira existe para matar (D75/#5: um
// agregado, uma fonte).
// ─────────────────────────────────────────────────────────────────────────────

/** Última corrida registrada entre os pipelines da malha. `em` é o INÍCIO da
 *  corrida (a API cai em criado_em quando ela ainda não partiu) — nunca a
 *  data_referencia, que é o dia de PROCESSAMENTO e pode estar longe do
 *  relógio. */
export interface UltimaExecucao {
  em: string | null
  status: string
  pipeline: string
}

/** Resumo do horário de disparo. `origem` diz de ONDE ele saiu, e é o que
 *  permite o tooltip ser honesto: 'malha' = agendamento próprio (nó Início),
 *  'membros' = derivado dos pipelines que disparam sozinhos, 'nenhum' = a
 *  malha só anda por disparo manual. */
export interface Gatilho {
  origem: 'malha' | 'membros' | 'nenhum'
  resumo: string
  horario: string | null
  qtd_pipelines: number
  horarios: string[]
  detalhes: { pipeline: string; resumo: string; horario: string }[]
}

export interface ApiMalha {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  criado_em: string | null
  qtd_pipelines: number
  qtd_ativos: number
  criticidade: string | null // agregada = a mais alta entre os membros
  // Aditivos do card. Opcionais de propósito: numa API antiga (deploy parcial
  // do front) a chave não vem e a linha correspondente some, em vez de a tela
  // exibir "undefined etapas".
  qtd_etapas?: number
  ultima_execucao?: UltimaExecucao | null
  gatilho?: Gatilho | null
  // Há agendamento salvo na malha que NÃO está vigente (o Início foi excluído,
  // ou ainda não foi desenhado): nenhuma raiz o carrega, então ele não é
  // gatilho — mas continua guardado e volta a valer quando o Início religar.
  agendamento_guardado?: boolean
  // F4 — a CORRIDA (o ciclo da malha). É ELA que responde "a malha rodou?".
  // Opcional, e a ausência é o contrato (Decisão 41): API anterior à fase,
  // banco sem a 085 e malha sem ciclo nenhum degradam no MESMO lugar, o
  // fallback "(membro mais recente)" do card. Nunca vem `null`.
  corrida?: CorridaApi
  // F9 (Decisão 58) — a corrida que NÃO ABRIU: o gatilho venceu e nenhuma
  // corrida nasceu. Chave ausente = não há o que acusar (o caso normal), e ela
  // só chega para malha ATIVA que já teve corrida antes — o que mantém a lista
  // muda no dia do deploy, com o interruptor ainda em 0.
  corrida_esperada?: CorridaEsperadaApi
}

export interface MalhasResponse {
  malhas: ApiMalha[]
  // Deploy parcial (API nova + migration 070 não aplicada): a API degrada
  // devolvendo lista vazia + esta flag, em vez de 500.
  migration_pendente?: boolean
  // F4: a 085 não está neste banco. NÃO é o que o card testa para decidir
  // renderizar (isso é a ausência da chave `corrida`) — é o que permite DIZER
  // ao operador que falta informação, em vez de degradar em silêncio.
  migration_085_pendente?: boolean
  // F9: esta API sabe responder sobre corrida. Marcador POSITIVO de versão, e
  // ele existe por causa da janela de deploy: o `dist/` sobe na etapa 3 e a
  // `api/` só na 7, então por alguns minutos o front novo fala com a API
  // velha — que não manda `corrida` nem flag nenhuma. Sem esta chave, o front
  // não distinguiria "esta malha não tem ciclo" (silêncio correto no dia do
  // deploy) de "esta API não sabe responder" (a hora de dizer que falta
  // informação). Ausente = API anterior à F9.
  corrida_suportada?: boolean
}

/** A chave de query compartilhada pela lista e pelo Dashboard.
 *
 *  Mesma chave = mesmo cache do react-query = **zero consulta nova** quando as
 *  duas telas estão montadas (Decisão 70, "mesmo payload da lista"). Exportada
 *  para que ninguém a escreva de novo com uma vírgula a mais e ganhe, sem
 *  perceber, uma segunda cópia do payload e um segundo polling. */
export const QUERY_MALHAS = ['malhas'] as const

/** A malha tem algo que ANDA sozinho na tela (Decisão 73)?
 *
 *  Duas coisas andam: a corrida em voo (o `x de y` e o decorrido) e a corrida
 *  que não abriu (o atraso, que cresce a cada minuto). As duas governam o
 *  polling E o alarme de dado velho, e por isso vivem numa função só: separá-las
 *  já produziu o card mais grave da manhã sendo o único a envelhecer em
 *  silêncio, com o relógio congelado no "há 7h12" da abertura da página. */
export function emMovimento(m: ApiMalha): boolean {
  return m.corrida?.status === 'ABERTA' || !!m.corrida_esperada
}

/** O `refetchInterval` da Decisão 73, numa função só — a lista e o Dashboard
 *  usam a MESMA cadência sobre a MESMA chave de cache.
 *
 *  `false` (e não um número grande) quando não há corrida aberta nem "não
 *  abriu": **zero refetch**. Ligar polling incondicional numa tela que hoje não
 *  tem nenhum seria pagar o custo das 24 h por causa das 4 da madrugada — e o
 *  endpoint faz duas consultas de conjunto por chamada.
 *
 *  O recorte é a lista INTEIRA, e não as malhas visíveis: o filtro é
 *  client-side, e uma corrida em voo escondida por um filtro continua sendo uma
 *  corrida em voo. Filtrar por "Concluídas" não pode congelar o relógio da que
 *  está falhando do outro lado do filtro. */
export function cadenciaDaLista(malhas: ApiMalha[] | undefined): 20_000 | false {
  return (malhas ?? []).some(emMovimento) ? 20_000 : false
}

/** O link CANÔNICO para a corrida — o mesmo molde que o card do Teams monta do
 *  outro lado (`dags/utils/ds_teams.py:url_da_corrida`).
 *
 *  Sem `corrida`, leva à lente de execução da data corrente, que já funciona
 *  hoje: é o que mantém o caminho testável no dia do deploy, com o interruptor
 *  `malha_corrida_ativa` ainda em `0` e nenhuma malha com ciclo.
 *
 *  `data` é o ODATE com que o painel abre, e serve ao caso em que não há
 *  corrida para apontar mas SE SABE o dia — é o do painel de dependência do
 *  Dashboard, que trabalha sobre uma data de referência declarada. */
export function linkDaCorrida(malha: string, corrida?: number | null,
                              data?: string | null): string {
  let url = `/malha?malha=${encodeURIComponent(malha)}&modo=execucao`
  if (corrida) url += `&corrida=${corrida}`
  if (data) url += `&data=${encodeURIComponent(data)}`
  return url
}

// ── O filtro por ESTADO DE CORRIDA ──────────────────────────────────────────
//
// Os estados são PREDICADOS, e não uma partição: uma corrida ABERTA com falha
// está rodando **e** falhando, e ela precisa aparecer nos dois filtros. Somar
// estados distintos para "simplificar" é o que a §9.15/#10 proíbe — `falhou` e
// `fora do prazo` têm donos diferentes e ações diferentes.

export type EstadoCorrida = 'rodando' | 'falha' | 'prazo' | 'nao_abriu' | 'concluida'

export interface DefinicaoEstado {
  chave: EstadoCorrida
  /** Rótulo do <option> e base do rótulo do contador. */
  rotulo: string
  /** Tom da pílula da stats bar. `null` = a pílula neutra padrão. */
  tom: string | null
  /** O que o contador diz quando o operador passa o mouse. */
  ajuda: string
}

const TOM_VERMELHO =
  'border-red-300 bg-red-50 text-red-800 '
  + 'dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
const TOM_AMBAR =
  'border-amber-300 bg-amber-50 text-amber-800 '
  + 'dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300'
const TOM_AZUL =
  'border-blue-300 bg-blue-50 text-blue-800 '
  + 'dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300'
const TOM_VERDE =
  'border-green-300 bg-green-50 text-green-800 '
  + 'dark:border-green-800 dark:bg-green-900/20 dark:text-green-300'

/** A ORDEM é a da gravidade decrescente, e ela é a mesma no <select> e na
 *  stats bar: dois lugares com a mesma lista em ordens diferentes fazem o olho
 *  procurar duas vezes. */
export const ESTADOS_CORRIDA: DefinicaoEstado[] = [
  {
    chave: 'rodando',
    rotulo: 'Rodando agora',
    tom: TOM_AZUL,
    // ⚠️ "em andamento", e não `ABERTA`: o rótulo pt-BR do status é o que o
    // `STATUS_CORRIDA` publica na pílula, e nome de máquina não entra na
    // interface (Decisão 74) — `title` inclusive, que é texto lido tanto pelo
    // olho quanto pelo leitor de tela.
    ajuda: 'Malhas com a corrida em andamento neste momento — inclusive as que '
      + 'já têm falha dentro (uma corrida que falhou continua rodando o resto).',
  },
  {
    chave: 'falha',
    rotulo: 'Com falha',
    tom: TOM_VERMELHO,
    ajuda: 'Malhas cuja corrida falhou — a que já fechou em falha e também a '
      + 'que ainda está rodando com uma falha dentro.',
  },
  {
    chave: 'prazo',
    rotulo: 'Fora do prazo',
    tom: TOM_AMBAR,
    ajuda: 'Malhas cuja corrida passou do limite: em andamento fora do prazo, '
      + 'ou encerrada sem terminar.',
  },
  {
    chave: 'nao_abriu',
    rotulo: 'Não abriram',
    tom: TOM_AMBAR,
    ajuda: 'O horário previsto passou e nenhuma corrida nasceu — o pior modo '
      + 'de falha, e o que a lista não sabia contar.',
  },
  {
    chave: 'concluida',
    rotulo: 'Concluídas',
    tom: TOM_VERDE,
    ajuda: 'Malhas que concluíram a corrida da data de referência indicada.',
  },
]

/** A data de referência a que o contador de concluídas se refere, e se todas
 *  elas de fato fecharam de madrugada.
 *
 *  ⚠️ **Esta é a "régua" da Decisão do aceite, e ela existe por um defeito
 *  concreto:** às 08:00 de 04/08, um contador que filtrasse `ODATE = hoje`
 *  mostraria `0` — as malhas da madrugada carimbam a referência 03/08. E um
 *  contador que somasse TODA malha concluída, de qualquer referência,
 *  produziria um número que não bate com relatório nenhum por ODATE (mistura
 *  a que rodou hoje com a que parou de rodar semana passada).
 *
 *  A saída é declarar a régua: conta-se a referência MAIS RECENTE entre as
 *  corridas concluídas em vista, e o rótulo diz qual é. O número passa a bater,
 *  exatamente, com o relatório daquele ODATE.
 *
 *  `madrugada` sai de `fechada_em`, que é carimbo do BANCO — ler a HORA de um
 *  carimbo não é conta de tempo (Decisão 60), é ler o rótulo que o banco
 *  escreveu. Serve só para não afirmar "na madrugada" sobre uma corrida que
 *  fechou às 15h. */
export interface ReferenciaConcluidas {
  /** ODATE em 'YYYY-MM-DD' — a régua. */
  data: string
  /** 'DD/MM' para o rótulo. */
  curta: string
  /** Quantas malhas concluíram a corrida DESSA referência. */
  total: number
  /** Quantas malhas concluíram uma corrida de OUTRA referência (e por isso
   *  ficam fora da conta) — é o que o tooltip precisa para ser honesto. */
  foraDaReferencia: number
  /** Todas as contadas fecharam antes das 06:00 do relógio do banco. */
  madrugada: boolean
}

const HORA_FIM_DA_MADRUGADA = 6

export function referenciaConcluidas(malhas: ApiMalha[]): ReferenciaConcluidas | null {
  const concluidas = malhas
    .map(m => m.corrida)
    .filter((c): c is CorridaApi =>
      !!c && c.status === 'CONCLUIDA' && !!c.data_referencia)
  if (concluidas.length === 0) return null
  // A referência é a data da MAIORIA, não a mais recente. Com o máximo, uma
  // única malha horária fechando às 07:30 já com a referência do dia seguinte
  // fazia a pílula virar "1 concluída (referência 04/08)" e jogava as outras 12
  // em `foraDaReferencia`: o número continuava batendo com o relatório daquele
  // ODATE, mas a pergunta que o contador existe para responder — "a madrugada
  // rodou?" — passava a ser respondida com 1.
  //
  // Empate resolvido pela data mais RECENTE, que é determinístico e mantém o
  // comportamento antigo quando não há maioria (uma corrida por data).
  // ISO 'YYYY-MM-DD' ordena lexicograficamente igual a cronologicamente — é a
  // razão de o formato viajar assim desde a API.
  const porData = new Map<string, number>()
  for (const c of concluidas) {
    porData.set(c.data_referencia, (porData.get(c.data_referencia) ?? 0) + 1)
  }
  let data = concluidas[0].data_referencia
  let maior = 0
  for (const [d, n] of porData) {
    if (n > maior || (n === maior && d > data)) { data = d; maior = n }
  }
  const daData = concluidas.filter(c => c.data_referencia === data)
  const madrugada = daData.every(c => {
    const hora = horaCurta(c.fechada_em)
    // Sem `fechada_em` não se afirma nada: "concluída" sem instante é dado
    // incompleto, e a frase da madrugada some em vez de ser chutada.
    return !!hora && Number(hora.slice(0, 2)) < HORA_FIM_DA_MADRUGADA
  })
  return {
    data,
    curta: diaCurto(data) ?? data,
    total: daData.length,
    foraDaReferencia: concluidas.length - daData.length,
    madrugada,
  }
}

/** A malha casa este estado? `referencia` só é consultada por `concluida` — é o
 *  que faz o contador e o filtro devolverem SEMPRE o mesmo conjunto (clicar
 *  num contador de 12 e ver 9 cards seria a tela mentindo de um jeito novo). */
export function casaEstado(m: ApiMalha, estado: EstadoCorrida,
                           referencia: ReferenciaConcluidas | null): boolean {
  const c = m.corrida
  switch (estado) {
    case 'nao_abriu':
      return !!m.corrida_esperada
    case 'rodando':
      return c?.status === 'ABERTA'
    case 'falha':
      // A saúde é o que faz a falha aparecer às 03:00, e não no fechamento:
      // esperar a corrida fechar para contá-la como falha é descobrir depois
      // do SLA (Decisão 11).
      // `ABORTADA` entra aqui, e a alternativa era pior: ela não casava filtro
      // nenhum, não tinha contador e não aparecia no Dashboard — a corrida que
      // aborta à 01:00 ficava INVISÍVEL às 8h, em todas as superfícies. É o
      // modo de falha silencioso que esta spec inteira existe para acabar, com
      // roupa nova. "Não chegou a começar" é um desfecho ruim que pede ação
      // agora, que é exatamente o que este filtro reúne.
      return c?.status === 'FALHA' || c?.status === 'ABORTADA'
        || (c?.status === 'ABERTA' && c?.saude === 'COM_FALHA')
    case 'prazo':
      // `SEM_PROGRESSO` fica FORA: "nada se moveu há 40 min" é sintoma de
      // execução órfã, não de prazo — e são ações diferentes (§9.15/#10).
      return c?.status === 'EXPIRADA'
        || (c?.status === 'ABERTA'
            && (c?.saude === 'ATRASADA' || c?.teto_vencido === true))
    case 'concluida':
      return !!referencia && c?.status === 'CONCLUIDA'
        && c?.data_referencia === referencia.data
    default:
      return false
  }
}

/** `{estado: quantas}` sobre o conjunto dado.
 *
 *  ⚠️ O conjunto é o de ANTES do filtro por estado, sempre. Contar sobre o
 *  resultado do próprio filtro faria os outros contadores irem a zero e
 *  sumirem no primeiro clique — e aí não haveria como trocar de filtro pela
 *  stats bar, que é justamente o gesto que esta fase entrega. */
export function contarEstados(malhas: ApiMalha[],
                              referencia: ReferenciaConcluidas | null,
                             ): Record<EstadoCorrida, number> {
  const saida = {
    rodando: 0, falha: 0, prazo: 0, nao_abriu: 0, concluida: 0,
  } as Record<EstadoCorrida, number>
  for (const m of malhas) {
    for (const def of ESTADOS_CORRIDA) {
      if (casaEstado(m, def.chave, referencia)) saida[def.chave] += 1
    }
  }
  return saida
}

/** O rótulo do contador — e é AQUI que a régua é declarada.
 *
 *  "12 concluídas na madrugada (referência 03/08)": sem a segunda metade, o
 *  número seria verdadeiro e ininterpretável — 12 concluídas de qual dia? */
export function rotuloEstado(estado: EstadoCorrida, n: number,
                             referencia: ReferenciaConcluidas | null): string {
  if (estado === 'nao_abriu') {
    // O único cujo verbo concorda em NÚMERO — "1 não abriram" é o tipo de
    // erro que faz o leitor duvidar do número ao lado.
    return n === 1 ? 'não abriu' : 'não abriram'
  }
  if (estado !== 'concluida') {
    const def = ESTADOS_CORRIDA.find(d => d.chave === estado)
    return (def?.rotulo ?? estado).toLowerCase()
  }
  // ── A RÉGUA, no rótulo ───────────────────────────────────────────────────
  // "12 concluídas na madrugada (referência 03/08)". Sem a segunda metade o
  // número é verdadeiro e ininterpretável, e não bate com relatório nenhum.
  // "na madrugada" só sai quando TODAS as contadas de fato fecharam antes das
  // 06:00 — dizê-lo sobre uma corrida que fechou às 15h seria inventar um
  // fato para caber numa frase bonita.
  const quando = referencia?.madrugada ? ' na madrugada' : ''
  const regua = referencia ? ` (referência ${referencia.curta})` : ''
  return `${n === 1 ? 'concluída' : 'concluídas'}${quando}${regua}`
}
