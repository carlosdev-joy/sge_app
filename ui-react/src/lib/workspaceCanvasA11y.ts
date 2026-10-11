// Acessibilidade do canvas compartilhado (Montagem e Execução). Sem React nem DOM
// real: a bancada tests/js/workspace_execution_harness.cjs executa este arquivo.

// Reenquadrar a etapa é instantâneo quando o sistema pede movimento reduzido.
export const FIT_VIEW_MS = 200
export function fitViewDuration(media?: ((query: string) => { matches: boolean }) | null): number {
 try { return media?.('(prefers-reduced-motion: reduce)').matches ? 0 : FIT_VIEW_MS } catch { return FIT_VIEW_MS }
}

export interface CanvasKey { key: string; repeat: boolean; isComposing: boolean; ctrlKey: boolean; altKey: boolean; metaKey: boolean; shiftKey: boolean; defaultPrevented: boolean }
export interface CanvasKeyTarget { classList: { contains(name: string): boolean }; getAttribute(name: string): string | null }

// Enter puro sobre a própria etapa focada (não um controle dentro dela) devolve a
// etapa a selecionar; qualquer outro caso fica com quem já trata a tecla.
export function nodeForEnter(event: CanvasKey, target: CanvasKeyTarget | null, known: (id: string) => boolean, overlay: boolean): string | null {
 if (event.key !== 'Enter' || event.defaultPrevented || event.repeat || event.isComposing || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || overlay) return null
 if (!target || !target.classList.contains('react-flow__node')) return null
 const id = target.getAttribute('data-id')
 return id && known(id) ? id : null
}
