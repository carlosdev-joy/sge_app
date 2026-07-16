// "Workflow de Propostas" (gaveta) no DS nativo — porte do
// ProposalWorkflowSheet shadcn sobre o Sheet nativo novo (F8). Mesmo mock (13
// propostas), cards de status clicáveis, filtro e lista. O componente traz o
// próprio botão-gatilho, como o original.
import { useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Sheet } from "../../components/ui/Sheet";
import { Select } from "../../components/ui/Input";

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

// Mesmo mock da versão original.
const mockWorkflowProposals: WorkflowProposal[] = [
  { id: 1, number: "80316460327404", insuredName: "Maria Silva", status: "pending_signature", value: "R$ 2.200,00", product: "Perda de Renda", region: "Sul", ageRange: "45-60", broker: "Mariana", daysInPending: 5 },
  { id: 2, number: "80316460327405", insuredName: "João Santos", status: "approved", value: "R$ 1.800,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "30-40", broker: "João", daysInPending: 0 },
  { id: 3, number: "80316460327406", insuredName: "Ana Costa", status: "awaiting_upload", value: "R$ 3.000,00", product: "Vida Mulher", region: "Sul", ageRange: "50-65", broker: "Ana", daysInPending: 3 },
  { id: 4, number: "80316460327407", insuredName: "Carlos Oliveira", status: "pending_signature", value: "R$ 950,00", product: "Vida Conforto", region: "Nordeste", ageRange: "25-35", broker: "Carlos", daysInPending: 6 },
  { id: 5, number: "80316460327408", insuredName: "Fernanda Lima", status: "declined", value: "R$ 2.700,00", product: "Perda de Renda", region: "Centro-Oeste", ageRange: "35-50", broker: "Fernanda", daysInPending: 0 },
  { id: 6, number: "80316460327409", insuredName: "Rafael Mendes", status: "approved", value: "R$ 2.500,00", product: "Vida Mulher", region: "Sudeste", ageRange: "28-45", broker: "Rafael", daysInPending: 0 },
  { id: 7, number: "80316460327410", insuredName: "Paula Rodrigues", status: "awaiting_sensitivity", value: "R$ 1.950,00", product: "Vida Conforto", region: "Sul", ageRange: "40-55", broker: "Mariana", daysInPending: 2 },
  { id: 8, number: "80316460327411", insuredName: "Bruno Alves", status: "awaiting_payment_link", value: "R$ 3.200,00", product: "Vida Multipremiado", region: "Nordeste", ageRange: "35-50", broker: "João", daysInPending: 4 },
  { id: 9, number: "80316460327412", insuredName: "Juliana Ferreira", status: "sensitivity_error", value: "R$ 1.650,00", product: "Perda de Renda", region: "Sudeste", ageRange: "30-45", broker: "Ana", daysInPending: 7 },
  { id: 10, number: "80316460327413", insuredName: "Ricardo Souza", status: "cancelled", value: "R$ 2.100,00", product: "Vida Mulher", region: "Centro-Oeste", ageRange: "45-60", broker: "Carlos", daysInPending: 0 },
  { id: 11, number: "80316460327414", insuredName: "Camila Torres", status: "expired", value: "R$ 1.450,00", product: "Vida Conforto", region: "Sul", ageRange: "25-40", broker: "Fernanda", daysInPending: 0 },
  { id: 12, number: "80316460327415", insuredName: "Lucas Martins", status: "quote", value: "R$ 2.800,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "40-55", broker: "Rafael", daysInPending: 1 },
  { id: 13, number: "80316460327416", insuredName: "Beatriz Campos", status: "draft", value: "R$ 1.200,00", product: "Perda de Renda", region: "Nordeste", ageRange: "28-42", broker: "Mariana", daysInPending: 3 },
];

const statusInfo = [
  { status: "pending_signature", label: "Ag. Assinatura" },
  { status: "approved", label: "Ass. e Sensibilizado" },
  { status: "awaiting_sensitivity", label: "Ass. e Ag. Sensibilização" },
  { status: "awaiting_payment_link", label: "Ag. Link Pagamento" },
  { status: "sensitivity_error", label: "Erro de Sensibilização" },
  { status: "cancelled", label: "Cancelada" },
  { status: "expired", label: "Expirada" },
  { status: "quote", label: "Cotação" },
  { status: "draft", label: "Rascunho" },
];

// Cores das vars do tema antigo → fixas: --orange/--chart-2→#F26B00,
// --green/--chart-3→emerald-600, --yellow/--chart-4→amber-500,
// destructive→red-600, muted→slate-500, --chart-1→azul fechado #0F4C88.
const STATUS_COLORS: Record<string, string> = {
  pending_signature: "bg-[#F26B00]",
  approved: "bg-emerald-600",
  awaiting_sensitivity: "bg-amber-500",
  awaiting_payment_link: "bg-amber-500",
  sensitivity_error: "bg-red-600",
  cancelled: "bg-slate-500",
  expired: "bg-slate-500",
  quote: "bg-[#0F4C88]",
  draft: "bg-[#F26B00]",
  awaiting_upload: "bg-emerald-600",
  declined: "bg-red-600",
};

const STATUS_LABELS: Record<string, string> = {
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

export default function ProposalWorkflowSheet() {
  const [aberto, setAberto] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<string>("all");

  const counts = statusInfo.map((info) => ({
    ...info,
    count: mockWorkflowProposals.filter((p) => p.status === info.status).length,
  }));

  const filteredProposals =
    selectedStatus === "all"
      ? mockWorkflowProposals
      : mockWorkflowProposals.filter((p) => p.status === selectedStatus);

  return (
    <>
      <Button variant="secondary" size="md" onClick={() => setAberto(true)}>
        <FileText size={16} />
        Workflow
      </Button>

      <Sheet open={aberto} onClose={() => setAberto(false)} title="Workflow de Propostas" widthClass="max-w-2xl">
        {/* Cards de status (clicáveis: filtram a lista) */}
        <div className="grid grid-cols-3 gap-2 mb-6">
          {counts.map((item) => (
            <button
              key={item.status}
              onClick={() => setSelectedStatus(item.status)}
              className={`${STATUS_COLORS[item.status]} rounded-lg p-3 text-white text-center cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-white/90 mb-1 leading-tight">{item.label}</div>
              <div className="text-2xl font-bold tracking-tight">{item.count}</div>
            </button>
          ))}
        </div>

        {/* Filtro */}
        <div className="mb-4">
          <Select value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)} aria-label="Filtrar por status" className="w-full">
            <option value="all">Todos os Status</option>
            {statusInfo.map((info) => (
              <option key={info.status} value={info.status}>
                {info.label}
              </option>
            ))}
          </Select>
        </div>

        {/* Lista */}
        <div className="flex flex-col gap-3">
          {filteredProposals.map((proposal) => (
            <div key={proposal.id} className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-2 gap-3">
                <div>
                  <div className="font-semibold text-lg text-ink">{proposal.insuredName}</div>
                  <div className="text-sm text-dim">Proposta: {proposal.number}</div>
                </div>
                <span className={`${STATUS_COLORS[proposal.status] ?? "bg-slate-500"} text-white rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap`}>
                  {STATUS_LABELS[proposal.status] ?? proposal.status}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm text-ink">
                <div>
                  <span className="text-dim">Produto:</span> {proposal.product}
                </div>
                <div>
                  <span className="text-dim">Valor:</span> {proposal.value}
                </div>
                <div>
                  <span className="text-dim">Região:</span> {proposal.region}
                </div>
                <div>
                  <span className="text-dim">Corretor:</span> {proposal.broker}
                </div>
                {proposal.daysInPending > 0 && (
                  <div className="col-span-2 text-red-600 dark:text-red-400 font-medium">
                    ⏱️ {proposal.daysInPending} dias em pendência
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </Sheet>
    </>
  );
}
