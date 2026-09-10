// O avatar do Maestro — desenhado a partir da marca do Orquestra
// (components/layout/Logo.tsx: três linhas diagonais com nós, em ciano, azul
// e azul-escuro). Aqui um REGENTE de braço erguido conduz com a batuta as
// três linhas do pipeline, que são as "partituras" que o Orquestra já usa
// como símbolo. Nada de imagem raster: SVG inline, a figura e a linha de
// fundo usam os tokens (`fill-ink`/`stroke-ink`) e funcionam nos dois temas;
// o ciano e o azul são os da marca.
//
// `estado`: 'ouvindo' (parado) ou 'pensando' (as linhas pulsam).

export interface MaestroAvatarProps {
  size?: number
  estado?: 'ouvindo' | 'pensando'
  className?: string
}

const CIANO = '#06B6D4'
const AZUL = '#1E40AF'

export function MaestroAvatar({ size = 32, estado = 'ouvindo', className = '' }: MaestroAvatarProps) {
  return (
    <svg
      viewBox="0 0 56 48"
      width={size}
      height={Math.round(size * 48 / 56)}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
      data-maestro-avatar={estado}
    >
      {/* As três linhas do pipeline (o motivo do logo), conduzidas à direita */}
      <g className={estado === 'pensando' ? 'animate-pulse' : ''}>
        {/* fundo */}
        <line x1="44" y1="46" x2="55" y2="28" className="stroke-ink" strokeOpacity="0.35" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="44" cy="46" r="2.2" className="fill-ink" fillOpacity="0.35" />
        <circle cx="49.5" cy="37" r="1.6" className="fill-ink" fillOpacity="0.35" />
        <circle cx="55" cy="28" r="2.2" className="fill-ink" fillOpacity="0.35" />
        {/* meio */}
        <line x1="37" y1="45" x2="48" y2="27" stroke={AZUL} strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="37" cy="45" r="2.2" fill={AZUL} />
        <circle cx="42.5" cy="36" r="1.6" fill={AZUL} />
        <circle cx="48" cy="27" r="2.2" fill={AZUL} />
        {/* frente (ciano) */}
        <line x1="30" y1="44" x2="41" y2="26" stroke={CIANO} strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="30" cy="44" r="2.2" fill={CIANO} />
        <circle cx="35.5" cy="35" r="1.6" fill={CIANO} />
        <circle cx="41" cy="26" r="2.2" fill={CIANO} />
      </g>

      {/* O regente: cabeça, torso, braço erguido e a batuta em ciano */}
      <circle cx="15" cy="12" r="5.5" className="fill-ink" />
      <path d="M6 46 C6 30 10 24 15 22 C20 24 24 30 24 46 Z" className="fill-ink" fillOpacity="0.85" />
      <line x1="20" y1="27" x2="31" y2="15" className="stroke-ink" strokeWidth="3" strokeLinecap="round" />
      <line x1="31" y1="15" x2="38" y2="7" stroke={CIANO} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="38" cy="7" r="1.8" fill={CIANO} />
    </svg>
  )
}
