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
import { textoDuracao } from './tempoCorrida'
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
