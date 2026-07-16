// Seção Caixa Seguro — POC Lovable portada como subpáginas do Orquestra.
// Montada pelo App.tsx sob a rota curinga /caixa-seguro/* (RequirePerm
// tela_caixa_seguro); as rotas internas abaixo são relativas ao prefixo.
// O wrapper .caixa-theme escopa os tokens do tema CAIXA (ver theme.css).
import { Routes, Route, Navigate } from "react-router-dom";
import "./theme.css";

// Desde a F9 da migração (docs/spec-caixa-ds-nativo.md) TODAS as telas da
// seção são nativas e vivem FORA deste wrapper, em rotas próprias no App.tsx.
// O splat /caixa-seguro/* só resta para redirecionar caminho desconhecido à
// home nativa — o componente inteiro (e o .caixa-theme/theme.css) morre na F10.
export default function CaixaSeguroApp() {
  return (
    <div className="caixa-theme min-h-full">
      <Routes>
        <Route path="*" element={<Navigate to="/caixa-seguro" replace />} />
      </Routes>
    </div>
  );
}
