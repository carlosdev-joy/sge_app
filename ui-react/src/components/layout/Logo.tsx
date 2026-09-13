/** Marca ORQ: arquivos originais fornecidos pelo usuário, com transparência. */
export const ORQUESTRA_NAME = 'ORQ'
export const ORQUESTRA_SUBTITLE = 'Plataforma de Orquestração de Dados, Processos e Inteligência'

export interface LogoProps {
  variant?: 'white' | 'brand' | 'header'
  iconSize?: number
  showText?: boolean
  showSubtitle?: boolean
  className?: string
  children?: React.ReactNode
}

export function Logo({
  variant = 'brand', iconSize = 36, showText = true, showSubtitle = false,
  className = '', children,
}: LogoProps) {
  const src = showText ? '/images/orq/logo-name.png' : '/images/orq/logo-orbital.png'
  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      <span className="inline-flex flex-col">
        <span className={`orq-logo-image orq-logo-${variant}`} style={{ width: iconSize * (showText ? 2.5 : 1.5), height: iconSize }}>
          <img src={src} alt={ORQUESTRA_NAME} width={showText ? 1983 : 1536} height={showText ? 793 : 1024} />
          {/* A máscara visual usa o próprio arquivo: clareia somente as letras
              no fundo escuro, mantendo cores e forma do orbital original. */}
          {showText && <img src={src} alt="" aria-hidden="true" className="orq-logo-white-letters" />}
        </span>
        {showSubtitle && <span className={`text-[10px] max-w-64 ${variant === 'white' ? 'text-white/75' : 'text-dim'}`}>{ORQUESTRA_SUBTITLE}</span>}
      </span>
      {children}
    </div>
  )
}
