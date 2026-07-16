// Histórico da proposta no DS nativo — porte do ProposalHistoryDialog shadcn
// sobre o Modal do Orquestra (mesmos eventos mock e mesma linha do tempo
// vertical). O scroll fica no corpo do Modal (max-h-[90vh]), sem ScrollArea.
import { Clock, CheckCircle, AlertCircle, FileText, Mail, CreditCard } from "lucide-react";
import { Modal } from "../../components/ui/Modal";

interface ProposalHistoryDialogOrqProps {
  proposalNumber: string;
  open: boolean;
  onClose: () => void;
}

interface HistoryEvent {
  id: string;
  action: string;
  description: string;
  timestamp: string;
  type: "success" | "info" | "warning";
  icon: React.ReactNode;
}

// Mesmos eventos mock da tela original — em produção viriam de uma API.
const historyEvents: HistoryEvent[] = [
  { id: "1", action: "Proposta Criada", description: "Proposta criada no sistema", timestamp: "2024-01-15 10:30:00", type: "success", icon: <FileText className="h-4 w-4" /> },
  { id: "2", action: "Link de Assinatura Enviado", description: "Link enviado via E-mail e SMS", timestamp: "2024-01-15 10:35:00", type: "info", icon: <Mail className="h-4 w-4" /> },
  { id: "3", action: "Proposta Assinada", description: "Cliente assinou a proposta digitalmente", timestamp: "2024-01-16 14:20:00", type: "success", icon: <CheckCircle className="h-4 w-4" /> },
  { id: "4", action: "Pagamento Processado", description: "Pagamento via PIX confirmado", timestamp: "2024-01-16 15:45:00", type: "success", icon: <CreditCard className="h-4 w-4" /> },
  { id: "5", action: "Aguardando DPS", description: "Documentação pendente de envio", timestamp: "2024-01-17 09:00:00", type: "warning", icon: <AlertCircle className="h-4 w-4" /> },
];

// success=verde, warning=laranja CAIXA, info=azul — bordas/textos com par
// claro+escuro (fora do .caixa-theme não há vars --green/--caixa-orange).
const EVENT_STYLE: Record<HistoryEvent["type"], { ring: string; bg: string }> = {
  success: { ring: "border-emerald-500 text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-500/10" },
  warning: { ring: "border-[#F26B00] text-[#F26B00]", bg: "bg-[#F26B00]/10" },
  info: { ring: "border-blue-500 text-blue-600 dark:text-blue-400", bg: "bg-blue-500/10" },
};

export default function ProposalHistoryDialogOrq({ proposalNumber, open, onClose }: ProposalHistoryDialogOrqProps) {
  return (
    <Modal open={open} onClose={onClose} title={`Histórico da Proposta ${proposalNumber}`} size="lg">
      <div className="flex items-center gap-2 text-sm text-dim mb-4">
        <Clock className="h-4 w-4" />
        Linha do tempo de eventos da proposta.
      </div>

      <div className="relative">
        {/* Linha vertical da timeline */}
        <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-edge" />

        <div className="space-y-4">
          {historyEvents.map((event) => {
            const style = EVENT_STYLE[event.type];
            return (
              <div key={event.id} className="relative pl-12">
                {/* Ponto da timeline */}
                <div className={`absolute left-0 w-10 h-10 rounded-full border-2 ${style.ring} ${style.bg} flex items-center justify-center`}>
                  {event.icon}
                </div>

                {/* Card do evento */}
                <div className={`p-4 rounded-lg border ${style.ring} ${style.bg}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <h4 className="font-semibold text-ink">{event.action}</h4>
                      <p className="text-sm text-dim mt-1">{event.description}</p>
                    </div>
                    <time className="text-xs text-dim whitespace-nowrap">
                      {new Date(event.timestamp).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}
