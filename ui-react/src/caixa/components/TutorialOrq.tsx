// Tutorial do mascote no DS nativo — porte do Tutorial shadcn com os 5 passos
// da HOME (mesmos textos, avatares e posições). Os passos das outras páginas
// foram removidos de propósito: o componente antigo desmontava ao navegar
// (vivia dentro do Index), então o tutorial morria no passo 6 — os passos
// cross-página nunca funcionaram; o Monitoramento tem tour próprio
// (ProductTourOrq) desde a F2. O último passo aponta o Menu para o usuário
// seguir sozinho. Visibilidade é controlada pelo pai (IndexOrq).
// PRESERVADO o clamp do balão à viewport (fix do PR #192) — não regredir.
import { useEffect, useState } from "react";
import { X, ArrowRight, ArrowLeft, Hand } from "lucide-react";
import { Button } from "../../components/ui/Button";
import diegoAvatar from "../assets/diego-avatar.png";
import lariAvatar from "../assets/lari-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";

interface TutorialStep {
  avatar: string;
  avatarName: string;
  message: string;
  avatarPosition: { x: string; y: string }; // posição do avatar na tela
  balloonPosition: "left" | "right" | "top" | "bottom"; // lado do balão
  highlight?: string; // seletor CSS a destacar
  pointTo?: { x: string; y: string }; // coordenadas para a mãozinha apontar
}

const tutorialSteps: TutorialStep[] = [
  {
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Olá! Bem-vindo ao sistema de acompanhamento de propostas da CAIXA. Vou te guiar pelas principais funcionalidades!",
    avatarPosition: { x: "50%", y: "50%" },
    balloonPosition: "top",
  },
  {
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Esta é a página de Consulta de Propostas. Aqui você pode buscar e acompanhar todas as propostas dos seus clientes usando diferentes filtros.",
    avatarPosition: { x: "20%", y: "40%" },
    balloonPosition: "right",
    highlight: ".search-section",
    pointTo: { x: "50%", y: "35%" },
  },
  {
    avatar: diegoAvatar,
    avatarName: "Diego",
    message: "Viu estes avatares flutuantes? Sou o Diego, especialista em Seguro de Vida! Clique em mim quando precisar de ajuda sobre produtos de vida.",
    avatarPosition: { x: "85%", y: "30%" },
    balloonPosition: "left",
  },
  {
    avatar: leoAvatar,
    avatarName: "Léo",
    message: "E eu sou o Léo, especialista em Previdência! Você pode conversar comigo sobre portabilidades e produtos previdenciários.",
    avatarPosition: { x: "85%", y: "50%" },
    balloonPosition: "left",
  },
  {
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Agora que você conhece as funcionalidades desta página, explore o Monitoramento Tático de Emissão! Use o Menu no canto superior esquerdo para navegar — lá também há um tour do produto.",
    avatarPosition: { x: "15%", y: "15%" },
    balloonPosition: "right",
    pointTo: { x: "5%", y: "10%" },
  },
];

interface TutorialOrqProps {
  onFechar: () => void;
}

export default function TutorialOrq({ onFechar }: TutorialOrqProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const step = tutorialSteps[currentStep];

  // Destaque do elemento apontado pelo passo (mesma classe .tutorial-highlight).
  useEffect(() => {
    if (step?.highlight) {
      const element = document.querySelector(step.highlight);
      if (element) element.classList.add("tutorial-highlight");
    }
    return () => {
      document.querySelectorAll(".tutorial-highlight").forEach((el) => el.classList.remove("tutorial-highlight"));
    };
  }, [step]);

  const handleNext = () => {
    if (currentStep < tutorialSteps.length - 1) setCurrentStep(currentStep + 1);
    else onFechar();
  };

  const handlePrevious = () => {
    if (currentStep > 0) setCurrentStep(currentStep - 1);
  };

  // Posições do balão em relação ao avatar — clamp mantém o balão dentro da
  // viewport (margem de 16px); sem isso, avatar central + balão "top" subia
  // acima da tela e cortava (bug corrigido no PR #192).
  const getBalloonPosition = () => {
    const offset = 180; // distância do avatar
    const W = 320; // maxWidth do balão
    const H = 340; // altura assumida p/ o clamp (o conteúdo rola se passar)
    const clampX = (v: string) => `clamp(16px, ${v}, calc(100% - 16px - ${W}px))`;
    const clampY = (v: string) => `clamp(16px, ${v}, calc(100% - 16px - ${H}px))`;
    const baseStyle: React.CSSProperties = {
      position: "fixed",
      maxWidth: `${W}px`,
      zIndex: 1001,
    };

    switch (step.balloonPosition) {
      case "right":
        return { ...baseStyle, left: clampX(`calc(${step.avatarPosition.x} + ${offset}px)`), top: clampY(step.avatarPosition.y) };
      case "left":
        return { ...baseStyle, right: clampX(`calc(100% - ${step.avatarPosition.x} + ${offset}px)`), top: clampY(step.avatarPosition.y) };
      case "top":
        return { ...baseStyle, left: step.avatarPosition.x, bottom: clampY(`calc(100% - ${step.avatarPosition.y} + ${offset}px)`), transform: "translateX(-50%)" };
      case "bottom":
        return { ...baseStyle, left: step.avatarPosition.x, top: clampY(`calc(${step.avatarPosition.y} + ${offset}px)`), transform: "translateX(-50%)" };
    }
  };

  const triangleClass =
    step.balloonPosition === "right"
      ? "border-r-panel border-t-transparent border-b-transparent border-l-transparent -left-4 top-8"
      : step.balloonPosition === "left"
      ? "border-l-panel border-t-transparent border-b-transparent border-r-transparent -right-4 top-8"
      : step.balloonPosition === "top"
      ? "border-t-panel border-l-transparent border-r-transparent border-b-transparent -bottom-4 left-1/2 -translate-x-1/2"
      : "border-b-panel border-l-transparent border-r-transparent border-t-transparent -top-4 left-1/2 -translate-x-1/2";

  return (
    <>
      {/* Overlay translúcido — deixa a página visível por trás */}
      <div className="fixed inset-0 bg-black/30 z-[999] animate-[tutFadeIn_0.5s_ease-out]" />

      {/* Avatar de corpo inteiro */}
      <div
        className="fixed z-[1000] transition-all duration-700 ease-out animate-[tutAvatarBounce_0.8s_ease-out]"
        style={{
          left: step.avatarPosition.x,
          top: step.avatarPosition.y,
          transform: "translate(-50%, -50%)",
        }}
      >
        <div className="relative">
          <div className="animate-[tutFloat_3s_ease-in-out_infinite]">
            <img
              src={step.avatar}
              alt={step.avatarName}
              className="h-32 w-32 object-cover rounded-full border-4 border-[#1A5FA8] shadow-2xl"
            />
          </div>

          {/* Mãozinha apontando, quando o passo tem pointTo */}
          {step.pointTo && (
            <Hand
              className="absolute text-[#1A5FA8] animate-[tutWave_1s_ease-in-out_infinite]"
              size={32}
              style={{
                left: parseFloat(step.pointTo.x) > parseFloat(step.avatarPosition.x) ? "100%" : "auto",
                right: parseFloat(step.pointTo.x) < parseFloat(step.avatarPosition.x) ? "100%" : "auto",
                top: "50%",
                transform: "translateY(-50%)",
              }}
            />
          )}
        </div>
      </div>

      {/* Balão de fala — o div externo posiciona (fixed + clamp + translateX
          nos casos top/bottom); a animação de "pop" (scale) fica num filho,
          senão o transform da animação (fill:both) sobrescreveria o translateX
          e o balão top/bottom ficaria descentrado. */}
      <div style={getBalloonPosition()}>
        <div className="animate-[tutBalloonPop_0.5s_ease-out_0.3s_both]">
          {/* Card SEM overflow — o triângulo (fora do padding box) não pode ser
              clipado; o scroll de conteúdo alto fica no wrapper interno. */}
          <div className="bg-panel rounded-2xl shadow-2xl p-6 border-2 border-[#1A5FA8]/30 relative">
            {/* Triângulo do balão */}
            <div className={`absolute w-0 h-0 border-8 ${triangleClass}`} />

            <button
              onClick={onFechar}
              aria-label="Fechar tutorial"
              className="absolute top-2 right-2 text-dim hover:text-ink transition-colors z-10"
            >
              <X className="h-5 w-5" />
            </button>

            {/* Só o conteúdo rola em telas baixas; card e triângulo ficam fora. */}
            <div className="max-h-[calc(100vh-140px)] overflow-y-auto">
              <div className="mb-4">
                <h3 className="font-bold text-xl text-[#1A5FA8] dark:text-blue-400 mb-3 flex items-center gap-2">
                  {step.avatarName}
                  <span className="text-sm">💬</span>
                </h3>
                <p className="text-ink leading-relaxed">{step.message}</p>
              </div>

              {/* Progresso */}
              <div className="mb-4">
                <div className="flex gap-1">
                  {tutorialSteps.map((_, index) => (
                    <div
                      key={index}
                      className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                        index <= currentStep ? "bg-[#1A5FA8] scale-110" : "bg-edge"
                      }`}
                    />
                  ))}
                </div>
                <p className="text-xs text-dim mt-2 text-center font-medium">
                  Passo {currentStep + 1} de {tutorialSteps.length}
                </p>
              </div>

              {/* Ações */}
              <div className="flex justify-between items-center gap-2">
                <Button variant="ghost" onClick={onFechar}>
                  Pular Tutorial
                </Button>
                <div className="flex gap-2">
                  {currentStep > 0 && (
                    <Button variant="secondary" onClick={handlePrevious} aria-label="Passo anterior">
                      <ArrowLeft className="h-4 w-4" />
                    </Button>
                  )}
                  <Button variant="primary" onClick={handleNext}>
                    {currentStep === tutorialSteps.length - 1 ? (
                      "Finalizar 🎉"
                    ) : (
                      <>
                        Próximo
                        <ArrowRight className="h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Estilos do destaque e das animações */}
      <style>{`
        .tutorial-highlight {
          position: relative;
          z-index: 998 !important;
          box-shadow: 0 0 0 4px #1A5FA8, 0 0 0 8px rgba(26, 95, 168, 0.3) !important;
          border-radius: 8px;
          animation: tutHighlightPulse 2s ease-in-out infinite;
        }

        @keyframes tutHighlightPulse {
          0%, 100% { box-shadow: 0 0 0 4px #1A5FA8, 0 0 0 8px rgba(26, 95, 168, 0.3); }
          50% { box-shadow: 0 0 0 4px #1A5FA8, 0 0 0 12px rgba(26, 95, 168, 0.2); }
        }

        @keyframes tutFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes tutAvatarBounce {
          0% { opacity: 0; transform: translate(-50%, -50%) scale(0.3); }
          50% { transform: translate(-50%, -50%) scale(1.1); }
          100% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        }

        @keyframes tutBalloonPop {
          0% { opacity: 0; transform: scale(0.5); }
          70% { transform: scale(1.05); }
          100% { opacity: 1; transform: scale(1); }
        }

        @keyframes tutFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }

        @keyframes tutWave {
          0%, 100% { transform: translateY(-50%) rotate(0deg); }
          25% { transform: translateY(-50%) rotate(-15deg); }
          75% { transform: translateY(-50%) rotate(15deg); }
        }
      `}</style>
    </>
  );
}
