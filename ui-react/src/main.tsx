import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initTheme } from './lib/theme'
import { initDensity } from './lib/density'

// Aplica o tema salvo (compartilhado com a UI legada) antes de renderizar.
initTheme()
initDensity()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
