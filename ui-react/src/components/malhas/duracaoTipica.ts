// A DURAÇÃO TÍPICA por membro (F12 — spec-malha-execucao §9.5, Decisão 64).
// Módulo PURO, como `tempoCorrida`: sem React e sem import de componente — é o
// que permite executá-lo no Node, byte a byte como está aqui, sem runner de
// testes no front (e o produto faz deploy offline: acrescentar um runner traria
// dependência de rede).
//
// ── A pergunta que este módulo responde ─────────────────────────────────────
// `4 de 7 · 2 rodando · há 12 min` não diz se os dois vivos são de 5 min ou de
// 3h. Sem isso, `4 de 7` com os dois pipelines mais pesados ainda por rodar
// parece "quase lá" — e manda o operador dormir na noite errada.
//
//   CARGA_B · há 12 min · típico 18 min (n=23)      normal
//   CARGA_D · há 41 min · típico 18 min (n=23)  ⚠ 2x   acima de 2x o p50
//   CARGA_E · há  3 min                             n < 5: SÓ o decorrido
//
// ── As três regras que o tornam honesto ─────────────────────────────────────
//  1. **piso duro de `n ≥ 5`** — quem não passou nem chega aqui: o servidor não
//     o inclui na lista. Sem amostra não sai número;
//  2. **o `n` nunca aparece sozinho.** Ou saem o típico e o `n` juntos, num
//     texto só, ou não sai nada. `(n=23)` ao lado de nada é ruído com cara de
//     precisão;
//  3. **isto NÃO é ETA.** É a duração típica DAQUELE membro, medida. Somar
//     típicos não dá previsão de conclusão da corrida — ela roda em paralelo e
//     com dependências —, e nenhuma frase daqui usa a palavra "previsão",
//     "estimativa" ou "conclusão".
//
// ── A marca `⚠ 2x` é leitura de tela, não evento ────────────────────────────
// Ela pinta de âmbar o membro que já passou de duas vezes a própria mediana. E
// para aí: **não vira alarme no Teams**. Um alarme por "está demorando" tocaria
// toda madrugada, e alarme que toca sempre é alarme que ninguém lê (Decisões
// 26/27).
import { decorridoMin, duracaoEntre, textoDuracao } from './tempoCorrida'
import type { TipicoMembro, TipicosApi } from '../../types'

/** A partir de quantas vezes o p50 o membro fica âmbar. */
export const FATOR_ATIPICO = 2

/** Índice por nome de pipeline, em `casefold`.
 *
 *  ⚠️ A ponte de caixa é obrigatória, e não zelo: os nomes de `execucoes[]` vêm
 *  da grafia OFICIAL de `etl_pipeline` e os de `tipicos[]` vêm do SNAPSHOT da
 *  corrida, que guarda a grafia do dia da abertura. O SQL Server compara sem
 *  distinguir caixa; o `Map` do JavaScript distingue. Sem a ponte, `CARGA_A` e
 *  `Carga_A` seriam dois membros e o típico sumiria da linha — em silêncio,
 *  que é o pior jeito de um número desaparecer. */
export function mapaTipicos(tipicos: TipicosApi | null | undefined):
Map<string, TipicoMembro> {
  const mapa = new Map<string, TipicoMembro>()
  for (const t of tipicos?.itens ?? []) {
    const chave = String(t.pipeline ?? '').trim().toLowerCase()
    if (chave) mapa.set(chave, t)
  }
  return mapa
}

/** O típico de UM membro, ou `undefined` — que é "não tenho amostra para ele". */
export function tipicoDe(mapa: Map<string, TipicoMembro>,
                         pipeline: string): TipicoMembro | undefined {
  return mapa.get(String(pipeline ?? '').trim().toLowerCase())
}

/** Minutos do p50 — o arredondamento mora aqui, num lugar só.
 *
 *  Abaixo de 1 min a fração passa inteira para `textoDuracao`, que responde
 *  "menos de 1 min": arredondar 20 s para "1 min" seria inventar meio minuto
 *  num número que existe para ser comparado com o decorrido. */
export function minutosTipicos(t: TipicoMembro | null | undefined):
number | null {
  const seg = t?.p50_seg
  if (seg === null || seg === undefined || !isFinite(seg) || seg <= 0) {
    return null
  }
  return seg < 60 ? seg / 60 : Math.round(seg / 60)
}

/** `típico 18 min (n=23)` — ou `null`, e aí a linha mostra só o decorrido.
 *
 *  Os dois números saem juntos DE PROPÓSITO: é esta função que garante que o
 *  `n` nunca apareça sem o número ao lado. */
export function textoTipico(t: TipicoMembro | null | undefined): string | null {
  const min = minutosTipicos(t)
  if (min === null || !t) return null
  const dur = textoDuracao(min)
  return dur === null ? null : `típico ${dur} (n=${t.n})`
}

/** A marca do atípico: `⚠ 2x`, `⚠ 3x`… — ou `null` abaixo do fator.
 *
 *  O múltiplo é **truncado** (41 min sobre um p50 de 18 dá 2,3× e a marca diz
 *  `2x`): arredondar para cima diria `3x` de algo que ainda não é o triplo, e
 *  este número aparece ao lado de um relógio que o operador consegue conferir
 *  na mesma linha. */
export function marcaAtipica(decorridoMin: number | null | undefined,
                             t: TipicoMembro | null | undefined): string | null {
  const min = minutosTipicos(t)
  if (min === null || min <= 0) return null
  if (decorridoMin === null || decorridoMin === undefined
      || !isFinite(decorridoMin)) {
    return null
  }
  const vezes = Math.floor(decorridoMin / min)
  return vezes >= FATOR_ATIPICO ? `⚠ ${vezes}x` : null
}

/** O `title` da marca — a frase que diz o FATO e recusa a palavra proibida.
 *
 *  "está demorando mais que o normal" é leitura de tela; "vai atrasar" seria
 *  previsão, e previsão de conclusão de corrida não sai de duração de membro. */
export function tituloAtipico(t: TipicoMembro | null | undefined):
string | null {
  const texto = textoTipico(t)
  return texto === null
    ? null
    : `Já passou de ${FATOR_ATIPICO}x a duração típica deste pipeline `
      + `(${texto}). É leitura de tela, não alarme.`
}

// ═══════ O PERCENTUAL DA DECISÃO 56b — e ele mede TEMPO, nunca pipelines ════
//
// O "%" que o usuário pediu ("dentro de cada malha % de execução"), e o ÚNICO
// que esta spec permite em superfície nenhuma.
//
// ── Por que não é percentual de CONTAGEM (Decisão 56) ──────────────────────
// Numa malha de 6 em que o último pipeline leva 3h e os cinco primeiros levam
// 5 min cada, `5 de 6` é 83% dos pipelines e **12% do trabalho**: aos 25
// minutos o painel diria "83%" faltando 87% do tempo, e o operador iria dormir.
// O percentual ponderado dá 12%, que é a verdade. É a mesma razão por que a
// `ui/Progress` exige `aria-valuetext`: sem ele o leitor de tela calcularia
// "57%" de `4/7` sozinho — o percentual de contagem entrando pela porta da
// acessibilidade.
//
// ── As regras que o tornam honesto, e a ausência de QUALQUER uma o tira ────
//  1. **minutos, não pipelines** — numerador e denominador são a duração
//     típica de cada membro (Decisão 64);
//  2. **`n ≥ 5` em TODOS os membros do snapshot** (`tipicos.completo`).
//     Faltando um só, o percentual SOME por inteiro: não é estimado, não é
//     "aproximado com ressalva". Fica o `x de y` e a duração típica dos vivos;
//  3. **`≈` e "do tempo típico", sempre.** Nunca `60%` solto, nunca a palavra
//     "concluído". O `≈` é parte do dado, não enfeite: ele remove a promessa de
//     precisão que um número de duas casas daria a uma mediana;
//  4. **`Math.floor`, teto em 99** enquanto a corrida não é terminal — o
//     arredondamento `99,6 → 100` é o defeito clássico, e "100%" com a corrida
//     aberta é a palavra "pronto" dita por um número;
//  5. **nenhum percentual em corrida TERMINAL** — lá o estado já diz tudo, e
//     um "≈ 94%" ao lado de "concluída" só levantaria a dúvida de onde foram
//     parar os 6%;
//  6. **ele nunca substitui o `x de y`**, que continua primário e primeiro. O
//     percentual é o SEGUNDO número, e some antes dele em qualquer aperto de
//     espaço (por isso o CARD não o recebe: lá cabe uma coisa só).
//
// ── ⚠️ O denominador NÃO ENCOLHE, e isso é deliberado ──────────────────────
// Ele é a soma dos típicos de TODOS os membros do snapshot — inclusive os
// `PULADO` de hoje, que somam zero no numerador. A alternativa (tirá-los dos
// dois lados) faria o número SUBIR sozinho no instante em que três pipelines
// fossem barrados por divergência de ODATE: é o incidente `Carga_Vida` outra
// vez, um andar acima, com o olho lendo "avançou" onde a situação piorou. O
// preço é um número que sub-lê num dia com muitos dispensados — e ele erra
// para o lado de "não vá dormir", que é o lado certo de errar.
export const TETO_PERCENTUAL_EM_VOO = 99

/** O estado de um membro, do jeito que `execucoes[]` entrega. */
export interface MembroEmCurso {
  pipeline_name: string
  status: string
  inicio: string | null
}

export interface EntradaPercentual {
  tipicos: TipicosApi | null | undefined
  execucoes: MembroEmCurso[]
  /** Status e saúde da CORRIDA — o percentual não existe em corrida terminal,
   *  e `ATRASADA` é o único caso em que ele passa de 100. */
  status: string
  saude?: string | null
  /** Relógio do BANCO no instante da apuração: a outra ponta do decorrido de
   *  cada membro (Decisão 60). Nunca `Date.now()` contra `inicio`. */
  apuradoEm: string | null | undefined
  /** Instante LOCAL da resposta e o relógio LOCAL de agora. */
  respostaEm: number
  agoraLocal: number
}

/** `{ pct, texto }` — ou `null`, e aí a faixa mostra só o `x de y`.
 *
 *  `null` é a resposta em TODOS estes casos, e nenhum deles vira número: sem
 *  `tipicos`, sem `completo`, sem denominador, e em corrida terminal. */
export function percentualTempoTipico(e: EntradaPercentual):
{ pct: number; texto: string } | null {
  const t = e.tipicos
  // Regra 2: o piso é do CONJUNTO, não do membro. Um único membro sem amostra
  // e o número inteiro deixa de existir — porque a fatia dele seria zero no
  // denominador, e um denominador incompleto infla tudo o que está em cima.
  if (!t || t.completo !== true) return null
  // Regra 5: corrida terminal não tem percentual.
  if (e.status !== 'ABERTA') return null

  const emCurso = new Map<string, MembroEmCurso>()
  for (const x of e.execucoes) {
    // A MESMA ponte de caixa do `mapaTipicos`, e pela mesma razão.
    const chave = String(x.pipeline_name ?? '').trim().toLowerCase()
    if (chave) emCurso.set(chave, x)
  }

  // `ATRASADA` é o único estado em que a fatia de um membro pode passar da
  // própria duração típica. Fora dele o teto por membro existe para que UM
  // pipeline lento não pinte progresso que não houve; dentro dele, truncar
  // esconderia exatamente o que o operador precisa ver — `≈ 140% do tempo
  // típico` É o sinal de atraso.
  const semTeto = e.saude === 'ATRASADA'
  let denominador = 0
  let numerador = 0
  for (const item of t.itens) {
    const fatia = minutosTipicos(item)
    if (fatia === null) continue
    denominador += fatia
    const membro = emCurso.get(
      String(item.pipeline ?? '').trim().toLowerCase())
    if (!membro) continue
    if (membro.status === 'SUCESSO') {
      numerador += fatia
      continue
    }
    // Só quem está RODANDO acumula. `AGUARDANDO_DEPENDENCIA` acumula tempo de
    // FILA, e fila não é trabalho: contá-la faria o número subir enquanto nada
    // acontece, que é o oposto do que ele existe para dizer. Falha e pulado
    // somam zero — nem trabalho feito, nem trabalho em curso.
    if (membro.status !== 'EXECUTANDO') continue
    const decorrido = decorridoMin(
      duracaoEntre(membro.inicio, e.apuradoEm), e.respostaEm, e.agoraLocal)
    if (decorrido === null) continue
    numerador += semTeto ? decorrido : Math.min(decorrido, fatia)
  }
  if (denominador <= 0) return null

  const bruto = Math.floor((numerador / denominador) * 100)
  // Regra 4: acima de 100 só existe de verdade no ramo sem teto; abaixo dele,
  // 100 com a corrida aberta é a palavra "pronto" dita por um número.
  const pct = bruto >= 100 && !semTeto ? TETO_PERCENTUAL_EM_VOO : bruto
  return { pct, texto: `≈ ${pct}% do tempo típico` }
}
