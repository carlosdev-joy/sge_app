// Seção Caixa Seguro — POC Lovable portada como subpáginas do Orquestra.
// Montada pelo App.tsx sob a rota curinga /caixa-seguro/* (RequirePerm
// tela_caixa_seguro); as rotas internas abaixo são relativas ao prefixo.
// O wrapper .caixa-theme escopa os tokens do tema CAIXA (ver theme.css).
import { Routes, Route, Navigate } from "react-router-dom";
import { ProfileProvider } from "./contexts/ProfileContext";
import { Toaster } from "./components/ui/toaster";
import Index from "./pages/Index";
import ProposalTracking from "./pages/ProposalTracking";
import PortabilityTracking from "./pages/PortabilityTracking";
import AICommercialPanel from "./pages/AICommercialPanel";
import "./theme.css";

export default function CaixaSeguroApp() {
  return (
    <div className="caixa-theme min-h-full">
      <ProfileProvider>
        <Routes>
          <Route index element={<Index />} />
          {/* "acompanhamento" (sem :status) é a tela nativa MonitoramentoOrq,
              registrada FORA deste wrapper no App.tsx (F2 da migração). */}
          <Route path="acompanhamento/:status" element={<ProposalTracking />} />
          <Route path="portabilidades" element={<PortabilityTracking />} />
          <Route path="ia-operacional" element={<AICommercialPanel />} />
          <Route path="*" element={<Navigate to="/caixa-seguro" replace />} />
        </Routes>
        <Toaster />
      </ProfileProvider>
    </div>
  );
}
