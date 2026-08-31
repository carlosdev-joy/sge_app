// Workflow inline da home no DS nativo — card colapsável com resumo por
// status, filtros com sub-status, alerta em lote e lista de propostas com ação
// por status, incluindo o movimento de Emissão (sensitization_monitoring →
// emission_sent, estado local). Todos os diálogos são os nativos das F3/F7/F8.
//
// A sequência dos cards, os rótulos e as propostas vêm de `lib/workflow.ts` —
// a MESMA fonte que o painel do botão "Workflow" (ProposalWorkflowSheet) lê.
// Antes cada um tinha a sua lista e o seu mock, na mesma tela.
import { useState } from "react";
import { ChevronDown, ChevronUp, CircleCheck, Send, TrendingDown, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import ProposalDetailDialog from "./ProposalDetailDialog";
import ResendLinkDialog from "./ResendLinkDialog";
import DocumentUploadDialog from "./DocumentUploadDialog";
import DPSLinkDialog from "./DPSLinkDialog";
import SendAlertDialog from "./SendAlertDialog";
import PaymentOptionsDialog from "./PaymentOptionsDialog";
import RefundManagementDialog from "./RefundManagementDialog";
import {
  contarPorStatus,
  propostasWorkflow,
  FORMA_PAGAMENTO,
  SEQUENCIA_WORKFLOW,
  STATUS_COR,
  STATUS_LABEL_CURTO,
  SUB_STATUS_ANALISE,
  SUB_STATUS_DEVOLUCAO,
  SUB_STATUS_PAGAMENTO,
  type PropostaWorkflow,
  type SinalWorkflow,
  type StatusWorkflow,
} from "../lib/workflow";

// ÍCONE, não bolinha: a forma carrega o significado sozinha. Um triângulo de
// alerta, uma seta caindo e um "certo" são lidos de relance mesmo em preto e
// branco — a cor vira reforço, não a informação. E o `title`/`aria-label` leva
// a frase inteira, para quem usa leitor de tela.
//
// Discretos de propósito (14px, traço fino, tom 500): o número é a informação
// principal do card; o sinal qualifica, não compete.
const SINAL_ICONE: Record<SinalWorkflow, LucideIcon> = {
  aviso:    TriangleAlert,   // atenção: algo esperando
  perda:    TrendingDown,    // negócio que caiu — não é "erro", é perda
  positivo: CircleCheck,     // avançou
};

// Tom 500 nos três: forte o bastante para distinguir, fraco o bastante para
// não brigar com o número ao lado. O dark: mantém o contraste no tema escuro,
// onde o 500 puro fica apagado.
const SINAL_CLASSE: Record<SinalWorkflow, string> = {
  aviso:    "text-amber-500 dark:text-amber-400",
  perda:    "text-red-500 dark:text-red-400",
  positivo: "text-emerald-500 dark:text-emerald-400",
};

const SINAL_TEXTO: Record<SinalWorkflow, string> = {
  aviso:    "Aviso: propostas paradas aguardando ação",
  perda:    "Perda: negócios que não seguiram adiante",
  positivo: "Ação positiva: propostas que avançaram no funil",
};

// Qual campo cada status filtra no segundo Select. Um mapa só, em vez de três
// blocos repetidos: status novo com sub-status entra aqui e passa a valer no
// filtro E na contagem, sem depender de alguém lembrar dos dois lugares.
const SUB_FILTRO: Partial<Record<StatusWorkflow, { campo: keyof PropostaWorkflow; opcoes: Record<string, string> }>> = {
  awaiting_payment: { campo: "pagamentoSubStatus", opcoes: SUB_STATUS_PAGAMENTO },
  in_analysis:      { campo: "analiseSubStatus",   opcoes: SUB_STATUS_ANALISE },
  refund_scheduled: { campo: "refundSubStatus",    opcoes: SUB_STATUS_DEVOLUCAO },
};

export default function InlineWorkflow() {
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
  const [selectedProposal, setSelectedProposal] = useState<PropostaWorkflow | null>(null);
  const [proposalStatuses, setProposalStatuses] = useState<Record<string, string>>({});
  const [sendingEmission, setSendingEmission] = useState<string | null>(null);

  const counts = contarPorStatus(propostasWorkflow, proposalStatuses);
  const subFiltroAtivo = SUB_FILTRO[selectedStatus as StatusWorkflow];

  const filteredProposals = propostasWorkflow
    .filter((proposta) => {
      const statusAtual = proposalStatuses[proposta.id] || proposta.status;
      if (selectedStatus !== "all" && statusAtual !== selectedStatus) return false;
      if (subFiltroAtivo && selectedSubStatus !== "all") {
        return proposta[subFiltroAtivo.campo] === selectedSubStatus;
      }
      return true;
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

  const abrir = (proposta: PropostaWorkflow, setter: (v: boolean) => void) => {
    setSelectedProposal(proposta);
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
            {/* Cards-resumo por status — 4 + 4 nas telas largas */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {SEQUENCIA_WORKFLOW.map((status) => (
                <button
                  key={status.value}
                  onClick={() => {
                    setSelectedStatus(status.value);
                    setSelectedSubStatus("all");
                  }}
                  className={`relative p-2 rounded-lg border-2 transition-all ${
                    selectedStatus === status.value
                      ? "border-[#1A5FA8] bg-[#1A5FA8]/10"
                      : "border-edge hover:border-[#1A5FA8]/50"
                  }`}
                >
                  {/* Sinal no canto INFERIOR direito, FORA do fluxo.
                      Duas razões, nesta ordem:
                      1. no topo ele disputaria espaço com o rótulo, que é o
                         elemento longo e de altura variável ("Devolução de
                         Prêmio de Propostas Rejeitadas" ocupa três linhas);
                         embaixo convive com o número, que é curto e
                         centralizado;
                      2. tira o ícone do fluxo e devolve ao número o centro
                         do card. Antes os dois eram centralizados JUNTOS, e
                         o número mudava de posição conforme tivesse 1 ou 2
                         dígitos — numa fileira de cards, dançavam. */}
                  {(() => {
                    const Icone = SINAL_ICONE[status.sinal];
                    return (
                      <Icone
                        className={`absolute bottom-1.5 right-1.5 h-3.5 w-3.5 ${SINAL_CLASSE[status.sinal]}`}
                        strokeWidth={2}
                        role="img"
                        aria-label={SINAL_TEXTO[status.sinal]}
                      >
                        <title>{SINAL_TEXTO[status.sinal]}</title>
                      </Icone>
                    );
                  })()}
                  {/* Sem folga lateral: com o sinal embaixo, o rótulo usa a
                      largura inteira e quebra em menos linhas. */}
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
                  <option value="all">Todas as Propostas ({counts.all})</option>
                  {SEQUENCIA_WORKFLOW.map((status) => (
                    <option key={status.value} value={status.value}>
                      {status.label} ({counts[status.value]})
                    </option>
                  ))}
                </Select>
              </div>

              {subFiltroAtivo && (
                <div className="flex-1 min-w-[220px]">
                  <Select
                    value={selectedSubStatus}
                    onChange={(e) => setSelectedSubStatus(e.target.value)}
                    aria-label="Filtrar por sub-status"
                    className="w-full"
                  >
                    <option value="all">Todos os sub-status</option>
                    {Object.entries(subFiltroAtivo.opcoes).map(([valor, rotulo]) => (
                      <option key={valor} value={valor}>
                        {rotulo}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
            </div>

            {/* Alerta em lote */}
            {filteredProposals.length > 0 && selectedStatus !== "all" && (
              <Button variant="primary" onClick={() => setAlertDialogOpen(true)} className="w-full justify-center">
                Enviar Alertas para Responsáveis
              </Button>
            )}

            {/* Lista */}
            <div className="max-h-[400px] overflow-y-auto pr-1">
              <div className="space-y-3">
                {filteredProposals.map((proposta) => {
                  const statusAtual = (proposalStatuses[proposta.id] || proposta.status) as StatusWorkflow;
                  return (
                    <div
                      key={proposta.id}
                      className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => abrir(proposta, setDetailDialogOpen)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") abrir(proposta, setDetailDialogOpen);
                      }}
                    >
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="flex-1 min-w-[240px] space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-ink">{proposta.number}</span>
                            <span className={`${STATUS_COR[statusAtual] ?? "bg-slate-500"} text-white rounded-full px-2 py-0.5 text-xs font-medium`}>
                              {STATUS_LABEL_CURTO[statusAtual] ?? statusAtual}
                            </span>
                            {proposta.daysInPending > 0 && (
                              <span className="inline-flex items-center rounded-full border border-[#F26B00] text-[#F26B00] px-2 py-0.5 text-xs font-medium">
                                {proposta.daysInPending} dias pendente
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-dim">
                            <p className="font-medium text-ink">{proposta.insuredName}</p>
                            <p>
                              {proposta.product} - {proposta.value}
                            </p>
                            <p>
                              Região: {proposta.region} | Faixa: {proposta.ageRange}
                            </p>
                            {statusAtual === "in_analysis" && proposta.analiseSubStatus && (
                              <p className="text-red-600 dark:text-red-400 font-medium">
                                {SUB_STATUS_ANALISE[proposta.analiseSubStatus]}
                              </p>
                            )}
                            {statusAtual === "awaiting_payment" && proposta.paymentMethod && (
                              <p className="font-medium text-ink">Forma de Pagamento: {FORMA_PAGAMENTO[proposta.paymentMethod]}</p>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                          {statusAtual === "pending_signature" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposta, setResendDialogOpen)}>
                              <Send className="h-4 w-4" />
                              Enviar
                            </Button>
                          )}
                          {/* A DPS virou sub-status da crítica: o botão segue a
                              pendência da proposta, não mais o card. */}
                          {statusAtual === "in_analysis" &&
                            (proposta.analiseSubStatus === "dps" ? (
                              <Button variant="primary" size="sm" onClick={() => abrir(proposta, setDpsDialogOpen)}>
                                Enviar Link DPS
                              </Button>
                            ) : (
                              <Button variant="danger" size="sm" onClick={() => abrir(proposta, setUploadDialogOpen)}>
                                Upload
                              </Button>
                            ))}
                          {statusAtual === "awaiting_payment" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposta, setPaymentDialogOpen)}>
                              Alterar forma de pagamento
                            </Button>
                          )}
                          {statusAtual === "sensitization_monitoring" && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleSendEmission(proposta.id)}
                              disabled={sendingEmission === proposta.id}
                              loading={sendingEmission === proposta.id}
                            >
                              {sendingEmission === proposta.id ? "Enviando..." : "Enviar movimento de Emissão"}
                            </Button>
                          )}
                          {/* Rejeitada e devolução compartilham o diálogo: na
                              rejeitada ele INICIA a devolução (o card 6 vira o
                              7); na devolução, gerencia a que já existe. */}
                          {(statusAtual === "declined" || statusAtual === "refund_scheduled") && (
                            <Button variant="danger" size="sm" onClick={() => abrir(proposta, setRefundDialogOpen)}>
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
          <ProposalDetailDialog
            proposal={{
              ...selectedProposal,
              status: (proposalStatuses[selectedProposal.id] || selectedProposal.status) as StatusWorkflow,
            }}
            open={detailDialogOpen}
            onClose={() => setDetailDialogOpen(false)}
          />
          <ResendLinkDialog
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
          <DocumentUploadDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={uploadDialogOpen}
            onClose={() => setUploadDialogOpen(false)}
          />
          <DPSLinkDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={dpsDialogOpen}
            onClose={() => setDpsDialogOpen(false)}
          />
          <PaymentOptionsDialog
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
          <RefundManagementDialog
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

      <SendAlertDialog proposals={filteredProposals} open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} />
    </div>
  );
}
