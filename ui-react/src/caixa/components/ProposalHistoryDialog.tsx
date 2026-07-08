import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Clock, CheckCircle, AlertCircle, FileText, Mail, CreditCard } from "lucide-react";
import { ScrollArea } from "./ui/scroll-area";

interface ProposalHistoryDialogProps {
  proposalNumber: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface HistoryEvent {
  id: string;
  action: string;
  description: string;
  timestamp: string;
  type: "success" | "info" | "warning";
  icon: React.ReactNode;
}

const ProposalHistoryDialog = ({
  proposalNumber,
  open,
  onOpenChange,
}: ProposalHistoryDialogProps) => {
  // Mock history data - in production this would come from an API
  const historyEvents: HistoryEvent[] = [
    {
      id: "1",
      action: "Proposta Criada",
      description: "Proposta criada no sistema",
      timestamp: "2024-01-15 10:30:00",
      type: "success",
      icon: <FileText className="h-4 w-4" />,
    },
    {
      id: "2",
      action: "Link de Assinatura Enviado",
      description: "Link enviado via E-mail e SMS",
      timestamp: "2024-01-15 10:35:00",
      type: "info",
      icon: <Mail className="h-4 w-4" />,
    },
    {
      id: "3",
      action: "Proposta Assinada",
      description: "Cliente assinou a proposta digitalmente",
      timestamp: "2024-01-16 14:20:00",
      type: "success",
      icon: <CheckCircle className="h-4 w-4" />,
    },
    {
      id: "4",
      action: "Pagamento Processado",
      description: "Pagamento via PIX confirmado",
      timestamp: "2024-01-16 15:45:00",
      type: "success",
      icon: <CreditCard className="h-4 w-4" />,
    },
    {
      id: "5",
      action: "Aguardando DPS",
      description: "Documentação pendente de envio",
      timestamp: "2024-01-17 09:00:00",
      type: "warning",
      icon: <AlertCircle className="h-4 w-4" />,
    },
  ];

  const getEventColor = (type: string) => {
    switch (type) {
      case "success":
        return "border-green text-green";
      case "warning":
        return "border-caixa-orange text-caixa-orange";
      default:
        return "border-caixa-aqua text-caixa-aqua";
    }
  };

  const getEventBg = (type: string) => {
    switch (type) {
      case "success":
        return "bg-green/10";
      case "warning":
        return "bg-caixa-orange/10";
      default:
        return "bg-caixa-aqua/10";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-card border-caixa-aqua/30 max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-caixa-aqua flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Histórico da Proposta {proposalNumber}
          </DialogTitle>
        </DialogHeader>

        <ScrollArea className="h-[500px] pr-4">
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-border" />

            <div className="space-y-4">
              {historyEvents.map((event, index) => (
                <div
                  key={event.id}
                  className="relative pl-10 animate-slide-in-bottom"
                  style={{ animationDelay: `${index * 0.1}s` }}
                >
                  {/* Timeline dot */}
                  <div
                    className={`absolute left-0 w-10 h-10 rounded-full border-2 ${getEventColor(
                      event.type
                    )} ${getEventBg(event.type)} flex items-center justify-center`}
                  >
                    {event.icon}
                  </div>

                  {/* Event card */}
                  <div className={`p-4 rounded-lg border ${getEventColor(event.type)} ${getEventBg(event.type)}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <h4 className="font-semibold text-foreground">{event.action}</h4>
                        <p className="text-sm text-muted-foreground mt-1">{event.description}</p>
                      </div>
                      <time className="text-xs text-muted-foreground whitespace-nowrap">
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
              ))}
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
};

export default ProposalHistoryDialog;
