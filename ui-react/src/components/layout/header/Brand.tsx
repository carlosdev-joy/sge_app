import { useAppVersion } from '../../../lib/version'
import { Logo } from '../Logo'

// Identidade visual (logo CVP + marca ORQUESTRA + versão). Reusada pelo header
// clássico e pelo header fino do shell v2. Volta à raiz (sistema) ao clicar.
export function Brand() {
  const appVersion = useAppVersion()
  return (
    <a href="/" className="shrink-0 flex items-center gap-3" title="Voltar ao sistema">
      <img
        src="/branding/logo-cvp.png"
        className="h-9 w-auto"
        alt="Caixa Vida e Previdência"
        onError={(e) => {
          const img = e.currentTarget
          if (!img.dataset.fallback) { img.dataset.fallback = '1'; img.src = '/images/logo-cvp.svg' }
        }}
      />
      <Logo variant="white" iconSize={28}>
        <span className="text-[9px] text-white/40 font-mono">v{appVersion}</span>
      </Logo>
    </a>
  )
}
