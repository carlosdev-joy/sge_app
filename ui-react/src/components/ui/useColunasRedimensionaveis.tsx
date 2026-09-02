// Colunas de tabela que o usuário arrasta para ver o conteúdo inteiro.
//
// Nasceu na tela Etapas (2026-09-02): nomes de pipeline e de etapa passam da
// largura da coluna e ficavam truncados, com o valor inteiro só no `title` —
// que não dá para ler com calma nem copiar por partes.
//
// A largura fica no localStorage POR TABELA (a chave é o `id`), então a pessoa
// ajusta uma vez e a tela abre do jeito dela na próxima visita.
import { useCallback, useEffect, useRef, useState } from 'react'

/** Menor largura que ainda deixa o cabeçalho legível. Sem um piso, um arrasto
 *  distraído some com a coluna e não há como pegá-la de volta. */
const MIN_PX = 56

export interface ColunasRedimensionaveis {
  /** Largura atual de cada coluna, em px. */
  larguras: Record<string, number>
  /** `<colgroup>` da tabela — é ele que aplica as larguras. */
  colgroup: React.ReactNode
  /** Soma das larguras: use como `width` da tabela (com `table-layout: fixed`). */
  total: number
  /** Props da alça de arrasto, para render dentro do `<th>`. */
  alcaDe: (chave: string) => {
    onMouseDown: (e: React.MouseEvent) => void
    onDoubleClick: () => void
    onKeyDown: (e: React.KeyboardEvent) => void
  }
  /** Devolve UMA coluna à largura padrão (duplo clique na alça). */
  restaurar: (chave: string) => void
}

export function useColunasRedimensionaveis(
  id: string,
  padrao: Record<string, number>,
): ColunasRedimensionaveis {
  const chaveStorage = `orq.${id}.colunas`

  const [larguras, setLarguras] = useState<Record<string, number>>(() => {
    // localStorage pode estourar (janela privada, site data bloqueado) e pode
    // ter lixo de uma versão anterior da tabela: o padrão sempre entra por
    // baixo, então coluna nova nunca nasce sem largura.
    try {
      const salvo = JSON.parse(localStorage.getItem(chaveStorage) || '{}')
      const limpo: Record<string, number> = {}
      for (const [k, v] of Object.entries(salvo)) {
        if (k in padrao && typeof v === 'number' && v >= MIN_PX) limpo[k] = v
      }
      return { ...padrao, ...limpo }
    } catch {
      return { ...padrao }
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(chaveStorage, JSON.stringify(larguras))
    } catch {
      /* sem persistência é degradação aceitável: a tabela continua ajustável */
    }
  }, [chaveStorage, larguras])

  // O arrasto vive em refs, não em estado: um setState por pixel de mouse
  // re-renderiza a tabela inteira a cada movimento.
  const arrasto = useRef<{ chave: string; xInicial: number; larguraInicial: number } | null>(null)

  useEffect(() => {
    function mover(e: MouseEvent) {
      const a = arrasto.current
      if (!a) return
      const nova = Math.max(MIN_PX, a.larguraInicial + (e.clientX - a.xInicial))
      setLarguras(prev => (prev[a.chave] === nova ? prev : { ...prev, [a.chave]: nova }))
    }
    function soltar() {
      if (!arrasto.current) return
      arrasto.current = null
      // O cursor e a seleção ficam travados durante o arrasto; sem devolver
      // aqui, a página inteira segue com cursor de resize se o mouse soltar
      // fora da janela.
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', mover)
    window.addEventListener('mouseup', soltar)
    return () => {
      window.removeEventListener('mousemove', mover)
      window.removeEventListener('mouseup', soltar)
    }
  }, [])

  const restaurar = useCallback((chave: string) => {
    setLarguras(prev => ({ ...prev, [chave]: padrao[chave] }))
  }, [padrao])

  const alcaDe = useCallback((chave: string) => ({
    onMouseDown: (e: React.MouseEvent) => {
      e.preventDefault()   // sem isso o arrasto seleciona o texto do cabeçalho
      e.stopPropagation()  // e dispara a ordenação da coluna
      arrasto.current = { chave, xInicial: e.clientX, larguraInicial: larguras[chave] }
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    },
    onDoubleClick: () => restaurar(chave),
    // Teclado: a alça é focável, e ←/→ ajustam de 16 em 16. Redimensionar só
    // com mouse deixa de fora quem navega por teclado.
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      e.preventDefault()
      const passo = e.key === 'ArrowRight' ? 16 : -16
      setLarguras(prev => ({
        ...prev,
        [chave]: Math.max(MIN_PX, (prev[chave] ?? padrao[chave]) + passo),
      }))
    },
  }), [larguras, padrao, restaurar])

  const colgroup = (
    <colgroup>
      {Object.keys(padrao).map(k => <col key={k} style={{ width: larguras[k] }} />)}
    </colgroup>
  )

  const total = Object.keys(padrao).reduce((s, k) => s + (larguras[k] ?? 0), 0)

  return { larguras, colgroup, total, alcaDe, restaurar }
}
