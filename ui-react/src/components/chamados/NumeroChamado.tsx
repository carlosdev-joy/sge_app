// O número de um chamado ou task, com o botão de copiar ao lado.
//
// Um componente só para os dois porque eles andam juntos em toda tela onde o
// número aparece — card do kanban, tasks filhas, tabela do painel, tabela dos
// indicadores, cabeçalho do detalhe — e o pedido foi exatamente esse: poder
// copiar o número em qualquer lugar, para levar a outra pessoa sem redigitar.
//
// Redigitar não é só lento: `RITM0103367` e `RITM0103387` diferem por um
// caractere, e um número errado numa conversa manda a outra pessoa investigar
// o chamado de outra pessoa.
import { useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { AVISO_COPIA, copiarTexto, type ResultadoCopia } from '../../lib/copiar'

export function NumeroChamado({ numero, aoAbrir, ajuda, className = '' }: {
  numero: string
  /** Quando existe, o número abre o detalhe. Sem isto ele é só texto. */
  aoAbrir?: () => void
  ajuda?: string
  className?: string
}) {
  // `null` = parado. Depois de copiar, o aviso vive ~2s e some.
  const [aviso, setAviso] = useState<ResultadoCopia | null>(null)
  const alvo = useRef<HTMLElement | null>(null)
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null)

  const copiar = async () => {
    const r = await copiarTexto(numero)
    // Não deu para escrever na área de transferência: seleciona o número na
    // tela, para o Ctrl+C do usuário pegar o texto CERTO. Sem isto, o aviso
    // "use Ctrl+C" mandaria o usuário selecionar à mão o que a tela trunca.
    if (r !== 'copiado' && alvo.current) {
      try {
        globalThis.getSelection?.()?.selectAllChildren(alvo.current)
      } catch { /* seleção é o resgate, não pode virar um segundo erro */ }
    }
    setAviso(r)
    if (relogio.current) clearTimeout(relogio.current)
    relogio.current = setTimeout(() => setAviso(null), 2500)
  }

  const conteudo = <span ref={alvo} className="font-mono">{numero}</span>

  return (
    <span className={`inline-flex items-center gap-1 min-w-0 ${className}`}>
      {aoAbrir
        ? (
          <button type="button" data-numero onClick={aoAbrir}
            className="font-semibold text-blue-600 dark:text-blue-400 hover:underline
              truncate min-w-0"
            title={ajuda || 'Ver descrição, histórico de notas e anexos'}>
            {conteudo}
          </button>
        )
        : <span data-numero className="text-ink truncate min-w-0">{conteudo}</span>}

      <button type="button" data-copiar onClick={copiar}
        className="shrink-0 text-dim hover:text-ink"
        // O `title` diz O QUE será copiado. "Copiar" sozinho, ao lado de um
        // número truncado, deixa a dúvida de se copia o número ou a linha.
        title={`Copiar ${numero}`}
        aria-label={`Copiar ${numero}`}>
        {aviso === 'copiado'
          ? <Check size={12} className="text-emerald-600 dark:text-emerald-400" />
          : <Copy size={12} />}
      </button>

      {/* A confirmação em PALAVRA, não só no ícone: copiar não muda nada na
          tela, e sem retorno o usuário clica de novo sem saber se funcionou.
          `aria-live` para quem usa leitor de tela receber o mesmo aviso. */}
      {aviso && (
        <span data-aviso aria-live="polite"
          className={`text-[10px] shrink-0 ${aviso === 'copiado'
            ? 'text-emerald-600 dark:text-emerald-400'
            : 'text-amber-600 dark:text-amber-400'}`}>
          {AVISO_COPIA[aviso]}
        </span>
      )}
    </span>
  )
}
