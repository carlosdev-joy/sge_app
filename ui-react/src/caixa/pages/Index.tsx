import MenuButton from "../components/MenuButton";
import ProposalWorkflowSheet from "../components/ProposalWorkflowSheet";
import SearchProposals from "../components/SearchProposals";
import DiegoAssistant from "../components/DiegoAssistant";
import Tutorial from "../components/Tutorial";
import TutorialRestart from "../components/TutorialRestart";
import { Badge } from "../components/ui/badge";
import { useProfile } from "../contexts/ProfileContext";
import { Users, User } from "lucide-react";

const Index = () => {
  const { profile } = useProfile();

  return (
    <div className="min-h-screen bg-background">
      
      <main className="container mx-auto px-6 py-8 max-w-7xl">
        <div className="mb-6 flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <MenuButton />
            <ProposalWorkflowSheet />
            <TutorialRestart />
          </div>
          
          {/* Perfil vem do RBAC (caixa_seguro_operacional) — sem toggle demo */}
          <Badge variant="outline" className="gap-2 px-3 py-1.5 text-sm border-primary/50">
            {profile === "operational" ? (
              <>
                <Users className="h-4 w-4" />
                <span>Perfil Operacional</span>
              </>
            ) : (
              <>
                <User className="h-4 w-4" />
                <span>Perfil Funcionário CAIXA</span>
              </>
            )}
          </Badge>
        </div>
        
        <SearchProposals />
      </main>
      
      <DiegoAssistant 
        pageContext="Página Inicial"
        suggestedQuestions={[
          "O que são os status das propostas?",
          "Como funciona o envio de DPS?",
          "Quais são os perfis de acesso?",
          "Como gerenciar pagamentos?",
        ]}
      />
      <Tutorial />
    </div>
  );
};

export default Index;
