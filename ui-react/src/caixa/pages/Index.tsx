// Home "Consulta de Propostas" da seção Caixa Seguro no visual NATIVO do
// Orquestra — tela oficial de /caixa-seguro desde a F3 da migração
// (docs/spec-caixa-ds-nativo.md); substitui o Index navy/glass. Dados mock,
// iguais aos da tela original. Requer ProfileProvider (aplicado na rota,
// App.tsx). O card "Workflow" e o sheet de workflow da home antiga voltam nas
// F6–F8 (decisão de escopo da F3 com o usuário em 2026-07-16).
import { useEffect, useState } from "react";
import { Search, RotateCcw, Users, User } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { useProfile } from "../contexts/ProfileContext";
import MenuButton from "../components/MenuButton";
import ProposalWorkflowSheet from "../components/ProposalWorkflowSheet";
import SearchProposals from "../components/SearchProposals";
import Tutorial from "../components/Tutorial";
import ChatAssistant from "../components/ChatAssistant";
import diegoAvatar from "../assets/diego-avatar.png";

export default function Index() {
  const { profile } = useProfile();
  const [tutorialAberto, setTutorialAberto] = useState(false);

  // Primeira visita: abre o tutorial sozinho após 1s (mesma regra da POC).
  useEffect(() => {
    if (!localStorage.getItem("hasSeenTutorial")) {
      const timer = setTimeout(() => setTutorialAberto(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const fecharTutorial = () => {
    localStorage.setItem("hasSeenTutorial", "true");
    setTutorialAberto(false);
  };

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1200px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
              <Search size={18} className="text-[#1A5FA8]" />
              Consulta de Propostas
            </h1>
            <p className="text-sm text-dim mt-0.5">Busca e acompanhamento de propostas dos clientes</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <MenuButton />
            <ProposalWorkflowSheet />
            {/* Reabre o tutorial na hora — sem o reload da versão antiga. */}
            <Button variant="secondary" size="md" onClick={() => setTutorialAberto(true)}>
              <RotateCcw size={14} />
              Ver Tutorial Novamente
            </Button>
            {/* Perfil vem do RBAC (caixa_seguro_operacional) — sem toggle demo */}
            <span className="inline-flex items-center gap-2 rounded-full border border-[#1A5FA8]/50 px-3 py-1.5 text-sm text-ink">
              {profile === "operational" ? (
                <>
                  <Users size={15} />
                  Perfil Operacional
                </>
              ) : (
                <>
                  <User size={15} />
                  Perfil Funcionário CAIXA
                </>
              )}
            </span>
          </div>
        </div>

        <SearchProposals />
      </div>

      {/* Tutorial do mascote (controlado; auto-abre na primeira visita) */}
      {tutorialAberto && <Tutorial onFechar={fecharTutorial} />}

      {/* FAB de chat do Diego (gate useAssistentesIA dentro do componente) */}
      <ChatAssistant
        assistente="diego"
        nome="Diego"
        avatar={diegoAvatar}
        pageContext="Página Inicial"
        suggestedQuestions={[
          "O que são os status das propostas?",
          "Como funciona o envio de DPS?",
          "Quais são os perfis de acesso?",
          "Como gerenciar pagamentos?",
        ]}
      />
    </div>
  );
}
