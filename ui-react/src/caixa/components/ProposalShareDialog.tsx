import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { toast } from "../hooks/use-toast";
import { Mail, MessageSquare, Share2 } from "lucide-react";
import { Checkbox } from "./ui/checkbox";
import { useState } from "react";

interface ProposalShareDialogProps {
  proposalNumber: string;
  clientEmail?: string;
  clientPhone?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const ProposalShareDialog = ({
  proposalNumber,
  clientEmail,
  clientPhone,
  open,
  onOpenChange,
}: ProposalShareDialogProps) => {
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleToggleOption = (option: string) => {
    setSelectedOptions((prev) =>
      prev.includes(option)
        ? prev.filter((o) => o !== option)
        : [...prev, option]
    );
  };

  const handleShare = () => {
    if (selectedOptions.length === 0) {
      toast({
        title: "Selecione ao menos uma opção",
        description: "Escolha como deseja compartilhar o link da proposta.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);

    setTimeout(() => {
      setIsLoading(false);
      const channels = selectedOptions.join(", ");
      toast({
        title: "Link Compartilhado",
        description: `O link da proposta ${proposalNumber} foi enviado via ${channels}.`,
      });
      onOpenChange(false);
      setSelectedOptions([]);
    }, 1500);
  };

  const proposalLink = `https://seguros.caixa.gov.br/proposta/${proposalNumber}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card border-caixa-aqua/30">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-caixa-aqua flex items-center gap-2">
            <Share2 className="h-5 w-5" />
            Compartilhar Proposta
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="bg-muted/30 p-3 rounded-lg">
            <p className="text-sm text-muted-foreground mb-1">Link da Proposta:</p>
            <p className="text-sm font-mono text-foreground break-all">{proposalLink}</p>
          </div>

          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">Selecione os canais de envio:</p>

            {clientEmail && (
              <div className="flex items-center space-x-3 p-3 bg-muted/20 rounded-lg border border-border hover:border-caixa-aqua/50 transition-colors">
                <Checkbox
                  id="email"
                  checked={selectedOptions.includes("E-mail")}
                  onCheckedChange={() => handleToggleOption("E-mail")}
                />
                <label
                  htmlFor="email"
                  className="flex items-center gap-2 text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                >
                  <Mail className="h-4 w-4 text-caixa-aqua" />
                  <div>
                    <p className="text-foreground">E-mail</p>
                    <p className="text-xs text-muted-foreground">{clientEmail}</p>
                  </div>
                </label>
              </div>
            )}

            {clientPhone && (
              <div className="flex items-center space-x-3 p-3 bg-muted/20 rounded-lg border border-border hover:border-caixa-aqua/50 transition-colors">
                <Checkbox
                  id="sms"
                  checked={selectedOptions.includes("SMS")}
                  onCheckedChange={() => handleToggleOption("SMS")}
                />
                <label
                  htmlFor="sms"
                  className="flex items-center gap-2 text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                >
                  <MessageSquare className="h-4 w-4 text-caixa-orange" />
                  <div>
                    <p className="text-foreground">SMS</p>
                    <p className="text-xs text-muted-foreground">{clientPhone}</p>
                  </div>
                </label>
              </div>
            )}

            {clientPhone && (
              <div className="flex items-center space-x-3 p-3 bg-muted/20 rounded-lg border border-border hover:border-caixa-aqua/50 transition-colors">
                <Checkbox
                  id="whatsapp"
                  checked={selectedOptions.includes("WhatsApp")}
                  onCheckedChange={() => handleToggleOption("WhatsApp")}
                />
                <label
                  htmlFor="whatsapp"
                  className="flex items-center gap-2 text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                >
                  <MessageSquare className="h-4 w-4 text-green" />
                  <div>
                    <p className="text-foreground">WhatsApp</p>
                    <p className="text-xs text-muted-foreground">{clientPhone}</p>
                  </div>
                </label>
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1 border-border hover:bg-muted"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleShare}
              disabled={selectedOptions.length === 0 || isLoading}
              className="flex-1 bg-gradient-primary hover:opacity-90 text-white"
            >
              {isLoading ? "Enviando..." : "Compartilhar"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default ProposalShareDialog;
