// "Workflow de Propostas" (gaveta) no DS nativo — cards de status clicáveis,
// filtro e lista. O componente traz o próprio botão-gatilho, como o original.
//
// A sequência, os rótulos e as propostas vêm de `lib/workflow.ts`, a MESMA
// fonte do card colapsável da home (InlineWorkflow). Até 2026-08-31 este
// painel tinha lista e mock PRÓPRIOS — 9 status que não existiam em nenhum
// outro lugar do sistema ("Ag. Link Pagamento", "Cotação", "Rascunho") sobre
// 13 propostas que não eram as da tela. Duas verdades na mesma tela; com os
// dados reais entrando, tinha que virar uma.
import { useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Sheet } from "../../components/ui/Sheet";
import { Select } from "../../components/ui/Input";
import {
  contarPorStatus,
  propostasWorkflow,
  SEQUENCIA_WORKFLOW,
  STATUS_COR,
  STATUS_LABEL_CURTO,
  type StatusWorkflow,
} from "../lib/workflow";

export default function ProposalWorkflowSheet() {
  const [aberto, setAberto] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<string>("all");

  const contagem = contarPorStatus(propostasWorkflow);

  const filteredProposals =
    selectedStatus === "all"
      ? propostasWorkflow
      : propostasWorkflow.filter((p) => p.status === selectedStatus);

  return (
    <>
      <Button variant="secondary" size="md" onClick={() => setAberto(true)}>
        <FileText size={16} />
        Workflow
      </Button>

      <Sheet open={aberto} onClose={() => setAberto(false)} title="Workflow de Propostas" widthClass="max-w-2xl">
        {/* Cards de status (clicáveis: filtram a lista). Duas colunas: os nomes
            da sequência são longos, e em três eles quebravam em cinco linhas. */}
        <div className="grid grid-cols-2 gap-2 mb-6">
          {SEQUENCIA_WORKFLOW.map((etapa) => (
            <button
              key={etapa.value}
              onClick={() => setSelectedStatus(etapa.value)}
              className={`${STATUS_COR[etapa.value]} rounded-lg p-3 text-white text-center cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg ${
                selectedStatus === etapa.value ? "ring-2 ring-offset-2 ring-[#1A5FA8] ring-offset-panel" : ""
              }`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-white/90 mb-1 leading-tight">{etapa.label}</div>
              <div className="text-2xl font-bold tracking-tight">{contagem[etapa.value]}</div>
            </button>
          ))}
        </div>

        {/* Filtro */}
        <div className="mb-4">
          <Select value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)} aria-label="Filtrar por status" className="w-full">
            <option value="all">Todos os Status ({contagem.all})</option>
            {SEQUENCIA_WORKFLOW.map((etapa) => (
              <option key={etapa.value} value={etapa.value}>
                {etapa.label} ({contagem[etapa.value]})
              </option>
            ))}
          </Select>
        </div>

        {/* Lista */}
        <div className="flex flex-col gap-3">
          {filteredProposals.map((proposta) => (
            <div key={proposta.id} className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-2 gap-3">
                <div>
                  <div className="font-semibold text-lg text-ink">{proposta.insuredName}</div>
                  <div className="text-sm text-dim">Proposta: {proposta.number}</div>
                </div>
                <span className={`${STATUS_COR[proposta.status as StatusWorkflow] ?? "bg-slate-500"} text-white rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap`}>
                  {STATUS_LABEL_CURTO[proposta.status as StatusWorkflow] ?? proposta.status}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm text-ink">
                <div>
                  <span className="text-dim">Produto:</span> {proposta.product}
                </div>
                <div>
                  <span className="text-dim">Valor:</span> {proposta.value}
                </div>
                <div>
                  <span className="text-dim">Região:</span> {proposta.region}
                </div>
                <div>
                  <span className="text-dim">Corretor:</span> {proposta.broker}
                </div>
                {proposta.daysInPending > 0 && (
                  <div className="col-span-2 text-red-600 dark:text-red-400 font-medium">
                    ⏱️ {proposta.daysInPending} dias em pendência
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
