// Tema compartilhado com a UI legada: classe html.dark + localStorage['theme'].
// Default light (igual ao legado: qualquer valor != 'dark' é tratado como light).

export type Theme = 'light' | 'dark'

export function getTheme(): Theme {
  try {
    return localStorage.getItem('theme') === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('dark', t === 'dark')
  try { localStorage.setItem('theme', t) } catch { /* ignore */ }
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains('dark') ? 'light' : 'dark'
  applyTheme(next)
  return next
}

// Aplica o tema salvo o quanto antes (chamado em main.tsx, evita flash).
export function initTheme() {
  applyTheme(getTheme())
}
