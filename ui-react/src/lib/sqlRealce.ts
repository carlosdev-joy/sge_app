// Realce de SQL do chat dos agentes (C2 da spec docs/spec-agentes-ferramenta-banco.md, T5).
//
// Tokenizador PRÓPRIO, sem dependência nova: o bloco "Consulta SQL" só precisa
// separar palavra-chave, texto, número, comentário e nome — nada de parser.
// Duas garantias que os testes prendem:
//   • juntar os `texto` dos tokens devolve a entrada EXATA — o realce nunca
//     altera o que o usuário copia nem o que ele lê;
//   • nada aqui produz HTML: quem desenha monta elementos React com o texto.
// Sem imports: o harness Node (tests/js) executa este arquivo direto.

export type TipoTokenSql = 'palavra' | 'texto' | 'numero' | 'comentario' | 'nome' | 'outro'

export interface TokenSql {
  tipo: TipoTokenSql
  texto: string
}

// As palavras que o leitor procura com os olhos numa consulta. Não é a lista
// de reservadas do T-SQL: função comum (COUNT, CAST…) entra porque ajuda a
// ler; o que não está aqui aparece como texto normal, sem prejuízo.
const PALAVRAS = new Set(`
SELECT FROM WHERE JOIN INNER LEFT RIGHT FULL OUTER CROSS APPLY ON AND OR NOT IN IS NULL AS GROUP BY ORDER
HAVING TOP DISTINCT UNION ALL EXCEPT INTERSECT WITH CASE WHEN THEN ELSE END OVER PARTITION ROWS ROW RANGE
BETWEEN LIKE ESCAPE EXISTS ANY SOME ASC DESC OFFSET FETCH NEXT FIRST ONLY PERCENT TIES PIVOT UNPIVOT FOR
VALUES CAST TRY_CAST CONVERT TRY_CONVERT COALESCE NULLIF ISNULL IIF COUNT COUNT_BIG SUM AVG MIN MAX
STRING_AGG WITHIN ROW_NUMBER RANK DENSE_RANK LAG LEAD PRECEDING FOLLOWING UNBOUNDED CURRENT COLLATE
INSERT INTO UPDATE DELETE MERGE SET CREATE ALTER DROP TABLE VIEW DECLARE EXEC EXECUTE BEGIN COMMIT ROLLBACK
`.split(/\s+/).filter(Boolean))

const LETRA = /[A-Za-z_@#$À-ɏ]/
const PALAVRA = /[A-Za-z0-9_@#$À-ɏ]/

export function tokensSql(sql: string): TokenSql[] {
  const t: TokenSql[] = []
  const s = sql ?? ''
  let i = 0
  let outro = ''
  const soltar = () => { if (outro) { t.push({ tipo: 'outro', texto: outro }); outro = '' } }
  const ate = (fim: number, tipo: TipoTokenSql) => { soltar(); t.push({ tipo, texto: s.slice(i, fim) }); i = fim }

  while (i < s.length) {
    const c = s[i]
    if (c === '-' && s[i + 1] === '-') {
      const nl = s.indexOf('\n', i)
      ate(nl === -1 ? s.length : nl, 'comentario')
    } else if (c === '/' && s[i + 1] === '*') {
      const fim = s.indexOf('*/', i + 2)
      ate(fim === -1 ? s.length : fim + 2, 'comentario')
    } else if (c === "'" || ((c === 'N' || c === 'n') && s[i + 1] === "'" && !PALAVRA.test(s[i - 1] ?? ''))) {
      let j = s.indexOf("'", i) + 1
      for (;;) {
        const k = s.indexOf("'", j)
        if (k === -1) { j = s.length; break }
        if (s[k + 1] === "'") { j = k + 2; continue }
        j = k + 1
        break
      }
      ate(j, 'texto')
    } else if (c === '[' || c === '"') {
      const fecha = c === '[' ? ']' : '"'
      let j = i + 1
      for (;;) {
        const k = s.indexOf(fecha, j)
        if (k === -1) { j = s.length; break }
        if (s[k + 1] === fecha) { j = k + 2; continue }
        j = k + 1
        break
      }
      ate(j, 'nome')
    } else if (/[0-9]/.test(c) && !PALAVRA.test(s[i - 1] ?? '')) {
      let j = i + 1
      if (c === '0' && (s[j] === 'x' || s[j] === 'X')) {
        j++
        while (j < s.length && /[0-9a-fA-F]/.test(s[j])) j++
      } else {
        while (j < s.length && /[0-9.]/.test(s[j])) j++
        if ((s[j] === 'e' || s[j] === 'E') && /[0-9+-]/.test(s[j + 1] ?? '')) {
          j += 2
          while (j < s.length && /[0-9]/.test(s[j])) j++
        }
      }
      ate(j, 'numero')
    } else if (LETRA.test(c)) {
      let j = i + 1
      while (j < s.length && PALAVRA.test(s[j])) j++
      const w = s.slice(i, j)
      ate(j, PALAVRAS.has(w.toUpperCase()) ? 'palavra' : 'nome')
    } else {
      outro += c
      i++
    }
  }
  soltar()
  return t
}

/** "3 linhas · 0,8 s" — o rodapé de uma consulta executada. */
export function resumoConsulta(meta: { linhas?: number; havia_mais?: boolean; ms?: number }): string {
  const partes: string[] = []
  if (typeof meta.linhas === 'number') {
    const n = meta.linhas
    partes.push(meta.havia_mais ? `${n}+ linhas (havia mais)` : n === 1 ? '1 linha' : `${n} linhas`)
  }
  if (typeof meta.ms === 'number') {
    partes.push(meta.ms < 1000 ? `${meta.ms} ms` : `${(meta.ms / 1000).toFixed(1).replace('.', ',')} s`)
  }
  return partes.join(' · ')
}
