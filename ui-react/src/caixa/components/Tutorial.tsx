import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Button } from "./ui/button";
import { X, ArrowRight, ArrowLeft, Hand } from "lucide-react";
import diegoAvatar from "../assets/diego-avatar.png";
import lariAvatar from "../assets/lari-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";

interface TutorialStep {
  page: string;
  avatar: string;
  avatarName: string;
  message: string;
  avatarPosition: { x: string; y: string }; // Posição do avatar na tela
  balloonPosition: "left" | "right" | "top" | "bottom"; // Lado do balão em relação ao avatar
  highlight?: string; // CSS selector to highlight
  pointTo?: { x: string; y: string }; // Coordenadas para apontar
}

const tutorialSteps: TutorialStep[] = [
  // Página inicial - Consulta de Proposta
  {
    page: "/caixa-seguro",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Olá! Bem-vindo ao sistema de acompanhamento de propostas da CAIXA. Vou te guiar pelas principais funcionalidades!",
    avatarPosition: { x: "50%", y: "50%" },
    balloonPosition: "top",
  },
  {
    page: "/caixa-seguro",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Esta é a página de Consulta de Propostas. Aqui você pode buscar e acompanhar todas as propostas dos seus clientes usando diferentes filtros.",
    avatarPosition: { x: "20%", y: "40%" },
    balloonPosition: "right",
    highlight: ".search-section",
    pointTo: { x: "50%", y: "35%" },
  },
  {
    page: "/caixa-seguro",
    avatar: diegoAvatar,
    avatarName: "Diego",
    message: "Viu estes avatares flutuantes? Sou o Diego, especialista em Seguro de Vida! Clique em mim quando precisar de ajuda sobre produtos de vida.",
    avatarPosition: { x: "85%", y: "30%" },
    balloonPosition: "left",
  },
  {
    page: "/caixa-seguro",
    avatar: leoAvatar,
    avatarName: "Léo",
    message: "E eu sou o Léo, especialista em Previdência! Você pode conversar comigo sobre portabilidades e produtos previdenciários.",
    avatarPosition: { x: "85%", y: "50%" },
    balloonPosition: "left",
  },
  {
    page: "/caixa-seguro",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Agora que você conhece as funcionalidades desta página, vamos explorar o Monitoramento Tático de Emissão! Use o Menu no canto superior esquerdo para navegar.",
    avatarPosition: { x: "15%", y: "15%" },
    balloonPosition: "right",
    pointTo: { x: "5%", y: "10%" },
  },
  
  // Página de Monitoramento Tático
  {
    page: "/caixa-seguro/acompanhamento",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Chegamos ao Monitoramento Tático de Emissão! Aqui você acompanha o desempenho e status de todas as suas propostas em tempo real.",
    avatarPosition: { x: "50%", y: "30%" },
    balloonPosition: "bottom",
  },
  {
    page: "/caixa-seguro/acompanhamento",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Use os filtros de data para visualizar propostas de períodos específicos: dia, mês ou ano. Isso ajuda a analisar o desempenho em diferentes períodos!",
    avatarPosition: { x: "15%", y: "25%" },
    balloonPosition: "right",
    highlight: ".date-filters",
    pointTo: { x: "30%", y: "22%" },
  },
  {
    page: "/caixa-seguro/acompanhamento",
    avatar: diegoAvatar,
    avatarName: "Diego",
    message: "Aqui você pode alternar entre diferentes produtos: Seguro de Vida, Previdência e Prestamista! Cada produto tem seus próprios dados e indicadores.",
    avatarPosition: { x: "50%", y: "35%" },
    balloonPosition: "bottom",
  },
  {
    page: "/caixa-seguro/acompanhamento",
    avatar: leoAvatar,
    avatarName: "Léo",
    message: "Estes cards coloridos mostram o status de todas as suas propostas: aguardando assinatura, pagamento, pendências documentais e muito mais! Clique neles para ver detalhes.",
    avatarPosition: { x: "20%", y: "60%" },
    balloonPosition: "right",
    highlight: ".grid",
    pointTo: { x: "50%", y: "60%" },
  },
  {
    page: "/caixa-seguro/acompanhamento",
    avatar: leoAvatar,
    avatarName: "Léo",
    message: "Quando estiver na aba de Previdência, eu apareço para te ajudar com portabilidades, produtos previdenciários e análises específicas!",
    avatarPosition: { x: "85%", y: "40%" },
    balloonPosition: "left",
  },
  
  // Página de IA Operacional
  {
    page: "/caixa-seguro/ia-operacional",
    avatar: lariAvatar,
    avatarName: "Lari",
    message: "Esta é a área mais avançada: o Painel de IA Operacional! Aqui a inteligência artificial analisa seus dados e gera insights poderosos.",
    avatarPosition: { x: "50%", y: "35%" },
    balloonPosition: "bottom",
  },
  {
    page: "/caixa-seguro/ia-operacional",
    avatar: diegoAvatar,
    avatarName: "Diego",
    message: "A IA pode analisar pendências, prever riscos, aprender com casos declinados e gerar alertas automáticos para melhorar suas vendas!",
    avatarPosition: { x: "30%", y: "50%" },
    balloonPosition: "right",
  },
  {
    page: "/caixa-seguro/ia-operacional",
    avatar: leoAvatar,
    avatarName: "Léo",
    message: "Pronto! Agora você conhece as principais funcionalidades do sistema. Lembre-se: estamos sempre disponíveis nos avatares flutuantes. Conte conosco!",
    avatarPosition: { x: "50%", y: "50%" },
    balloonPosition: "top",
  },
];

const Tutorial = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem("hasSeenTutorial");
    if (!hasSeenTutorial) {
      setTimeout(() => setIsVisible(true), 1000);
    }
  }, []);

  useEffect(() => {
    if (isVisible) {
      const currentPageStep = tutorialSteps[currentStep];
      
      // Navigate if needed and wait for page to load
      if (currentPageStep && location.pathname !== currentPageStep.page) {
        navigate(currentPageStep.page);
        // Wait for navigation to complete before showing highlights
        const timer = setTimeout(() => {
          if (currentPageStep?.highlight) {
            const element = document.querySelector(currentPageStep.highlight);
            if (element) {
              element.classList.add("tutorial-highlight");
            }
          }
        }, 500);
        return () => clearTimeout(timer);
      }

      // Add highlight effect
      if (currentPageStep?.highlight) {
        const element = document.querySelector(currentPageStep.highlight);
        if (element) {
          element.classList.add("tutorial-highlight");
        }
      }

      // Cleanup highlight on step change
      return () => {
        const elements = document.querySelectorAll(".tutorial-highlight");
        elements.forEach((el) => el.classList.remove("tutorial-highlight"));
      };
    }
  }, [currentStep, isVisible, location.pathname, navigate]);

  const handleNext = () => {
    if (currentStep < tutorialSteps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleClose();
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleClose = () => {
    setIsVisible(false);
    localStorage.setItem("hasSeenTutorial", "true");
  };

  const handleSkip = () => {
    handleClose();
  };

  if (!isVisible) return null;

  const step = tutorialSteps[currentStep];
  
  // Posições do balão em relação ao avatar
  const getBalloonPosition = () => {
    const offset = 180; // distância do avatar
    const baseStyle: React.CSSProperties = {
      position: "absolute",
      maxWidth: "320px",
      zIndex: 1001,
    };

    switch (step.balloonPosition) {
      case "right":
        return { ...baseStyle, left: `calc(${step.avatarPosition.x} + ${offset}px)`, top: step.avatarPosition.y };
      case "left":
        return { ...baseStyle, right: `calc(100% - ${step.avatarPosition.x} + ${offset}px)`, top: step.avatarPosition.y };
      case "top":
        return { ...baseStyle, left: step.avatarPosition.x, bottom: `calc(100% - ${step.avatarPosition.y} + ${offset}px)`, transform: "translateX(-50%)" };
      case "bottom":
        return { ...baseStyle, left: step.avatarPosition.x, top: `calc(${step.avatarPosition.y} + ${offset}px)`, transform: "translateX(-50%)" };
    }
  };

  return (
    <>
      {/* Overlay - mais transparente para ver a página */}
      <div className="fixed inset-0 bg-black/30 z-[999] animate-[fadeIn_0.5s_ease-out]" />

      {/* Avatar de Corpo Inteiro */}
      <div
        className="fixed z-[1000] transition-all duration-700 ease-out animate-[avatarBounce_0.8s_ease-out]"
        style={{
          left: step.avatarPosition.x,
          top: step.avatarPosition.y,
          transform: "translate(-50%, -50%)",
        }}
      >
        <div className="relative">
          {/* Avatar com sombra e efeito de "flutuação" */}
          <div className="animate-[float_3s_ease-in-out_infinite]">
            <img
              src={step.avatar}
              alt={step.avatarName}
              className="h-32 w-32 object-cover rounded-full border-4 border-primary shadow-2xl"
            />
          </div>
          
          {/* Indicador de mão apontando se houver pointTo */}
          {step.pointTo && (
            <Hand 
              className="absolute text-primary animate-[wave_1s_ease-in-out_infinite]"
              size={32}
              style={{
                left: step.pointTo.x > step.avatarPosition.x ? "100%" : "auto",
                right: step.pointTo.x < step.avatarPosition.x ? "100%" : "auto",
                top: "50%",
                transform: "translateY(-50%)",
              }}
            />
          )}
        </div>
      </div>

      {/* Balão de Fala */}
      <div
        className="animate-[balloonPop_0.5s_ease-out_0.3s_both]"
        style={getBalloonPosition()}
      >
        <div className="bg-background rounded-2xl shadow-2xl p-6 border-2 border-primary/30 relative">
          {/* Triângulo do balão */}
          <div
            className={`absolute w-0 h-0 border-8 ${
              step.balloonPosition === "right"
                ? "border-r-background border-t-transparent border-b-transparent border-l-transparent -left-4 top-8"
                : step.balloonPosition === "left"
                ? "border-l-background border-t-transparent border-b-transparent border-r-transparent -right-4 top-8"
                : step.balloonPosition === "top"
                ? "border-t-background border-l-transparent border-r-transparent border-b-transparent -bottom-4 left-1/2 -translate-x-1/2"
                : "border-b-background border-l-transparent border-r-transparent border-t-transparent -top-4 left-1/2 -translate-x-1/2"
            }`}
          />

          {/* Close Button */}
          <button
            onClick={handleClose}
            className="absolute top-2 right-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>

          {/* Conteúdo */}
          <div className="mb-4">
            <h3 className="font-bold text-xl text-primary mb-3 flex items-center gap-2">
              {step.avatarName}
              <span className="text-sm">💬</span>
            </h3>
            <p className="text-foreground leading-relaxed">{step.message}</p>
          </div>

          {/* Progress */}
          <div className="mb-4">
            <div className="flex gap-1">
              {tutorialSteps.map((_, index) => (
                <div
                  key={index}
                  className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                    index <= currentStep ? "bg-primary scale-110" : "bg-muted"
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2 text-center font-medium">
              Passo {currentStep + 1} de {tutorialSteps.length}
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-between items-center gap-2">
            <Button
              variant="ghost"
              onClick={handleSkip}
              className="text-muted-foreground hover:text-foreground"
            >
              Pular Tutorial
            </Button>
            <div className="flex gap-2">
              {currentStep > 0 && (
                <Button variant="outline" onClick={handlePrevious} size="icon">
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              )}
              <Button onClick={handleNext} className="gap-2">
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

      {/* Custom Styles */}
      <style>{`
        .tutorial-highlight {
          position: relative;
          z-index: 998 !important;
          box-shadow: 0 0 0 4px hsl(var(--primary)), 0 0 0 8px hsl(var(--primary) / 0.3) !important;
          border-radius: 8px;
          animation: tutorialPulse 2s ease-in-out infinite;
        }

        @keyframes tutorialPulse {
          0%, 100% {
            box-shadow: 0 0 0 4px hsl(var(--primary)), 0 0 0 8px hsl(var(--primary) / 0.3);
          }
          50% {
            box-shadow: 0 0 0 4px hsl(var(--primary)), 0 0 0 12px hsl(var(--primary) / 0.2);
          }
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes avatarBounce {
          0% {
            opacity: 0;
            transform: translate(-50%, -50%) scale(0.3);
          }
          50% {
            transform: translate(-50%, -50%) scale(1.1);
          }
          100% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
        }

        @keyframes balloonPop {
          0% {
            opacity: 0;
            transform: scale(0.5);
          }
          70% {
            transform: scale(1.05);
          }
          100% {
            opacity: 1;
            transform: scale(1);
          }
        }

        @keyframes float {
          0%, 100% {
            transform: translateY(0px);
          }
          50% {
            transform: translateY(-10px);
          }
        }

        @keyframes wave {
          0%, 100% {
            transform: translateY(-50%) rotate(0deg);
          }
          25% {
            transform: translateY(-50%) rotate(-15deg);
          }
          75% {
            transform: translateY(-50%) rotate(15deg);
          }
        }
      `}</style>
    </>
  );
};

export default Tutorial;
