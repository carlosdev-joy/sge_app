import { useState } from "react";
import { Button } from "./ui/button";
import { X, ArrowRight, ArrowLeft } from "lucide-react";
import diegoAvatar from "../assets/diego-avatar.png";
import lariAvatar from "../assets/lari-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";

interface TourStep {
  avatar: string;
  avatarName: string;
  message: string;
  position: { top?: string; bottom?: string; left?: string; right?: string };
  highlight?: string;
}

interface ProductTourProps {
  productType: "vida" | "previdencia" | "prestamista";
  onClose: () => void;
}

const tourSteps: Record<string, TourStep[]> = {
  vida: [
    {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Bem-vindo ao tour de Seguro de Vida! Sou especialista neste produto e vou te mostrar os recursos específicos.",
      position: { top: "30%", left: "50%" },
    },
    {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Aqui você pode acompanhar as propostas de Seguro de Vida. Os cards mostram pendências de documentação, assinaturas e pagamentos específicos deste produto.",
      position: { top: "55%", left: "50%" },
      highlight: ".grid",
    },
    {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Dica: Propostas de vida geralmente têm análise de risco. Fique atento aos cards de 'Aguardando Análise' e 'Pendências Médicas'!",
      position: { top: "45%", right: "15%" },
    },
  ],
  previdencia: [
    {
      avatar: leoAvatar,
      avatarName: "Léo",
      message: "Oi! Vamos explorar juntos a área de Previdência. Este produto tem características únicas que vou te mostrar.",
      position: { top: "30%", left: "50%" },
    },
    {
      avatar: leoAvatar,
      avatarName: "Léo",
      message: "Em Previdência, você pode acompanhar portabilidades! Este é um diferencial importante. Clique nos cards para ver detalhes das movimentações.",
      position: { top: "55%", left: "50%" },
      highlight: ".grid",
    },
    {
      avatar: leoAvatar,
      avatarName: "Léo",
      message: "Dica: Para portabilidades, use os filtros de data para acompanhar o prazo de conclusão. Elas têm prazos regulatórios!",
      position: { top: "45%", right: "15%" },
    },
  ],
  prestamista: [
    {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Vamos conhecer o acompanhamento de Seguro Prestamista! Este produto está vinculado a operações de crédito.",
      position: { top: "30%", left: "50%" },
    },
    {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Os cards de Prestamista mostram o status das propostas vinculadas às operações de crédito. Preste atenção especial às pendências documentais!",
      position: { top: "55%", left: "50%" },
      highlight: ".grid",
    },
    {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Dica: Propostas de Prestamista precisam ser concluídas antes da liberação do crédito. Agilidade aqui é fundamental!",
      position: { top: "45%", right: "15%" },
    },
  ],
};

const ProductTour = ({ productType, onClose }: ProductTourProps) => {
  const [currentStep, setCurrentStep] = useState(0);
  const steps = tourSteps[productType];

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      onClose();
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const step = steps[currentStep];
  const { top, bottom, left, right } = step.position;

  const transform =
    left === "50%" && top === "50%"
      ? "translate(-50%, -50%)"
      : left === "50%"
      ? "translateX(-50%)"
      : top === "50%"
      ? "translateY(-50%)"
      : undefined;

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-[999] animate-[fadeIn_0.4s_ease-out] backdrop-blur-sm" />

      <div
        className="fixed z-[1000] animate-[slideInUp_0.5s_ease-out]"
        style={{
          top,
          bottom,
          left,
          right,
          transform,
        }}
      >
        <div className="bg-background rounded-xl shadow-2xl p-6 max-w-md border-2 border-primary/20 relative">
          <button
            onClick={onClose}
            className="absolute top-2 right-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>

          <div className="flex items-start gap-4 mb-4">
            <img
              src={step.avatar}
              alt={step.avatarName}
              className="h-16 w-16 rounded-full border-2 border-primary object-cover"
            />
            <div className="flex-1">
              <h3 className="font-bold text-lg text-primary mb-2">
                {step.avatarName}
              </h3>
              <p className="text-foreground">{step.message}</p>
            </div>
          </div>

          <div className="mb-4">
            <div className="flex gap-1">
              {steps.map((_, index) => (
                <div
                  key={index}
                  className={`h-1 flex-1 rounded-full transition-colors ${
                    index <= currentStep ? "bg-primary" : "bg-muted"
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2 text-center">
              {currentStep + 1} de {steps.length}
            </p>
          </div>

          <div className="flex justify-between items-center gap-2">
            <Button
              variant="ghost"
              onClick={onClose}
              className="text-muted-foreground"
            >
              Fechar
            </Button>
            <div className="flex gap-2">
              {currentStep > 0 && (
                <Button variant="outline" onClick={handlePrevious} size="icon">
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              )}
              <Button onClick={handleNext}>
                {currentStep === steps.length - 1 ? (
                  "Finalizar"
                ) : (
                  <>
                    Próximo
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes slideInUp {
          from {
            opacity: 0;
            transform: translateY(30px) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
      `}</style>
    </>
  );
};

export default ProductTour;
