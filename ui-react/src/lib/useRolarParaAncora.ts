// Chegada por âncora (/performance#sla, /powerbi#como-liberar-acessos): o
// React Router troca de tela mas não rola até o `id` do hash — o navegador só
// faz isso no carregamento inicial, e nem nele, porque a seção ainda não
// existe quando a página pinta. Este hook rola UMA vez por chegada (a `key` da
// location), quando `pronto` diz que o conteúdo acima já tem a altura final
// (senão a tabela que termina de carregar empurra a seção para baixo de novo).
//
// Ao chegar: um <details> alvo abre (a seção recolhível começa fechada, mas
// quem veio pelo link quer lê-la) e o foco vai para o título da seção
// (`tabindex="-1"`; no <details>, o próprio <summary>), para o leitor de tela
// anunciar onde a pessoa caiu.
import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

export function useRolarParaAncora(pronto: boolean): void {
  const { hash, key } = useLocation()
  const chegadaTratada = useRef<string | null>(null)

  useEffect(() => {
    if (!pronto || !hash || chegadaTratada.current === key) return
    let id: string
    try { id = decodeURIComponent(hash.slice(1)) } catch { return }
    const alvo = document.getElementById(id)
    if (!alvo) return
    if (alvo instanceof HTMLDetailsElement) alvo.open = true
    // Marca só quando rolou: um efeito desfeito antes do quadro (StrictMode,
    // re-render) cancela o quadro e a próxima execução tenta de novo.
    const quadro = requestAnimationFrame(() => {
      chegadaTratada.current = key
      alvo.scrollIntoView({ block: 'start' })
      const titulo = alvo instanceof HTMLDetailsElement
        ? alvo.querySelector<HTMLElement>(':scope > summary')
        : alvo.matches('[tabindex="-1"]') ? alvo : alvo.querySelector<HTMLElement>('[tabindex="-1"]')
      titulo?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(quadro)
  }, [pronto, hash, key])
}
