// Compartilhar proposta no DS nativo — porte do ProposalShareDialog shadcn
// sobre Modal + Checkbox nativos (mesmos canais E-mail/SMS/WhatsApp e mesmo
// envio simulado de 1,5s). Contrato do Checkbox nativo: checked/onChange.
import { useState } from "react";
import { Mail, MessageSquare, Share2 } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Checkbox";
import { toast } from "../../components/ui/Toast";

interface ProposalShareDialogProps {
  proposalNumber: string;
  clientEmail?: string;
  clientPhone?: string;
  open: boolean;
  onClose: () => void;
}

export default function ProposalShareDialog({
  proposalNumber,
  clientEmail,
  clientPhone,
  open,
  onClose,
}: ProposalShareDialogProps) {
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleToggleOption = (option: string) => {
    setSelectedOptions((prev) =>
      prev.includes(option) ? prev.filter((o) => o !== option) : [...prev, option]
    );
  };

  const handleShare = () => {
    if (selectedOptions.length === 0) {
      toast.error("Selecione ao menos uma opção de envio do link da proposta.");
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      const channels = selectedOptions.join(", ");
      toast.success(`O link da proposta ${proposalNumber} foi enviado via ${channels}.`);
      onClose();
      setSelectedOptions([]);
    }, 1500);
  };

  const proposalLink = `https://seguros.caixa.gov.br/proposta/${proposalNumber}`;

  const canais: { id: string; icon: React.ReactNode; nome: string; destino?: string }[] = [
    ...(clientEmail ? [{ id: "E-mail", icon: <Mail className="h-4 w-4 text-blue-500" />, nome: "E-mail", destino: clientEmail }] : []),
    ...(clientPhone ? [{ id: "SMS", icon: <MessageSquare className="h-4 w-4 text-[#F26B00]" />, nome: "SMS", destino: clientPhone }] : []),
    ...(clientPhone ? [{ id: "WhatsApp", icon: <MessageSquare className="h-4 w-4 text-emerald-500" />, nome: "WhatsApp", destino: clientPhone }] : []),
  ];

  return (
    <Modal open={open} onClose={onClose} title="Compartilhar Proposta" size="md">
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-dim">
          <Share2 className="h-4 w-4" />
          Envie os dados da proposta por e-mail ou WhatsApp.
        </div>

        <div className="bg-canvas border border-edge p-3 rounded-lg">
          <p className="text-sm text-dim mb-1">Link da Proposta:</p>
          <p className="text-sm font-mono text-ink break-all">{proposalLink}</p>
        </div>

        <div className="space-y-3">
          <p className="text-sm font-medium text-ink">Selecione os canais de envio:</p>

          {canais.map((canal) => (
            <div
              key={canal.id}
              className="p-3 bg-canvas rounded-lg border border-edge hover:border-blue-400 transition-colors"
            >
              <Checkbox
                checked={selectedOptions.includes(canal.id)}
                onChange={() => handleToggleOption(canal.id)}
                label={
                  <span className="flex items-center gap-2">
                    {canal.icon}
                    <span>
                      <span className="block text-ink">{canal.nome}</span>
                      <span className="block text-xs text-dim">{canal.destino}</span>
                    </span>
                  </span>
                }
              />
            </div>
          ))}
        </div>

        <div className="flex gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} className="flex-1 justify-center">
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={handleShare}
            disabled={selectedOptions.length === 0 || isLoading}
            loading={isLoading}
            className="flex-1 justify-center"
          >
            {isLoading ? "Enviando..." : "Compartilhar"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
