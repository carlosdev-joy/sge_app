// Workflow inline da home no DS nativo — reescrita do InlineWorkflow shadcn
// (F8). Card colapsável com resumo por status, filtros com sub-status,
// alerta em lote e lista de propostas com ação por status — incluindo o
// movimento de Emissão (sensitization_monitoring → emission_sent, estado
// local). Todos os diálogos são os nativos das F3/F7/F8. Mock idêntico ao
// original (16 propostas).
import { useState } from "react";
import { ChevronDown, ChevronUp, Send } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import ProposalDetailDialogOrq, { type ProposalOrq } from "./ProposalDetailDialogOrq";
import ResendLinkDialogOrq from "./ResendLinkDialogOrq";
import DocumentUploadDialogOrq from "./DocumentUploadDialogOrq";
import DPSLinkDialogOrq from "./DPSLinkDialogOrq";
import SendAlertDialogOrq from "./SendAlertDialogOrq";
import PaymentOptionsDialogOrq from "./PaymentOptionsDialogOrq";
import RefundManagementDialogOrq from "./RefundManagementDialogOrq";

type WorkflowStatus = ProposalOrq["status"];

interface WorkflowProposal extends ProposalOrq {
  status: WorkflowStatus;
  region: string;
  ageRange: string;
  broker: string;
  daysInPending: number;
  documentSubStatus?: "incomplete" | "mismatch" | "no_signature" | "illegible";
  paymentMethod?: "boleto" | "debit" | "credit";
  signedSubStatus?: "payment_cycle" | "payment_ended";
  refundSubStatus?: "scheduled" | "pending_value";
  policy?: string;
}

// Mesmo mock do InlineWorkflow original (16 propostas).
const mockWorkflowProposals: WorkflowProposal[] = [
  { id: "1", number: "80316460327404", insuredName: "Maria Silva", status: "pending_signature", value: "R$ 2.200,00", product: "Perda de Renda", region: "Sul", ageRange: "45-60", broker: "Mariana", daysInPending: 5, date: "23/10/2025", indicatorId: "106562-2", agency: "316", cpf: "397.750.878-48", phone: "(11) 98765-4321", email: "maria@example.com" },
  { id: "2", number: "80316460327405", insuredName: "João Santos", status: "approved", value: "R$ 1.800,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "30-40", broker: "João", daysInPending: 0, date: "22/10/2025", indicatorId: "106563-3", agency: "315", cpf: "123.456.789-00", phone: "(11) 98765-4322", email: "joao@example.com" },
  { id: "3", number: "80316460327406", insuredName: "Ana Costa", status: "pending_documentation", value: "R$ 3.000,00", product: "Vida Mulher", region: "Sul", ageRange: "50-65", broker: "Ana", daysInPending: 8, date: "21/10/2025", indicatorId: "106564-4", agency: "314", cpf: "234.567.890-11", phone: "(11) 98765-4323", email: "ana@example.com", documentSubStatus: "incomplete" },
  { id: "4", number: "80316460327407", insuredName: "Carlos Oliveira", status: "pending_signature", value: "R$ 950,00", product: "Vida Conforto", region: "Nordeste", ageRange: "25-35", broker: "Carlos", daysInPending: 6, date: "20/10/2025", indicatorId: "106565-5", agency: "313", cpf: "345.678.901-22", phone: "(11) 98765-4324", email: "carlos@example.com" },
  { id: "5", number: "80316460327408", insuredName: "Fernanda Lima", status: "declined", value: "R$ 2.700,00", product: "Perda de Renda", region: "Centro-Oeste", ageRange: "35-50", broker: "Fernanda", daysInPending: 0, date: "19/10/2025", indicatorId: "106566-6", agency: "312", cpf: "456.789.012-33", phone: "(11) 98765-4325", email: "fernanda@example.com", declineReason: "Renda insuficiente para o valor solicitado. Perfil de risco não compatível com os critérios de aceitação." },
  { id: "6", number: "80316460327409", insuredName: "Rafael Mendes", status: "sensitization_monitoring", value: "R$ 2.500,00", product: "Vida Mulher", region: "Sudeste", ageRange: "28-45", broker: "Rafael", daysInPending: 2, date: "18/10/2025", indicatorId: "106567-7", agency: "311", cpf: "567.890.123-44", phone: "(11) 98765-4326", email: "rafael@example.com" },
  { id: "7", number: "80316460327410", insuredName: "Paula Rodrigues", status: "declined", value: "R$ 1.500,00", product: "Vida Conforto", region: "Norte", ageRange: "40-55", broker: "Paula", daysInPending: 0, date: "17/10/2025", indicatorId: "106568-8", agency: "310", cpf: "678.901.234-55", phone: "(11) 98765-4327", email: "paula@example.com", declineReason: "Histórico de saúde pré-existente incompatível com as condições da apólice. Necessária reavaliação médica." },
  { id: "8", number: "80316460327411", insuredName: "Bruno Alves", status: "sensitization_monitoring", value: "R$ 3.200,00", product: "Perda de Renda", region: "Sul", ageRange: "35-50", broker: "Bruno", daysInPending: 4, date: "16/10/2025", indicatorId: "106569-9", agency: "309", cpf: "789.012.345-66", phone: "(11) 98765-4328", email: "bruno@example.com" },
  { id: "9", number: "80316460327412", insuredName: "Juliana Costa", status: "pending_documentation", value: "R$ 1.900,00", product: "Vida Conforto", region: "Nordeste", ageRange: "30-45", broker: "Juliana", daysInPending: 10, date: "15/10/2025", indicatorId: "106570-0", agency: "308", cpf: "890.123.456-77", phone: "(11) 98765-4329", email: "juliana@example.com", documentSubStatus: "mismatch" },
  { id: "10", number: "80316460327413", insuredName: "Roberto Silva", status: "pending_documentation", value: "R$ 2.100,00", product: "Vida Mulher", region: "Sul", ageRange: "40-55", broker: "Roberto", daysInPending: 7, date: "14/10/2025", indicatorId: "106571-1", agency: "307", cpf: "901.234.567-88", phone: "(11) 98765-4330", email: "roberto@example.com", documentSubStatus: "no_signature" },
  { id: "11", number: "80316460327414", insuredName: "Carla Mendes", status: "pending_documentation", value: "R$ 1.750,00", product: "Perda de Renda", region: "Centro-Oeste", ageRange: "35-50", broker: "Carla", daysInPending: 12, date: "13/10/2025", indicatorId: "106572-2", agency: "306", cpf: "012.345.678-99", phone: "(11) 98765-4331", email: "carla@example.com", documentSubStatus: "illegible" },
  { id: "12", number: "80316460327415", insuredName: "Pedro Santos", status: "awaiting_payment", value: "R$ 2.400,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "30-40", broker: "Pedro", daysInPending: 4, date: "12/10/2025", indicatorId: "106573-3", agency: "305", cpf: "123.456.789-10", phone: "(11) 98765-4332", email: "pedro@example.com", paymentMethod: "debit" },
  { id: "13", number: "80316460327416", insuredName: "Lucia Oliveira", status: "awaiting_payment", value: "R$ 1.650,00", product: "Vida Conforto", region: "Norte", ageRange: "45-60", broker: "Lucia", daysInPending: 6, date: "11/10/2025", indicatorId: "106574-4", agency: "304", cpf: "234.567.890-21", phone: "(11) 98765-4333", email: "lucia@example.com", paymentMethod: "boleto" },
  { id: "13b", number: "80316460327414", insuredName: "Antonio Souza", status: "awaiting_payment", value: "R$ 1.980,00", product: "Vida Multipremiado", region: "Centro-Oeste", ageRange: "35-50", broker: "Antonio", daysInPending: 3, date: "11/10/2025", indicatorId: "106574-5", agency: "304", cpf: "345.678.901-43", phone: "(11) 98765-4337", email: "antonio@example.com", paymentMethod: "credit" },
  { id: "14", number: "80316460327417", insuredName: "Marcos Costa", status: "pending_dps", value: "R$ 2.800,00", product: "Vida Mulher", region: "Sul", ageRange: "50-65", broker: "Marcos", daysInPending: 5, date: "10/10/2025", indicatorId: "106575-5", agency: "303", cpf: "345.678.901-32", phone: "(11) 98765-4334", email: "marcos@example.com" },
  { id: "15", number: "80316460327418", insuredName: "Adriana Lima", status: "signed_proposal", value: "R$ 1.950,00", product: "Perda de Renda", region: "Nordeste", ageRange: "35-50", broker: "Adriana", daysInPending: 0, date: "09/10/2025", indicatorId: "106576-6", agency: "302", cpf: "456.789.012-43", phone: "(11) 98765-4335", email: "adriana@example.com", signedSubStatus: "payment_cycle", policy: "12345678" },
  { id: "16", number: "80316460327419", insuredName: "Ricardo Santos", status: "refund_scheduled", value: "R$ 2.300,00", product: "Vida Mulher", region: "Sul", ageRange: "40-55", broker: "Ricardo", daysInPending: 7, date: "08/10/2025", indicatorId: "106577-7", agency: "301", cpf: "567.890.123-54", phone: "(11) 98765-4336", email: "ricardo@example.com", declineReason: "Informações inconsistentes na documentação.", refundSubStatus: "pending_value", policy: "23456789" },
];

const statusInfo = [
  { value: "all", label: "Todas as Propostas" },
  { value: "pending_signature", label: "Aguardando Assinatura" },
  { value: "approved", label: "Ass. e Sensibilizado" },
  { value: "awaiting_payment", label: "Aguardando Pagamento" },
  { value: "signed_proposal", label: "Proposta Assinada" },
  { value: "pending_documentation", label: "Pendência Documental" },
  { value: "pending_dps", label: "Pendência de DPS" },
  { value: "sensitization_monitoring", label: "Monitoramento de Sensibilização" },
  { value: "return_in_progress", label: "Devolução em Andamento" },
  { value: "refund_scheduled", label: "Propostas Declinadas" },
];

const documentSubStatusLabels: Record<string, string> = {
  incomplete: "Proposta incompleta",
  mismatch: "Documento não corresponde a proposta",
  no_signature: "Proposta sem assinatura",
  illegible: "Documento Ilegível",
};

// Cores das vars antigas → fixas (mesma régua das outras telas nativas).
const STATUS_BADGE: Record<string, string> = {
  pending_signature: "bg-[#F26B00]",
  approved: "bg-emerald-600",
  awaiting_payment: "bg-amber-500",
  signed_proposal: "bg-emerald-600",
  pending_documentation: "bg-red-600",
  pending_dps: "bg-blue-600",
  sensitization_monitoring: "bg-red-500",
  return_in_progress: "bg-emerald-600",
  declined: "bg-amber-500",
  emission_sent: "bg-blue-600",
  refund_scheduled: "bg-red-600",
};

const STATUS_LABELS: Record<string, string> = {
  pending_signature: "Aguardando Assinatura",
  approved: "Assinado e Sensibilizado",
  awaiting_payment: "Aguardando Pagamento",
  signed_proposal: "Proposta Assinada",
  pending_documentation: "Pendência Documental",
  pending_dps: "Pendência de DPS",
  sensitization_monitoring: "Monitoramento de Sensibilização",
  return_in_progress: "Devolução em Andamento",
  declined: "Rejeitada",
  emission_sent: "Movimento de Emissão Enviado, Aguardando confirmação",
  refund_scheduled: "Propostas Declinadas",
};

const PAYMENT_LABELS: Record<string, string> = { boleto: "Boleto", debit: "Débito em Conta", credit: "Crédito em Conta" };

export default function InlineWorkflowOrq() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [selectedSubStatus, setSelectedSubStatus] = useState("all");
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [resendDialogOpen, setResendDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [dpsDialogOpen, setDpsDialogOpen] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [refundDialogOpen, setRefundDialogOpen] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState<WorkflowProposal | null>(null);
  const [proposalStatuses, setProposalStatuses] = useState<Record<string, string>>({});
  const [sendingEmission, setSendingEmission] = useState<string | null>(null);

  const counts: Record<string, number> = {
    all: mockWorkflowProposals.length,
    pending_signature: 0,
    approved: 0,
    awaiting_payment: 0,
    signed_proposal: 0,
    pending_documentation: 0,
    pending_dps: 0,
    sensitization_monitoring: 0,
    return_in_progress: 0,
    declined: 0,
    refund_scheduled: 0,
  };
  mockWorkflowProposals.forEach((proposal) => {
    const currentStatus = proposalStatuses[proposal.id] || proposal.status;
    if (counts[currentStatus] !== undefined) counts[currentStatus]++;
  });

  const filteredProposals = mockWorkflowProposals
    .filter((proposal) => {
      const currentStatus = proposalStatuses[proposal.id] || proposal.status;
      const statusMatch = selectedStatus === "all" || currentStatus === selectedStatus;
      if (currentStatus === "pending_documentation" && selectedSubStatus !== "all") {
        return statusMatch && proposal.documentSubStatus === selectedSubStatus;
      }
      if (currentStatus === "signed_proposal" && selectedSubStatus !== "all") {
        return statusMatch && proposal.signedSubStatus === selectedSubStatus;
      }
      if (currentStatus === "refund_scheduled" && selectedSubStatus !== "all") {
        return statusMatch && proposal.refundSubStatus === selectedSubStatus;
      }
      return statusMatch;
    })
    .sort((a, b) => b.daysInPending - a.daysInPending);

  const handleSendEmission = (proposalId: string) => {
    setSendingEmission(proposalId);
    setTimeout(() => {
      setProposalStatuses((prev) => ({ ...prev, [proposalId]: "emission_sent" }));
      setSendingEmission(null);
      toast.success("Movimento de Emissão enviado com sucesso. Aguardando confirmação.");
    }, 2000);
  };

  const abrir = (proposal: WorkflowProposal, setter: (v: boolean) => void) => {
    setSelectedProposal(proposal);
    setter(true);
  };

  return (
    <div className="space-y-4">
      <div className="bg-panel border border-edge rounded-lg">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-canvas/60 transition-colors rounded-lg text-ink"
          aria-expanded={isExpanded}
        >
          <div className="flex items-center gap-3">
            <span className="font-semibold text-lg">Workflow</span>
            <span className="inline-flex items-center rounded-full border border-edge px-2 py-0.5 text-xs font-medium text-dim">
              {counts.all} propostas
            </span>
          </div>
          {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </button>

        {isExpanded && (
          <div className="p-6 border-t border-edge space-y-4">
            {/* Cards-resumo por status */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
              {statusInfo.slice(1).map((status) => (
                <button
                  key={status.value}
                  onClick={() => {
                    setSelectedStatus(status.value);
                    setSelectedSubStatus("all");
                  }}
                  className={`p-2 rounded-lg border-2 transition-all ${
                    selectedStatus === status.value
                      ? "border-[#1A5FA8] bg-[#1A5FA8]/10"
                      : "border-edge hover:border-[#1A5FA8]/50"
                  }`}
                >
                  <div className="text-xs font-medium text-center text-ink">{status.label}</div>
                  <div className="text-xl font-bold text-center mt-1 text-ink">{counts[status.value]}</div>
                </button>
              ))}
            </div>

            {/* Filtros */}
            <div className="flex gap-3 flex-wrap">
              <div className="flex-1 min-w-[220px]">
                <Select
                  value={selectedStatus}
                  onChange={(e) => {
                    setSelectedStatus(e.target.value);
                    setSelectedSubStatus("all");
                  }}
                  aria-label="Filtrar por status"
                  className="w-full"
                >
                  {statusInfo.map((status) => (
                    <option key={status.value} value={status.value}>
                      {status.label} ({counts[status.value]})
                    </option>
                  ))}
                </Select>
              </div>

              {selectedStatus === "pending_documentation" && (
                <div className="flex-1 min-w-[220px]">
                  <Select value={selectedSubStatus} onChange={(e) => setSelectedSubStatus(e.target.value)} aria-label="Filtrar por sub-status" className="w-full">
                    <option value="all">Todos os sub-status</option>
                    <option value="incomplete">Proposta incompleta</option>
                    <option value="mismatch">Documento não corresponde</option>
                    <option value="no_signature">Proposta sem assinatura</option>
                    <option value="illegible">Documento Ilegível</option>
                  </Select>
                </div>
              )}
              {selectedStatus === "signed_proposal" && (
                <div className="flex-1 min-w-[220px]">
                  <Select value={selectedSubStatus} onChange={(e) => setSelectedSubStatus(e.target.value)} aria-label="Filtrar por sub-status" className="w-full">
                    <option value="all">Todos os sub-status</option>
                    <option value="payment_cycle">Propostas em fase pagamento</option>
                    <option value="payment_ended">Propostas com ciclo de pagamento encerrado</option>
                  </Select>
                </div>
              )}
              {selectedStatus === "refund_scheduled" && (
                <div className="flex-1 min-w-[220px]">
                  <Select value={selectedSubStatus} onChange={(e) => setSelectedSubStatus(e.target.value)} aria-label="Filtrar por sub-status" className="w-full">
                    <option value="all">Todos os sub-status</option>
                    <option value="scheduled">Devolução Programada</option>
                    <option value="pending_value">Valor Pendente de Devolução</option>
                  </Select>
                </div>
              )}
            </div>

            {/* Alerta em lote */}
            {filteredProposals.length > 0 && selectedStatus !== "all" && selectedStatus !== "approved" && (
              <Button variant="primary" onClick={() => setAlertDialogOpen(true)} className="w-full justify-center">
                Enviar Alertas para Responsáveis
              </Button>
            )}

            {/* Lista */}
            <div className="max-h-[400px] overflow-y-auto pr-1">
              <div className="space-y-3">
                {filteredProposals.map((proposal) => {
                  const currentStatus = proposalStatuses[proposal.id] || proposal.status;
                  return (
                    <div
                      key={proposal.id}
                      className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => abrir(proposal, setDetailDialogOpen)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") abrir(proposal, setDetailDialogOpen);
                      }}
                    >
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="flex-1 min-w-[240px] space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-ink">{proposal.number}</span>
                            <span className={`${STATUS_BADGE[currentStatus] ?? "bg-slate-500"} text-white rounded-full px-2 py-0.5 text-xs font-medium`}>
                              {STATUS_LABELS[currentStatus] ?? currentStatus}
                            </span>
                            {proposal.daysInPending > 0 && (
                              <span className="inline-flex items-center rounded-full border border-[#F26B00] text-[#F26B00] px-2 py-0.5 text-xs font-medium">
                                {proposal.daysInPending} dias pendente
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-dim">
                            <p className="font-medium text-ink">{proposal.insuredName}</p>
                            <p>
                              {proposal.product} - {proposal.value}
                            </p>
                            <p>
                              Região: {proposal.region} | Faixa: {proposal.ageRange}
                            </p>
                            {currentStatus === "pending_documentation" && proposal.documentSubStatus && (
                              <p className="text-red-600 dark:text-red-400 font-medium">
                                {documentSubStatusLabels[proposal.documentSubStatus]}
                              </p>
                            )}
                            {currentStatus === "awaiting_payment" && proposal.paymentMethod && (
                              <p className="font-medium text-ink">Forma de Pagamento: {PAYMENT_LABELS[proposal.paymentMethod]}</p>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                          {currentStatus === "pending_signature" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposal, setResendDialogOpen)}>
                              <Send className="h-4 w-4" />
                              Enviar
                            </Button>
                          )}
                          {currentStatus === "pending_documentation" && (
                            <Button variant="danger" size="sm" onClick={() => abrir(proposal, setUploadDialogOpen)}>
                              Upload
                            </Button>
                          )}
                          {currentStatus === "pending_dps" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposal, setDpsDialogOpen)}>
                              Enviar Link DPS
                            </Button>
                          )}
                          {currentStatus === "awaiting_payment" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposal, setPaymentDialogOpen)}>
                              Alterar forma de pagamento
                            </Button>
                          )}
                          {currentStatus === "sensitization_monitoring" && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleSendEmission(proposal.id)}
                              disabled={sendingEmission === proposal.id}
                              loading={sendingEmission === proposal.id}
                            >
                              {sendingEmission === proposal.id ? "Enviando..." : "Enviar movimento de Emissão"}
                            </Button>
                          )}
                          {currentStatus === "refund_scheduled" && (
                            <Button variant="danger" size="sm" onClick={() => abrir(proposal, setRefundDialogOpen)}>
                              Gerenciar Devolução
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {selectedProposal && (
        <>
          <ProposalDetailDialogOrq
            proposal={{
              ...selectedProposal,
              status: (proposalStatuses[selectedProposal.id] || selectedProposal.status) as WorkflowStatus,
            }}
            open={detailDialogOpen}
            onClose={() => setDetailDialogOpen(false)}
          />
          <ResendLinkDialogOrq
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              cpf: selectedProposal.cpf,
              value: selectedProposal.value,
              email: selectedProposal.email,
              phone: selectedProposal.phone,
            }}
            open={resendDialogOpen}
            onClose={() => setResendDialogOpen(false)}
          />
          <DocumentUploadDialogOrq
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={uploadDialogOpen}
            onClose={() => setUploadDialogOpen(false)}
          />
          <DPSLinkDialogOrq
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={dpsDialogOpen}
            onClose={() => setDpsDialogOpen(false)}
          />
          <PaymentOptionsDialogOrq
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              value: selectedProposal.value,
              paymentMethod: selectedProposal.paymentMethod || "boleto",
              email: selectedProposal.email,
              phone: selectedProposal.phone,
            }}
            open={paymentDialogOpen}
            onClose={() => setPaymentDialogOpen(false)}
          />
          <RefundManagementDialogOrq
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              cpf: selectedProposal.cpf,
              product: selectedProposal.product,
              policy: selectedProposal.policy || "N/A",
              value: selectedProposal.value,
            }}
            open={refundDialogOpen}
            onClose={() => setRefundDialogOpen(false)}
            onStatusChange={() => {
              setProposalStatuses((prev) => ({ ...prev, [selectedProposal.id]: "refund_scheduled" }));
            }}
          />
        </>
      )}

      <SendAlertDialogOrq proposals={filteredProposals} open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} />
    </div>
  );
}
