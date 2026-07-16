// "Enviar Link DPS - Samplemed" no DS nativo — porte do DPSLinkDialog shadcn
// sobre Modal + RadioGroup nativos (F7). Mesmo fluxo (método de envio →
// simulação de 2s → toast) e mesmos textos.
import { useState } from "react";
import { ExternalLink, Mail, MessageSquare, Phone } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { RadioGroup, RadioItem } from "../../components/ui/RadioGroup";
import { toast } from "../../components/ui/Toast";

interface DPSLinkDialogOrqProps {
  open: boolean;
  onClose: () => void;
  proposalNumber: string;
  insuredName: string;
}

type SendMethod = "email" | "sms" | "whatsapp";

const METHOD_LABELS: Record<SendMethod, string> = {
  email: "E-mail",
  sms: "SMS",
  whatsapp: "WhatsApp",
};

export default function DPSLinkDialogOrq({ open, onClose, proposalNumber, insuredName }: DPSLinkDialogOrqProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [sendMethod, setSendMethod] = useState<SendMethod>("email");

  const handleSendLink = async () => {
    setIsLoading(true);
    // Simula a chamada à integração Samplemed (mock, como na tela original)
    await new Promise((resolve) => setTimeout(resolve, 2000));
    setIsLoading(false);
    toast.success(`Link para DPS enviado via ${METHOD_LABELS[sendMethod]} ao Samplemed para a proposta ${proposalNumber}`);
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="Enviar Link DPS - Samplemed" size="md">
      <div className="space-y-4">
        <p className="flex items-center gap-2 text-sm text-dim">
          <ExternalLink className="h-4 w-4" />
          Enviar link para preenchimento da DPS através da integração com Samplemed
        </p>

        <div className="bg-canvas border border-edge p-4 rounded-lg space-y-2">
          <div>
            <span className="text-sm text-dim">Proposta:</span>
            <p className="font-semibold text-ink">{proposalNumber}</p>
          </div>
          <div>
            <span className="text-sm text-dim">Segurado:</span>
            <p className="font-semibold text-ink">{insuredName}</p>
          </div>
        </div>

        <div className="space-y-3">
          <p className="text-base font-semibold text-ink">Selecione o método de envio:</p>
          <RadioGroup value={sendMethod} onValueChange={(v) => setSendMethod(v as SendMethod)} label="Método de envio">
            <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
              <RadioItem
                value="email"
                className="flex-1"
                label={
                  <span className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    E-mail
                  </span>
                }
              />
            </div>
            <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
              <RadioItem
                value="sms"
                className="flex-1"
                label={
                  <span className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                    SMS
                  </span>
                }
              />
            </div>
            <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
              <RadioItem
                value="whatsapp"
                className="flex-1"
                label={
                  <span className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-emerald-500" />
                    WhatsApp
                  </span>
                }
              />
            </div>
          </RadioGroup>
        </div>

        <div className="bg-blue-50 dark:bg-blue-950/20 p-4 rounded-lg border border-blue-200 dark:border-blue-800">
          <p className="text-sm text-blue-900 dark:text-blue-100">
            <strong>Integração Samplemed:</strong> O link será enviado automaticamente para o portal Samplemed para
            preenchimento da Declaração Pessoal de Saúde (DPS).
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleSendLink} disabled={isLoading} loading={isLoading}>
            Enviar para Samplemed
          </Button>
        </div>
      </div>
    </Modal>
  );
}
