import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Loader2, Copy, Check, Mail } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import SendOptionsDialog from "./SendOptionsDialog";

interface CreditCardLinkDialogProps {
  proposal: {
    number: string;
    insuredName: string;
    value: string;
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CreditCardLinkDialog = ({ proposal, open, onOpenChange }: CreditCardLinkDialogProps) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [linkGenerated, setLinkGenerated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showSendOptions, setShowSendOptions] = useState(false);
  const { toast } = useToast();

  const generatedLink = `https://pagamento.seguradora.com.br/cc/${proposal.number}`;

  const handleGenerateLink = () => {
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setLinkGenerated(true);
      toast({
        title: "Link gerado com sucesso",
        description: "O link de pagamento por cartão de crédito foi criado.",
      });
    }, 2000);
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(generatedLink);
    setCopied(true);
    toast({
      title: "Link copiado",
      description: "O link foi copiado para a área de transferência.",
    });
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Gerar Link de Pagamento - Cartão de Crédito
          </DialogTitle>
        </DialogHeader>

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
              <span className="text-sm text-muted-foreground">Valor:</span>
              <span className="font-semibold text-primary">{proposal.value}</span>
            </div>
          </div>

          {!linkGenerated ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground text-center">
                O link de pagamento conterá um formulário seguro para captura dos dados do cartão:
              </p>
              <div className="bg-muted/50 p-4 rounded-lg space-y-2 text-sm">
                <p>• Nome completo</p>
                <p>• CPF</p>
                <p>• Número do cartão</p>
                <p>• Data de validade</p>
                <p>• Código de segurança (CVV)</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 p-4 rounded-lg">
                <Label className="text-sm font-semibold mb-2 block">Link de Pagamento:</Label>
                <div className="flex gap-2">
                  <Input
                    value={generatedLink}
                    readOnly
                    className="flex-1 bg-white dark:bg-gray-900"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleCopyLink}
                    className="shrink-0"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-600" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
              
              <div className="space-y-3">
                <Label className="text-sm font-semibold">Enviar link via:</Label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      setShowSendOptions(true);
                    }}
                    className="bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90"
                  >
                    <Mail className="h-4 w-4 mr-2" />
                    Enviar por E-mail/SMS/WhatsApp
                  </Button>
                </div>
              </div>
              
              <p className="text-xs text-muted-foreground text-center">
                Compartilhe este link com o cliente para efetuar o pagamento
              </p>
            </div>
          )}

          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                setLinkGenerated(false);
                setCopied(false);
              }}
              className="flex-1"
            >
              {linkGenerated ? "Fechar" : "Cancelar"}
            </Button>
            {!linkGenerated && (
              <Button
                onClick={handleGenerateLink}
                disabled={isGenerating}
                className="flex-1 bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Gerando...
                  </>
                ) : (
                  "Gerar Link"
                )}
              </Button>
            )}
          </div>
        </div>
        
        <SendOptionsDialog
          title="Enviar Link de Pagamento"
          description="Selecione os canais para envio do link"
          open={showSendOptions}
          onOpenChange={setShowSendOptions}
        />
      </DialogContent>
    </Dialog>
  );
};

export default CreditCardLinkDialog;
