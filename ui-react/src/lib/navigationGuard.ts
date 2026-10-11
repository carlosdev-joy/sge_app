import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { confirmAction } from './dialogs'

// Proteção de saída para alterações locais sobre o BrowserRouter existente.
// Links (clique), voltar/avançar (popstate) e navegações programáticas passam
// pelo mesmo registro; cada guarda decide se o destino sai da sua sessão. A
// confirmação é o diálogo da aplicação e só navega se a tela continua no
// endereço em que a pergunta foi feita.
//
// Voltar/avançar: o listener de popstate é instalado na carga do módulo (App
// importa este arquivo antes de montar o BrowserRouter), portanto roda antes do
// listener do router. Uma saída protegida é interceptada, desfeita com
// history.go pelo índice que o próprio router grava em history.state.idx e só
// é refeita depois da confirmação. Entradas sem esse índice não são desfeitas.
export interface NavigationGuard { leaves: (from: URL, to: URL) => boolean; message: string; onLeave?: () => void }
export interface NavigationGuardEntry { guard: () => NavigationGuard | null; navigate: (to: string) => void }

let win: Window | null = null
const entries = new Set<NavigationGuardEntry>()
let accepted: { href: string; index: number | null } | null = null
let reverting = false, bypass = false, unloading = false

function routerIndex(): number | null {
 const idx = (win?.history.state as { idx?: unknown } | null)?.idx
 return typeof idx === 'number' ? idx : null
}
function blocking(from: URL, to: URL): { entry: NavigationGuardEntry; guard: NavigationGuard } | null {
 for (const entry of entries) { const guard = entry.guard(); if (guard?.leaves(from, to)) return { entry, guard } }
 return null
}
function leaving(from: URL, to: URL) {
 for (const entry of [...entries]) { const guard = entry.guard(); if (guard?.leaves(from, to)) guard.onLeave?.() }
}
async function confirmLeave(to: URL, go: (entry: NavigationGuardEntry | null) => void) {
 if (!win) { go(null); return }
 const asked = win.location.href, from = new URL(asked), found = blocking(from, to)
 if (!found) { go(null); return }
 if (!await confirmAction(found.guard.message, () => win?.location.href === asked)) return
 leaving(from, to); go(found.entry)
}
function onClick(event: MouseEvent) {
 if (!win || !entries.size || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
 const target = event.target as Element | null
 const anchor = typeof target?.closest === 'function' ? target.closest<HTMLAnchorElement>('a[href]') : null
 if (!anchor || (anchor.target && anchor.target !== '_self') || anchor.hasAttribute('download')) return
 const to = new URL(anchor.href, win.location.href), current = win
 if (!blocking(new URL(current.location.href), to)) return
 event.preventDefault(); event.stopImmediatePropagation()
 void confirmLeave(to, entry => {
  if (to.origin === current.location.origin && entry) entry.navigate(to.pathname + to.search + to.hash)
  else { unloading = true; current.location.assign(to.href) }
 })
}
function onPop(event: PopStateEvent) {
 if (!win) return
 if (reverting) { reverting = false; event.stopImmediatePropagation(); return }
 if (bypass) { bypass = false; return }
 if (!entries.size || !accepted) return
 const from = new URL(accepted.href), to = new URL(win.location.href), index = routerIndex(), found = blocking(from, to)
 if (!found) return
 const delta = index !== null && accepted.index !== null ? accepted.index - index : 0
 if (!delta) return
 event.stopImmediatePropagation()
 reverting = true; win.history.go(delta)
 const current = win
 void confirmAction(found.guard.message, () => !reverting && current.location.href === from.href).then(ok => {
  if (!ok) return
  leaving(from, to); bypass = true; current.history.go(-delta)
 })
}
function onUnload(event: BeforeUnloadEvent) {
 if (unloading || !entries.size) return
 event.preventDefault(); event.returnValue = ''
}

export function installNavigationGuard(target: Window) {
 if (win) return
 win = target
 target.addEventListener('popstate', onPop)
 target.document.addEventListener('click', onClick, true)
}
if (typeof window !== 'undefined') installNavigationGuard(window)

// Endereço aceito pelo router: base para desfazer um voltar/avançar.
export function acceptNavigation() { if (win) accepted = { href: win.location.href, index: routerIndex() } }
export function registerNavigationGuard(entry: NavigationGuardEntry): () => void {
 entries.add(entry)
 if (entries.size === 1) win?.addEventListener('beforeunload', onUnload)
 return () => { entries.delete(entry); if (!entries.size) win?.removeEventListener('beforeunload', onUnload) }
}
// Navegação programática (seletores, ações) sujeita às mesmas guardas.
export function guardedNavigation(to: string, navigate: (to: string) => void) {
 void confirmLeave(new URL(to, win?.location.href ?? 'http://localhost/'), () => navigate(to))
}

// A guarda vale enquanto `guard` não for nulo (ex.: há alterações não salvas).
export function useNavigationGuard(guard: NavigationGuard | null) {
 const navigate = useNavigate(); const location = useLocation()
 const current = useRef(guard)
 useLayoutEffect(() => { current.current = guard })
 useLayoutEffect(() => { acceptNavigation() }, [location.key])
 const active = !!guard
 useEffect(() => active ? registerNavigationGuard({ guard: () => current.current, navigate }) : undefined, [active, navigate])
}
export function useGuardedNavigate(): (to: string) => void {
 const navigate = useNavigate()
 return useCallback((to: string) => guardedNavigation(to, navigate), [navigate])
}
