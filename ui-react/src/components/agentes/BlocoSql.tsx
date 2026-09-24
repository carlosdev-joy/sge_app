// "Consulta SQL" do chat dos agentes (C5 da spec docs/spec-agentes-ferramenta-banco.md).
//
// Um bloco ```sql da resposta e cada consulta executada aparecem aqui:
// realce de palavras-chave, textos, números e comentários (tokenizador
// próprio, `lib/sqlRealce.ts`), fonte monoespaçada, rolagem horizontal e
// Copiar. O texto copiado é o do bloco, SEM alteração — o realce só pinta.
//
// Copiar vai por `lib/copiar.ts`, não `navigator.clipboard` direto: a
// produção é servida por HTTP, onde a API de clipboard não existe. O botão
// diz o que aconteceu ("copiado" / "use Ctrl+C" / "não copiou").
//
// Cores: palavra-chave no azul da marca (`cvp-blue`, com par escuro), texto
// e número nos tons permitidos com o par `dark:`, comentário em `dim`.
import { useMemo, useRef, useState } from 'react'
import { Copy } from 'lucide-react'
import { AVISO_COPIA, copiarTexto, type ResultadoCopia } from '../../lib/copiar'
import { tokensSql, type TipoTokenSql } from '../../lib/sqlRealce'

const COR: Record<TipoTokenSql, string> = {
  palavra: 'text-cvp-blue dark:text-orq-primary font-semibold',
  texto: 'text-emerald-700 dark:text-emerald-300',
  numero: 'text-amber-700 dark:text-amber-300',
  comentario: 'text-dim italic',
  nome: '',
  outro: '',
}

export function BlocoSql({ sql, rotulo, rodape }: {
  sql: string
  /** "conexão/banco" quando a consulta rodou num banco. */
  rotulo?: string
  /** "3 linhas · 0,8 s" nas consultas executadas. */
  rodape?: string
}) {
  const tokens = useMemo(() => tokensSql(sql), [sql])
  const [copia, setCopia] = useState<ResultadoCopia | null>(null)
  const alvo = useRef<HTMLPreElement | null>(null)

  async function copiar() {
    // `bruto`: o SQL como está — o espaço e a quebra de linha fazem parte.
    const r = await copiarTexto(sql, { bruto: true })
    // Não copiou: SELECIONA o SQL, para o "use Ctrl+C" do botão ser verdade
    // (o mesmo resgate do ModalConteudoArquivo e do NumeroChamado).
    if (r !== 'copiado' && alvo.current) {
      try { globalThis.getSelection?.()?.selectAllChildren(alvo.current) } catch { /* resgate, não erro */ }
    }
    setCopia(r)
    window.setTimeout(() => setCopia(null), 2500)
  }

  return (
    <figure className="my-1 rounded border border-edge bg-canvas text-ink" data-agentes-sql>
      <figcaption className="flex items-center gap-2 px-2 py-1 border-b border-edge text-[11px] text-dim">
        <span className="font-semibold text-ink">Consulta SQL</span>
        {rotulo && <span className="truncate" data-agentes-sql-banco>{rotulo}</span>}
        <button
          type="button"
          onClick={copiar}
          className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-panel border border-transparent
                     hover:border-edge focus:outline-none focus:ring-2 focus:ring-cvp-blue"
          aria-label="Copiar a consulta SQL"
          data-agentes-sql-copiar
        >
          <Copy className="w-3 h-3" aria-hidden="true" />
          <span aria-live="polite">{copia ? AVISO_COPIA[copia] : 'Copiar'}</span>
        </button>
      </figcaption>
      <pre ref={alvo} className="text-[11px] leading-relaxed font-mono p-2 overflow-x-auto whitespace-pre" tabIndex={0}
           aria-label="Consulta SQL">
        <code>
          {tokens.map((t, i) => (COR[t.tipo]
            ? <span key={i} className={COR[t.tipo]}>{t.texto}</span>
            : <span key={i}>{t.texto}</span>))}
        </code>
      </pre>
      {rodape && (
        <p className="px-2 py-1 border-t border-edge text-[11px] text-dim text-right" data-agentes-sql-rodape>
          {rodape}
        </p>
      )}
    </figure>
  )
}
