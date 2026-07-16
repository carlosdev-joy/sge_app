// "Acompanhamento por status" no DS nativo — F6 da migração
// (docs/spec-caixa-ds-nativo.md), em ROTA PARALELA
// /caixa-seguro/acompanhamento-orq/:status. A tela oficial continua sendo o
// ProposalTracking shadcn até a F9 promover esta. Entrega da F6 = tela base
// (banner por status, filtros de sub-status, lista com os 4 formatos) +
// CONSULTA (ProposalCardOrq → detalhe/timeline/histórico portados na F3) +
// balão de ajuda do status em Modal nativo + FABs por status via
// ChatAssistantOrq. Os botões de AÇÃO (alertas, upload, DPS, pagamento,
// devolução, nova venda, sensibilização) ficam desabilitados — são as F7/F8.
// Dados mock idênticos aos da tela original.
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Mail, DollarSign, PlusCircle, History, ExternalLink, HelpCircle } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { Modal } from "../../components/ui/Modal";
import ProposalCardOrq, { type ProposalTrackingOrq } from "../components/ProposalCardOrq";
import ProposalTimelineOrq from "../components/ProposalTimelineOrq";
import ChatAssistantOrq from "../components/ChatAssistantOrq";
import MenuButtonOrq from "../components/MenuButtonOrq";
import lariAvatar from "../assets/lari-avatar.png";
import diegoAvatar from "../assets/diego-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";

type ProposalStatus =
  | "pending_signature"
  | "awaiting_payment"
  | "signed_proposal"
  | "pending_documentation"
  | "pending_dps"
  | "refund_scheduled"
  | "refund_pending"
  | "valores_programados"
  | "sensitization_monitoring";

type DocumentSubStatus = "incomplete" | "not_match" | "no_signature" | "illegible" | "non_compliant" | "procuration_curatela" | "all";
type SignedSubStatus = "payment_cycle" | "payment_ended" | "all";
type RefundSubStatus = "scheduled" | "pending" | "all";
type PaymentSubStatus = "payment_phase" | "payment_ended_no_payment" | "all";

interface Proposal extends ProposalTrackingOrq {
  status: ProposalStatus;
  policy?: string;
  documentSubStatus?: DocumentSubStatus;
  signedSubStatus?: SignedSubStatus;
  paymentSubStatus?: PaymentSubStatus;
  broker?: string;
  refundDate?: string;
  paymentMethod?: string;
  daysInPending?: number;
}

// Mesmo mock da tela original (17 propostas).
const mockProposals: Proposal[] = [
  { id: "1", number: "8047413032422-7", insuredName: "DIEBSON BITENCOURT DA SILVA", date: "17/10/2025", status: "pending_signature", value: "R$ 5.624,75", indicatorId: "0000122795-B", agency: "474", cpf: "025.359.088-03", product: "Vida Multipremiado Total", phone: "(11) 98765-4321", email: "diebson@email.com", daysInPending: 5 },
  { id: "2", number: "8047413032423-8", insuredName: "MARIA OLIVEIRA SANTOS", date: "18/10/2025", status: "pending_signature", value: "R$ 3.200,00", indicatorId: "0000122796-C", agency: "474", cpf: "123.456.789-00", product: "Vida Mulher", phone: "(11) 91234-5678", email: "maria@email.com", daysInPending: 3 },
  { id: "3", number: "8047413032424-9", insuredName: "JOÃO CARLOS FERREIRA", date: "19/10/2025", status: "awaiting_payment", paymentSubStatus: "payment_phase", value: "R$ 4.500,00", indicatorId: "0000122797-D", agency: "474", cpf: "234.567.890-11", product: "Vida Conforto", phone: "(11) 92345-6789", email: "joao@email.com", paymentMethod: "Boleto", daysInPending: 7 },
  { id: "4", number: "8047413032425-0", insuredName: "ANA PAULA COSTA", date: "20/10/2025", status: "awaiting_payment", paymentSubStatus: "payment_ended_no_payment", value: "R$ 6.800,00", indicatorId: "0000122798-E", agency: "474", cpf: "345.678.901-22", product: "Perda de Renda", phone: "(11) 93456-7890", email: "ana@email.com", paymentMethod: "Débito em Conta", daysInPending: 4 },
  { id: "5", number: "8047413032426-1", insuredName: "PEDRO HENRIQUE LIMA", date: "21/10/2025", status: "signed_proposal", signedSubStatus: "payment_cycle", value: "R$ 5.100,00", indicatorId: "0000122799-F", agency: "474", cpf: "456.789.012-33", product: "Vida Multipremiado Total", policy: "POL-2024-001", phone: "(11) 94567-8901", email: "pedro@email.com" },
  { id: "6", number: "8047413032427-2", insuredName: "CARLA REGINA SOUZA", date: "22/10/2025", status: "signed_proposal", signedSubStatus: "payment_ended", value: "R$ 7.300,00", indicatorId: "0000122800-G", agency: "474", cpf: "567.890.123-44", product: "Vida Mulher", policy: "POL-2024-002", phone: "(11) 95678-9012", email: "carla@email.com" },
  { id: "7", number: "8047413032428-3", insuredName: "ROBERTO SILVA SANTOS", date: "23/10/2025", status: "pending_documentation", value: "R$ 4.200,00", indicatorId: "0000122801-H", agency: "474", cpf: "678.901.234-55", product: "Vida Conforto", phone: "(11) 96789-0123", email: "roberto@email.com", documentSubStatus: "incomplete", broker: "João Silva", daysInPending: 12 },
  { id: "8", number: "8047413032429-4", insuredName: "LUCIA MARIA FERNANDES", date: "24/10/2025", status: "pending_documentation", value: "R$ 5.800,00", indicatorId: "0000122802-I", agency: "474", cpf: "789.012.345-66", product: "Perda de Renda", phone: "(11) 97890-1234", email: "lucia@email.com", documentSubStatus: "illegible", broker: "Maria Santos", daysInPending: 8 },
  { id: "14", number: "8047413032435-0", insuredName: "AMANDA CRISTINA ROCHA", date: "30/10/2025", status: "pending_documentation", value: "R$ 3.900,00", indicatorId: "0000122808-O", agency: "474", cpf: "345.678.901-30", product: "Vida Mulher", phone: "(11) 94444-5555", email: "amanda@email.com", documentSubStatus: "not_match", broker: "Carlos Pereira", daysInPending: 6 },
  { id: "15", number: "8047413032436-1", insuredName: "EDUARDO SANTOS LIMA", date: "31/10/2025", status: "pending_documentation", value: "R$ 5.200,00", indicatorId: "0000122809-P", agency: "474", cpf: "456.789.012-40", product: "Vida Multipremiado Total", phone: "(11) 95555-6666", email: "eduardo@email.com", documentSubStatus: "no_signature", broker: "Ana Paula", daysInPending: 10 },
  { id: "16", number: "8047413032437-2", insuredName: "MARCOS VINÍCIUS ALMEIDA", date: "01/11/2025", status: "pending_documentation", value: "R$ 650.000,00", indicatorId: "0000122810-Q", agency: "474", cpf: "567.890.123-50", product: "Previdência PGBL", phone: "(11) 96666-7777", email: "marcos@email.com", documentSubStatus: "non_compliant", broker: "Roberto Lima", daysInPending: 15 },
  { id: "17", number: "8047413032438-3", insuredName: "JULIANA COSTA PEREIRA", date: "02/11/2025", status: "pending_documentation", value: "R$ 820.000,00", indicatorId: "0000122811-R", agency: "474", cpf: "678.901.234-60", product: "Previdência VGBL", phone: "(11) 97777-8888", email: "juliana@email.com", documentSubStatus: "non_compliant", broker: "Patricia Santos", daysInPending: 18 },
  { id: "18", number: "8047413032439-4", insuredName: "ANTONIO CARLOS RODRIGUES", date: "03/11/2025", status: "pending_documentation", value: "R$ 45.000,00", indicatorId: "0000122812-S", agency: "474", cpf: "789.012.345-70", product: "Previdência Total", phone: "(11) 98888-9999", email: "antonio@email.com", documentSubStatus: "procuration_curatela", broker: "Fernando Alves", daysInPending: 9 },
  { id: "19", number: "8047413032440-5", insuredName: "BEATRIZ OLIVEIRA SOUZA", date: "04/11/2025", status: "pending_documentation", value: "R$ 32.500,00", indicatorId: "0000122813-T", agency: "474", cpf: "890.123.456-80", product: "Previdência Ativa", phone: "(11) 99999-0000", email: "beatriz@email.com", documentSubStatus: "procuration_curatela", broker: "Carla Regina", daysInPending: 11 },
  { id: "9", number: "8047413032430-5", insuredName: "FERNANDO AUGUSTO LIMA", date: "25/10/2025", status: "refund_scheduled", refundSubStatus: "scheduled", value: "R$ 3.500,00", indicatorId: "0000122803-J", agency: "474", cpf: "890.123.456-77", product: "Vida Multipremiado Total", policy: "POL-2024-003", phone: "(11) 98901-2345", email: "fernando@email.com", declineReason: "Análise de crédito negativa", refundDate: "15/12/2025" },
  { id: "10", number: "8047413032431-6", insuredName: "PATRICIA SANTOS COSTA", date: "26/10/2025", status: "refund_pending", refundSubStatus: "pending", value: "R$ 4.900,00", indicatorId: "0000122804-K", agency: "474", cpf: "901.234.567-88", product: "Vida Mulher", policy: "POL-2024-004", phone: "(11) 99012-3456", email: "patricia@email.com", declineReason: "Documentação irregular", receiptNumber: "REC-2024-12345" },
  { id: "13", number: "8047413032434-9", insuredName: "RAFAEL MENDES ALMEIDA", date: "29/10/2025", status: "refund_pending", refundSubStatus: "pending", value: "R$ 3.300,00", indicatorId: "0000122807-N", agency: "474", cpf: "234.567.890-20", product: "Vida Conforto", policy: "POL-2024-006", phone: "(11) 93333-4444", email: "rafael@email.com", declineReason: "Análise de risco", receiptNumber: "REC-2024-12346" },
  { id: "11", number: "8047413032432-7", insuredName: "MARCOS ANTONIO PEREIRA", date: "27/10/2025", status: "pending_dps", value: "R$ 2.800,00", indicatorId: "0000122805-L", agency: "474", cpf: "012.345.678-99", product: "Vida Conforto", phone: "(11) 91111-2222", email: "marcos@email.com", broker: "Carlos Oliveira", daysInPending: 6 },
  { id: "12", number: "8047413032433-8", insuredName: "JULIANA ROCHA ALVES", date: "28/10/2025", status: "valores_programados", value: "R$ 5.200,00", indicatorId: "0000122806-M", agency: "474", cpf: "123.456.789-10", product: "Perda de Renda", policy: "POL-2024-005", phone: "(11) 92222-3333", email: "juliana@email.com", declineReason: "Não atende critérios de aceitação", refundDate: "20/12/2025" },
];

// Ajuda contextual por status (mesmos textos/assistentes da POC e do
// Monitoramento nativo).
const statusHelpInfo: Record<string, { avatar: string; avatarName: string; message: string }> = {
  pending_signature: { avatar: lariAvatar, avatarName: "Lari", message: "Este status corresponde a propostas que estão pendentes de assinatura. Você pode utilizar o botão 'Enviar Link' para enviar ao cliente o link para assinatura da proposta via e-mail, WhatsApp ou SMS!" },
  awaiting_payment: { avatar: diegoAvatar, avatarName: "Diego", message: "Estas são propostas já assinadas que aguardam o pagamento. Você pode gerenciar as opções de pagamento e enviar lembretes ao cliente através do botão 'Gerenciar Pagamento'." },
  pending_documentation: { avatar: lariAvatar, avatarName: "Lari", message: "Propostas com pendências documentais precisam de documentos adicionais. Use o botão 'Upload de Documentos' para enviar os arquivos necessários e dar andamento à proposta." },
  pending_dps: { avatar: leoAvatar, avatarName: "Léo", message: "Pendência de DPS (Declaração Pessoal de Saúde) significa que o cliente precisa preencher informações de saúde. Clique em 'Enviar Link DPS' para enviar o formulário ao segurado." },
  refund_pending: { avatar: diegoAvatar, avatarName: "Diego", message: "Estas são propostas que foram declinadas pela seguradora. Você pode gerenciar o reembolso através do botão 'Gerenciar Reembolso' ou criar uma nova venda revisando as informações." },
};

const STATUS_LABELS: Record<string, string> = {
  all: "Todos os Status",
  pending_signature: "Aguardando Assinatura",
  awaiting_payment: "Aguardando Pagamento",
  signed_proposal: "Proposta Assinada",
  pending_documentation: "Pendência Documental",
  pending_dps: "Pendência de DPS",
  refund_scheduled: "Devolução Programada",
  refund_pending: "Valor Pendente de Devolução",
  valores_programados: "Valores Programados",
  sensitization_monitoring: "Monitoramento de Sensibilização",
};

// Cores dos banners — mapeadas das vars do tema antigo p/ cores fixas
// (--orange→#F26B00, --yellow→amber-500, --green→emerald-600, --blue→blue-600,
// --chart-2 era o MESMO laranja, --chart-5→red-500). Texto sempre branco — o
// banner de DPS antigo usava texto preto sobre azul médio (contraste ruim).
const STATUS_BANNER: Record<string, string> = {
  all: "bg-[#1A5FA8]",
  pending_signature: "bg-[#F26B00]",
  awaiting_payment: "bg-amber-500",
  signed_proposal: "bg-emerald-600",
  pending_documentation: "bg-red-600",
  pending_dps: "bg-blue-600",
  refund_scheduled: "bg-[#F26B00]",
  refund_pending: "bg-red-600",
  valores_programados: "bg-purple-600",
  sensitization_monitoring: "bg-red-500",
};

const DOC_SUB_LABELS: Record<string, string> = {
  all: "Todos",
  incomplete: "Proposta incompleta",
  not_match: "Documento não corresponde a proposta",
  no_signature: "Proposta sem assinatura",
  illegible: "Documento Ilegível",
  non_compliant: "Propostas fora da conformidade",
  procuration_curatela: "Pendências relacionadas a Procuração/Curatela e A Rogo",
};

const TITULO_FASE = "Ação portada nas fases F7/F8 da migração (rota paralela)";

function CampoPainel({ rotulo, valor, tom = "normal", className = "" }: { rotulo: string; valor: React.ReactNode; tom?: "normal" | "azul" | "laranja" | "vermelho" | "verde"; className?: string }) {
  const cores: Record<string, string> = {
    normal: "text-ink",
    azul: "text-[#1A5FA8] dark:text-blue-400",
    laranja: "text-[#F26B00]",
    vermelho: "text-red-600 dark:text-red-400",
    verde: "text-emerald-600 dark:text-emerald-400",
  };
  return (
    <div className={className}>
      <span className="text-sm text-dim">{rotulo}</span>
      <p className={`font-semibold ${cores[tom]}`}>{valor}</p>
    </div>
  );
}

export default function AcompanhamentoOrq() {
  const { status } = useParams<{ status: string }>();
  const navigate = useNavigate();
  const [documentSubStatusFilter, setDocumentSubStatusFilter] = useState<DocumentSubStatus>("all");
  const [signedSubStatusFilter, setSignedSubStatusFilter] = useState<SignedSubStatus>("all");
  const [refundSubStatusFilter, setRefundSubStatusFilter] = useState<RefundSubStatus>("all");
  const [paymentSubStatusFilter, setPaymentSubStatusFilter] = useState<PaymentSubStatus>("all");
  const [ajudaAberta, setAjudaAberta] = useState(false);

  // Derivado direto da URL (a tela antiga sincronizava via useEffect+state,
  // mas o único gatilho é o próprio :status — sem efeito é equivalente).
  const selectedStatus: ProposalStatus | "all" =
    status && status in STATUS_LABELS && status !== "all" ? (status as ProposalStatus) : "all";

  let filteredProposals = selectedStatus === "all"
    ? mockProposals
    : mockProposals.filter((p) => p.status === selectedStatus);

  if (selectedStatus === "pending_documentation" && documentSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter((p) => p.documentSubStatus === documentSubStatusFilter);
  }
  if (selectedStatus === "signed_proposal" && signedSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter((p) => p.signedSubStatus === signedSubStatusFilter);
  }
  if (selectedStatus === "awaiting_payment" && paymentSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter((p) => p.paymentSubStatus === paymentSubStatusFilter);
  }
  // Quirk herdado da POC: o filtro de devolução troca o STATUS exibido
  // (scheduled↔pending), não sub-filtra — preservado para paridade.
  if ((selectedStatus === "refund_scheduled" || selectedStatus === "refund_pending") && refundSubStatusFilter !== "all") {
    const targetStatus = refundSubStatusFilter === "scheduled" ? "refund_scheduled" : "refund_pending";
    filteredProposals = mockProposals.filter((p) => p.status === targetStatus);
  }

  const ajuda = statusHelpInfo[selectedStatus as string];

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1200px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="ghost" size="md" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Button>
          <MenuButtonOrq />
        </div>

        {/* Banner do status */}
        <div className={`${STATUS_BANNER[selectedStatus] ?? "bg-[#1A5FA8]"} text-white px-6 py-4 rounded-lg`}>
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold">{STATUS_LABELS[selectedStatus]}</h1>
            {ajuda && (
              <button
                onClick={() => setAjudaAberta(true)}
                className="hover:scale-110 transition-transform"
                aria-label="Sobre este status"
              >
                <HelpCircle className="h-6 w-6 opacity-80 hover:opacity-100" />
              </button>
            )}
          </div>
        </div>

        {/* Botões de ação da tela (F7/F8 — desabilitados na rota paralela) */}
        <div className="flex gap-3 flex-wrap">
          <Button variant="secondary" size="md" disabled title={TITULO_FASE}>
            <Mail className="h-4 w-4" />
            Enviar Alertas ({filteredProposals.length})
          </Button>
          {selectedStatus === "pending_documentation" && (
            <Button variant="secondary" size="md" disabled title={TITULO_FASE}>
              <ExternalLink className="h-4 w-4" />
              Upload de Documentos
            </Button>
          )}
          {selectedStatus === "pending_dps" && filteredProposals.length > 0 && (
            <Button variant="secondary" size="md" disabled title={TITULO_FASE}>
              <ExternalLink className="h-4 w-4" />
              Enviar Link DPS
            </Button>
          )}
        </div>

        {/* Filtros de sub-status (mesmas opções da POC) */}
        {selectedStatus === "pending_documentation" && (
          <Select
            value={documentSubStatusFilter}
            onChange={(e) => setDocumentSubStatusFilter(e.target.value as DocumentSubStatus)}
            aria-label="Filtrar por sub-status"
            className="w-[320px]"
          >
            <option value="all">Todos</option>
            <option value="incomplete">Proposta incompleta</option>
            <option value="not_match">Documento não corresponde a proposta</option>
            <option value="no_signature">Proposta sem assinatura</option>
            <option value="illegible">Documento Ilegível</option>
            <option value="non_compliant">Propostas fora da conformidade</option>
            <option value="procuration_curatela">Pendências Procuração/Curatela e A Rogo</option>
          </Select>
        )}
        {selectedStatus === "signed_proposal" && (
          <Select
            value={signedSubStatusFilter}
            onChange={(e) => setSignedSubStatusFilter(e.target.value as SignedSubStatus)}
            aria-label="Filtrar por subgrupo"
            className="w-[320px]"
          >
            <option value="all">Todos</option>
            <option value="payment_cycle">Propostas em fase pagamento</option>
            <option value="payment_ended">Propostas com ciclo de pagamento encerrado</option>
          </Select>
        )}
        {selectedStatus === "awaiting_payment" && (
          <Select
            value={paymentSubStatusFilter}
            onChange={(e) => setPaymentSubStatusFilter(e.target.value as PaymentSubStatus)}
            aria-label="Filtrar por substatus"
            className="w-[350px]"
          >
            <option value="all">Todos</option>
            <option value="payment_phase">Propostas em fase de pagamento</option>
            <option value="payment_ended_no_payment">Ciclo encerrado sem quitação</option>
          </Select>
        )}
        {(selectedStatus === "refund_scheduled" || selectedStatus === "refund_pending") && (
          <Select
            value={refundSubStatusFilter}
            onChange={(e) => setRefundSubStatusFilter(e.target.value as RefundSubStatus)}
            aria-label="Filtrar por subgrupo de devolução"
            className="w-[320px]"
          >
            <option value="all">Todos</option>
            <option value="scheduled">Devolução Programada</option>
            <option value="pending">Valor Pendente de Devolução</option>
          </Select>
        )}

        {/* Lista */}
        <div className="flex flex-col gap-4">
          {filteredProposals.length === 0 ? (
            <div className="text-center py-8 text-dim">Nenhuma proposta encontrada para este status.</div>
          ) : (
            filteredProposals.map((proposal) => {
              // Painel detalhado: aguardando pagamento
              if (proposal.status === "awaiting_payment") {
                return (
                  <div key={proposal.id} className="bg-panel border border-edge rounded-lg p-6">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                      <CampoPainel rotulo="Número da Proposta:" valor={proposal.number} tom="azul" />
                      <CampoPainel rotulo="Nome:" valor={proposal.insuredName} />
                      <CampoPainel rotulo="CPF:" valor={proposal.cpf} />
                      <CampoPainel rotulo="Produto:" valor={proposal.product} />
                      <CampoPainel rotulo="Valor:" valor={proposal.value} tom="azul" />
                      <CampoPainel rotulo="Telefone:" valor={proposal.phone} />
                      <CampoPainel rotulo="E-mail:" valor={proposal.email} />
                      {proposal.paymentMethod && <CampoPainel rotulo="Forma de Pagamento:" valor={proposal.paymentMethod} />}
                      {proposal.daysInPending && <CampoPainel rotulo="Dias Pendente:" valor={`${proposal.daysInPending} dias`} tom="laranja" />}
                    </div>
                    <div className="flex gap-2 pt-4 border-t border-edge">
                      <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                        Alterar forma de pagamento
                      </Button>
                    </div>
                  </div>
                );
              }

              // Painel detalhado: pendência documental
              if (proposal.status === "pending_documentation") {
                return (
                  <div key={proposal.id} className="bg-panel border border-edge rounded-lg p-6">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                      <CampoPainel rotulo="Número da Proposta:" valor={proposal.number} tom="azul" />
                      <CampoPainel rotulo="Nome:" valor={proposal.insuredName} />
                      <CampoPainel rotulo="CPF:" valor={proposal.cpf} />
                      <CampoPainel rotulo="Produto:" valor={proposal.product} />
                      <CampoPainel rotulo="Valor:" valor={proposal.value} tom="azul" />
                      <CampoPainel rotulo="Telefone:" valor={proposal.phone} />
                      <CampoPainel rotulo="E-mail:" valor={proposal.email} />
                      {proposal.documentSubStatus && (
                        <CampoPainel rotulo="Pendência:" valor={DOC_SUB_LABELS[proposal.documentSubStatus]} tom="vermelho" className="col-span-2" />
                      )}
                      {proposal.daysInPending && <CampoPainel rotulo="Dias Pendente:" valor={`${proposal.daysInPending} dias`} tom="vermelho" />}
                    </div>
                    <div className="flex gap-2 pt-4 border-t border-edge flex-wrap">
                      <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                        <ExternalLink className="h-4 w-4" />
                        Upload de Documentos
                      </Button>
                      <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                        <History className="h-4 w-4" />
                        Histórico de Sensibilização
                      </Button>
                    </div>
                  </div>
                );
              }

              // Painel detalhado: devolução / valores programados (com timeline)
              if (proposal.status === "refund_scheduled" || proposal.status === "refund_pending" || proposal.status === "valores_programados") {
                return (
                  <div key={proposal.id} className="bg-panel border border-edge rounded-lg p-6">
                    <div className="mb-6">
                      <ProposalTimelineOrq currentStatus={proposal.status === "refund_pending" ? "refund_pending" : "awaiting_payment"} />
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                      <CampoPainel rotulo="Nome:" valor={proposal.insuredName} />
                      <CampoPainel rotulo="CPF:" valor={proposal.cpf} />
                      <CampoPainel rotulo="Número da Proposta:" valor={proposal.number} />
                      <CampoPainel rotulo="Produto:" valor={proposal.product} />
                      <CampoPainel rotulo="Apólice:" valor={proposal.policy} />
                      <CampoPainel rotulo="Valor da Devolução:" valor={proposal.value} tom="azul" />
                      <CampoPainel rotulo="Telefone:" valor={proposal.phone} />
                      <CampoPainel rotulo="E-mail:" valor={proposal.email} />
                      {proposal.status === "refund_scheduled" || proposal.status === "valores_programados" ? (
                        <CampoPainel rotulo="Data prevista para o crédito:" valor={proposal.refundDate} tom="verde" />
                      ) : (
                        <CampoPainel rotulo="Número de Recibo:" valor={proposal.receiptNumber} />
                      )}
                      {proposal.declineReason && (
                        <CampoPainel rotulo="Motivo do Declínio:" valor={proposal.declineReason} tom="vermelho" className="col-span-2 md:col-span-3" />
                      )}
                    </div>
                    {proposal.status === "refund_pending" && proposal.refundSubStatus === "pending" && (
                      <div className="flex gap-2 pt-4 border-t border-edge flex-wrap">
                        <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                          <DollarSign className="h-4 w-4" />
                          Gerenciar Devolução
                        </Button>
                        <Button variant="secondary" size="sm" disabled title={TITULO_FASE}>
                          <PlusCircle className="h-4 w-4" />
                          Nova Venda
                        </Button>
                      </div>
                    )}
                  </div>
                );
              }

              return <ProposalCardOrq key={proposal.id} proposal={proposal} />;
            })
          )}
        </div>
      </div>

      {/* Balão de ajuda do status — Modal nativo (mesmo padrão do Monitoramento) */}
      <Modal open={ajudaAberta && !!ajuda} onClose={() => setAjudaAberta(false)} title="Sobre este status" size="lg">
        {ajuda && (
          <div className="flex items-start gap-5">
            <img
              src={ajuda.avatar}
              alt={ajuda.avatarName}
              className="w-24 h-24 rounded-full border-4 border-[#1A5FA8] shadow object-cover shrink-0 animate-bounce"
              style={{ animationDuration: "2s" }}
            />
            <div className="flex-1 min-w-0">
              <div className="relative bg-[#1A5FA8] text-white rounded-2xl p-5 shadow">
                <div className="absolute -left-2 top-6 w-0 h-0 border-t-8 border-t-transparent border-b-8 border-b-transparent border-r-8 border-r-[#1A5FA8]" />
                <p className="text-xs font-semibold opacity-90 mb-1">{ajuda.avatarName}</p>
                <p className="text-sm leading-relaxed">{ajuda.message}</p>
              </div>
              <div className="mt-4 flex justify-end">
                <Button variant="primary" size="sm" onClick={() => setAjudaAberta(false)}>Entendi!</Button>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* FABs contextuais por status (gate useAssistentesIA nos componentes) */}
      {(status === "pending_signature" || status === "pending_documentation") && (
        <ChatAssistantOrq
          assistente="lari"
          nome="Lari"
          avatar={lariAvatar}
          pageContext={`Acompanhamento - ${status === "pending_signature" ? "Aguardando Assinatura" : "Pendência Documental"}`}
          suggestedQuestions={
            status === "pending_signature"
              ? [
                  "Quantas propostas estão aguardando assinatura?",
                  "Como enviar o link de assinatura para o cliente?",
                  "Quais propostas estão há mais tempo pendentes?",
                  "Como reenviar um link de assinatura expirado?",
                ]
              : [
                  "Quais documentos estão pendentes?",
                  "Como fazer upload de documentos?",
                  "Quais propostas estão fora da conformidade?",
                  "Como verificar o status dos documentos enviados?",
                ]
          }
        />
      )}
      {(status === "awaiting_payment" || status === "refund_pending" || status === "refund_scheduled" || status === "signed_proposal") && (
        <ChatAssistantOrq
          assistente="diego"
          nome="Diego"
          avatar={diegoAvatar}
          pageContext={`Acompanhamento - ${
            status === "awaiting_payment" ? "Aguardando Pagamento" : status === "signed_proposal" ? "Proposta Assinada" : "Devolução"
          }`}
          suggestedQuestions={
            status === "awaiting_payment"
              ? [
                  "Quais são as formas de pagamento disponíveis?",
                  "Como enviar lembrete de pagamento ao cliente?",
                  "Quantas propostas estão aguardando pagamento?",
                  "Como alterar a forma de pagamento?",
                ]
              : status === "signed_proposal"
              ? [
                  "Quantas propostas foram assinadas este mês?",
                  "Qual o valor total das propostas assinadas?",
                  "Como acompanhar o ciclo de pagamento?",
                  "Quais propostas finalizaram o ciclo?",
                ]
              : [
                  "Como gerenciar uma devolução pendente?",
                  "Qual o motivo do declínio da proposta?",
                  "Como vincular uma nova venda ao recibo?",
                  "Quando será processada a devolução?",
                ]
          }
        />
      )}
      {(status === "pending_dps" || status === "valores_programados" || status === "sensitization_monitoring") && (
        <ChatAssistantOrq
          assistente="leo"
          nome="Léo"
          avatar={leoAvatar}
          pageContext={`Acompanhamento - ${
            status === "pending_dps" ? "Pendência de DPS" : status === "valores_programados" ? "Valores Programados" : "Sensibilização"
          }`}
          suggestedQuestions={
            status === "pending_dps"
              ? [
                  "O que é DPS e para que serve?",
                  "Como enviar o link da DPS ao cliente?",
                  "Quantas propostas estão pendentes de DPS?",
                  "O que acontece após o cliente preencher a DPS?",
                ]
              : status === "valores_programados"
              ? [
                  "Qual o valor total programado para este mês?",
                  "Como são calculados os valores programados?",
                  "Quais propostas têm valores programados?",
                  "Como consultar a previsão de recebimento?",
                ]
              : [
                  "O que são movimentos de sensibilização?",
                  "Como enviar um movimento EMT, MAN ou CAN?",
                  "Qual o histórico de sensibilização desta proposta?",
                  "Como acompanhar os movimentos pendentes?",
                ]
          }
        />
      )}
    </div>
  );
}
