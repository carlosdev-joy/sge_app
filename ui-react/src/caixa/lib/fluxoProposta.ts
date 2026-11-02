// O FLUXO de uma proposta até o card em que ela está — regra única do Resumo do Seguro.
//
// A linha do tempo mostra TODAS as etapas anteriores como concluídas (sucesso) e a etapa do card
// atual em destaque, como o fluxo real da proposta. Exemplo: no Card 4 (Em Análise) aparecem
// Pendente de Assinatura ✓ → Pendente de Pagamento ✓ → Assinada e Paga ✓ → Em Análise (atual).
//
// O caminho de cada card segue a ordem da operação (`SEQUENCIA_WORKFLOW`), com dois desvios
// reais: a proposta REJEITADA não passa por "Emitida", e a DEVOLUÇÃO vem depois da rejeição; já a
// SENSIBILIZAÇÃO acompanha propostas emitidas. Lógica pura: roda no node nos testes.
import { STATUS_LABEL_CURTO, type StatusWorkflow } from "./workflow";

export type TomPasso = "laranja" | "ambar" | "verde" | "vermelho" | "azul" | "azulEscuro";

export interface PassoFluxo {
  id: StatusWorkflow;
  label: string;
  tom: TomPasso;
  estado: "completed" | "active";
}

/** O que mostrar na etapa ATUAL quando o card sabe mais que o nome dele (ex.: "Cancelada"). */
export interface AtualDoFluxo {
  rotulo?: string;
  tom?: TomPasso;
}

export const FLUXO_POR_STATUS: Record<StatusWorkflow, StatusWorkflow[]> = {
  pending_signature: ["pending_signature"],
  awaiting_payment: ["pending_signature", "awaiting_payment"],
  paid: ["pending_signature", "awaiting_payment", "paid"],
  in_analysis: ["pending_signature", "awaiting_payment", "paid", "in_analysis"],
  emission_sent: ["pending_signature", "awaiting_payment", "paid", "in_analysis", "emission_sent"],
  declined: ["pending_signature", "awaiting_payment", "paid", "in_analysis", "declined"],
  refund_scheduled: ["pending_signature", "awaiting_payment", "paid", "in_analysis", "declined", "refund_scheduled"],
  sensitization_monitoring: ["pending_signature", "awaiting_payment", "paid", "in_analysis", "emission_sent", "sensitization_monitoring"],
};

/** Cor da etapa quando ela é a ATUAL (as concluídas são sempre verdes). */
const TOM_DA_ETAPA: Record<StatusWorkflow, TomPasso> = {
  pending_signature: "laranja",
  awaiting_payment: "ambar",
  paid: "verde",
  in_analysis: "vermelho",
  emission_sent: "azul",
  declined: "vermelho",
  refund_scheduled: "ambar",
  sensitization_monitoring: "azulEscuro",
};

/** Status de card conhecido? (`pending_dps`, `refund_pending`… e afins ficam no fluxo antigo.) */
export function statusDeFluxo(status: string): status is StatusWorkflow {
  return Object.prototype.hasOwnProperty.call(FLUXO_POR_STATUS, status);
}

/** As etapas de `status` até ele mesmo; `null` se o status não é de um card do Workflow. */
export function passosDoFluxo(status: string, atual?: AtualDoFluxo): PassoFluxo[] | null {
  if (!statusDeFluxo(status)) return null;
  const caminho = FLUXO_POR_STATUS[status];
  return caminho.map((etapa, i) => {
    const ultima = i === caminho.length - 1;
    if (!ultima) return { id: etapa, label: STATUS_LABEL_CURTO[etapa], tom: "verde" as const, estado: "completed" as const };
    return {
      id: etapa,
      label: atual?.rotulo || STATUS_LABEL_CURTO[etapa],
      tom: atual?.tom ?? TOM_DA_ETAPA[etapa],
      estado: "active" as const,
    };
  });
}
