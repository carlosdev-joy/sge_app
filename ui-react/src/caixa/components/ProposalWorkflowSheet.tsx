import { useState } from "react";
import { FileText } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Card, CardContent } from "./ui/card";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";

interface WorkflowProposal {
  id: number;
  number: string;
  insuredName: string;
  status: string;
  value: string;
  product: string;
  region: string;
  ageRange: string;
  broker: string;
  daysInPending: number;
}

const mockWorkflowProposals: WorkflowProposal[] = [
  {
    id: 1,
    number: "80316460327404",
    insuredName: "Maria Silva",
    status: "pending_signature",
    value: "R$ 2.200,00",
    product: "Perda de Renda",
    region: "Sul",
    ageRange: "45-60",
    broker: "Mariana",
    daysInPending: 5,
  },
  {
    id: 2,
    number: "80316460327405",
    insuredName: "João Santos",
    status: "approved",
    value: "R$ 1.800,00",
    product: "Vida Multipremiado",
    region: "Sudeste",
    ageRange: "30-40",
    broker: "João",
    daysInPending: 0,
  },
  {
    id: 3,
    number: "80316460327406",
    insuredName: "Ana Costa",
    status: "awaiting_upload",
    value: "R$ 3.000,00",
    product: "Vida Mulher",
    region: "Sul",
    ageRange: "50-65",
    broker: "Ana",
    daysInPending: 3,
  },
  {
    id: 4,
    number: "80316460327407",
    insuredName: "Carlos Oliveira",
    status: "pending_signature",
    value: "R$ 950,00",
    product: "Vida Conforto",
    region: "Nordeste",
    ageRange: "25-35",
    broker: "Carlos",
    daysInPending: 6,
  },
  {
    id: 5,
    number: "80316460327408",
    insuredName: "Fernanda Lima",
    status: "declined",
    value: "R$ 2.700,00",
    product: "Perda de Renda",
    region: "Centro-Oeste",
    ageRange: "35-50",
    broker: "Fernanda",
    daysInPending: 0,
  },
  {
    id: 6,
    number: "80316460327409",
    insuredName: "Rafael Mendes",
    status: "approved",
    value: "R$ 2.500,00",
    product: "Vida Mulher",
    region: "Sudeste",
    ageRange: "28-45",
    broker: "Rafael",
    daysInPending: 0,
  },
  {
    id: 7,
    number: "80316460327410",
    insuredName: "Paula Rodrigues",
    status: "awaiting_sensitivity",
    value: "R$ 1.950,00",
    product: "Vida Conforto",
    region: "Sul",
    ageRange: "40-55",
    broker: "Mariana",
    daysInPending: 2,
  },
  {
    id: 8,
    number: "80316460327411",
    insuredName: "Bruno Alves",
    status: "awaiting_payment_link",
    value: "R$ 3.200,00",
    product: "Vida Multipremiado",
    region: "Nordeste",
    ageRange: "35-50",
    broker: "João",
    daysInPending: 4,
  },
  {
    id: 9,
    number: "80316460327412",
    insuredName: "Juliana Ferreira",
    status: "sensitivity_error",
    value: "R$ 1.650,00",
    product: "Perda de Renda",
    region: "Sudeste",
    ageRange: "30-45",
    broker: "Ana",
    daysInPending: 7,
  },
  {
    id: 10,
    number: "80316460327413",
    insuredName: "Ricardo Souza",
    status: "cancelled",
    value: "R$ 2.100,00",
    product: "Vida Mulher",
    region: "Centro-Oeste",
    ageRange: "45-60",
    broker: "Carlos",
    daysInPending: 0,
  },
  {
    id: 11,
    number: "80316460327414",
    insuredName: "Camila Torres",
    status: "expired",
    value: "R$ 1.450,00",
    product: "Vida Conforto",
    region: "Sul",
    ageRange: "25-40",
    broker: "Fernanda",
    daysInPending: 0,
  },
  {
    id: 12,
    number: "80316460327415",
    insuredName: "Lucas Martins",
    status: "quote",
    value: "R$ 2.800,00",
    product: "Vida Multipremiado",
    region: "Sudeste",
    ageRange: "40-55",
    broker: "Rafael",
    daysInPending: 1,
  },
  {
    id: 13,
    number: "80316460327416",
    insuredName: "Beatriz Campos",
    status: "draft",
    value: "R$ 1.200,00",
    product: "Perda de Renda",
    region: "Nordeste",
    ageRange: "28-42",
    broker: "Mariana",
    daysInPending: 3,
  },
];

const statusInfo = [
  { status: "pending_signature", label: "Ag. Assinatura", count: 0 },
  { status: "approved", label: "Ass. e Sensibilizado", count: 0 },
  { status: "awaiting_sensitivity", label: "Ass. e Ag. Sensibilização", count: 0 },
  { status: "awaiting_payment_link", label: "Ag. Link Pagamento", count: 0 },
  { status: "sensitivity_error", label: "Erro de Sensibilização", count: 0 },
  { status: "cancelled", label: "Cancelada", count: 0 },
  { status: "expired", label: "Expirada", count: 0 },
  { status: "quote", label: "Cotação", count: 0 },
  { status: "draft", label: "Rascunho", count: 0 },
];

const ProposalWorkflowSheet = () => {
  const [selectedStatus, setSelectedStatus] = useState<string>("all");

  const getStatusCounts = () => {
    return statusInfo.map((info) => ({
      ...info,
      count: mockWorkflowProposals.filter((p) => p.status === info.status).length,
    }));
  };

  const filteredProposals =
    selectedStatus === "all"
      ? mockWorkflowProposals
      : mockWorkflowProposals.filter((p) => p.status === selectedStatus);

  const getStatusBadgeColor = (status: string) => {
    const colors: Record<string, string> = {
      pending_signature: "bg-[hsl(var(--orange))]",
      approved: "bg-[hsl(var(--green))]",
      awaiting_sensitivity: "bg-[hsl(var(--yellow))]",
      awaiting_payment_link: "bg-[hsl(var(--yellow))]",
      sensitivity_error: "bg-destructive",
      cancelled: "bg-muted",
      expired: "bg-muted",
      quote: "bg-[hsl(var(--chart-1))]",
      draft: "bg-[hsl(var(--chart-2))]",
      awaiting_upload: "bg-[hsl(var(--chart-3))]",
      declined: "bg-destructive",
    };
    return colors[status] || "bg-muted";
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending_signature: "Ag. Assinatura",
      approved: "Ass. e Sensibilizado",
      awaiting_sensitivity: "Ass. e Ag. Sensibilização",
      awaiting_payment_link: "Ag. Link Pagamento",
      sensitivity_error: "Erro de Sensibilização",
      cancelled: "Cancelada",
      expired: "Expirada",
      quote: "Cotação",
      draft: "Rascunho",
      awaiting_upload: "Aguardando Upload",
      declined: "Declinada",
    };
    return labels[status] || status;
  };

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button className="flex items-center gap-2 text-[#005CA9] hover:text-[#0073CF] transition-colors py-3 px-4 hover:bg-accent/50 rounded-lg">
          <FileText className="h-6 w-6" />
          <span className="font-semibold">Workflow</span>
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Workflow de Propostas</SheetTitle>
        </SheetHeader>

        <div className="mt-6">
          {/* Status Cards - Compact Version */}
          <div className="grid grid-cols-3 gap-2 mb-6">
            {getStatusCounts().map((item) => (
              <Card
                key={item.status}
                className={`${getStatusBadgeColor(item.status)} border-none cursor-pointer transition-all hover:scale-105`}
                onClick={() => setSelectedStatus(item.status)}
              >
                <CardContent className="p-3 text-white text-center">
                  <div className="text-xs font-medium mb-1">{item.label}</div>
                  <div className="text-2xl font-bold">{item.count}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Filter */}
          <div className="mb-4">
            <Select value={selectedStatus} onValueChange={setSelectedStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Filtrar por status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os Status</SelectItem>
                {statusInfo.map((info) => (
                  <SelectItem key={info.status} value={info.status}>
                    {info.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Proposals List */}
          <ScrollArea className="h-[calc(100vh-400px)]">
            <div className="space-y-3">
              {filteredProposals.map((proposal) => (
                <Card key={proposal.id} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <div className="font-semibold text-lg">{proposal.insuredName}</div>
                        <div className="text-sm text-muted-foreground">
                          Proposta: {proposal.number}
                        </div>
                      </div>
                      <Badge className={`${getStatusBadgeColor(proposal.status)} text-white`}>
                        {getStatusLabel(proposal.status)}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Produto:</span> {proposal.product}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Valor:</span> {proposal.value}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Região:</span> {proposal.region}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Corretor:</span> {proposal.broker}
                      </div>
                      {proposal.daysInPending > 0 && (
                        <div className="col-span-2 text-destructive font-medium">
                          ⏱️ {proposal.daysInPending} dias em pendência
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default ProposalWorkflowSheet;
