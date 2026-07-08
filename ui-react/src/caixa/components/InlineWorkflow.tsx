import { useState } from "react";
import { ChevronDown, ChevronUp, Send, Loader2 } from "lucide-react";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { Badge } from "./ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { ScrollArea } from "./ui/scroll-area";
import { useToast } from "../hooks/use-toast";
import ProposalDetailDialog from "./ProposalDetailDialog";
import ResendLinkDialog from "./ResendLinkDialog";
import DocumentUploadDialog from "./DocumentUploadDialog";
import DPSLinkDialog from "./DPSLinkDialog";
import SendAlertDialog from "./SendAlertDialog";
import PaymentOptionsDialog from "./PaymentOptionsDialog";
import RefundManagementDialog from "./RefundManagementDialog";

interface WorkflowProposal {
  id: string;
  number: string;
  insuredName: string;
  status: "pending_signature" | "approved" | "awaiting_payment" | "pending_documentation" | "declined" | "sensitization_monitoring" | "emission_sent" | "pending_dps" | "return_in_progress" | "signed_proposal" | "refund_scheduled" | "refund_pending";
  value: string;
  product: string;
  region: string;
  ageRange: string;
  broker: string;
  daysInPending: number;
  date: string;
  indicatorId: string;
  agency: string;
  cpf: string;
  phone: string;
  email: string;
  declineReason?: string;
  documentSubStatus?: "incomplete" | "mismatch" | "no_signature" | "illegible";
  paymentMethod?: "boleto" | "debit" | "credit";
  signedSubStatus?: "payment_cycle" | "payment_ended";
  refundSubStatus?: "scheduled" | "pending_value";
  policy?: string;
}

const mockWorkflowProposals: WorkflowProposal[] = [
  {
    id: "1",
    number: "80316460327404",
    insuredName: "Maria Silva",
    status: "pending_signature",
    value: "R$ 2.200,00",
    product: "Perda de Renda",
    region: "Sul",
    ageRange: "45-60",
    broker: "Mariana",
    daysInPending: 5,
    date: "23/10/2025",
    indicatorId: "106562-2",
    agency: "316",
    cpf: "397.750.878-48",
    phone: "(11) 98765-4321",
    email: "maria@example.com",
  },
  {
    id: "2",
    number: "80316460327405",
    insuredName: "João Santos",
    status: "approved",
    value: "R$ 1.800,00",
    product: "Vida Multipremiado",
    region: "Sudeste",
    ageRange: "30-40",
    broker: "João",
    daysInPending: 0,
    date: "22/10/2025",
    indicatorId: "106563-3",
    agency: "315",
    cpf: "123.456.789-00",
    phone: "(11) 98765-4322",
    email: "joao@example.com",
  },
  {
    id: "3",
    number: "80316460327406",
    insuredName: "Ana Costa",
    status: "pending_documentation",
    value: "R$ 3.000,00",
    product: "Vida Mulher",
    region: "Sul",
    ageRange: "50-65",
    broker: "Ana",
    daysInPending: 8,
    date: "21/10/2025",
    indicatorId: "106564-4",
    agency: "314",
    cpf: "234.567.890-11",
    phone: "(11) 98765-4323",
    email: "ana@example.com",
    documentSubStatus: "incomplete",
  },
  {
    id: "4",
    number: "80316460327407",
    insuredName: "Carlos Oliveira",
    status: "pending_signature",
    value: "R$ 950,00",
    product: "Vida Conforto",
    region: "Nordeste",
    ageRange: "25-35",
    broker: "Carlos",
    daysInPending: 6,
    date: "20/10/2025",
    indicatorId: "106565-5",
    agency: "313",
    cpf: "345.678.901-22",
    phone: "(11) 98765-4324",
    email: "carlos@example.com",
  },
  {
    id: "5",
    number: "80316460327408",
    insuredName: "Fernanda Lima",
    status: "declined",
    value: "R$ 2.700,00",
    product: "Perda de Renda",
    region: "Centro-Oeste",
    ageRange: "35-50",
    broker: "Fernanda",
    daysInPending: 0,
    date: "19/10/2025",
    indicatorId: "106566-6",
    agency: "312",
    cpf: "456.789.012-33",
    phone: "(11) 98765-4325",
    email: "fernanda@example.com",
    declineReason: "Renda insuficiente para o valor solicitado. Perfil de risco não compatível com os critérios de aceitação.",
  },
  {
    id: "6",
    number: "80316460327409",
    insuredName: "Rafael Mendes",
    status: "sensitization_monitoring",
    value: "R$ 2.500,00",
    product: "Vida Mulher",
    region: "Sudeste",
    ageRange: "28-45",
    broker: "Rafael",
    daysInPending: 2,
    date: "18/10/2025",
    indicatorId: "106567-7",
    agency: "311",
    cpf: "567.890.123-44",
    phone: "(11) 98765-4326",
    email: "rafael@example.com",
  },
  {
    id: "7",
    number: "80316460327410",
    insuredName: "Paula Rodrigues",
    status: "declined",
    value: "R$ 1.500,00",
    product: "Vida Conforto",
    region: "Norte",
    ageRange: "40-55",
    broker: "Paula",
    daysInPending: 0,
    date: "17/10/2025",
    indicatorId: "106568-8",
    agency: "310",
    cpf: "678.901.234-55",
    phone: "(11) 98765-4327",
    email: "paula@example.com",
    declineReason: "Histórico de saúde pré-existente incompatível com as condições da apólice. Necessária reavaliação médica.",
  },
  {
    id: "8",
    number: "80316460327411",
    insuredName: "Bruno Alves",
    status: "sensitization_monitoring",
    value: "R$ 3.200,00",
    product: "Perda de Renda",
    region: "Sul",
    ageRange: "35-50",
    broker: "Bruno",
    daysInPending: 4,
    date: "16/10/2025",
    indicatorId: "106569-9",
    agency: "309",
    cpf: "789.012.345-66",
    phone: "(11) 98765-4328",
    email: "bruno@example.com",
  },
  {
    id: "9",
    number: "80316460327412",
    insuredName: "Juliana Costa",
    status: "pending_documentation",
    value: "R$ 1.900,00",
    product: "Vida Conforto",
    region: "Nordeste",
    ageRange: "30-45",
    broker: "Juliana",
    daysInPending: 10,
    date: "15/10/2025",
    indicatorId: "106570-0",
    agency: "308",
    cpf: "890.123.456-77",
    phone: "(11) 98765-4329",
    email: "juliana@example.com",
    documentSubStatus: "mismatch",
  },
  {
    id: "10",
    number: "80316460327413",
    insuredName: "Roberto Silva",
    status: "pending_documentation",
    value: "R$ 2.100,00",
    product: "Vida Mulher",
    region: "Sul",
    ageRange: "40-55",
    broker: "Roberto",
    daysInPending: 7,
    date: "14/10/2025",
    indicatorId: "106571-1",
    agency: "307",
    cpf: "901.234.567-88",
    phone: "(11) 98765-4330",
    email: "roberto@example.com",
    documentSubStatus: "no_signature",
  },
  {
    id: "11",
    number: "80316460327414",
    insuredName: "Carla Mendes",
    status: "pending_documentation",
    value: "R$ 1.750,00",
    product: "Perda de Renda",
    region: "Centro-Oeste",
    ageRange: "35-50",
    broker: "Carla",
    daysInPending: 12,
    date: "13/10/2025",
    indicatorId: "106572-2",
    agency: "306",
    cpf: "012.345.678-99",
    phone: "(11) 98765-4331",
    email: "carla@example.com",
    documentSubStatus: "illegible",
  },
  {
    id: "12",
    number: "80316460327415",
    insuredName: "Pedro Santos",
    status: "awaiting_payment",
    value: "R$ 2.400,00",
    product: "Vida Multipremiado",
    region: "Sudeste",
    ageRange: "30-40",
    broker: "Pedro",
    daysInPending: 4,
    date: "12/10/2025",
    indicatorId: "106573-3",
    agency: "305",
    cpf: "123.456.789-10",
    phone: "(11) 98765-4332",
    email: "pedro@example.com",
    paymentMethod: "debit",
  },
  {
    id: "13",
    number: "80316460327416",
    insuredName: "Lucia Oliveira",
    status: "awaiting_payment",
    value: "R$ 1.650,00",
    product: "Vida Conforto",
    region: "Norte",
    ageRange: "45-60",
    broker: "Lucia",
    daysInPending: 6,
    date: "11/10/2025",
    indicatorId: "106574-4",
    agency: "304",
    cpf: "234.567.890-21",
    phone: "(11) 98765-4333",
    email: "lucia@example.com",
    paymentMethod: "boleto",
  },
  {
    id: "13b",
    number: "80316460327414",
    insuredName: "Antonio Souza",
    status: "awaiting_payment",
    value: "R$ 1.980,00",
    product: "Vida Multipremiado",
    region: "Centro-Oeste",
    ageRange: "35-50",
    broker: "Antonio",
    daysInPending: 3,
    date: "11/10/2025",
    indicatorId: "106574-5",
    agency: "304",
    cpf: "345.678.901-43",
    phone: "(11) 98765-4337",
    email: "antonio@example.com",
    paymentMethod: "credit",
  },
  {
    id: "14",
    number: "80316460327417",
    insuredName: "Marcos Costa",
    status: "pending_dps",
    value: "R$ 2.800,00",
    product: "Vida Mulher",
    region: "Sul",
    ageRange: "50-65",
    broker: "Marcos",
    daysInPending: 5,
    date: "10/10/2025",
    indicatorId: "106575-5",
    agency: "303",
    cpf: "345.678.901-32",
    phone: "(11) 98765-4334",
    email: "marcos@example.com",
  },
  {
    id: "15",
    number: "80316460327418",
    insuredName: "Adriana Lima",
    status: "signed_proposal",
    value: "R$ 1.950,00",
    product: "Perda de Renda",
    region: "Nordeste",
    ageRange: "35-50",
    broker: "Adriana",
    daysInPending: 0,
    date: "09/10/2025",
    indicatorId: "106576-6",
    agency: "302",
    cpf: "456.789.012-43",
    phone: "(11) 98765-4335",
    email: "adriana@example.com",
    signedSubStatus: "payment_cycle",
    policy: "12345678",
  },
  {
    id: "16",
    number: "80316460327419",
    insuredName: "Ricardo Santos",
    status: "refund_scheduled",
    value: "R$ 2.300,00",
    product: "Vida Mulher",
    region: "Sul",
    ageRange: "40-55",
    broker: "Ricardo",
    daysInPending: 7,
    date: "08/10/2025",
    indicatorId: "106577-7",
    agency: "301",
    cpf: "567.890.123-54",
    phone: "(11) 98765-4336",
    email: "ricardo@example.com",
    declineReason: "Informações inconsistentes na documentação.",
    refundSubStatus: "pending_value",
    policy: "23456789",
  },
];

const statusInfo = [
  { value: "all", label: "Todas as Propostas", count: 0 },
  { value: "pending_signature", label: "Aguardando Assinatura", count: 0 },
  { value: "approved", label: "Ass. e Sensibilizado", count: 0 },
  { value: "awaiting_payment", label: "Aguardando Pagamento", count: 0 },
  { value: "signed_proposal", label: "Proposta Assinada", count: 0 },
  { value: "pending_documentation", label: "Pendência Documental", count: 0 },
  { value: "pending_dps", label: "Pendência de DPS", count: 0 },
  { value: "sensitization_monitoring", label: "Monitoramento de Sensibilização", count: 0 },
  { value: "return_in_progress", label: "Devolução em Andamento", count: 0 },
 
  { value: "refund_scheduled", label: "Propostas Declinadas", count: 0 },
 
];

const documentSubStatusLabels: Record<string, string> = {
  incomplete: "Proposta incompleta",
  mismatch: "Documento não corresponde a proposta",
  no_signature: "Proposta sem assinatura",
  illegible: "Documento Ilegível",
};

const InlineWorkflow = () => {
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
  const { toast } = useToast();

  const getStatusCounts = () => {
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
      if (counts[currentStatus] !== undefined) {
        counts[currentStatus]++;
      }
    });

    return counts;
  };

  const counts = getStatusCounts();

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

  const getStatusBadgeColor = (status: string) => {
    const statusColors: Record<string, string> = {
      pending_signature: "bg-[hsl(var(--orange))]",
      approved: "bg-[hsl(var(--green))]",
      awaiting_payment: "bg-[hsl(var(--yellow))]",
      signed_proposal: "bg-[hsl(var(--green))]",
      pending_documentation: "bg-destructive",
      pending_dps: "bg-[hsl(var(--blue))]",
      sensitization_monitoring: "bg-[hsl(var(--chart-5))]",
      return_in_progress: "bg-[hsl(var(--chart-3))]",
      declined: "bg-[hsl(var(--chart-4))]",
      emission_sent: "bg-[hsl(var(--blue))]",
      refund_scheduled: "bg-red-600",
    };
    return statusColors[status] || "bg-secondary";
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
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
    return labels[status] || status;
  };

  const handleSendEmission = async (proposalId: string) => {
    setSendingEmission(proposalId);
    
    setTimeout(() => {
      setProposalStatuses((prev) => ({
        ...prev,
        [proposalId]: "emission_sent",
      }));
      setSendingEmission(null);
      toast({
        title: "Movimento de Emissão Enviado",
        description: "O movimento foi enviado com sucesso. Aguardando confirmação.",
      });
    }, 2000);
  };

  const handleProposalClick = (proposal: WorkflowProposal) => {
    setSelectedProposal(proposal);
    setDetailDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="border rounded-lg bg-card">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-accent/50 transition-colors rounded-lg"
        >
          <div className="flex items-center gap-3">
            <span className="font-semibold text-lg">Workflow</span>
            <Badge variant="secondary">{counts.all} propostas</Badge>
          </div>
          {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </button>

        {isExpanded && (
          <div className="p-6 border-t space-y-4">
            {/* Status Summary Cards */}
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
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="text-xs font-medium text-center">{status.label}</div>
                  <div className="text-xl font-bold text-center mt-1">{counts[status.value]}</div>
                </button>
              ))}
            </div>

            {/* Filter Selects */}
            <div className="flex gap-3">
              <div className="flex-1">
                <Select value={selectedStatus} onValueChange={(value) => {
                  setSelectedStatus(value);
                  setSelectedSubStatus("all");
                }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Filtrar por status" />
                  </SelectTrigger>
                  <SelectContent>
                    {statusInfo.map((status) => (
                      <SelectItem key={status.value} value={status.value}>
                        {status.label} ({counts[status.value]})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              {selectedStatus === "pending_documentation" && (
                <div className="flex-1">
                  <Select value={selectedSubStatus} onValueChange={setSelectedSubStatus}>
                    <SelectTrigger>
                      <SelectValue placeholder="Filtrar por sub-status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos os sub-status</SelectItem>
                      <SelectItem value="incomplete">Proposta incompleta</SelectItem>
                      <SelectItem value="mismatch">Documento não corresponde</SelectItem>
                      <SelectItem value="no_signature">Proposta sem assinatura</SelectItem>
                      <SelectItem value="illegible">Documento Ilegível</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {selectedStatus === "signed_proposal" && (
                <div className="flex-1">
                  <Select value={selectedSubStatus} onValueChange={setSelectedSubStatus}>
                    <SelectTrigger>
                      <SelectValue placeholder="Filtrar por sub-status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos os sub-status</SelectItem>
                      <SelectItem value="payment_cycle">Propostas em fase pagamento</SelectItem>
                      <SelectItem value="payment_ended">Propostas com ciclo de pagamento encerrado</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {selectedStatus === "refund_scheduled" && (
                <div className="flex-1">
                  <Select value={selectedSubStatus} onValueChange={setSelectedSubStatus}>
                    <SelectTrigger>
                      <SelectValue placeholder="Filtrar por sub-status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos os sub-status</SelectItem>
                      <SelectItem value="scheduled">Devolução Programada</SelectItem>
                      <SelectItem value="pending_value">Valor Pendente de Devolução</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            {/* Send Alert Button */}
            {filteredProposals.length > 0 && selectedStatus !== "all" && selectedStatus !== "approved" && (
              <Button
                onClick={() => setAlertDialogOpen(true)}
                className="w-full bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
              >
                Enviar Alertas para Responsáveis
              </Button>
            )}

            {/* Proposals List */}
            <ScrollArea className="h-[400px]">
              <div className="space-y-3">
                {filteredProposals.map((proposal) => {
                  const currentStatus = proposalStatuses[proposal.id] || proposal.status;
                  return (
                    <Card
                      key={proposal.id}
                      className="hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => handleProposalClick(proposal)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 space-y-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold">{proposal.number}</span>
                              <Badge className={`${getStatusBadgeColor(currentStatus)} text-white`}>
                                {getStatusLabel(currentStatus)}
                              </Badge>
                              {proposal.daysInPending > 0 && (
                                <Badge variant="outline" className="border-orange-500 text-orange-500">
                                  {proposal.daysInPending} dias pendente
                                </Badge>
                              )}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              <p className="font-medium text-foreground">{proposal.insuredName}</p>
                              <p>{proposal.product} - {proposal.value}</p>
                              <p>Região: {proposal.region} | Faixa: {proposal.ageRange}</p>
                              {currentStatus === "pending_documentation" && proposal.documentSubStatus && (
                                <p className="text-destructive font-medium">
                                  {documentSubStatusLabels[proposal.documentSubStatus]}
                                </p>
                              )}
                              {currentStatus === "awaiting_payment" && proposal.paymentMethod && (
                                <p className="font-medium">
                                  Forma de Pagamento: {
                                    proposal.paymentMethod === "boleto" ? "Boleto" : 
                                    proposal.paymentMethod === "debit" ? "Débito em Conta" :
                                    "Crédito em Conta"
                                  }
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                            {currentStatus === "pending_signature" && (
                              <Button
                                size="sm"
                                onClick={() => {
                                  setSelectedProposal(proposal);
                                  setResendDialogOpen(true);
                                }}
                                className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
                              >
                                <Send className="h-4 w-4 mr-1" />
                                Enviar
                              </Button>
                            )}
                            {currentStatus === "pending_documentation" && (
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={() => {
                                  setSelectedProposal(proposal);
                                  setUploadDialogOpen(true);
                                }}
                              >
                                Upload
                              </Button>
                            )}
                            {currentStatus === "pending_dps" && (
                              <Button
                                size="sm"
                                onClick={() => {
                                  setSelectedProposal(proposal);
                                  setDpsDialogOpen(true);
                                }}
                                className="bg-[hsl(var(--blue))] hover:bg-[hsl(var(--blue))]/90 text-white"
                              >
                                Enviar Link DPS
                              </Button>
                            )}
                            {currentStatus === "awaiting_payment" && (
                              <Button
                                size="sm"
                                onClick={() => {
                                  setSelectedProposal(proposal);
                                  setPaymentDialogOpen(true);
                                }}
                                className="bg-[hsl(var(--yellow))] hover:bg-[hsl(var(--yellow))]/90"
                              >
                                Alterar forma de pagamento
                              </Button>
                            )}
                            {currentStatus === "sensitization_monitoring" && (
                              <Button
                                size="sm"
                                onClick={() => handleSendEmission(proposal.id)}
                                disabled={sendingEmission === proposal.id}
                                className="bg-[hsl(var(--blue))] hover:bg-[hsl(var(--blue))]/90"
                              >
                                {sendingEmission === proposal.id ? (
                                  <>
                                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                    Enviando...
                                  </>
                                ) : (
                                  "Enviar movimento de Emissão"
                                )}
                              </Button>
                            )}
                            {currentStatus === "refund_scheduled" && (
                              <Button
                                size="sm"
                                onClick={() => {
                                  setSelectedProposal(proposal);
                                  setRefundDialogOpen(true);
                                }}
                                className="bg-red-600 hover:bg-red-600/90"
                              >
                                Gerenciar Devolução
                              </Button>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        )}
      </div>

      {selectedProposal && (
        <>
          <ProposalDetailDialog
            proposal={{
              ...selectedProposal,
              status: (proposalStatuses[selectedProposal.id] || selectedProposal.status) as typeof selectedProposal.status
            }}
            open={detailDialogOpen}
            onOpenChange={setDetailDialogOpen}
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
            onOpenChange={setResendDialogOpen}
          />
          <DocumentUploadDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={uploadDialogOpen}
            onOpenChange={setUploadDialogOpen}
          />
          <DPSLinkDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={dpsDialogOpen}
            onOpenChange={setDpsDialogOpen}
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
            onOpenChange={setPaymentDialogOpen}
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
            onOpenChange={setRefundDialogOpen}
            onStatusChange={() => {
              setProposalStatuses((prev) => ({
                ...prev,
                [selectedProposal.id]: "refund_scheduled",
              }));
            }}
          />
        </>
      )}
      
      <SendAlertDialog
        proposals={filteredProposals}
        open={alertDialogOpen}
        onOpenChange={setAlertDialogOpen}
      />
    </div>
  );
};

export default InlineWorkflow;
