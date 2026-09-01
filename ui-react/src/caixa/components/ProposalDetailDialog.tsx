// "Resumo do seguro" no DS nativo — porte do ProposalDetailDialog shadcn sobre
// o Modal do Orquestra (mesmas seções, textos e mock de PDF). Abre a partir do
// resultado da busca na home (F3) e é reutilizável no acompanhamento por
// status (F6). Encadeia os diálogos nativos de compartilhar e histórico.
import { useState } from "react";
import { FileDown, Share2, Clock } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { toast } from "../../components/ui/Toast";
import ProposalTimeline from "./ProposalTimeline";
import ProposalShareDialog from "./ProposalShareDialog";
import ProposalHistoryDialog from "./ProposalHistoryDialog";

export interface ProposalOrq {
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
    // Crítica (análise): funde documental + DPS na sequência do Workflow
    // (lib/workflow.ts). As duas antigas continuam no tipo porque o
    // Acompanhamento e o Monitoramento ainda as usam.
    | "in_analysis"
    | "refund_scheduled"
    | "refund_pending"
    | "valores_programados"
    | "sensitization_monitoring"
    | "approved"
    | "declined"
    | "emission_sent"
    | "paid"
    | "return_in_progress";
  value: string;
  indicatorId: string;
  agency: string;
  cpf: string;
  product: string;
  phone: string;
  email: string;
  /** Renda declarada do proponente, já formatada (VLR_RENDA_FORMAL na carga do
   *  PIO). Opcional: as propostas de exemplo não têm renda, e o campo some da
   *  tela em vez de exibir outro número no lugar. */
  individualIncome?: string;
  /** Importância segurada, já formatada (VLR_IMP_SEGURADA) — o capital coberto
   *  pela apólice. Opcional pelo mesmo motivo da renda. */
  insuredAmount?: string;
  declineReason?: string;
}

interface ProposalDetailDialogProps {
  proposal: ProposalOrq;
  open: boolean;
  onClose: () => void;
}

function Secao({ titulo, children, tom = "azul" }: { titulo: string; children: React.ReactNode; tom?: "azul" | "vermelho" }) {
  return (
    <div>
      <h3
        className={`text-lg font-bold text-center mb-3 ${
          tom === "vermelho" ? "text-red-600 dark:text-red-400" : "text-[#1A5FA8] dark:text-blue-400"
        }`}
      >
        {titulo}
      </h3>
      {children}
    </div>
  );
}

function CampoInfo({ rotulo, valor, className = "" }: { rotulo: string; valor: string; className?: string }) {
  return (
    <div className={className}>
      <p className="text-sm text-dim">{rotulo}</p>
      <p className="font-semibold text-ink">{valor}</p>
    </div>
  );
}

export default function ProposalDetailDialog({ proposal, open, onClose }: ProposalDetailDialogProps) {
  const [isShareDialogOpen, setIsShareDialogOpen] = useState(false);
  const [isHistoryDialogOpen, setIsHistoryDialogOpen] = useState(false);

  const handleDownloadPDF = () => {
    toast.info(`Baixando PDF da proposta ${proposal.number}...`);
    // Download simulado (mock, como na tela original)
    setTimeout(() => {
      toast.success("O PDF da proposta foi baixado com sucesso.");
    }, 1500);
  };

  return (
    <>
      <Modal open={open} onClose={onClose} title="Resumo do seguro" size="xl">
        <div className="space-y-6">
          {/* Linha do tempo do status */}
          <ProposalTimeline currentStatus={proposal.status} />

          {/* Ações */}
          <div className="flex flex-wrap justify-center gap-3">
            <Button variant="primary" onClick={handleDownloadPDF}>
              <FileDown className="h-4 w-4" />
              Localizar PDF da proposta
            </Button>
            <Button variant="secondary" onClick={() => setIsShareDialogOpen(true)}>
              <Share2 className="h-4 w-4" />
              Compartilhar Proposta
            </Button>
            <Button variant="ghost" onClick={() => setIsHistoryDialogOpen(true)}>
              <Clock className="h-4 w-4" />
              Ver Histórico
            </Button>
          </div>

          {/* Dados da Venda */}
          <Secao titulo="Dados da Venda">
            <div className="bg-canvas p-6 rounded-lg border border-edge">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <CampoInfo rotulo="Data de Venda:" valor={proposal.date} />
                <CampoInfo rotulo="Matrícula do Indicador:" valor={proposal.indicatorId} />
                <CampoInfo rotulo="Agência:" valor={proposal.agency} />
                <CampoInfo
                  rotulo="Usuário:"
                  valor={`c${proposal.indicatorId.replace(/[^0-9]/g, "").substring(0, 6)}`}
                  className="md:col-span-3"
                />
              </div>
            </div>
          </Secao>

          {/* Dados do Segurado.
              Saíram daqui em 2026-09-01, a pedido do usuário: Sexo, Profissão e
              Estado Civil — os três eram valores ESCRITOS DUROS no código
              ("Masculino", "SUPERV, INSPETOR…", "Solteiro"), iguais em toda
              proposta, e a carga do PIO não traz nenhum deles.
              "Renda Individual" ficou, mas trocou de fonte: mostrava o `value`,
              que é o PRÊMIO (VLR_PREMIO), sob o rótulo de renda. Agora lê
              `individualIncome`, que vem de VLR_RENDA_FORMAL. Rótulo de um dado
              com o número de outro é diferença que ninguém explica olhando a
              tela — foi o que motivou esta revisão.
              A seção "Dados do Beneficiário" saiu inteira pelo mesmo motivo dos
              três primeiros: nome, parentesco e percentual eram fixos
              ("Herdeiros Legais", "100%"). Se o beneficiário voltar, vem da carga.
              Ver docs/pio-fonte-de-dados.md → "Que coluna preenche cada campo". */}
          <Secao titulo="Dados do Segurado">
            <div className="bg-canvas p-6 rounded-lg border border-edge">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <CampoInfo rotulo="Nome civil*:" valor={proposal.insuredName} />
                <CampoInfo rotulo="CPF:" valor={proposal.cpf} />
                <CampoInfo rotulo="Produto:" valor={proposal.product} />
                <CampoInfo rotulo="Telefone:" valor={proposal.phone} />
                <CampoInfo rotulo="E-mail:" valor={proposal.email} />
                {/* Só aparece quando a carga trouxe a renda. Proposta de
                    exemplo não tem — e um campo vazio é melhor que o número
                    errado que estava aqui. */}
                {proposal.individualIncome && (
                  <CampoInfo rotulo="Renda Individual:" valor={proposal.individualIncome} />
                )}
                {/* Importância segurada: o capital COBERTO pela apólice. Vinha
                    do banco, chegava no front e parava aqui — nenhuma tela a
                    exibia. É o valor que se confere contra a proposta. */}
                {proposal.insuredAmount && (
                  <CampoInfo rotulo="Importância Segurada:" valor={proposal.insuredAmount} />
                )}
              </div>
              <p className="text-xs text-dim mt-4 italic">*conforme registro civil</p>
            </div>
          </Secao>

          {/* Motivo de Declínio — inclui `declined`, o card "Propostas
              Rejeitadas": a recusa vem ANTES da devolução do prêmio, e é
              justamente ali que o motivo precisa ser lido. */}
          {(proposal.status === "declined" ||
            proposal.status === "refund_scheduled" ||
            proposal.status === "refund_pending" ||
            proposal.status === "valores_programados") &&
            proposal.declineReason && (
              <Secao titulo="Motivo do Declínio" tom="vermelho">
                <div className="bg-red-500/10 p-6 rounded-lg border-2 border-red-500">
                  <p className="text-sm font-semibold text-ink">{proposal.declineReason}</p>
                </div>
              </Secao>
            )}

          {/* Rodapé com resumo */}
          <div className="bg-canvas p-4 rounded-lg border border-edge">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink">
              <span className="font-semibold">{proposal.number}</span>
              <span>{proposal.cpf}</span>
              <span>{proposal.insuredName}</span>
              <span>{proposal.product}</span>
              <span>{proposal.value}</span>
              <span>{proposal.date}</span>
              <span>{proposal.agency}</span>
              <span>{proposal.indicatorId}</span>
              <span className="w-3 h-3 rounded-full bg-emerald-500" />
            </div>
          </div>
        </div>
      </Modal>

      <ProposalShareDialog
        proposalNumber={proposal.number}
        clientEmail={proposal.email}
        clientPhone={proposal.phone}
        open={isShareDialogOpen}
        onClose={() => setIsShareDialogOpen(false)}
      />

      <ProposalHistoryDialog
        proposalNumber={proposal.number}
        open={isHistoryDialogOpen}
        onClose={() => setIsHistoryDialogOpen(false)}
      />
    </>
  );
}
