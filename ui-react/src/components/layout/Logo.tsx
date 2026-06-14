// Logo Caixa Vida e Previdência — SVG inline (renderiza sempre, sem depender
// de arquivo servido/CDN). Layout vertical: símbolo laranja, wordmark e subtítulo.
export function Logo({ className = 'h-10 w-auto' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 200 116" fill="none" role="img" aria-label="Caixa Vida e Previdência">
      {/* Símbolo Caixa — dois paralelogramos laranja em diagonal */}
      <polygon points="104,6 134,6 116,34 86,34" fill="#f39200" />
      <polygon points="84,30 114,30 96,58 66,58" fill="#f39200" />
      {/* Wordmark CAIXA */}
      <text x="100" y="86" textAnchor="middle" fontFamily="Arial, Helvetica, sans-serif"
            fontSize="26" fontWeight="800" fill="#ffffff" letterSpacing="4">CAIXA</text>
      {/* Subtítulo */}
      <text x="100" y="108" textAnchor="middle" fontFamily="Georgia, 'Times New Roman', serif"
            fontSize="13" fontStyle="italic" fill="#ffffff" opacity="0.9" letterSpacing="0.5">Vida e Previdência</text>
    </svg>
  )
}
