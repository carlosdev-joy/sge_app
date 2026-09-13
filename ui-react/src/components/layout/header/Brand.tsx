import { Link } from 'react-router-dom'
import { useAppVersion } from '../../../lib/version'
import { Logo } from '../Logo'

// Identidade visual (logo CVP + marca ORQ + versão). Reusada pelo header
// clássico e pelo header fino do shell v2. Volta à raiz (sistema) ao clicar.
export function Brand() {
  const appVersion = useAppVersion()
  return (
    <Link to="/" className="shrink-0 flex items-center gap-3 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white" aria-label="Ir para o início do ORQ" title="Voltar ao sistema">
      <img
        src="/branding/logo-cvp.png"
        className="hidden md:block h-9 w-auto max-w-28 object-contain"
        alt="Caixa Vida e Previdência"
        onError={(e) => {
          const img = e.currentTarget
          if (!img.dataset.fallback) { img.dataset.fallback = '1'; img.src = '/images/logo-cvp.svg' }
        }}
      />
      <span aria-hidden="true" className="hidden md:block h-6 w-px bg-white/25" />
      <Logo variant="header" iconSize={28}>
        <span className="hidden sm:inline text-[9px] text-white/75 font-mono">v{appVersion}</span>
      </Logo>
    </Link>
  )
}
