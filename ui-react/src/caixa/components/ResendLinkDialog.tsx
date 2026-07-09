import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";
import { Label } from "./ui/label";
import { Check, Loader2 } from "lucide-react";

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
  onOpenChange: (open: boolean) => void;
}

type SendMethod = "email" | "phone" | "whatsapp" | "";
type DialogState = "selection" | "confirmation" | "loading" | "success";

const ResendLinkDialog = ({ proposal, open, onOpenChange }: ResendLinkDialogProps) => {
  const [sendMethod, setSendMethod] = useState<SendMethod>("");
  const [dialogState, setDialogState] = useState<DialogState>("selection");

  const handleSend = () => {
    setDialogState("confirmation");
  };

  const handleConfirm = () => {
    setDialogState("loading");
    setTimeout(() => {
      setDialogState("success");
      setTimeout(() => {
        onOpenChange(false);
        // Reset state when dialog closes
        setTimeout(() => {
          setSendMethod("");
          setDialogState("selection");
        }, 300);
      }, 2000);
    }, 2000);
  };

  const handleCancel = () => {
    setDialogState("selection");
  };

  const getMethodLabel = () => {
    if (sendMethod === "email") return "e-mail";
    if (sendMethod === "phone") return "telefone";
    return "WhatsApp";
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Reenviar Link de Assinatura
          </DialogTitle>
          <DialogDescription className="sr-only">Reenvie ao cliente o link de assinatura da proposta.</DialogDescription>
        </DialogHeader>

        {dialogState === "selection" && (
          <div className="space-y-6">
            <div className="bg-accent/30 p-4 rounded-lg space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Proposta:</span>
                <span className="font-semibold">{proposal.number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Nome:</span>
                <span className="font-semibold">{proposal.insuredName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">CPF:</span>
                <span className="font-semibold">{proposal.cpf}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Valor:</span>
                <span className="font-semibold text-primary">{proposal.value}</span>
              </div>
            </div>

            <div>
              <p className="font-semibold mb-4 text-center">Como você deseja reenviar o Link?</p>
              <RadioGroup value={sendMethod} onValueChange={(value) => setSendMethod(value as SendMethod)}>
                <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                  <RadioGroupItem value="email" id="email" />
                  <Label htmlFor="email" className="flex-1 cursor-pointer">{proposal.email}</Label>
                </div>
                <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                  <RadioGroupItem value="phone" id="phone" />
                  <Label htmlFor="phone" className="flex-1 cursor-pointer">{proposal.phone}</Label>
                </div>
                <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                  <RadioGroupItem value="whatsapp" id="whatsapp" />
                  <Label htmlFor="whatsapp" className="flex-1 cursor-pointer">WhatsApp: {proposal.phone}</Label>
                </div>
              </RadioGroup>
            </div>

            <Button
              onClick={handleSend}
              disabled={!sendMethod}
              className="w-full bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white"
            >
              Enviar
            </Button>
          </div>
        )}

        {dialogState === "confirmation" && (
          <div className="space-y-6 py-4">
            <p className="text-center text-lg">
              Confirma o reenvio para o {getMethodLabel()}: <span className="font-bold">{sendMethod === 'email' ? proposal.email : (sendMethod === 'phone' ? proposal.phone : `WhatsApp ${proposal.phone}`)}</span>?
            </p>
            <div className="flex gap-3">
              <Button
                onClick={handleCancel}
                variant="outline"
                className="flex-1"
              >
                Não
              </Button>
              <Button
                onClick={handleConfirm}
                className="flex-1 bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white"
              >
                Sim
              </Button>
            </div>
          </div>
        )}

        {dialogState === "loading" && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <Loader2 className="h-12 w-12 animate-spin text-[hsl(var(--orange))]" />
            <p className="text-muted-foreground">Enviando link...</p>
          </div>
        )}

        {dialogState === "success" && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <div className="rounded-full bg-[hsl(var(--green))] p-3">
              <Check className="h-12 w-12 text-white" />
            </div>
            <p className="font-semibold text-lg text-center">Link reenviado com sucesso!</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ResendLinkDialog;
