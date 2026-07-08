import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Header from "../components/Header";
import MenuButton from "../components/MenuButton";
import ProposalWorkflowSheet from "../components/ProposalWorkflowSheet";
import ProposalCard from "../components/ProposalCard";
import ProposalTimeline from "../components/ProposalTimeline";
import SendAlertDialog from "../components/SendAlertDialog";
import RefundManagementDialog from "../components/RefundManagementDialog";
import NewSaleDialog from "../components/NewSaleDialog";
import SensitizationDialog from "../components/SensitizationDialog";
import DPSLinkDialog from "../components/DPSLinkDialog";
import PaymentOptionsDialog from "../components/PaymentOptionsDialog";
import LeoAssistant from "../components/LeoAssistant";
import DiegoAssistant from "../components/DiegoAssistant";
import LariAssistant from "../components/LariAssistant";
import DocumentUploadDialog from "../components/DocumentUploadDialog";
import SensitizationHistoryDialog from "../components/SensitizationHistoryDialog";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ArrowLeft, Mail, DollarSign, PlusCircle, History, ExternalLink, HelpCircle, X } from "lucide-react";
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

interface Proposal {
  id: string;
  number: string;
  insuredName: string;
  date: string;
  status: ProposalStatus;
  value: string;
  indicatorId: string;
  agency: string;
  cpf: string;
  product: string;
  phone: string;
  email: string;
  policy?: string;
  documentSubStatus?: DocumentSubStatus;
  signedSubStatus?: SignedSubStatus;
  refundSubStatus?: RefundSubStatus;
  paymentSubStatus?: PaymentSubStatus;
  broker?: string;
  declineReason?: string;
  refundDate?: string;
  receiptNumber?: string;
  paymentMethod?: string;
  daysInPending?: number;
}

const mockProposals: Proposal[] = [
  {
    id: "1",
    number: "8047413032422-7",
    insuredName: "DIEBSON BITENCOURT DA SILVA",
    date: "17/10/2025",
    status: "pending_signature",
    value: "R$ 5.624,75",
    indicatorId: "0000122795-B",
    agency: "474",
    cpf: "025.359.088-03",
    product: "Vida Multipremiado Total",
    phone: "(11) 98765-4321",
    email: "diebson@email.com",
    daysInPending: 5,
  },
  {
    id: "2",
    number: "8047413032423-8",
    insuredName: "MARIA OLIVEIRA SANTOS",
    date: "18/10/2025",
    status: "pending_signature",
    value: "R$ 3.200,00",
    indicatorId: "0000122796-C",
    agency: "474",
    cpf: "123.456.789-00",
    product: "Vida Mulher",
    phone: "(11) 91234-5678",
    email: "maria@email.com",
    daysInPending: 3,
  },
  {
    id: "3",
    number: "8047413032424-9",
    insuredName: "JOÃO CARLOS FERREIRA",
    date: "19/10/2025",
    status: "awaiting_payment",
    paymentSubStatus: "payment_phase",
    value: "R$ 4.500,00",
    indicatorId: "0000122797-D",
    agency: "474",
    cpf: "234.567.890-11",
    product: "Vida Conforto",
    phone: "(11) 92345-6789",
    email: "joao@email.com",
    paymentMethod: "Boleto",
    daysInPending: 7,
  },
  {
    id: "4",
    number: "8047413032425-0",
    insuredName: "ANA PAULA COSTA",
    date: "20/10/2025",
    status: "awaiting_payment",
    paymentSubStatus: "payment_ended_no_payment",
    value: "R$ 6.800,00",
    indicatorId: "0000122798-E",
    agency: "474",
    cpf: "345.678.901-22",
    product: "Perda de Renda",
    phone: "(11) 93456-7890",
    email: "ana@email.com",
    paymentMethod: "Débito em Conta",
    daysInPending: 4,
  },
  {
    id: "5",
    number: "8047413032426-1",
    insuredName: "PEDRO HENRIQUE LIMA",
    date: "21/10/2025",
    status: "signed_proposal",
    signedSubStatus: "payment_cycle",
    value: "R$ 5.100,00",
    indicatorId: "0000122799-F",
    agency: "474",
    cpf: "456.789.012-33",
    product: "Vida Multipremiado Total",
    policy: "POL-2024-001",
    phone: "(11) 94567-8901",
    email: "pedro@email.com",
  },
  {
    id: "6",
    number: "8047413032427-2",
    insuredName: "CARLA REGINA SOUZA",
    date: "22/10/2025",
    status: "signed_proposal",
    signedSubStatus: "payment_ended",
    value: "R$ 7.300,00",
    indicatorId: "0000122800-G",
    agency: "474",
    cpf: "567.890.123-44",
    product: "Vida Mulher",
    policy: "POL-2024-002",
    phone: "(11) 95678-9012",
    email: "carla@email.com",
  },
  {
    id: "7",
    number: "8047413032428-3",
    insuredName: "ROBERTO SILVA SANTOS",
    date: "23/10/2025",
    status: "pending_documentation",
    value: "R$ 4.200,00",
    indicatorId: "0000122801-H",
    agency: "474",
    cpf: "678.901.234-55",
    product: "Vida Conforto",
    phone: "(11) 96789-0123",
    email: "roberto@email.com",
    documentSubStatus: "incomplete",
    broker: "João Silva",
    daysInPending: 12,
  },
  {
    id: "8",
    number: "8047413032429-4",
    insuredName: "LUCIA MARIA FERNANDES",
    date: "24/10/2025",
    status: "pending_documentation",
    value: "R$ 5.800,00",
    indicatorId: "0000122802-I",
    agency: "474",
    cpf: "789.012.345-66",
    product: "Perda de Renda",
    phone: "(11) 97890-1234",
    email: "lucia@email.com",
    documentSubStatus: "illegible",
    broker: "Maria Santos",
    daysInPending: 8,
  },
  {
    id: "14",
    number: "8047413032435-0",
    insuredName: "AMANDA CRISTINA ROCHA",
    date: "30/10/2025",
    status: "pending_documentation",
    value: "R$ 3.900,00",
    indicatorId: "0000122808-O",
    agency: "474",
    cpf: "345.678.901-30",
    product: "Vida Mulher",
    phone: "(11) 94444-5555",
    email: "amanda@email.com",
    documentSubStatus: "not_match",
    broker: "Carlos Pereira",
    daysInPending: 6,
  },
  {
    id: "15",
    number: "8047413032436-1",
    insuredName: "EDUARDO SANTOS LIMA",
    date: "31/10/2025",
    status: "pending_documentation",
    value: "R$ 5.200,00",
    indicatorId: "0000122809-P",
    agency: "474",
    cpf: "456.789.012-40",
    product: "Vida Multipremiado Total",
    phone: "(11) 95555-6666",
    email: "eduardo@email.com",
    documentSubStatus: "no_signature",
    broker: "Ana Paula",
    daysInPending: 10,
  },
  {
    id: "16",
    number: "8047413032437-2",
    insuredName: "MARCOS VINÍCIUS ALMEIDA",
    date: "01/11/2025",
    status: "pending_documentation",
    value: "R$ 650.000,00",
    indicatorId: "0000122810-Q",
    agency: "474",
    cpf: "567.890.123-50",
    product: "Previdência PGBL",
    phone: "(11) 96666-7777",
    email: "marcos@email.com",
    documentSubStatus: "non_compliant",
    broker: "Roberto Lima",
    daysInPending: 15,
  },
  {
    id: "17",
    number: "8047413032438-3",
    insuredName: "JULIANA COSTA PEREIRA",
    date: "02/11/2025",
    status: "pending_documentation",
    value: "R$ 820.000,00",
    indicatorId: "0000122811-R",
    agency: "474",
    cpf: "678.901.234-60",
    product: "Previdência VGBL",
    phone: "(11) 97777-8888",
    email: "juliana@email.com",
    documentSubStatus: "non_compliant",
    broker: "Patricia Santos",
    daysInPending: 18,
  },
  {
    id: "18",
    number: "8047413032439-4",
    insuredName: "ANTONIO CARLOS RODRIGUES",
    date: "03/11/2025",
    status: "pending_documentation",
    value: "R$ 45.000,00",
    indicatorId: "0000122812-S",
    agency: "474",
    cpf: "789.012.345-70",
    product: "Previdência Total",
    phone: "(11) 98888-9999",
    email: "antonio@email.com",
    documentSubStatus: "procuration_curatela",
    broker: "Fernando Alves",
    daysInPending: 9,
  },
  {
    id: "19",
    number: "8047413032440-5",
    insuredName: "BEATRIZ OLIVEIRA SOUZA",
    date: "04/11/2025",
    status: "pending_documentation",
    value: "R$ 32.500,00",
    indicatorId: "0000122813-T",
    agency: "474",
    cpf: "890.123.456-80",
    product: "Previdência Ativa",
    phone: "(11) 99999-0000",
    email: "beatriz@email.com",
    documentSubStatus: "procuration_curatela",
    broker: "Carla Regina",
    daysInPending: 11,
  },
  {
    id: "9",
    number: "8047413032430-5",
    insuredName: "FERNANDO AUGUSTO LIMA",
    date: "25/10/2025",
    status: "refund_scheduled",
    refundSubStatus: "scheduled",
    value: "R$ 3.500,00",
    indicatorId: "0000122803-J",
    agency: "474",
    cpf: "890.123.456-77",
    product: "Vida Multipremiado Total",
    policy: "POL-2024-003",
    phone: "(11) 98901-2345",
    email: "fernando@email.com",
    declineReason: "Análise de crédito negativa",
    refundDate: "15/12/2025",
  },
  {
    id: "10",
    number: "8047413032431-6",
    insuredName: "PATRICIA SANTOS COSTA",
    date: "26/10/2025",
    status: "refund_pending",
    refundSubStatus: "pending",
    value: "R$ 4.900,00",
    indicatorId: "0000122804-K",
    agency: "474",
    cpf: "901.234.567-88",
    product: "Vida Mulher",
    policy: "POL-2024-004",
    phone: "(11) 99012-3456",
    email: "patricia@email.com",
    declineReason: "Documentação irregular",
    receiptNumber: "REC-2024-12345",
  },
  {
    id: "13",
    number: "8047413032434-9",
    insuredName: "RAFAEL MENDES ALMEIDA",
    date: "29/10/2025",
    status: "refund_pending",
    refundSubStatus: "pending",
    value: "R$ 3.300,00",
    indicatorId: "0000122807-N",
    agency: "474",
    cpf: "234.567.890-20",
    product: "Vida Conforto",
    policy: "POL-2024-006",
    phone: "(11) 93333-4444",
    email: "rafael@email.com",
    declineReason: "Análise de risco",
    receiptNumber: "REC-2024-12346",
  },
  {
    id: "11",
    number: "8047413032432-7",
    insuredName: "MARCOS ANTONIO PEREIRA",
    date: "27/10/2025",
    status: "pending_dps",
    value: "R$ 2.800,00",
    indicatorId: "0000122805-L",
    agency: "474",
    cpf: "012.345.678-99",
    product: "Vida Conforto",
    phone: "(11) 91111-2222",
    email: "marcos@email.com",
    broker: "Carlos Oliveira",
    daysInPending: 6,
  },
  {
    id: "12",
    number: "8047413032433-8",
    insuredName: "JULIANA ROCHA ALVES",
    date: "28/10/2025",
    status: "valores_programados",
    value: "R$ 5.200,00",
    indicatorId: "0000122806-M",
    agency: "474",
    cpf: "123.456.789-10",
    product: "Perda de Renda",
    policy: "POL-2024-005",
    phone: "(11) 92222-3333",
    email: "juliana@email.com",
    declineReason: "Não atende critérios de aceitação",
    refundDate: "20/12/2025",
  },
];

const ProposalTracking = () => {
  const { status } = useParams<{ status: string }>();
  const navigate = useNavigate();
  const [selectedStatus, setSelectedStatus] = useState<ProposalStatus | "all">("all");
  const [documentSubStatusFilter, setDocumentSubStatusFilter] = useState<DocumentSubStatus>("all");
  const [signedSubStatusFilter, setSignedSubStatusFilter] = useState<SignedSubStatus>("all");
  const [refundSubStatusFilter, setRefundSubStatusFilter] = useState<RefundSubStatus>("all");
  const [paymentSubStatusFilter, setPaymentSubStatusFilter] = useState<PaymentSubStatus>("all");
  const [isAlertDialogOpen, setIsAlertDialogOpen] = useState(false);
  const [isRefundDialogOpen, setIsRefundDialogOpen] = useState(false);
  const [isNewSaleDialogOpen, setIsNewSaleDialogOpen] = useState(false);
  const [isSensitizationDialogOpen, setIsSensitizationDialogOpen] = useState(false);
  const [isDPSDialogOpen, setIsDPSDialogOpen] = useState(false);
  const [isPaymentDialogOpen, setIsPaymentDialogOpen] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [selectedProposalForUpload, setSelectedProposalForUpload] = useState<Proposal | null>(null);
  const [isSensitizationHistoryOpen, setIsSensitizationHistoryOpen] = useState(false);
  const [selectedProposalForHistory, setSelectedProposalForHistory] = useState<Proposal | null>(null);
  const [activeStatusHelp, setActiveStatusHelp] = useState<boolean>(false);

  const statusHelpInfo: { [key: string]: { avatar: string; avatarName: string; message: string } } = {
    pending_signature: {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Este status corresponde a propostas que estão pendentes de assinatura. Você pode utilizar o botão 'Enviar Link' para enviar ao cliente o link para assinatura da proposta via e-mail, WhatsApp ou SMS!"
    },
    awaiting_payment: {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Estas são propostas já assinadas que aguardam o pagamento. Você pode gerenciar as opções de pagamento e enviar lembretes ao cliente através do botão 'Gerenciar Pagamento'."
    },
    pending_documentation: {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Propostas com pendências documentais precisam de documentos adicionais. Use o botão 'Upload de Documentos' para enviar os arquivos necessários e dar andamento à proposta."
    },
    pending_dps: {
      avatar: leoAvatar,
      avatarName: "Léo",
      message: "Pendência de DPS (Declaração Pessoal de Saúde) significa que o cliente precisa preencher informações de saúde. Clique em 'Enviar Link DPS' para enviar o formulário ao segurado."
    },
    refund_pending: {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Estas são propostas que foram declinadas pela seguradora. Você pode gerenciar o reembolso através do botão 'Gerenciar Reembolso' ou criar uma nova venda revisando as informações."
    }
  };

  useEffect(() => {
    if (status && (
      status === "pending_signature" || 
      status === "awaiting_payment" || 
      status === "signed_proposal" ||
      status === "pending_documentation" ||
      status === "pending_dps" || 
      status === "refund_scheduled" ||
      status === "refund_pending" ||
      status === "valores_programados" ||
      status === "sensitization_monitoring"
    )) {
      setSelectedStatus(status as ProposalStatus);
    }
  }, [status]);

  let filteredProposals = selectedStatus === "all" 
    ? mockProposals 
    : mockProposals.filter(p => p.status === selectedStatus);

  // Filter by document sub-status if applicable
  if (selectedStatus === "pending_documentation" && documentSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter(p => p.documentSubStatus === documentSubStatusFilter);
  }

  // Filter by signed sub-status if applicable
  if (selectedStatus === "signed_proposal" && signedSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter(p => p.signedSubStatus === signedSubStatusFilter);
  }

  // Filter by payment sub-status if applicable
  if (selectedStatus === "awaiting_payment" && paymentSubStatusFilter !== "all") {
    filteredProposals = filteredProposals.filter(p => p.paymentSubStatus === paymentSubStatusFilter);
  }

  // Filter by refund sub-status if applicable
  if ((selectedStatus === "refund_scheduled" || selectedStatus === "refund_pending") && refundSubStatusFilter !== "all") {
    const targetStatus = refundSubStatusFilter === "scheduled" ? "refund_scheduled" : "refund_pending";
    filteredProposals = mockProposals.filter(p => p.status === targetStatus);
  }

  const alertProposals = filteredProposals.map(p => ({
    id: p.id,
    number: p.number,
    insuredName: p.insuredName,
    broker: p.broker || "Não informado",
    agency: p.agency,
  }));

  const getStatusLabel = (status: ProposalStatus | "all") => {
    const labels: Record<string, string> = {
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
    return labels[status];
  };

  const getDocumentSubStatusLabel = (subStatus: DocumentSubStatus) => {
    const labels = {
      all: "Todos",
      incomplete: "Proposta incompleta",
      not_match: "Documento não corresponde a proposta",
      no_signature: "Proposta sem assinatura",
      illegible: "Documento Ilegível",
      non_compliant: "Propostas fora da conformidade",
      procuration_curatela: "Pendências relacionadas a Procuração/Curatela e A Rogo",
    };
    return labels[subStatus];
  };

  const getStatusColor = (status: ProposalStatus | "all") => {
    const colors: Record<string, string> = {
      all: "bg-primary text-white",
      pending_signature: "bg-[hsl(var(--orange))] text-white",
      awaiting_payment: "bg-[hsl(var(--yellow))] text-white",
      signed_proposal: "bg-[hsl(var(--green))] text-white",
      pending_documentation: "bg-destructive text-white",
      pending_dps: "bg-[hsl(var(--blue))] text-white",
      refund_scheduled: "bg-[hsl(var(--chart-2))] text-white",
      refund_pending: "bg-red-600 text-white",
      valores_programados: "bg-purple-600 text-white",
      sensitization_monitoring: "bg-[hsl(var(--chart-5))] text-white",
    };
    return colors[status] || "bg-primary text-white";
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <main className="container mx-auto px-6 py-8 max-w-7xl">
        <div className="mb-6 flex items-center gap-4">
          <Button
            variant="ghost"
            onClick={() => navigate(-1)}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Button>
          <MenuButton />
          <ProposalWorkflowSheet />
        </div>

        <div className="mb-8">
          <div className={`${selectedStatus === "pending_dps" ? "bg-[hsl(var(--blue))] text-black" : getStatusColor(selectedStatus as ProposalStatus)} px-6 py-4 rounded-lg mb-6`}>
            <div className="flex items-center justify-between">
              <h1 className="text-3xl font-bold">
                {getStatusLabel(selectedStatus)}
              </h1>
              {selectedStatus && statusHelpInfo[selectedStatus as string] && (
                <button
                  onClick={() => setActiveStatusHelp(true)}
                  className="hover:scale-110 transition-transform"
                >
                  <HelpCircle className="h-6 w-6 opacity-80 hover:opacity-100" />
                </button>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 mb-6">
            <Button
              onClick={() => setIsAlertDialogOpen(true)}
              className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
              disabled={filteredProposals.length === 0}
            >
              <Mail className="h-4 w-4 mr-2" />
              Enviar Alertas ({filteredProposals.length})
            </Button>
            {selectedStatus === "pending_documentation" && (
              <Button
                onClick={() => setIsUploadDialogOpen(true)}
                className="bg-green-600 hover:bg-green-700"
                disabled={filteredProposals.length === 0}
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Upload de Documentos
              </Button>
            )}
            {selectedStatus === "pending_dps" && filteredProposals.length > 0 && (
              <Button
                onClick={() => {
                  setSelectedProposal(filteredProposals[0]);
                  setIsDPSDialogOpen(true);
                }}
                className="bg-[hsl(var(--blue))] hover:bg-[hsl(var(--blue))]/90 text-white"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Enviar Link DPS
              </Button>
            )}
          </div>

          {/* Document Sub-Status Filter */}
          {selectedStatus === "pending_documentation" && (
            <div className="mb-6">
              <Select value={documentSubStatusFilter} onValueChange={(value) => setDocumentSubStatusFilter(value as DocumentSubStatus)}>
                <SelectTrigger className="w-[300px]">
                  <SelectValue placeholder="Filtrar por sub-status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="incomplete">Proposta incompleta</SelectItem>
                  <SelectItem value="not_match">Documento não corresponde a proposta</SelectItem>
                  <SelectItem value="no_signature">Proposta sem assinatura</SelectItem>
                  <SelectItem value="illegible">Documento Ilegível</SelectItem>
                  <SelectItem value="non_compliant">Propostas fora da conformidade</SelectItem>
                  <SelectItem value="procuration_curatela">Pendências Procuração/Curatela e A Rogo</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Signed Sub-Status Filter */}
          {selectedStatus === "signed_proposal" && (
            <div className="mb-6">
              <Select value={signedSubStatusFilter} onValueChange={(value) => setSignedSubStatusFilter(value as SignedSubStatus)}>
                <SelectTrigger className="w-[300px]">
                  <SelectValue placeholder="Filtrar por subgrupo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="payment_cycle">Propostas em fase pagamento</SelectItem>
                  <SelectItem value="payment_ended">Propostas com ciclo de pagamento encerrado</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Payment Sub-Status Filter */}
          {selectedStatus === "awaiting_payment" && (
            <div className="mb-6">
              <Select value={paymentSubStatusFilter} onValueChange={(value) => setPaymentSubStatusFilter(value as PaymentSubStatus)}>
                <SelectTrigger className="w-[350px]">
                  <SelectValue placeholder="Filtrar por substatus" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="payment_phase">Propostas em fase de pagamento</SelectItem>
                  <SelectItem value="payment_ended_no_payment">Ciclo encerrado sem quitação</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Refund Sub-Status Filter */}
          {(selectedStatus === "refund_scheduled" || selectedStatus === "refund_pending") && (
            <div className="mb-6">
              <Select value={refundSubStatusFilter} onValueChange={(value) => setRefundSubStatusFilter(value as RefundSubStatus)}>
                <SelectTrigger className="w-[300px]">
                  <SelectValue placeholder="Filtrar por subgrupo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="scheduled">Devolução Programada</SelectItem>
                  <SelectItem value="pending">Valor Pendente de Devolução</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-4">
            {filteredProposals.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                Nenhuma proposta encontrada para este status.
              </div>
            ) : (
              filteredProposals.map((proposal) => {
                // Detailed view for awaiting payment proposals
                if (proposal.status === "awaiting_payment") {
                  return (
                    <div key={proposal.id} className="bg-card border rounded-lg p-6">
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                        <div>
                          <span className="text-sm text-muted-foreground">Número da Proposta:</span>
                          <p className="font-semibold text-primary">{proposal.number}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Nome:</span>
                          <p className="font-semibold">{proposal.insuredName}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">CPF:</span>
                          <p className="font-semibold">{proposal.cpf}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Produto:</span>
                          <p className="font-semibold">{proposal.product}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Valor:</span>
                          <p className="font-semibold text-primary">{proposal.value}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Telefone:</span>
                          <p className="font-semibold">{proposal.phone}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">E-mail:</span>
                          <p className="font-semibold">{proposal.email}</p>
                        </div>
                        {proposal.paymentMethod && (
                          <div>
                            <span className="text-sm text-muted-foreground">Forma de Pagamento:</span>
                            <p className="font-semibold">
                              {proposal.paymentMethod === "Boleto" ? "Boleto" : 
                               proposal.paymentMethod === "Débito em Conta" ? "Débito em Conta" :
                               "Crédito em Conta"}
                            </p>
                          </div>
                        )}
                        {proposal.daysInPending && (
                          <div>
                            <span className="text-sm text-muted-foreground">Dias Pendente:</span>
                            <p className="font-semibold text-[hsl(var(--orange))]">{proposal.daysInPending} dias</p>
                          </div>
                        )}
                      </div>
                      
                      <div className="flex gap-2 pt-4 border-t">
                        <Button
                          onClick={() => {
                            setSelectedProposal(proposal);
                            setIsPaymentDialogOpen(true);
                          }}
                          size="sm"
                          className="bg-[hsl(var(--yellow))] hover:bg-[hsl(var(--yellow))]/90 text-white"
                        >
                          Alterar forma de pagamento
                        </Button>
                      </div>
                    </div>
                  );
                }

                // Detailed view for pending documentation proposals
                if (proposal.status === "pending_documentation") {
                  return (
                    <div key={proposal.id} className="bg-card border rounded-lg p-6">
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                        <div>
                          <span className="text-sm text-muted-foreground">Número da Proposta:</span>
                          <p className="font-semibold text-primary">{proposal.number}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Nome:</span>
                          <p className="font-semibold">{proposal.insuredName}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">CPF:</span>
                          <p className="font-semibold">{proposal.cpf}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Produto:</span>
                          <p className="font-semibold">{proposal.product}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Valor:</span>
                          <p className="font-semibold text-primary">{proposal.value}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Telefone:</span>
                          <p className="font-semibold">{proposal.phone}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">E-mail:</span>
                          <p className="font-semibold">{proposal.email}</p>
                        </div>
                        {proposal.documentSubStatus && (
                          <div className="col-span-2">
                            <span className="text-sm text-muted-foreground">Pendência:</span>
                            <p className="font-semibold text-destructive">
                              {getDocumentSubStatusLabel(proposal.documentSubStatus)}
                            </p>
                          </div>
                        )}
                        {proposal.daysInPending && (
                          <div>
                            <span className="text-sm text-muted-foreground">Dias Pendente:</span>
                            <p className="font-semibold text-destructive">{proposal.daysInPending} dias</p>
                          </div>
                        )}
                      </div>
                      
                      <div className="flex gap-2 pt-4 border-t">
                        <Button
                          onClick={() => {
                            setSelectedProposalForUpload(proposal);
                            setIsUploadDialogOpen(true);
                          }}
                          size="sm"
                          variant="outline"
                          className="bg-green-600 hover:bg-green-700 text-white border-green-700"
                        >
                          <ExternalLink className="h-4 w-4 mr-2" />
                          Upload de Documentos
                        </Button>
                        <Button
                          onClick={() => {
                            setSelectedProposalForHistory(proposal);
                            setIsSensitizationHistoryOpen(true);
                          }}
                          size="sm"
                          className="bg-[hsl(211,70%,50%)] hover:bg-[hsl(211,70%,45%)] text-white"
                        >
                          <History className="h-4 w-4 mr-2" />
                          Histórico de Sensibilização
                        </Button>
                      </div>
                    </div>
                  );
                }

                // Detailed view for refund proposals
                if (proposal.status === "refund_scheduled" || proposal.status === "refund_pending" || proposal.status === "valores_programados") {
                  return (
                    <div key={proposal.id} className="bg-card border rounded-lg p-6">
                      {/* Timeline at the top */}
                      <div className="mb-6">
                        <ProposalTimeline currentStatus={proposal.status === "refund_pending" ? "refund_pending" : "awaiting_payment"} />
                      </div>
                      
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                        <div>
                          <span className="text-sm text-muted-foreground">Nome:</span>
                          <p className="font-semibold">{proposal.insuredName}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">CPF:</span>
                          <p className="font-semibold">{proposal.cpf}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Número da Proposta:</span>
                          <p className="font-semibold">{proposal.number}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Produto:</span>
                          <p className="font-semibold">{proposal.product}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Apólice:</span>
                          <p className="font-semibold">{proposal.policy}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Valor da Devolução:</span>
                          <p className="font-semibold text-primary">{proposal.value}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Telefone:</span>
                          <p className="font-semibold">{proposal.phone}</p>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">E-mail:</span>
                          <p className="font-semibold">{proposal.email}</p>
                        </div>
                        {proposal.status === "refund_scheduled" || proposal.status === "valores_programados" ? (
                          <div>
                            <span className="text-sm text-muted-foreground">Data prevista para o crédito:</span>
                            <p className="font-semibold text-[hsl(var(--green))]">{proposal.refundDate}</p>
                          </div>
                        ) : (
                          <div>
                            <span className="text-sm text-muted-foreground">Número de Recibo:</span>
                            <p className="font-semibold">{proposal.receiptNumber}</p>
                          </div>
                        )}
                        {proposal.declineReason && (
                          <div className="col-span-2 md:col-span-3">
                            <span className="text-sm text-muted-foreground">Motivo do Declínio:</span>
                            <p className="font-semibold text-destructive">{proposal.declineReason}</p>
                          </div>
                        )}
                      </div>
                      
                      {/* Action Buttons for Refund Pending */}
                      {proposal.status === "refund_pending" && proposal.refundSubStatus === "pending" && (
                        <div className="flex gap-2 pt-4 border-t">
                          <Button
                            onClick={() => {
                              setSelectedProposal(proposal);
                              setIsRefundDialogOpen(true);
                            }}
                            size="sm"
                            className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white"
                          >
                            <DollarSign className="h-4 w-4 mr-2" />
                            Gerenciar Devolução
                          </Button>
                          <Button
                            onClick={() => {
                              setSelectedProposal(proposal);
                              setIsNewSaleDialogOpen(true);
                            }}
                            size="sm"
                            className="bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90 text-white"
                          >
                            <PlusCircle className="h-4 w-4 mr-2" />
                            Nova Venda
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                }
                
                return <ProposalCard key={proposal.id} proposal={proposal} />;
              })
            )}
          </div>
        </div>
      </main>

      <SendAlertDialog
        proposals={alertProposals}
        open={isAlertDialogOpen}
        onOpenChange={setIsAlertDialogOpen}
      />

      {selectedProposal && (
        <>
          <RefundManagementDialog
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              cpf: selectedProposal.cpf,
              value: selectedProposal.value,
              policy: selectedProposal.policy || selectedProposal.number,
              product: selectedProposal.product,
            }}
            open={isRefundDialogOpen}
            onOpenChange={setIsRefundDialogOpen}
          />

          <NewSaleDialog
            open={isNewSaleDialogOpen}
            onOpenChange={setIsNewSaleDialogOpen}
            receiptNumber={selectedProposal.receiptNumber || selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            prefillValue={selectedProposal.value}
          />
          
          <DPSLinkDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={isDPSDialogOpen}
            onOpenChange={setIsDPSDialogOpen}
          />

          <PaymentOptionsDialog
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              value: selectedProposal.value || "R$ 0,00",
              email: selectedProposal.email || "",
              phone: selectedProposal.phone || "",
              paymentMethod: selectedProposal.paymentMethod === "Crédito em Conta" ? "credit" : 
                            selectedProposal.paymentMethod === "Débito em Conta" ? "debit" : "boleto",
            }}
            open={isPaymentDialogOpen}
            onOpenChange={setIsPaymentDialogOpen}
          />
        </>
      )}

      <SensitizationDialog
        open={isSensitizationDialogOpen}
        onOpenChange={setIsSensitizationDialogOpen}
      />
      
      <DocumentUploadDialog
        open={isUploadDialogOpen}
        onOpenChange={setIsUploadDialogOpen}
        proposalNumber={selectedProposalForUpload?.number || ""}
        insuredName={selectedProposalForUpload?.insuredName || ""}
      />
      
      {selectedProposalForHistory && (
        <SensitizationHistoryDialog
          open={isSensitizationHistoryOpen}
          onOpenChange={setIsSensitizationHistoryOpen}
          proposalNumber={selectedProposalForHistory.number}
          insuredName={selectedProposalForHistory.insuredName}
        />
      )}
      
      {/* Status Help Dialog */}
      {activeStatusHelp && selectedStatus && statusHelpInfo[selectedStatus as string] && (
        <div 
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 animate-in fade-in-0"
          onClick={() => setActiveStatusHelp(false)}
        >
          <div 
            className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full animate-in zoom-in-95 slide-in-from-bottom-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-8 relative">
              <button
                onClick={() => setActiveStatusHelp(false)}
                className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="h-6 w-6" />
              </button>
              
              <div className="flex items-start gap-6">
                <div className="relative">
                  <img
                    src={statusHelpInfo[selectedStatus as string].avatar}
                    alt={statusHelpInfo[selectedStatus as string].avatarName}
                    className="w-32 h-32 rounded-full border-4 border-[hsl(211,70%,50%)] shadow-lg animate-bounce object-cover"
                    style={{ animationDuration: '2s' }}
                  />
                </div>
                
                <div className="flex-1">
                  <div className="bg-[hsl(211,70%,50%)] text-white rounded-2xl p-6 relative shadow-xl animate-in slide-in-from-left-5">
                    <div className="absolute -left-3 top-8 w-0 h-0 border-t-8 border-t-transparent border-b-8 border-b-transparent border-r-8 border-r-[hsl(211,70%,50%)]" />
                    <p className="text-sm font-semibold mb-2 opacity-90">
                      {statusHelpInfo[selectedStatus as string].avatarName}
                    </p>
                    <p className="text-lg leading-relaxed">
                      {statusHelpInfo[selectedStatus as string].message}
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="mt-6 flex justify-end">
                <Button
                  onClick={() => setActiveStatusHelp(false)}
                  className="bg-[hsl(211,70%,50%)] hover:bg-[hsl(211,70%,45%)] text-white"
                >
                  Entendi!
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Assistentes contextuais baseados no status */}
      {(status === "pending_signature" || status === "pending_documentation") && (
        <LariAssistant 
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
        <DiegoAssistant 
          pageContext={`Acompanhamento - ${
            status === "awaiting_payment" ? "Aguardando Pagamento" : 
            status === "signed_proposal" ? "Proposta Assinada" : "Devolução"
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
        <LeoAssistant 
          pageContext={`Acompanhamento - ${
            status === "pending_dps" ? "Pendência de DPS" : 
            status === "valores_programados" ? "Valores Programados" : "Sensibilização"
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
};

export default ProposalTracking;
