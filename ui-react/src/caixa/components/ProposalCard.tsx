import { useState } from "react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Send, Upload, DollarSign, PlusCircle, ExternalLink, History } from "lucide-react";
import ProposalDetailDialog from "./ProposalDetailDialog";
import ResendLinkDialog from "./ResendLinkDialog";
import DocumentUploadDialog from "./DocumentUploadDialog";
import RefundManagementDialog from "./RefundManagementDialog";
import NewSaleDialog from "./NewSaleDialog";
import DPSLinkDialog from "./DPSLinkDialog";
import SensitizationHistoryDialog from "./SensitizationHistoryDialog";

interface Proposal {
  id: string;
  number: string;
  insuredName: string;
  date: string;
  status: 
    | "pending_signature" 
    | "awaiting_payment" 
    | "signed_proposal"
    | "pending_documentation" 
    | "pending_dps" 
    | "refund_scheduled"
    | "refund_pending"
    | "valores_programados"
    | "sensitization_monitoring"
    | "approved"
    | "declined"
    | "emission_sent"
    | "return_in_progress";
  value: string;
  indicatorId: string;
  agency: string;
  cpf: string;
  product: string;
  phone: string;
  email: string;
  refundSubStatus?: string;
  receiptNumber?: string;
}

interface ProposalCardProps {
  proposal: Proposal;
}

const ProposalCard = ({ proposal }: ProposalCardProps) => {
  const [isDetailDialogOpen, setIsDetailDialogOpen] = useState(false);
  const [isResendDialogOpen, setIsResendDialogOpen] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [isRefundDialogOpen, setIsRefundDialogOpen] = useState(false);
  const [isNewSaleDialogOpen, setIsNewSaleDialogOpen] = useState(false);
  const [isDPSDialogOpen, setIsDPSDialogOpen] = useState(false);
  const [isSensitizationHistoryOpen, setIsSensitizationHistoryOpen] = useState(false);

  const handleCardClick = () => {
    setIsDetailDialogOpen(true);
  };

  const handleResendClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsResendDialogOpen(true);
  };

  const handleUploadClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsUploadDialogOpen(true);
  };

  const handleRefundClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsRefundDialogOpen(true);
  };

  const handleNewSaleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsNewSaleDialogOpen(true);
  };

  const handleDPSClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDPSDialogOpen(true);
  };

  const handleSensitizationHistoryClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsSensitizationHistoryOpen(true);
  };

  return (
    <>
      <Card 
        className="p-4 hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-primary"
        onClick={handleCardClick}
      >
        <div className="flex justify-between items-start gap-4">
          <div className="flex-1">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Número da Proposta</p>
                <p className="font-semibold text-primary">{proposal.number}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Nome do Segurado</p>
                <p className="font-semibold">{proposal.insuredName}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">CPF</p>
                <p className="font-semibold">{proposal.cpf}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Valor</p>
                <p className="font-semibold text-primary">{proposal.value}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Telefone</p>
                <p className="font-semibold">{proposal.phone}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">E-mail</p>
                <p className="font-semibold">{proposal.email}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Produto</p>
                <p className="font-semibold">{proposal.product}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Data</p>
                <p className="font-semibold">{proposal.date}</p>
              </div>
            </div>
          </div>
          
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={handleSensitizationHistoryClick}
              size="sm"
              variant="outline"
              className="border-primary/30 hover:bg-primary/10"
            >
              <History className="h-4 w-4 mr-2" />
              Histórico
            </Button>

            {proposal.status === "pending_signature" && (
              <Button
                onClick={handleResendClick}
                size="sm"
                className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white shrink-0"
              >
                <Send className="h-4 w-4 mr-2" />
                Enviar Link
              </Button>
            )}

            {proposal.status === "pending_documentation" && (
              <Button
                onClick={handleUploadClick}
                size="sm"
                className="bg-destructive hover:bg-destructive/90 text-white shrink-0"
              >
                <Upload className="h-4 w-4 mr-2" />
                Upload
              </Button>
            )}

            {proposal.status === "pending_dps" && (
              <Button
                onClick={handleDPSClick}
                size="sm"
                className="bg-[hsl(var(--blue))] hover:bg-[hsl(var(--blue))]/90 text-white shrink-0"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Enviar Link DPS
              </Button>
            )}

            {(proposal.status === "declined" || proposal.status === "refund_pending") && 
             proposal.refundSubStatus === "pending" && (
              <>
                <Button
                  onClick={handleRefundClick}
                  size="sm"
                  className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white"
                >
                  <DollarSign className="h-4 w-4 mr-2" />
                  Gerenciar Devolução
                </Button>
                <Button
                  onClick={handleNewSaleClick}
                  size="sm"
                  className="bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90 text-white"
                >
                  <PlusCircle className="h-4 w-4 mr-2" />
                  Nova Venda
                </Button>
              </>
            )}
          </div>
        </div>
      </Card>

      <ProposalDetailDialog 
        proposal={proposal}
        open={isDetailDialogOpen}
        onOpenChange={setIsDetailDialogOpen}
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
        onOpenChange={setIsResendDialogOpen}
      />

      <DocumentUploadDialog
        open={isUploadDialogOpen}
        onOpenChange={setIsUploadDialogOpen}
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
        onOpenChange={setIsRefundDialogOpen}
      />

      <NewSaleDialog
        open={isNewSaleDialogOpen}
        onOpenChange={setIsNewSaleDialogOpen}
        receiptNumber={proposal.receiptNumber || proposal.number}
        insuredName={proposal.insuredName}
      />

      <DPSLinkDialog
        open={isDPSDialogOpen}
        onOpenChange={setIsDPSDialogOpen}
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
      />

      <SensitizationHistoryDialog
        open={isSensitizationHistoryOpen}
        onOpenChange={setIsSensitizationHistoryOpen}
        proposalNumber={proposal.number}
        insuredName={proposal.insuredName}
      />
    </>
  );
};

export default ProposalCard;
