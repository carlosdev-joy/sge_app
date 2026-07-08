import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Button } from "./ui/button";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";
import { Label } from "./ui/label";
import { useToast } from "../hooks/use-toast";
import { Loader2, ExternalLink, Mail, MessageSquare, Phone } from "lucide-react";

interface DPSLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proposalNumber: string;
  insuredName: string;
}

type SendMethod = "email" | "sms" | "whatsapp";

const DPSLinkDialog = ({ open, onOpenChange, proposalNumber, insuredName }: DPSLinkDialogProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [sendMethod, setSendMethod] = useState<SendMethod>("email");
  const { toast } = useToast();

  const handleSendLink = async () => {
    setIsLoading(true);
    
    // Simulate API call to Samplemed integration
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    setIsLoading(false);
    
    const methodLabels = {
      email: "E-mail",
      sms: "SMS",
      whatsapp: "WhatsApp"
    };
    
    toast({
      title: "Link enviado com sucesso!",
      description: `Link para DPS enviado via ${methodLabels[sendMethod]} ao Samplemed para a proposta ${proposalNumber}`,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ExternalLink className="h-5 w-5" />
            Enviar Link DPS - Samplemed
          </DialogTitle>
          <DialogDescription>
            Enviar link para preenchimento da DPS através da integração com Samplemed
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="bg-muted p-4 rounded-lg space-y-2">
            <div>
              <span className="text-sm text-muted-foreground">Proposta:</span>
              <p className="font-semibold">{proposalNumber}</p>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Segurado:</span>
              <p className="font-semibold">{insuredName}</p>
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-base font-semibold">Selecione o método de envio:</Label>
            <RadioGroup value={sendMethod} onValueChange={(value) => setSendMethod(value as SendMethod)}>
              <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                <RadioGroupItem value="email" id="email" />
                <Label htmlFor="email" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <Mail className="h-4 w-4 text-blue-600" />
                  <span>E-mail</span>
                </Label>
              </div>
              <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                <RadioGroupItem value="sms" id="sms" />
                <Label htmlFor="sms" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <MessageSquare className="h-4 w-4 text-green-600" />
                  <span>SMS</span>
                </Label>
              </div>
              <div className="flex items-center space-x-2 p-3 border rounded-lg hover:bg-accent/50 cursor-pointer">
                <RadioGroupItem value="whatsapp" id="whatsapp" />
                <Label htmlFor="whatsapp" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <Phone className="h-4 w-4 text-green-500" />
                  <span>WhatsApp</span>
                </Label>
              </div>
            </RadioGroup>
          </div>

          <div className="bg-blue-50 dark:bg-blue-950/20 p-4 rounded-lg border border-blue-200 dark:border-blue-800">
            <p className="text-sm text-blue-900 dark:text-blue-100">
              <strong>Integração Samplemed:</strong> O link será enviado automaticamente para o portal Samplemed para preenchimento da Declaração Pessoal de Saúde (DPS).
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSendLink}
            disabled={isLoading}
            className="bg-[hsl(var(--blue))] hover:bg-[hsl(var(--blue))]/90"
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Enviar para Samplemed
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DPSLinkDialog;
