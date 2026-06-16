/**
 * Logo ORQUESTRA — símbolo abstrato de pipeline:
 * três linhas paralelas diagonais (entrada → processamento → saída)
 * com nós de conexão, nas cores corporativas.
 *
 * variant="white"  → para fundos escuros/azuis (header, login lateral)
 * variant="brand"  → para fundos claros (standalone, ícone colorido)
 *
 * Alterar ORQUESTRA_NAME ou ORQUESTRA_SUBTITLE aqui reflete em todos os locais.
 */

export const ORQUESTRA_NAME     = 'ORQUESTRA'
export const ORQUESTRA_SUBTITLE = 'Gestão de Pipelines'

export interface LogoProps {
  variant?:  'white' | 'brand'
  iconSize?: number
  showText?: boolean
  className?: string
  /** Slot renderizado após o nome (ex.: badge de versão no header) */
  children?: React.ReactNode
}

export function Logo({
  variant  = 'brand',
  iconSize = 36,
  showText = true,
  className = '',
  children,
}: LogoProps) {
  const w = variant === 'white'

  /* Cores do símbolo SVG */
  const c1 = '#06B6D4'                        // ciano  — sempre vibrante
  const c2 = w ? 'rgba(255,255,255,0.68)' : '#1E40AF'   // azul médio
  const c3 = w ? 'rgba(255,255,255,0.28)' : '#0B1A30'   // azul escuro

  /* Cores do texto */
  const tPrimary = w ? 'rgba(255,255,255,0.95)' : '#0B1A30'
  const tSub     = w ? 'rgba(255,255,255,0.55)' : '#1E40AF'

  /*
   * ViewBox 0 0 48 44  — três linhas diagonais paralelas
   * Linha 1 (ciano, frente):  (4,38)→(24,5)   nós: (4,38)  (11,27) (17,16) (24,5)
   * Linha 2 (azul,  meio):   (14,38)→(34,5)   nós: (14,38) (21,27) (27,16) (34,5)
   * Linha 3 (escuro, fundo): (24,38)→(44,5)   nós: (24,38) (31,27) (37,16) (44,5)
   */
  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      <svg
        viewBox="0 0 48 44"
        height={iconSize}
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        {/* Linha 3 — fundo */}
        <line x1="24" y1="38" x2="44" y2="5" stroke={c3} strokeWidth="2.8" strokeLinecap="round" />
        <circle cx="24" cy="38" r="3"   fill={c3} />
        <circle cx="31" cy="27" r="2.1" fill={c3} />
        <circle cx="37" cy="16" r="2.1" fill={c3} />
        <circle cx="44" cy="5"  r="3"   fill={c3} />

        {/* Linha 2 — meio */}
        <line x1="14" y1="38" x2="34" y2="5" stroke={c2} strokeWidth="2.8" strokeLinecap="round" />
        <circle cx="14" cy="38" r="3"   fill={c2} />
        <circle cx="21" cy="27" r="2.1" fill={c2} />
        <circle cx="27" cy="16" r="2.1" fill={c2} />
        <circle cx="34" cy="5"  r="3"   fill={c2} />

        {/* Linha 1 — frente (ciano) */}
        <line x1="4"  y1="38" x2="24" y2="5" stroke={c1} strokeWidth="2.8" strokeLinecap="round" />
        <circle cx="4"  cy="38" r="3"   fill={c1} />
        <circle cx="11" cy="27" r="2.1" fill={c1} />
        <circle cx="17" cy="16" r="2.1" fill={c1} />
        <circle cx="24" cy="5"  r="3"   fill={c1} />
      </svg>

      {showText && (
        <span className="flex flex-col leading-tight">
          <span className="flex items-baseline gap-1.5">
            <span
              className="font-bold tracking-widest uppercase text-xs"
              style={{ color: tPrimary }}
            >
              {ORQUESTRA_NAME}
            </span>
            {children}
          </span>
          <span
            className="text-[10px] tracking-wide"
            style={{ color: tSub }}
          >
            {ORQUESTRA_SUBTITLE}
          </span>
        </span>
      )}
    </div>
  )
}
