// "Reenviar Link de Assinatura" no DS nativo — porte do ResendLinkDialog
// shadcn sobre Modal + RadioGroup nativos (F7). Mesmos 4 estados
// (seleção → confirmação → enviando → sucesso) e mesmos textos; o estado é
// zerado SEMPRE que o modal fecha (o antigo só zerava no caminho de sucesso —
// fechar por Esc no meio reabria na confirmação).
import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { RadioGroup, RadioItem } from "../../components/ui/RadioGroup";

interface Proposal {
  number: string;
  insuredName: string;
  cpf: string;
  value: string;
  email: string;
  phone: string;
}

interface ResendLinkDialogProps {
  proposal: Proposal;
  open: boolean;
  onClose: () => void;
}

type SendMethod = "email" | "phone" | "whatsapp" | "";
type DialogState = "selection" | "confirmation" | "loading" | "success";

export default function ResendLinkDialog({ proposal, open, onClose }: ResendLinkDialogProps) {
  const [sendMethod, setSendMethod] = useState<SendMethod>("");
  const [dialogState, setDialogState] = useState<DialogState>("selection");

  // Todo caminho de fechar (Esc/backdrop/X do Modal e o auto-close do
  // sucesso) passa aqui e zera o fluxo.
  const handleClose = () => {
    setSendMethod("");
    setDialogState("selection");
    onClose();
  };

  const handleConfirm = () => {
    setDialogState("loading");
    setTimeout(() => {
      setDialogState("success");
      setTimeout(() => handleClose(), 2000);
    }, 2000);
  };

  const getMethodLabel = () => {
    if (sendMethod === "email") return "e-mail";
    if (sendMethod === "phone") return "telefone";
    return "WhatsApp";
  };

  return (
    <Modal open={open} onClose={handleClose} title="Reenviar Link de Assinatura" size="md">
      {dialogState === "selection" && (
        <div className="space-y-6">
          <div className="bg-canvas border border-edge p-4 rounded-lg space-y-2">
            <div className="flex justify-between gap-3">
              <span className="text-sm text-dim">Proposta:</span>
              <span className="font-semibold text-ink">{proposal.number}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-sm text-dim">Nome:</span>
              <span className="font-semibold text-ink">{proposal.insuredName}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-sm text-dim">CPF:</span>
              <span className="font-semibold text-ink">{proposal.cpf}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-sm text-dim">Valor:</span>
              <span className="font-semibold text-[#1A5FA8] dark:text-blue-400">{proposal.value}</span>
            </div>
          </div>

          <div>
            <p className="font-semibold text-ink mb-4 text-center">Como você deseja reenviar o Link?</p>
            <RadioGroup value={sendMethod} onValueChange={(v) => setSendMethod(v as SendMethod)} label="Método de reenvio">
              <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="email" label={proposal.email} className="flex-1" />
              </div>
              <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="phone" label={proposal.phone} className="flex-1" />
              </div>
              <div className="flex items-center p-3 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="whatsapp" label={`WhatsApp: ${proposal.phone}`} className="flex-1" />
              </div>
            </RadioGroup>
          </div>

          <Button
            variant="primary"
            onClick={() => setDialogState("confirmation")}
            disabled={!sendMethod}
            className="w-full justify-center"
          >
            Enviar
          </Button>
        </div>
      )}

      {dialogState === "confirmation" && (
        <div className="space-y-6 py-4">
          <p className="text-center text-lg text-ink">
            Confirma o reenvio para o {getMethodLabel()}:{" "}
            <span className="font-bold">
              {sendMethod === "email" ? proposal.email : sendMethod === "phone" ? proposal.phone : `WhatsApp ${proposal.phone}`}
            </span>
            ?
          </p>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setDialogState("selection")} className="flex-1 justify-center">
              Não
            </Button>
            <Button variant="primary" onClick={handleConfirm} className="flex-1 justify-center">
              Sim
            </Button>
          </div>
        </div>
      )}

      {dialogState === "loading" && (
        <div className="flex flex-col items-center justify-center py-8 gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-[#F26B00]" />
          <p className="text-dim">Enviando link...</p>
        </div>
      )}

      {dialogState === "success" && (
        <div className="flex flex-col items-center justify-center py-8 gap-4">
          <div className="rounded-full bg-emerald-600 p-3">
            <Check className="h-12 w-12 text-white" />
          </div>
          <p className="font-semibold text-lg text-center text-ink">Link reenviado com sucesso!</p>
        </div>
      )}
    </Modal>
  );
}
