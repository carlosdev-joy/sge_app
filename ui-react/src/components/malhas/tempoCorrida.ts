// Os relógios da corrida de malha (F4+/4 — spec-malha-execucao §9.4, Decisão
// 60). Módulo PURO: sem React, sem import nenhum — é o que permite testá-lo
// com o relógio deslocado, que é o único jeito de provar que ele não mente.
//
// ── O DEFEITO QUE ESTE MÓDULO EXISTE PARA EVITAR ────────────────────────────
// No dev, o SQL Server responde 13:59 enquanto o navegador (e o container da
// API) marcam 10:59: **3 horas de desvio, medidas**. Com isso:
//
//   frescor = Date.now() − Date.parse(apurado_em)     ← ERRADO
//
// daria "atualizado há -3h" (ou "agora" para sempre, se alguém aparar o
// negativo), e o alarme de dado velho **nunca dispararia** — um carimbo de
// frescor mentindo justamente sobre o próprio frescor. A regra é:
//
//   decorridoBase = apurado_em − aberta_em     ← os DOIS do banco, subtraídos
//                                                NO SERVIDOR (`decorrido_min`)
//   decorrido     = decorridoBase + (agora − instanteLocalDaResposta)
//   frescor       = agora − instanteLocalDaResposta   ← SÓ o relógio local
//
// `apurado_em` não entra em conta nenhuma: ele alimenta apenas o texto
// ABSOLUTO do tooltip ("apurado em 05/08/2026 13:59:20"), onde o desvio é
// informação, não erro.
//
// ── Por que nada aqui usa `new Date(texto)` ─────────────────────────────────
// O contrato manda 'YYYY-MM-DD HH:MM:SS' (sem fuso) e 'YYYY-MM-DD' na data de
// referência. `new Date('2026-08-05')` é interpretado como UTC e, em Brasília
// (UTC−3), `toLocaleDateString` devolve **04/08** — a corrida de hoje
// apareceria como a de ontem no card. Aqui os carimbos são lidos por regex e a
// aritmética entre DOIS deles é feita em UTC puro: mesmo relógio nas duas
// pontas, sem horário de verão no meio.

/** Acima disto o dado na tela é velho o bastante para virar alarme (§9.4). */
export const LIMIAR_DADO_VELHO_MS = 90_000

const RE_CARIMBO = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/
const RE_DIA = /^(\d{4})-(\d{2})-(\d{2})$/

/** Carimbo do banco → epoch tratando o texto como UTC. O valor absoluto NÃO
 *  tem significado (o banco não diz o fuso); só a DIFERENÇA entre dois
 *  carimbos da mesma origem tem — e é só para isso que ele é usado. */
function epochDoCarimbo(v: string | null | undefined): number | null {
  if (!v) return null
  const m = RE_CARIMBO.exec(v)
  if (!m) return null
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] ?? 0))
}

/** 'YYYY-MM-DD HH:MM:SS' → 'HH:MM'. Fora do formato, devolve o texto cru — a
 *  tela mostra o que o banco tem, nunca um "Invalid Date". */
export function horaCurta(v: string | null | undefined): string | null {
  if (!v) return null
  const m = RE_CARIMBO.exec(v)
  return m ? `${m[4]}:${m[5]}` : v
}

/** 'YYYY-MM-DD' (data de referência) ou carimbo completo → 'DD/MM'. */
export function diaCurto(v: string | null | undefined): string | null {
  if (!v) return null
  const d = RE_DIA.exec(v) ?? RE_CARIMBO.exec(v)
  return d ? `${d[3]}/${d[2]}` : v
}

/** Texto ABSOLUTO do tooltip — o único lugar em que `apurado_em` aparece. */
export function carimboLongo(v: string | null | undefined): string | null {
  if (!v) return null
  const m = RE_CARIMBO.exec(v)
  if (!m) return v
  return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}:${m[6] ?? '00'}`
}

/** Duração em minutos → texto pt-BR.
 *
 *  Três formas, e a fronteira de cada uma é o que o operador precisa a 1,5 m:
 *  abaixo de 1 h o minuto é o dado; entre 1 h e 1 dia o formato compacto
 *  (`3h50`) cabe no card; acima de 24 h o dia inteiro virou incidente e o
 *  número precisa gritar (`25h 14min`). */
export function textoDuracao(min: number | null | undefined): string | null {
  if (min === null || min === undefined || !isFinite(min)) return null
  const total = Math.max(0, Math.floor(min))
  if (total < 1) return 'menos de 1 min'
  if (total < 60) return `${total} min`
  const h = Math.floor(total / 60)
  const m = total % 60
  if (total < 24 * 60) return m === 0 ? `${h}h` : `${h}h${String(m).padStart(2, '0')}`
  return m === 0 ? `${h}h` : `${h}h ${m}min`
}

/** Minutos entre dois carimbos DO BANCO. Legítimo no cliente porque as duas
 *  pontas vêm do MESMO relógio: o desvio cancela na subtração (é o oposto de
 *  misturar `apurado_em` com `Date.now()`). */
export function duracaoEntre(a: string | null | undefined,
                             b: string | null | undefined): number | null {
  const ea = epochDoCarimbo(a)
  const eb = epochDoCarimbo(b)
  if (ea === null || eb === null) return null
  return Math.max(0, Math.round((eb - ea) / 60_000))
}

/** O DECORRIDO da corrida em voo: a base subtraída no servidor mais o tempo
 *  que passou no relógio LOCAL desde que a resposta chegou. */
export function decorridoMin(baseMin: number | null | undefined,
                             respostaEm: number, agora: number): number | null {
  if (baseMin === null || baseMin === undefined || !isFinite(baseMin)) return null
  const desdeAResposta = Math.max(0, agora - respostaEm)
  return Math.max(0, Math.floor(baseMin + desdeAResposta / 60_000))
}

export interface Frescor {
  /** Idade da resposta em ms — só relógio local, nunca negativa. */
  ms: number
  /** Texto de granularidade GROSSA (§9.4): precisão de segundo em polling de
   *  20 s sugere tempo real, e dois cards com "há 8s" e "há 31s" na mesma tela
   *  fazem duvidar dos dois. */
  texto: string
  /** Passou de 90 s sem refetch com sucesso: o dado na tela é velho. */
  velho: boolean
}

/** O FRESCOR — o relógio local consigo mesmo, e com mais nenhum.
 *
 *  `respostaEm` é o instante LOCAL em que a resposta chegou (o
 *  `dataUpdatedAt` do react-query). Com o relógio do banco 3 h à frente, isto
 *  continua dizendo "agora" no instante da resposta, e o alarme dispara aos
 *  90 s como deve. */
export function frescor(respostaEm: number, agora: number): Frescor {
  // Nunca negativo: relógio do sistema ajustado para trás no meio da sessão
  // faria "há -2 min", que é pior que a imprecisão que o clamp introduz.
  const ms = Math.max(0, agora - respostaEm)
  const velho = ms > LIMIAR_DADO_VELHO_MS
  let texto: string
  if (ms < 30_000) texto = 'agora'
  else if (ms < 60_000) texto = 'há menos de 1 min'
  else texto = `há ${textoDuracao(Math.floor(ms / 60_000))}`
  return { ms, texto, velho }
}
