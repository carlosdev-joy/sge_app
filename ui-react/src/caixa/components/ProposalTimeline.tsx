import { Check, FileText, CreditCard, CheckCircle, Inbox } from "lucide-react";

interface TimelineStep {
  id: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  status: "completed" | "active" | "pending";
}

interface ProposalTimelineProps {
  currentStatus: string;
}

const ProposalTimeline = ({ currentStatus }: ProposalTimelineProps) => {
  // Define the steps based on the proposal status
  const getTimelineSteps = (): TimelineStep[] => {
    // Check if it's an exception flow (has DPS pending)
    const isExceptionFlow = currentStatus === "pending_dps";
    const isRefundFlow = currentStatus === "refund_pending";

    if (isRefundFlow) {
      return [
        {
          id: "available",
          label: "Valor disponível para devolução",
          icon: <CreditCard className="h-5 w-5" />,
          color: "hsl(var(--orange))",
          status: "completed",
        },
        {
          id: "scheduled",
          label: "Devolução Programada",
          icon: <CheckCircle className="h-5 w-5" />,
          color: "hsl(var(--yellow))",
          status: "active",
        },
        {
          id: "completed",
          label: "Pagamento efetivado",
          icon: <Check className="h-5 w-5" />,
          color: "hsl(var(--green))",
          status: "pending",
        },
      ];
    }

    if (isExceptionFlow) {
      return [
        {
          id: "signature",
          label: "Aguardando Assinatura",
          icon: <FileText className="h-5 w-5" />,
          color: "hsl(var(--orange))",
          status: "completed",
        },
        {
          id: "payment",
          label: "Aguardando Pagamento",
          icon: <CreditCard className="h-5 w-5" />,
          color: "hsl(var(--yellow))",
          status: "completed",
        },
        {
          id: "payment_done",
          label: "Pagamento Efetuado",
          icon: <CheckCircle className="h-5 w-5" />,
          color: "hsl(var(--green))",
          status: "completed",
        },
        {
          id: "dps",
          label: "Aguardando Envio da DPS",
          icon: <Inbox className="h-5 w-5" />,
          color: "hsl(var(--destructive))",
          status: "active",
        },
      ];
    }

    // Ideal flow
    const statusMap: Record<string, number> = {
      pending_signature: 0,
      awaiting_payment: 1,
      signed_proposal: 2,
      approved: 2,
      emission_sent: 2,
    };

    const currentStep = statusMap[currentStatus] ?? 0;

    return [
      {
        id: "signature",
        label: "Aguardando Assinatura",
        icon: <FileText className="h-5 w-5" />,
        color: "hsl(var(--orange))",
        status: currentStep > 0 ? "completed" : "active",
      },
      {
        id: "payment",
        label: "Aguardando Pagamento",
        icon: <CreditCard className="h-5 w-5" />,
        color: "hsl(var(--yellow))",
        status: currentStep > 1 ? "completed" : currentStep === 1 ? "active" : "pending",
      },
      {
        id: "issued",
        label: "Proposta Emitida",
        icon: <Check className="h-5 w-5" />,
        color: "hsl(var(--green))",
        status: currentStep >= 2 ? "active" : "pending",
      },
    ];
  };

  const steps = getTimelineSteps();

  return (
    <div className="py-8">
      <div className="flex items-center justify-between relative px-4">
        {/* Connection line */}
        <div className="absolute top-6 left-0 right-0 h-1 bg-primary/20 -z-10" 
             style={{ left: "calc(2rem + 24px)", right: "calc(2rem + 24px)" }} />
        
        {steps.map((step, index) => (
          <div key={step.id} className="flex flex-col items-center relative flex-1">
            {/* Circle with icon */}
            <div
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 ${
                step.status === "active" || step.status === "completed"
                  ? "bg-[var(--step-color)] text-white shadow-lg scale-110"
                  : "bg-muted text-muted-foreground"
              }`}
              style={{
                "--step-color": step.status !== "pending" ? step.color : undefined,
              } as React.CSSProperties}
            >
              {step.icon}
            </div>

            {/* Connecting line between steps */}
            {index < steps.length - 1 && (
              <div
                className={`absolute top-6 left-[50%] w-full h-1 transition-all duration-300 ${
                  step.status === "completed" ? "bg-primary" : "bg-primary/20"
                }`}
              />
            )}

            {/* Label */}
            <div className="mt-3 text-center">
              <p
                className={`text-sm font-medium transition-colors duration-300 ${
                  step.status === "active" || step.status === "completed"
                    ? "text-foreground"
                    : "text-muted-foreground"
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
};

export default ProposalTimeline;
