// Header da seção Caixa Seguro — usa o logo CVP oficial do Orquestra
// (/branding/logo-cvp.png, com fallback no SVG embarcado), mesmo padrão
// do Brand.tsx do shell. O logo já carrega "CAIXA" + "Vida e Previdência".
const Header = ({ title = "Busca & Vendas" }: { title?: string }) => {
  return (
    <header className="bg-gradient-to-r from-[#005CA9] via-[#0066BC] to-[#0073CF] text-white shadow-md">
      <div className="container mx-auto px-6 py-3">
        <div className="flex items-center gap-4">
          <img
            src="/branding/logo-cvp.png"
            className="h-12 w-auto drop-shadow-sm"
            alt="CAIXA Vida e Previdência"
            onError={(e) => {
              const img = e.currentTarget;
              if (!img.dataset.fallback) { img.dataset.fallback = "1"; img.src = "/images/logo-cvp.svg"; }
            }}
          />
          <div className="border-l border-white/25 pl-4">
            <div className="text-lg font-bold leading-tight tracking-wide">{title}</div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-white/75">Caixa Seguro</div>
          </div>
        </div>
      </div>
      {/* filete laranja institucional CAIXA */}
      <div className="h-1 bg-gradient-to-r from-[#F26B00] via-[#FF9D4D] to-[#F26B00]" />
    </header>
  );
};

export default Header;
