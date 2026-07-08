import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { Mail, MessageSquare, Phone, Loader2 } from "lucide-react";
import { useToast } from "../hooks/use-toast";

interface SendOptionsDialogProps {
  title: string;
  description: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientEmail?: string;
  clientPhone?: string;
}

const SendOptionsDialog = ({ title, description, open, onOpenChange, clientEmail, clientPhone }: SendOptionsDialogProps) => {
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const handleToggleOption = (option: string) => {
    setSelectedOptions((prev) =>
      prev.includes(option) ? prev.filter((o) => o !== option) : [...prev, option]
    );
  };

  const handleSend = () => {
    if (selectedOptions.length === 0) {
      toast({
        title: "Selecione uma opção",
        description: "Escolha pelo menos um canal de envio.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      const channels = selectedOptions.join(", ");
      toast({
        title: "Enviado com sucesso",
        description: `${description} enviado via ${channels}.`,
      });
      onOpenChange(false);
      setSelectedOptions([]);
    }, 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            {title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          <p className="text-center text-muted-foreground">{description}</p>

          <div className="space-y-4">
            <div className="flex items-center space-x-3 p-4 border rounded-lg hover:bg-accent/50">
              <Checkbox
                id="email"
                checked={selectedOptions.includes("email")}
                onCheckedChange={() => handleToggleOption("email")}
              />
              <Label
                htmlFor="email"
                className="flex items-center gap-2 flex-1 cursor-pointer"
              >
                <Mail className="h-5 w-5 text-primary" />
                <span>{clientEmail ? clientEmail : "E-mail"}</span>
              </Label>
            </div>

            <div className="flex items-center space-x-3 p-4 border rounded-lg hover:bg-accent/50">
              <Checkbox
                id="sms"
                checked={selectedOptions.includes("sms")}
                onCheckedChange={() => handleToggleOption("sms")}
              />
              <Label
                htmlFor="sms"
                className="flex items-center gap-2 flex-1 cursor-pointer"
              >
                <Phone className="h-5 w-5 text-primary" />
                <span>{clientPhone ? clientPhone : "SMS"}</span>
              </Label>
            </div>

            <div className="flex items-center space-x-3 p-4 border rounded-lg hover:bg-accent/50">
              <Checkbox
                id="whatsapp"
                checked={selectedOptions.includes("whatsapp")}
                onCheckedChange={() => handleToggleOption("whatsapp")}
              />
              <Label
                htmlFor="whatsapp"
                className="flex items-center gap-2 flex-1 cursor-pointer"
              >
                <MessageSquare className="h-5 w-5 text-primary" />
                <span>WhatsApp</span>
              </Label>
            </div>
          </div>

          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                setSelectedOptions([]);
              }}
              className="flex-1"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSend}
              disabled={isLoading || selectedOptions.length === 0}
              className="flex-1 bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Enviando...
                </>
              ) : (
                "Enviar"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SendOptionsDialog;
