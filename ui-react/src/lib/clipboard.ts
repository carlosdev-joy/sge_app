// Cópia robusta para a área de transferência.
//
// `navigator.clipboard.writeText` só funciona em contextos seguros (HTTPS ou
// localhost). Em ambiente de intranet servido por HTTP, `navigator.clipboard`
// é `undefined` e os botões de copiar falham silenciosamente. Esta função tenta
// a API moderna e, se indisponível/rejeitada, cai no fallback com textarea +
// execCommand('copy'), que funciona em HTTP.

export async function copyToClipboard(text: string): Promise<boolean> {
  // Caminho moderno (contexto seguro)
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      /* cai no fallback abaixo */
    }
  }

  // Fallback: textarea fora da tela + execCommand
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.top = '-9999px'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, ta.value.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
