/** Preferência local de apresentação; não participa de definição/payload. */
export type Density = 'comfortable' | 'compact'
const KEY = 'orquestra-ui-density-v1'

export function getDensity(): Density {
  try { return localStorage.getItem(KEY) === 'compact' ? 'compact' : 'comfortable' }
  catch { return 'comfortable' }
}

export function applyDensity(density: Density) {
  document.documentElement.dataset.density = density
  try { localStorage.setItem(KEY, density) } catch { /* sessão funciona sem storage */ }
}

export function initDensity() { applyDensity(getDensity()) }
