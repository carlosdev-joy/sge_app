// "Enviar via canais" no DS nativo — porte do SendOptionsDialog shadcn sobre
// Modal + Checkbox nativos (F7). Consumido pelo CreditCardLinkDialog; na
// F8 também pelo fluxo de pagamento. Mesmos canais e simulação de 2s.
import { useState } from "react";
import { Mail, MessageSquare, Phone } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Checkbox";
import { toast } from "../../components/ui/Toast";

interface SendOptionsDialogProps {
  title: string;
  description: string;
  open: boolean;
  onClose: () => void;
  clientEmail?: string;
  clientPhone?: string;
}

export default function SendOptionsDialog({ title, description, open, onClose, clientEmail, clientPhone }: SendOptionsDialogProps) {
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Todo caminho de fechar passa aqui e zera o fluxo.
  const handleClose = () => {
    setSelectedOptions([]);
    setIsLoading(false);
    onClose();
  };

  const handleToggleOption = (option: string) => {
    setSelectedOptions((prev) => (prev.includes(option) ? prev.filter((o) => o !== option) : [...prev, option]));
  };

  const handleSend = () => {
    if (selectedOptions.length === 0) {
      toast.error("Escolha pelo menos um canal de envio.");
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      const channels = selectedOptions.join(", ");
      toast.success(`${description} enviado via ${channels}.`);
      handleClose();
    }, 2000);
  };

  const canais: { id: string; icon: React.ReactNode; rotulo: string }[] = [
    { id: "email", icon: <Mail className="h-5 w-5 text-[#1A5FA8] dark:text-blue-400" />, rotulo: clientEmail || "E-mail" },
    { id: "sms", icon: <Phone className="h-5 w-5 text-[#1A5FA8] dark:text-blue-400" />, rotulo: clientPhone || "SMS" },
    { id: "whatsapp", icon: <MessageSquare className="h-5 w-5 text-[#1A5FA8] dark:text-blue-400" />, rotulo: "WhatsApp" },
  ];

  return (
    <Modal open={open} onClose={handleClose} title={title} size="md">
      <div className="space-y-6">
        <p className="text-center text-dim">{description}</p>

        <div className="space-y-4">
          {canais.map((canal) => (
            <div key={canal.id} className="p-4 border border-edge rounded-lg hover:border-blue-400 transition-colors">
              <Checkbox
                checked={selectedOptions.includes(canal.id)}
                onChange={() => handleToggleOption(canal.id)}
                label={
                  <span className="flex items-center gap-2">
                    {canal.icon}
                    {canal.rotulo}
                  </span>
                }
              />
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleClose} className="flex-1 justify-center">
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={handleSend}
            disabled={isLoading || selectedOptions.length === 0}
            loading={isLoading}
            className="flex-1 justify-center"
          >
            {isLoading ? "Enviando..." : "Enviar"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
