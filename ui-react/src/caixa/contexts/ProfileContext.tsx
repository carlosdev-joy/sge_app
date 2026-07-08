// Perfil do Caixa Seguro derivado do RBAC real do Orquestra (Fase 1):
// quem tem o recurso `caixa_seguro_operacional` é "operational"; os demais
// usuários da seção são "employee" (Funcionário CAIXA, acesso limitado).
// Substitui o toggle demo client-side da POC Lovable — a interface consumida
// pelas páginas (useProfile/hasAccess/canSendSensitization) foi preservada.
import { createContext, useContext, type ReactNode } from "react";
import { useAuthStore } from "../../store/auth";

type ProfileType = "operational" | "employee";

interface ProfileContextType {
  profile: ProfileType;
  hasAccess: (feature: string) => boolean;
  canSendSensitization: () => boolean;
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined);

// Funcionário CAIXA enxerga só o subconjunto abaixo (herdado da POC).
const EMPLOYEE_ACCESS = [
  "awaiting_payment",
  "pending_signature",
  "pending_documentation",
  "pending_dps",
  "declined",
  "refund_pending",
  "refund_scheduled",
  "valores_programados",
  "sensitization_monitoring_view",
  "sales_tactical_limited",
];

export const ProfileProvider = ({ children }: { children: ReactNode }) => {
  const perms = useAuthStore((s) => s.user?.permissoes) ?? [];
  const profile: ProfileType = perms.includes("caixa_seguro_operacional")
    ? "operational"
    : "employee";

  const hasAccess = (feature: string) =>
    profile === "operational" || EMPLOYEE_ACCESS.includes(feature);

  const canSendSensitization = () => profile === "operational";

  return (
    <ProfileContext.Provider value={{ profile, hasAccess, canSendSensitization }}>
      {children}
    </ProfileContext.Provider>
  );
};

export const useProfile = () => {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error("useProfile must be used within ProfileProvider");
  }
  return context;
};
