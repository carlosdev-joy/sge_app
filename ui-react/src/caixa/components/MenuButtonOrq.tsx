// Menu de navegação da seção Caixa Seguro para as telas NATIVAS (fora do
// .caixa-theme) — substitui o MenuButton shadcn nas telas migradas. Mesmos
// destinos e mesmo gate de perfil (ai_operational) do original.
import { Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { DropdownMenu, type DropdownItem } from "../../components/ui/DropdownMenu";
import { useProfile } from "../contexts/ProfileContext";

export default function MenuButtonOrq() {
  const navigate = useNavigate();
  const { hasAccess } = useProfile();

  const items: DropdownItem[] = [
    { label: "Consulta Proposta", onSelect: () => navigate("/caixa-seguro") },
    { label: "Monitoramento Tático de Emissão", onSelect: () => navigate("/caixa-seguro/acompanhamento") },
    ...(hasAccess("ai_operational")
      ? [{ label: "Painel de IA Operacional", onSelect: () => navigate("/caixa-seguro/ia-operacional") }]
      : []),
  ];

  return (
    <DropdownMenu
      trigger={
        <>
          <Menu size={16} />
          <span>Menu</span>
        </>
      }
      items={items}
    />
  );
}
