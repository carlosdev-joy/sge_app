// Linha do tempo do status da proposta no DS nativo — porte 1:1 do
// ProposalTimeline shadcn (mesmos fluxos ideal/DPS/devolução e mesmas cores de
// etapa), com tokens ink/dim/edge. Usado pelo ProposalDetailDialogOrq (F3) e
// reutilizável no acompanhamento por status (F6).
import { Check, FileText, CreditCard, CheckCircle, Inbox } from "lucide-react";

interface TimelineStep {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  status: "completed" | "active" | "pending";
}

interface ProposalTimelineOrqProps {
  currentStatus: string;
}

// Cores de etapa fixas (fora do .caixa-theme as vars --orange/--yellow/--green
// não existem): laranja CAIXA, âmbar, verde e vermelho — legíveis nos 2 temas
// porque pintam o FUNDO do círculo com texto branco.
const LARANJA = "#F26B00";
const AMBAR = "#f59e0b";
const VERDE = "#10b981";
const VERMELHO = "#ef4444";

export default function ProposalTimelineOrq({ currentStatus }: ProposalTimelineOrqProps) {
  const getTimelineSteps = (): TimelineStep[] => {
    const isExceptionFlow = currentStatus === "pending_dps";
    const isRefundFlow = currentStatus === "refund_pending";

    if (isRefundFlow) {
      return [
        { id: "available", label: "Valor disponível para devolução", icon: <CreditCard className="h-5 w-5" />, color: LARANJA, status: "completed" },
        { id: "scheduled", label: "Devolução Programada", icon: <CheckCircle className="h-5 w-5" />, color: AMBAR, status: "active" },
        { id: "completed", label: "Pagamento efetivado", icon: <Check className="h-5 w-5" />, color: VERDE, status: "pending" },
      ];
    }

    if (isExceptionFlow) {
      return [
        { id: "signature", label: "Aguardando Assinatura", icon: <FileText className="h-5 w-5" />, color: LARANJA, status: "completed" },
        { id: "payment", label: "Aguardando Pagamento", icon: <CreditCard className="h-5 w-5" />, color: AMBAR, status: "completed" },
        { id: "payment_done", label: "Pagamento Efetuado", icon: <CheckCircle className="h-5 w-5" />, color: VERDE, status: "completed" },
        { id: "dps", label: "Aguardando Envio da DPS", icon: <Inbox className="h-5 w-5" />, color: VERMELHO, status: "active" },
      ];
    }

    // Fluxo ideal
    const statusMap: Record<string, number> = {
      pending_signature: 0,
      awaiting_payment: 1,
      signed_proposal: 2,
      approved: 2,
      emission_sent: 2,
    };

    const currentStep = statusMap[currentStatus] ?? 0;

    return [
      { id: "signature", label: "Aguardando Assinatura", icon: <FileText className="h-5 w-5" />, color: LARANJA, status: currentStep > 0 ? "completed" : "active" },
      { id: "payment", label: "Aguardando Pagamento", icon: <CreditCard className="h-5 w-5" />, color: AMBAR, status: currentStep > 1 ? "completed" : currentStep === 1 ? "active" : "pending" },
      { id: "issued", label: "Proposta Emitida", icon: <Check className="h-5 w-5" />, color: VERDE, status: currentStep >= 2 ? "active" : "pending" },
    ];
  };

  const steps = getTimelineSteps();

  return (
    <div className="py-8">
      <div className="flex items-center justify-between relative px-4">
        {/* Linha de fundo entre o primeiro e o último círculo */}
        <div
          className="absolute top-6 h-1 bg-[#1A5FA8]/20 -z-10"
          style={{ left: "calc(2rem + 24px)", right: "calc(2rem + 24px)" }}
        />

        {steps.map((step, index) => (
          <div key={step.id} className="flex flex-col items-center relative flex-1">
            {/* Círculo com ícone */}
            <div
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                step.status === "active" || step.status === "completed"
                  ? "text-white shadow-lg scale-110"
                  : "bg-edge/60 text-dim"
              }`}
              style={step.status !== "pending" ? { backgroundColor: step.color } : undefined}
            >
              {step.icon}
            </div>

            {/* Trecho de linha até o próximo passo */}
            {index < steps.length - 1 && (
              <div
                className={`absolute top-6 left-[50%] w-full h-1 transition-all duration-300 ${
                  step.status === "completed" ? "bg-[#1A5FA8]" : "bg-[#1A5FA8]/20"
                }`}
              />
            )}

            {/* Rótulo */}
            <div className="mt-3 text-center">
              <p
                className={`text-sm font-medium transition-colors duration-300 ${
                  step.status === "active" || step.status === "completed" ? "text-ink" : "text-dim"
                }`}
              >
                {step.label}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
