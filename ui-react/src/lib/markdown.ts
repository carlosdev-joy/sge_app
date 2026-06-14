// Renderizador de markdown leve — espelha o _renderMarkdown da UI legada.
// Uso restrito ao Admin (conteúdo de versões), por isso o HTML é confiável.
// Faz escaping de & < > antes de aplicar as substituições.
export function renderMarkdown(text?: string): string {
  if (!text) return ''
  const html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // blocos de código ```...```
    .replace(/```([\s\S]*?)```/g, '<pre class="bg-canvas border border-edge rounded-md p-3 overflow-x-auto text-xs leading-relaxed my-2">$1</pre>')
    // código inline
    .replace(/`([^`]+)`/g, '<code class="bg-canvas px-1 py-0.5 rounded text-xs">$1</code>')
    // headers
    .replace(/^### (.+)$/gm, '<h4 class="font-bold text-sm mt-3 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-bold text-base mt-4 mb-1">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="font-bold text-lg mt-4 mb-1">$1</h2>')
    // negrito / itálico
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // listas
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // parágrafos / quebras
    .replace(/\n\n/g, '</p><p class="my-2">')
    .replace(/\n/g, '<br>')
  return `<div class="text-sm leading-relaxed"><p class="my-2">${html}</p></div>`
}
