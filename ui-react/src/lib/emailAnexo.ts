// Anexo do nó de e-mail: o que é puro e dá para testar na bancada (F3 da spec
// docs/spec-email-modelos-e-navegacao.md).
//
// Quem escolhe o arquivo pelo navegador de pastas escolhe o arquivo DE HOJE —
// e amanhã a corrida procuraria o mesmo nome, não o do dia. Por isso o campo
// oferece trocar a data pelo marcador `{odate}`, que o operador resolve na
// hora do envio com a data de REFERÊNCIA da corrida.
//
// A troca é uma SUGESTÃO: o usuário aceita ou ignora. Trocar sozinho quebraria
// o caso legítimo do arquivo com data fixa no nome (uma carga histórica).

/** `{odate}` sai como AAAAMMDD (dags/utils/email_operator.py, `_odate`). */
const ODATE_RE = /(?<![0-9])(20[0-9]{2})(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])(?![0-9])/g

/** O nome do arquivo tem uma data AAAAMMDD que valeria a pena marcar?
 *
 * Devolve `{ sugestao, data }` ou `null`.
 *
 * Com DUAS datas diferentes no nome (um intervalo, `de_20260901_a_20260911`) a
 * sugestão não é feita: a tela não tem como saber qual das duas é a da corrida,
 * e trocar a primeira produziria um nome que não existe em dia nenhum. Datas
 * repetidas são o outro caso — aí todas viram o marcador. */
export function sugerirOdate(nome: string): { sugestao: string; data: string } | null {
  const texto = String(nome || '')
  // Já usa o marcador: nada a sugerir (nem quando sobrou uma data ao lado —
  // quem misturou os dois fez de propósito).
  if (texto.includes('{odate}')) return null
  const achadas = texto.match(ODATE_RE)
  if (!achadas || achadas.length === 0) return null
  const data = achadas[0]
  if (achadas.some(d => d !== data)) return null
  return { sugestao: texto.split(data).join('{odate}'), data }
}

/** Data AAAAMMDD legível para a frase da sugestão: 20260911 → 11/09/2026. */
export function dataLegivel(aaaammdd: string): string {
  const s = String(aaaammdd || '')
  return s.length === 8 ? `${s.slice(6, 8)}/${s.slice(4, 6)}/${s.slice(0, 4)}` : s
}
