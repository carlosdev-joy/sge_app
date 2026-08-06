// O HISTÓRICO FACTUAL da malha (F12 — spec-malha-execucao §9.7, Decisão 68).
// Módulo PURO, como `tempoCorrida` e `duracaoTipica`: sem React e sem import de
// componente, para poder ser executado no Node byte a byte como está aqui (o
// produto faz deploy offline; acrescentar um runner de testes ao front traria
// dependência de rede).
//
// ── A FRONTEIRA, e ela é a razão deste arquivo existir ──────────────────────
// **Contar desfechos PASSADOS não é previsão.** A proibição de backfill do §3
// é contra INVENTAR corrida retroativa; ler as corridas que de fato existiram é
// fato registrado, disponível a partir do dia 2.
//
// Nada aqui prevê nada. Não existe "provavelmente vai falhar", não existe
// tendência, não existe score, e nenhuma frase deste módulo usa a palavra
// "previsão", "estimativa" ou "risco": o produto conta o que ACONTECEU e quem
// decide é a pessoa que está lendo às 3h. É a mesma fronteira que a Decisão 64
// traça do outro lado — lá o número é medido e vem com amostra; aqui ele é
// contado e vem com denominador.
//
//   card   falhou 2 das últimas 7 corridas
//   faixa  corrida anterior: 03/08 · concluída · 01:10 → 04:02
//   bloco  04/08 · concluída · 2h41 · travou: CARGA_A          (o `title`)
//
// ── ⚠️ O DIA 1 ──────────────────────────────────────────────────────────────
// Antes do primeiro smoke o histórico é literalmente ZERO. Toda função daqui
// devolve `null` sobre payload ausente ou vazio, e o card volta a ser o da F9 —
// byte a byte. `falhou 0 das últimas 0 corridas` seria um número sem amostra
// com cara de medida, que é o que esta spec inteira existe para não fazer:
// **`n = 0` é ausência, nunca "0%"**.
import { diaCurto, duracaoEntre, horaCurta, textoDuracao } from './tempoCorrida'
import type { CorridaCabecalho, HistoricoCorridas } from '../../types'

/** Os dias da semana por extenso, em pt-BR e no gênero certo — é assim que a
 *  frase sai: "as últimas 4 **terças** tiveram trabalho".
 *
 *  ⚠️ Índice de `getUTCDay()`: 0 = domingo. */
const DIAS_SEMANA = ['domingos', 'segundas', 'terças', 'quartas', 'quintas',
                     'sextas', 'sábados']

const RE_DIA = /^(\d{4})-(\d{2})-(\d{2})/

/** O rótulo de um estado quando o sujeito é uma corrida do PASSADO.
 *
 *  `STATUS_CORRIDA.SEM_TRABALHO` é escrito no presente — *"sem trabalho
 *  hoje"* — porque nasceu para a pílula da corrida CORRENTE. Aplicado sem
 *  ajuste às frases desta fase, ele produzia *"corrida anterior: 03/08 · sem
 *  trabalho hoje"*: a palavra "hoje" afirmando algo sobre anteontem, na linha
 *  cujo trabalho é exatamente responder *"está pior que ontem?"*.
 *
 *  O corte é do sufixo, e não um segundo mapa de rótulos: dois mapas para os
 *  mesmos sete estados é como o card e a faixa passam a chamar o mesmo
 *  desfecho por dois nomes. */
function rotuloPassado(status: string,
                       rotulo: (status: string) => string): string {
  return rotulo(status).replace(/\s+hoje$/, '')
}

/** O dia da semana de uma data de referência, no plural.
 *
 *  ⚠️ `Date.UTC(...)` e `getUTCDay()`, nunca `new Date('2026-08-04')` lido em
 *  hora local: aquele texto é interpretado como UTC e, em Brasília (UTC−3),
 *  a data "volta" um dia — a terça viraria segunda no rótulo. É o mesmo
 *  cuidado que `tempoCorrida` documenta para os carimbos. */
export function diaDaSemana(dataReferencia: string | null | undefined):
string | null {
  const m = RE_DIA.exec(String(dataReferencia ?? ''))
  if (!m) return null
  return DIAS_SEMANA[new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()]
}

/** `falhou 2 das últimas 7 corridas` — ou `null`.
 *
 *  Responde "está pior que antes?" sem obrigar o gestor a abrir malha por
 *  malha às 8h. Três silêncios deliberados:
 *
 *   • **sem histórico** (`consideradas === 0`) não sai nada. É o dia 1, e
 *     também a malha nova cuja primeira corrida ainda está em voo;
 *   • **zero falhas** não vira "falhou 0 das últimas 7": uma linha para dizer
 *     que está tudo como sempre esteve é ruído em 40 cards, e o card já diz o
 *     estado da corrente. O histórico só fala quando tem notícia;
 *   • o denominador é o do SERVIDOR (`consideradas`), nunca `janela`: dizer
 *     "das últimas 7" sobre uma malha que só teve 4 corridas seria inventar
 *     três madrugadas. */
export function textoFalhasRecentes(h: HistoricoCorridas | null | undefined):
string | null {
  if (!h || !h.consideradas || h.consideradas < 1) return null
  if (!h.falhou || h.falhou < 1) return null
  // Com UMA corrida no período a fração não existe: "falhou 1 das últimas 1
  // corridas" é a frase que faz o leitor duvidar do número ao lado. O fato é
  // o mesmo e a frase é outra.
  if (h.consideradas === 1) return 'falhou na última corrida'
  return `falhou ${h.falhou} das últimas ${h.consideradas} corridas`
}

/** `corrida anterior: 03/08 · concluída · 01:10 → 04:02` — ou `null`.
 *
 *  Exige `n = 1`, e não `n ≥ 5` (o piso da Decisão 64): isto é FATO, não
 *  mediana. É a resposta mais direta a "está pior que ontem?", e ela existe a
 *  partir da segunda corrida da malha.
 *
 *  `rotulo` vem de fora porque quem traduz status de corrida é o
 *  `STATUS_CORRIDA` do `statusExecucao` — importá-lo aqui puxaria `lucide-react`
 *  para dentro de um módulo que precisa rodar no Node sem React. */
export function textoCorridaAnterior(h: HistoricoCorridas | null | undefined,
                                     rotulo: (status: string) => string):
string | null {
  const a = h?.anterior
  if (!a) return null
  const dia = diaCurto(a.data_referencia) ?? a.data_referencia
  const nome = a.sequencia > 1 ? `${a.sequencia}ª corrida de ${dia}` : dia
  const partes = [`corrida anterior: ${nome}`, rotuloPassado(a.status, rotulo)]
  // O intervalo é ABSOLUTO (`01:10 → 04:02`), como todo tempo de corrida
  // FECHADA (Decisão 60): "há 22h" sobre uma corrida que acabou seria o
  // relógio de uma coisa colado no rótulo de outra.
  const inicio = horaCurta(a.aberta_em)
  const fim = horaCurta(a.fechada_em)
  if (inicio && fim) {
    const dur = textoDuracao(duracaoEntre(a.aberta_em, a.fechada_em))
    partes.push(`${inicio} → ${fim}${dur ? ` · ${dur}` : ''}`)
  }
  return partes.join(' · ')
}

/** `as últimas 4 terças tiveram trabalho` — ou `null`.
 *
 *  O caso que SÓ o histórico enxerga: alguém inativa membros numa terça, a
 *  corrida fecha `SEM_TRABALHO` e o card fica cinza e mudo — indistinguível de
 *  um sábado legítimo.
 *
 *  ⚠️ **No sábado a mesma malha continua cinza e muda.** Não é detalhe de
 *  polidez: um alarme de sábado toda semana treina o operador a ignorar o
 *  alarme (Decisão 26) — e aí ele ignora também a terça, que era a única que
 *  importava. Quem decide isso é o `atipico` do SERVIDOR; aqui só se escreve a
 *  frase, porque regra que mora em dois lugares vira duas regras. */
export function textoDiaAtipico(h: HistoricoCorridas | null | undefined,
                                dataReferencia: string | null | undefined):
string | null {
  const d = h?.dia_semana
  if (!d || !d.atipico) return null
  const dia = diaDaSemana(dataReferencia)
  return dia
    ? `as últimas ${d.com_trabalho} ${dia} tiveram trabalho`
    // Sem conseguir nomear o dia, a frase encolhe até o que continua
    // verdadeiro — nunca some, porque a COR já mudou e cor sem palavra é
    // exatamente o que a Decisão 59 proíbe.
    : `as últimas ${d.com_trabalho} ocorrências deste dia da semana tiveram trabalho`
}

/** O `title` de um bloco da faixa de corridas (Decisão 42 + Decisão 68).
 *
 *  `04/08 · concluída · 2h41 · travou: CARGA_A` — é o que transforma dez
 *  quadradinhos coloridos em diagnóstico: três madrugadas seguidas travando no
 *  MESMO membro é problema CRÔNICO e espera o horário comercial; nove verdes e
 *  uma vermelha é NOVIDADE e escala.
 *
 *  E ele carrega a AUDITORIA (Decisão 67), que é o que faltava para o
 *  fechamento do mês ser explicável sem abrir o banco: quem encerrou, por quê,
 *  por qual porta e se alguém já mexeu ali.
 *
 *  `linhas` (e não uma frase só) porque `title` respeita `\n`: às 3h a leitura
 *  é vertical, e uma frase de 180 caracteres numa linha só não se lê. */
export function tituloDoBloco(
  c: CorridaCabecalho,
  rotulo: (status: string) => string,
  /** Tradutor de `aberta_por`/`fechada_por` (formato de máquina) para gente —
   *  o `quemFez` do `statusExecucao`, injetado pela mesma razão do `rotulo`. */
  quem: (v: string | null | undefined) => string | null,
): string {
  const dia = diaCurto(c.data_referencia) ?? c.data_referencia
  const cabecalho = c.sequencia > 1
    ? `${c.sequencia}ª corrida de ${dia}`
    : `corrida de ${dia}`
  // O mesmo cuidado do `textoCorridaAnterior`: o bloco fala de uma corrida
  // datada, e "sem trabalho hoje" com a data de 09/08 ao lado é o presente
  // opinando sobre o passado.
  const linhas = [`${cabecalho} · ${rotuloPassado(c.status, rotulo)}`]
  const inicio = horaCurta(c.aberta_em)
  const fim = horaCurta(c.fechada_em)
  if (inicio && fim) {
    const dur = textoDuracao(duracaoEntre(c.aberta_em, c.fechada_em))
    linhas.push(`${inicio} → ${fim}${dur ? ` · ${dur}` : ''}`)
  } else if (inicio) {
    linhas.push(`aberta ${inicio}`)
  }
  // Decisão 68 — o nome de quem travou. `undefined` é "não apurei" e cala;
  // `null` é "apurei e ninguém travou" e também cala (o estado já diz).
  if (c.travou) {
    linhas.push(`travou: ${c.travou.pipeline}`)
  }
  // ── Decisão 67: a auditoria, na lista de corridas ───────────────────────
  const origem = textoOrigem(c)
  if (origem) linhas.push(origem)
  if (c.tentativas > 1) {
    const porQuem = quem(c.reaberta_por)
    linhas.push(`reaberta ${c.tentativas - 1}x`
      + (porQuem ? ` por ${porQuem}` : ''))
  }
  const fechou = pessoaQueFechou(c, quem)
  if (fechou) {
    linhas.push(`encerrada por ${fechou}`
      + (fim ? ` às ${fim}` : ''))
    const motivo = motivoLimpo(c.motivo)
    if (motivo) linhas.push(`motivo: "${motivo}"`)
  }
  return linhas.join('\n')
}

/** Decisão 44 — a marca discreta da ORIGEM, e ela só existe quando diz algo.
 *
 *  `origem = 'inicio'` é o caso normal e fica MUDO: uma linha em todo card
 *  para dizer "abriu como sempre abre" é ruído em 40 cards. As outras duas
 *  falam:
 *
 *   • `implicita` — **`sem nó Início`**. Nas 3 de 4 malhas sem Início o ODATE
 *     é "o que o primeiro membro achou", e apresentá-lo como "o ODATE da
 *     corrida" lhe dá uma autoridade que ele não tem;
 *   • `manual` — quem disparou. Na lista, uma corrida manual é hoje
 *     indistinguível de uma agendada, e são coisas diferentes na hora de
 *     entender por que a madrugada foi diferente. */
export function textoOrigem(c: CorridaCabecalho,
                            quem?: (v: string | null | undefined) => string | null):
string | null {
  if (c.origem === 'implicita') return 'sem nó Início'
  if (c.origem === 'manual') {
    const pessoa = quem ? quem(c.aberta_por) : matricula(c.aberta_por)
    return pessoa ? `início manual (${pessoa})` : 'início manual'
  }
  return null
}

/** A matrícula de um `manual:C123456`, sem depender do `quemFez`. */
function matricula(v: string | null | undefined): string | null {
  const s = String(v ?? '').trim()
  return s.startsWith('manual:') ? (s.slice('manual:'.length).trim() || null) : null
}

/** Quem encerrou, quando quem encerrou foi GENTE.
 *
 *  Decisão 67 quer "quem encerrou, por quê e por qual porta" na tela. Mas o
 *  fechador da imensa maioria das corridas é o monitor automático, e o
 *  `motivo` que ele grava é o texto do MOTOR ("3 pipeline(s) sem concluir: …")
 *  — vocabulário de máquina, que a Decisão 74 mantém fora da interface. Então
 *  a regra é o SUJEITO, não o status: fechou uma pessoa, o card diz quem e
 *  transcreve o que ela escreveu; fechou o monitor, a história dele é a aba de
 *  eventos, que é onde ela cabe. */
export function pessoaQueFechou(c: CorridaCabecalho,
                                quem: (v: string | null | undefined) => string | null):
string | null {
  return String(c.fechada_por ?? '').trim().startsWith('manual:')
    ? quem(c.fechada_por)
    : null
}

/** O `motivo` do encerramento manual vem composto pelo servidor como
 *  `"encerrada por C123456: <texto>"`. Quem e quando já saem numa linha
 *  estruturada — repetir o prefixo é ruído em cima da única frase que o
 *  operador escreveu com as próprias palavras.
 *
 *  ⚠️ E o prefixo **nem sempre está no começo do texto**: a coluna `motivo`
 *  ACUMULA em `' | '` (`SQL_FECHAR`/`SQL_REABRIR` concatenam com
 *  `LEFT(ISNULL(motivo + ' | ', '') + ..., 500)`), então uma corrida que foi
 *  reaberta e depois encerrada à mão chega assim:
 *
 *    `reaberta apos CONCLUIDA de 2026-08-04 05:12 | encerrada por C123456: …`
 *
 *  Uma limpeza ancorada em `^` não casaria, e o card publicaria o texto do
 *  MOTOR ("reaberta apos CONCLUIDA de…") — vocabulário de máquina, que a
 *  Decisão 74 mantém fora da interface — **e** repetiria "encerrada por
 *  C123456" na linha de baixo da que já diz exatamente isso. Por isso o corte
 *  é na ÚLTIMA ocorrência do prefixo: o encerramento manual é sempre o último
 *  trecho a ser concatenado, e o que vem antes dele é história do ciclo, cuja
 *  casa é a aba de eventos. */
const RE_ENCERRADA_POR = /(?:^|\|\s*)encerrada por [^:|]{1,80}:\s*/gi

export function motivoLimpo(v: string | null | undefined): string | null {
  if (!v) return null
  const texto = String(v)
  let corte = -1
  for (const m of texto.matchAll(RE_ENCERRADA_POR)) {
    if (m.index !== undefined) corte = m.index + m[0].length
  }
  // Sem o prefixo em lugar nenhum, o que sobrou é texto de MÁQUINA e o card
  // se cala. O caso existe: `LEFT(..., 500)` corta pelo FIM, então uma corrida
  // com muita história acumulada perde justamente a frase do operador — e aí
  // publicar o resto seria trocar a palavra dele pela do motor.
  return corte >= 0 ? (texto.slice(corte).trim() || null) : null
}
