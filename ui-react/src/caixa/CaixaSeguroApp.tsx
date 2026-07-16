// Seção Caixa Seguro — POC Lovable portada como subpáginas do Orquestra.
// Montada pelo App.tsx sob a rota curinga /caixa-seguro/* (RequirePerm
// tela_caixa_seguro); as rotas internas abaixo são relativas ao prefixo.
// O wrapper .caixa-theme escopa os tokens do tema CAIXA (ver theme.css).
import { Routes, Route, Navigate } from "react-router-dom";
import { ProfileProvider } from "./contexts/ProfileContext";
import { Toaster } from "./components/ui/toaster";
import ProposalTracking from "./pages/ProposalTracking";
import AICommercialPanel from "./pages/AICommercialPanel";
import "./theme.css";

export default function CaixaSeguroApp() {
  return (
    <div className="caixa-theme min-h-full">
      <ProfileProvider>
        <Routes>
          {/* A home (index) é a tela nativa IndexOrq, registrada FORA deste
              wrapper no App.tsx (F3 da migração) — a rota estática exata
              /caixa-seguro vence este splat, então não há index aqui. */}
          {/* "acompanhamento" (sem :status) é a tela nativa MonitoramentoOrq,
              registrada FORA deste wrapper no App.tsx (F2 da migração). */}
          <Route path="acompanhamento/:status" element={<ProposalTracking />} />
          {/* "portabilidades" é a tela nativa PortabilidadesOrq, registrada
              FORA deste wrapper no App.tsx (F4 da migração). */}
          <Route path="ia-operacional" element={<AICommercialPanel />} />
          <Route path="*" element={<Navigate to="/caixa-seguro" replace />} />
        </Routes>
        <Toaster />
      </ProfileProvider>
    </div>
  );
}
