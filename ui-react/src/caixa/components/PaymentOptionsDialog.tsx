import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";
import { Loader2, FileText, QrCode, CreditCard, Send } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import SendOptionsDialog from "./SendOptionsDialog";
import CreditCardLinkDialog from "./CreditCardLinkDialog";

interface PaymentOptionsDialogProps {
  proposal: {
    number: string;
    insuredName: string;
    value: string;
    paymentMethod: "boleto" | "debit" | "credit";
    email: string;
    phone: string;
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const PaymentOptionsDialog = ({ proposal, open, onOpenChange }: PaymentOptionsDialogProps) => {
  const [selectedOption, setSelectedOption] = useState<"" | "boleto" | "pix" | "debit" | "credit">("");
  const [isLoading, setIsLoading] = useState(false);
  const [showQRCode, setShowQRCode] = useState(false);
  const [showCreditForm, setShowCreditForm] = useState(false);
  const [showSendOptions, setShowSendOptions] = useState(false);
  const [sendOptionsType, setSendOptionsType] = useState<"boleto" | "pix">("boleto");
  const [showCreditCardDialog, setShowCreditCardDialog] = useState(false);
  const [creditData, setCreditData] = useState({
    bank: "104 - Caixa Econômica Federal",
    agency: "",
    operation: "",
    account: "",
  });
  const { toast } = useToast();

  const handleGenerateBoleto = () => {
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      // Simulate PDF download
      const link = document.createElement('a');
      link.href = '#';
      link.download = `boleto_${proposal.insuredName.replace(/\s+/g, '_')}.pdf`;
      toast({
        title: "Boleto gerado com sucesso",
        description: `boleto_${proposal.insuredName.replace(/\s+/g, '_')}.pdf`,
      });
      setSendOptionsType("boleto");
      setShowSendOptions(true);
    }, 2000);
  };

  const handleGeneratePix = () => {
    setShowQRCode(true);
  };

  const handleShowCreditForm = () => {
    setShowCreditForm(true);
  };

  const handleSubmitCredit = () => {
    if (!creditData.agency || !creditData.operation || !creditData.account) {
      toast({
        title: "Campos obrigatórios",
        description: "Preencha todos os campos para continuar.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast({
        title: "Solicitação enviada",
        description: "A alteração para crédito em conta foi registrada.",
      });
      onOpenChange(false);
    }, 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Alterar forma de pagamento
          </DialogTitle>
          <DialogDescription className="sr-only">Escolha a nova forma de pagamento da proposta.</DialogDescription>
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
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Forma de Pagamento atual:</span>
              <span className="font-semibold">
                {proposal.paymentMethod === "boleto" ? "Boleto" : 
                 proposal.paymentMethod === "debit" ? "Débito em Conta" :
                 "Crédito em Conta"}
              </span>
            </div>
          </div>

          {!showQRCode && !showCreditForm && (
            <RadioGroup value={selectedOption} onValueChange={(value) => setSelectedOption(value as any)}>
              {/* Always show all payment options */}
              <div className="flex items-center space-x-2 p-4 border rounded-lg hover:bg-accent/50">
                <RadioGroupItem value="boleto" id="boleto_all" />
                <Label htmlFor="boleto_all" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <FileText className="h-5 w-5" />
                  Gerar Boleto
                </Label>
              </div>

              <div className="flex items-center space-x-2 p-4 border rounded-lg hover:bg-accent/50">
                <RadioGroupItem value="pix" id="pix_all" />
                <Label htmlFor="pix_all" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <QrCode className="h-5 w-5" />
                  Pagamento via PIX
                </Label>
              </div>

              <div className="flex items-center space-x-2 p-4 border rounded-lg hover:bg-accent/50">
                <RadioGroupItem value="debit" id="debit_all" />
                <Label htmlFor="debit_all" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <CreditCard className="h-5 w-5" />
                  Alterar para Débito em Conta
                </Label>
              </div>

              <div className="flex items-center space-x-2 p-4 border rounded-lg hover:bg-accent/50">
                <RadioGroupItem value="credit" id="credit_all" />
                <Label htmlFor="credit_all" className="flex items-center gap-2 flex-1 cursor-pointer">
                  <CreditCard className="h-5 w-5" />
                  Alterar para Cartão de Crédito
                </Label>
              </div>
            </RadioGroup>
          )}

          {showQRCode && (
            <div className="space-y-4">
              <div className="bg-white p-6 rounded-lg border-2 border-primary flex flex-col items-center">
                <div className="w-64 h-64 bg-gray-200 flex items-center justify-center mb-4">
                  <QrCode className="h-32 w-32 text-gray-400" />
                </div>
                <p className="text-sm text-center text-muted-foreground">
                  QR Code PIX para pagamento de {proposal.value}
                </p>
                <p className="text-xs text-center text-muted-foreground mt-2">
                  Válido por 10 dias
                </p>
              </div>
              <Button
                onClick={() => {
                  setSendOptionsType("pix");
                  setShowSendOptions(true);
                }}
                className="w-full bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90"
              >
                <Send className="h-4 w-4 mr-2" />
                Enviar QR Code
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowQRCode(false)}
                className="w-full"
              >
                Voltar
              </Button>
            </div>
          )}

          {showCreditForm && (
            <div className="space-y-4">
              <div className="space-y-3">
                <div>
                  <Label htmlFor="bank">Banco</Label>
                  <Input
                    id="bank"
                    value={creditData.bank}
                    disabled
                    className="bg-muted"
                  />
                </div>
                <div>
                  <Label htmlFor="agency">Agência *</Label>
                  <Input
                    id="agency"
                    value={creditData.agency}
                    onChange={(e) => setCreditData({ ...creditData, agency: e.target.value })}
                    placeholder="Digite a agência"
                  />
                </div>
                <div>
                  <Label htmlFor="operation">Operação *</Label>
                  <Input
                    id="operation"
                    value={creditData.operation}
                    onChange={(e) => setCreditData({ ...creditData, operation: e.target.value })}
                    placeholder="Digite a operação"
                  />
                </div>
                <div>
                  <Label htmlFor="account">Número da Conta (com Dígito) *</Label>
                  <Input
                    id="account"
                    value={creditData.account}
                    onChange={(e) => setCreditData({ ...creditData, account: e.target.value })}
                    placeholder="Digite a conta com dígito"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => setShowCreditForm(false)}
                  className="flex-1"
                >
                  Voltar
                </Button>
                <Button
                  onClick={handleSubmitCredit}
                  disabled={isLoading}
                  className="flex-1 bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Processando...
                    </>
                  ) : (
                    "Confirmar Alteração"
                  )}
                </Button>
              </div>
            </div>
          )}

          {!showQRCode && !showCreditForm && (
            <Button
              onClick={() => {
                if (selectedOption === "boleto") {
                  handleGenerateBoleto();
                } else if (selectedOption === "pix") {
                  handleGeneratePix();
                } else if (selectedOption === "debit") {
                  handleShowCreditForm();
                } else if (selectedOption === "credit") {
                  setShowCreditCardDialog(true);
                }
              }}
              disabled={!selectedOption || isLoading}
              className="w-full bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Processando...
                </>
              ) : (
                "Continuar"
              )}
            </Button>
          )}
        </div>

        <SendOptionsDialog
          title={sendOptionsType === "boleto" ? "Enviar Boleto" : "Enviar QR Code PIX"}
          description={sendOptionsType === "boleto" ? "Selecione os canais para envio do boleto" : "Selecione os canais para envio do QR Code"}
          open={showSendOptions}
          onOpenChange={setShowSendOptions}
        />

        <CreditCardLinkDialog
          proposal={proposal}
          open={showCreditCardDialog}
          onOpenChange={setShowCreditCardDialog}
        />
      </DialogContent>
    </Dialog>
  );
};

export default PaymentOptionsDialog;
