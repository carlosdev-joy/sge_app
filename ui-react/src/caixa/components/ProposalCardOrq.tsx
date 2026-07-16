// Card de proposta no DS nativo — porte do ProposalCard shadcn (mesma grade
// de campos e mesmos botões condicionais por status). Usado pela
// AcompanhamentoOrq (F6, rota paralela). O clique no card abre o
// ProposalDetailDialogOrq (consulta, portado na F3). Desde a F7, "Enviar
// Link" e "Enviar Link DPS" abrem os diálogos nativos; os botões de AÇÃO
// restantes (Upload, Devolução, Nova Venda, Histórico de Sensibilização)
// ficam DESABILITADOS até a F8; a rota oficial segue shadcn até a F9.
import { useState } from "react";
import { Send, Upload, DollarSign, PlusCircle, ExternalLink, History } from "lucide-react";
import { Button } from "../../components/ui/Button";
import ProposalDetailDialogOrq, { type ProposalOrq } from "./ProposalDetailDialogOrq";
import ResendLinkDialogOrq from "./ResendLinkDialogOrq";
import DPSLinkDialogOrq from "./DPSLinkDialogOrq";

export interface ProposalTrackingOrq extends ProposalOrq {
  refundSubStatus?: string;
  receiptNumber?: string;
}

interface ProposalCardOrqProps {
  proposal: ProposalTrackingOrq;
}

const TITULO_FASE = "Ação portada na fase F8 da migração (rota paralela)";

export default function ProposalCardOrq({ proposal }: ProposalCardOrqProps) {
  const [isDetailDialogOpen, setIsDetailDialogOpen] = useState(false);
  const [isResendDialogOpen, setIsResendDialogOpen] = useState(false);
  const [isDPSDialogOpen, setIsDPSDialogOpen] = useState(false);

  const campos: { rotulo: string; valor: string; destaque?: boolean }[] = [
    { rotulo: "Número da Proposta", valor: proposal.number, destaque: true },
    { rotulo: "Nome do Segurado", valor: proposal.insuredName },
    { rotulo: "CPF", valor: proposal.cpf },
    { rotulo: "Valor", valor: proposal.value, destaque: true },
    { rotulo: "Telefone", valor: proposal.phone },
    { rotulo: "E-mail", valor: proposal.email },
    { rotulo: "Produto", valor: proposal.product },
    { rotulo: "Data", valor: proposal.date },
  ];

  return (
    <>
      <div
        className="bg-panel border border-edge border-l-4 border-l-[#1A5FA8] rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
        onClick={() => setIsDetailDialogOpen(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter") setIsDetailDialogOpen(true);
        }}
        aria-label={`Abrir detalhe da proposta ${proposal.number}`}
      >
        <div className="flex justify-between items-start gap-4 flex-wrap">
          <div className="flex-1 min-w-[280px]">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {campos.map((c) => (
                <div key={c.rotulo}>
                  <p className="text-xs text-dim">{c.rotulo}</p>
                  <p className={`font-semibold ${c.destaque ? "text-[#1A5FA8] dark:text-blue-400" : "text-ink"}`}>{c.valor}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2 shrink-0 flex-wrap" onClick={(e) => e.stopPropagation()}>
            <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
              <History className="h-4 w-4" />
              Histórico
            </Button>

            {proposal.status === "pending_signature" && (
              <Button variant="primary" size="sm" onClick={() => setIsResendDialogOpen(true)}>
                <Send className="h-4 w-4" />
                Enviar Link
              </Button>
            )}

            {proposal.status === "pending_documentation" && (
              <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                <Upload className="h-4 w-4" />
                Upload
              </Button>
            )}

            {proposal.status === "pending_dps" && (
              <Button variant="primary" size="sm" onClick={() => setIsDPSDialogOpen(true)}>
                <ExternalLink className="h-4 w-4" />
                Enviar Link DPS
              </Button>
            )}

            {(proposal.status === "declined" || proposal.status === "refund_pending") &&
              proposal.refundSubStatus === "pending" && (
                <>
                  <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                    <DollarSign className="h-4 w-4" />
                    Gerenciar Devolução
                  </Button>
                  <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                    <PlusCircle className="h-4 w-4" />
                    Nova Venda
                  </Button>
                </>
              )}
          </div>
        </div>
      </div>

      <ProposalDetailDialogOrq
        proposal={proposal}
        open={isDetailDialogOpen}
        onClose={() => setIsDetailDialogOpen(false)}
      />

      <ResendLinkDialogOrq
        proposal={{
          number: proposal.number,
          insuredName: proposal.insuredName,
          cpf: proposal.cpf,
          value: proposal.value,
          email: proposal.email,
          phone: proposal.phone,
        }}
        open={isResendDialogOpen}
        onClose={() => setIsResendDialogOpen(false)}
      />

      <DPSLinkDialogOrq
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
        open={isDPSDialogOpen}
        onClose={() => setIsDPSDialogOpen(false)}
      />
    </>
  );
}
