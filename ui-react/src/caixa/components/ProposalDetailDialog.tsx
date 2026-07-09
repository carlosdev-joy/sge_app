import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { X, FileDown, Share2, Clock } from "lucide-react";
import { toast } from "../hooks/use-toast";
import { useState } from "react";
import ProposalTimeline from "./ProposalTimeline";
import ProposalShareDialog from "./ProposalShareDialog";
import ProposalHistoryDialog from "./ProposalHistoryDialog";

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
  declineReason?: string;
}

interface ProposalDetailDialogProps {
  proposal: Proposal;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const ProposalDetailDialog = ({ proposal, open, onOpenChange }: ProposalDetailDialogProps) => {
  const [isShareDialogOpen, setIsShareDialogOpen] = useState(false);
  const [isHistoryDialogOpen, setIsHistoryDialogOpen] = useState(false);

  const handleDownloadPDF = () => {
    toast({
      title: "PDF Localizado",
      description: `Baixando PDF da proposta ${proposal.number}...`,
    });
    
    // Simulate PDF download
    setTimeout(() => {
      toast({
        title: "Download Concluído",
        description: "O PDF da proposta foi baixado com sucesso.",
      });
    }, 1500);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto bg-card border-caixa-aqua/30">
          <button
            onClick={() => onOpenChange(false)}
            className="absolute left-4 top-4 rounded-full bg-caixa-orange text-white p-2 hover:bg-caixa-orange/90 transition-colors shadow-lg"
          >
            <X className="h-5 w-5" />
          </button>

          <DialogHeader className="text-center pt-8">
            <DialogTitle className="text-2xl font-bold text-caixa-orange">
              Resumo do seguro
            </DialogTitle>
          <DialogDescription className="sr-only">Detalhes completos da proposta selecionada.</DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            {/* Timeline */}
            <ProposalTimeline currentStatus={proposal.status} />

            {/* Action Buttons */}
            <div className="flex flex-wrap justify-center gap-3">
              <Button
                onClick={handleDownloadPDF}
                className="bg-gradient-primary hover:opacity-90 text-white shadow-lg"
              >
                <FileDown className="mr-2 h-4 w-4" />
                Localizar PDF da proposta
              </Button>
              <Button
                onClick={() => setIsShareDialogOpen(true)}
                className="bg-caixa-aqua hover:bg-caixa-aqua/90 text-black shadow-lg"
              >
                <Share2 className="mr-2 h-4 w-4" />
                Compartilhar Proposta
              </Button>
              <Button
                onClick={() => setIsHistoryDialogOpen(true)}
                className="bg-muted hover:bg-muted/80 text-foreground shadow-lg"
              >
                <Clock className="mr-2 h-4 w-4" />
                Ver Histórico
              </Button>
            </div>
          {/* Dados da Venda */}
          <div>
            <h3 className="text-xl font-bold text-caixa-aqua text-center mb-4">Dados da Venda</h3>
            <div className="bg-card/50 p-6 rounded-lg border border-caixa-aqua/20">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Data de Venda:</p>
                  <p className="font-semibold">{proposal.date}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Matrícula do Indicador:</p>
                  <p className="font-semibold">{proposal.indicatorId}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Agência:</p>
                  <p className="font-semibold">{proposal.agency}</p>
                </div>
                <div className="md:col-span-3">
                  <p className="text-sm text-muted-foreground">Usuário:</p>
                  <p className="font-semibold">c{proposal.indicatorId.replace(/[^0-9]/g, '').substring(0, 6)}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Dados do Segurado */}
          <div>
            <h3 className="text-xl font-bold text-caixa-aqua text-center mb-4">Dados do Segurado</h3>
            <div className="bg-card/50 p-6 rounded-lg border border-caixa-aqua/20">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Nome civil*:</p>
                  <p className="font-semibold">{proposal.insuredName}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">CPF:</p>
                  <p className="font-semibold">{proposal.cpf}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Produto:</p>
                  <p className="font-semibold">{proposal.product}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Telefone:</p>
                  <p className="font-semibold">{proposal.phone}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">E-mail:</p>
                  <p className="font-semibold">{proposal.email}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Sexo*:</p>
                  <p className="font-semibold">Masculino</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Profissão:</p>
                  <p className="font-semibold">SUPERV, INSPETOR E AGENTE DE COMPRAS/VENDAS</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Estado Civil:</p>
                  <p className="font-semibold">Solteiro</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Renda Individual:</p>
                  <p className="font-semibold">{proposal.value}</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-4 italic">*conforme registro civil</p>
            </div>
          </div>

          {/* Dados do Beneficiário */}
          <div>
            <h3 className="text-xl font-bold text-caixa-aqua text-center mb-4">Dados do Beneficiário</h3>
            <div className="bg-card/50 p-6 rounded-lg border border-caixa-aqua/20">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Nome:</p>
                  <p className="font-semibold">Herdeiros Legais</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Parentesco:</p>
                  <p className="font-semibold">Herdeiros Legais</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Percentual:</p>
                  <p className="font-semibold">100%</p>
                </div>
              </div>
            </div>
          </div>

          {/* Motivo de Declínio */}
          {(proposal.status === "refund_scheduled" || proposal.status === "refund_pending" || proposal.status === "valores_programados") && proposal.declineReason && (
            <div>
              <h3 className="text-xl font-bold text-destructive text-center mb-4">Motivo do Declínio</h3>
              <div className="bg-destructive/10 p-6 rounded-lg border-2 border-destructive">
                <p className="text-sm font-semibold">{proposal.declineReason}</p>
              </div>
            </div>
          )}

          {/* Footer com resumo */}
          <div className="bg-muted/50 p-4 rounded-lg border border-border">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-semibold">{proposal.number}</span>
              <span>{proposal.cpf}</span>
              <span>{proposal.insuredName}</span>
              <span>{proposal.product}</span>
              <span>{proposal.value}</span>
              <span>{proposal.date}</span>
              <span>{proposal.agency}</span>
              <span>{proposal.indicatorId}</span>
              <span className="w-3 h-3 rounded-full bg-green"></span>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <ProposalShareDialog
      proposalNumber={proposal.number}
      clientEmail={proposal.email}
      clientPhone={proposal.phone}
      open={isShareDialogOpen}
      onOpenChange={setIsShareDialogOpen}
    />

    <ProposalHistoryDialog
      proposalNumber={proposal.number}
      open={isHistoryDialogOpen}
      onOpenChange={setIsHistoryDialogOpen}
    />
  </>
  );
};

export default ProposalDetailDialog;
