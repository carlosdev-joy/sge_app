// Card de proposta no DS nativo — porte do ProposalCard shadcn (mesma grade
// de campos e mesmos botões condicionais por status). Usado pela
// Acompanhamento. O clique no card abre o ProposalDetailDialog (F3);
// desde a F8 todos os botões de ação estão ligados aos diálogos nativos
// (Enviar Link/DPS da F7; Histórico, Upload, Devolução e Nova Venda da F8).
import { useState } from "react";
import { Send, Upload, DollarSign, PlusCircle, ExternalLink, History } from "lucide-react";
import { Button } from "../../components/ui/Button";
import ProposalDetailDialog, { type ProposalOrq } from "./ProposalDetailDialog";
import ResendLinkDialog from "./ResendLinkDialog";
import DPSLinkDialog from "./DPSLinkDialog";
import DocumentUploadDialog from "./DocumentUploadDialog";
import RefundManagementDialog from "./RefundManagementDialog";
import NewSaleDialog from "./NewSaleDialog";
import SensitizationHistoryDialog from "./SensitizationHistoryDialog";

export interface ProposalTrackingOrq extends ProposalOrq {
  refundSubStatus?: string;
  receiptNumber?: string;
}

interface ProposalCardProps {
  proposal: ProposalTrackingOrq;
}

export default function ProposalCard({ proposal }: ProposalCardProps) {
  const [isDetailDialogOpen, setIsDetailDialogOpen] = useState(false);
  const [isResendDialogOpen, setIsResendDialogOpen] = useState(false);
  const [isDPSDialogOpen, setIsDPSDialogOpen] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [isRefundDialogOpen, setIsRefundDialogOpen] = useState(false);
  const [isNewSaleDialogOpen, setIsNewSaleDialogOpen] = useState(false);
  const [isSensitizationHistoryOpen, setIsSensitizationHistoryOpen] = useState(false);

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
            <Button variant="secondary" size="sm" onClick={() => setIsSensitizationHistoryOpen(true)}>
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
              <Button variant="danger" size="sm" onClick={() => setIsUploadDialogOpen(true)}>
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
                  <Button variant="primary" size="sm" onClick={() => setIsRefundDialogOpen(true)}>
                    <DollarSign className="h-4 w-4" />
                    Gerenciar Devolução
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => setIsNewSaleDialogOpen(true)}>
                    <PlusCircle className="h-4 w-4" />
                    Nova Venda
                  </Button>
                </>
              )}
          </div>
        </div>
      </div>

      <ProposalDetailDialog
        proposal={proposal}
        open={isDetailDialogOpen}
        onClose={() => setIsDetailDialogOpen(false)}
      />

      <ResendLinkDialog
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

      <DPSLinkDialog
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
        open={isDPSDialogOpen}
        onClose={() => setIsDPSDialogOpen(false)}
      />

      <DocumentUploadDialog
        open={isUploadDialogOpen}
        onClose={() => setIsUploadDialogOpen(false)}
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
      />

      <RefundManagementDialog
        proposal={{
          number: proposal.number,
          insuredName: proposal.insuredName,
          cpf: proposal.cpf,
          value: proposal.value,
          policy: proposal.number,
          product: proposal.product,
        }}
        open={isRefundDialogOpen}
        onClose={() => setIsRefundDialogOpen(false)}
      />

      <NewSaleDialog
        open={isNewSaleDialogOpen}
        onClose={() => setIsNewSaleDialogOpen(false)}
        receiptNumber={proposal.receiptNumber || proposal.number}
        insuredName={proposal.insuredName}
      />

      <SensitizationHistoryDialog
        open={isSensitizationHistoryOpen}
        onClose={() => setIsSensitizationHistoryOpen(false)}
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
      />
    </>
  );
}
