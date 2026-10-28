// Menu de navegação da seção Caixa Seguro — substituiu o MenuButton shadcn
// na migração. Mesmos destinos e mesmo gate de perfil (ai_operational).
import { Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { DropdownMenu, type DropdownItem } from "../../components/ui/DropdownMenu";
import { useAuthStore } from "../../store/auth";
import { useProfile } from "../contexts/ProfileContext";

export default function MenuButton() {
  const navigate = useNavigate();
  const { hasAccess } = useProfile();
  // Recurso explícito: quem não o recebeu no Admin não vê o item (a lista vazia de
  // permissões NÃO libera, ao contrário de `canAccess` das telas do NAV).
  const verUso = (useAuthStore((s) => s.user?.permissoes) ?? []).includes("caixa_seguro_uso");

  const items: DropdownItem[] = [
    { label: "Consulta Proposta", onSelect: () => navigate("/caixa-seguro") },
    { label: "Monitoramento Tático de Emissão", onSelect: () => navigate("/caixa-seguro/acompanhamento") },
    ...(hasAccess("ai_operational")
      ? [{ label: "Painel de IA Operacional", onSelect: () => navigate("/caixa-seguro/ia-operacional") }]
      : []),
    ...(verUso
      ? [{ label: "Uso do módulo", onSelect: () => navigate("/caixa-seguro/uso") }]
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
