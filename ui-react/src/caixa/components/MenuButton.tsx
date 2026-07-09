import { Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { useProfile } from "../contexts/ProfileContext";
const MenuButton = () => {
  const navigate = useNavigate();
  const { hasAccess } = useProfile();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 text-primary bg-white border border-primary/20 shadow-sm hover:shadow-md hover:border-primary/40 hover:bg-primary/5 transition-all py-2.5 px-4 rounded-lg">
          <Menu className="h-6 w-6" />
          <span className="font-semibold">Menu</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuItem className="cursor-pointer" onClick={() => navigate("/caixa-seguro")}>
          Consulta Proposta
        </DropdownMenuItem>
        <DropdownMenuItem className="cursor-pointer" onClick={() => navigate("/caixa-seguro/acompanhamento")}>
          Monitoramento Tático de Emissão
        </DropdownMenuItem>
        {hasAccess("ai_operational") && (
          <DropdownMenuItem className="cursor-pointer" onClick={() => navigate("/caixa-seguro/ia-operacional")}>
            Painel de IA Operacional
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default MenuButton;
