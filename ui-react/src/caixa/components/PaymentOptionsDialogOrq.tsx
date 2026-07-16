// "Alterar forma de pagamento" no DS nativo — porte do PaymentOptionsDialog
// shadcn sobre Modal + RadioGroup nativos (F8). Mesmos 4 caminhos: boleto
// (gera → envia via canais), PIX (QR → envia/volta), débito (formulário de
// dados bancários — o toast fala em "crédito em conta", quirk do mock
// original preservado) e cartão de crédito (CreditCardLinkDialogOrq da F7).
// SendOptions e CreditCard montados como IRMÃOS do Modal pai (pilha/trap).
import { useState } from "react";
import { FileText, QrCode, CreditCard, Send } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { RadioGroup, RadioItem } from "../../components/ui/RadioGroup";
import { toast } from "../../components/ui/Toast";
import SendOptionsDialogOrq from "./SendOptionsDialogOrq";
import CreditCardLinkDialogOrq from "./CreditCardLinkDialogOrq";

interface PaymentOptionsDialogOrqProps {
  proposal: {
    number: string;
    insuredName: string;
    value: string;
    paymentMethod: "boleto" | "debit" | "credit";
    email: string;
    phone: string;
  };
  open: boolean;
  onClose: () => void;
}

const METHOD_LABELS = { boleto: "Boleto", debit: "Débito em Conta", credit: "Crédito em Conta" } as const;

export default function PaymentOptionsDialogOrq({ proposal, open, onClose }: PaymentOptionsDialogOrqProps) {
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

  // Todo caminho de fechar passa aqui e zera o fluxo.
  const handleClose = () => {
    setSelectedOption("");
    setIsLoading(false);
    setShowQRCode(false);
    setShowCreditForm(false);
    setShowSendOptions(false);
    setShowCreditCardDialog(false);
    setCreditData({ bank: "104 - Caixa Econômica Federal", agency: "", operation: "", account: "" });
    onClose();
  };

  const handleGenerateBoleto = () => {
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast.success(`Boleto gerado com sucesso: boleto_${proposal.insuredName.replace(/\s+/g, "_")}.pdf`);
      setSendOptionsType("boleto");
      setShowSendOptions(true);
    }, 2000);
  };

  const handleSubmitCredit = () => {
    if (!creditData.agency || !creditData.operation || !creditData.account) {
      toast.error("Preencha todos os campos para continuar.");
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast.success("A alteração para crédito em conta foi registrada.");
      handleClose();
    }, 2000);
  };

  const handleContinue = () => {
    if (selectedOption === "boleto") handleGenerateBoleto();
    else if (selectedOption === "pix") setShowQRCode(true);
    else if (selectedOption === "debit") setShowCreditForm(true);
    else if (selectedOption === "credit") setShowCreditCardDialog(true);
  };

  return (
    <>
      <Modal open={open} onClose={handleClose} title="Alterar forma de pagamento" size="lg">
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
              <span className="text-sm text-dim">Valor:</span>
              <span className="font-semibold text-[#1A5FA8] dark:text-blue-400">{proposal.value}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-sm text-dim">Forma de Pagamento atual:</span>
              <span className="font-semibold text-ink">{METHOD_LABELS[proposal.paymentMethod]}</span>
            </div>
          </div>

          {!showQRCode && !showCreditForm && (
            <RadioGroup value={selectedOption} onValueChange={(v) => setSelectedOption(v as typeof selectedOption)} label="Nova forma de pagamento">
              <div className="flex items-center p-4 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="boleto" className="flex-1" label={<span className="flex items-center gap-2"><FileText className="h-5 w-5" /> Gerar Boleto</span>} />
              </div>
              <div className="flex items-center p-4 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="pix" className="flex-1" label={<span className="flex items-center gap-2"><QrCode className="h-5 w-5" /> Pagamento via PIX</span>} />
              </div>
              <div className="flex items-center p-4 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="debit" className="flex-1" label={<span className="flex items-center gap-2"><CreditCard className="h-5 w-5" /> Alterar para Débito em Conta</span>} />
              </div>
              <div className="flex items-center p-4 border border-edge rounded-lg hover:border-blue-400 transition-colors">
                <RadioItem value="credit" className="flex-1" label={<span className="flex items-center gap-2"><CreditCard className="h-5 w-5" /> Alterar para Cartão de Crédito</span>} />
              </div>
            </RadioGroup>
          )}

          {showQRCode && (
            <div className="space-y-4">
              <div className="bg-canvas p-6 rounded-lg border-2 border-[#1A5FA8] flex flex-col items-center">
                <div className="w-64 h-64 bg-edge/40 flex items-center justify-center mb-4 rounded">
                  <QrCode className="h-32 w-32 text-dim" />
                </div>
                <p className="text-sm text-center text-dim">QR Code PIX para pagamento de {proposal.value}</p>
                <p className="text-xs text-center text-dim mt-2">Válido por 10 dias</p>
              </div>
              <Button
                variant="primary"
                onClick={() => {
                  setSendOptionsType("pix");
                  setShowSendOptions(true);
                }}
                className="w-full justify-center"
              >
                <Send className="h-4 w-4" />
                Enviar QR Code
              </Button>
              <Button variant="secondary" onClick={() => setShowQRCode(false)} className="w-full justify-center">
                Voltar
              </Button>
            </div>
          )}

          {showCreditForm && (
            <div className="space-y-4">
              <div className="space-y-3">
                <Input label="Banco" value={creditData.bank} disabled className="w-full" />
                <Input
                  label="Agência *"
                  value={creditData.agency}
                  onChange={(e) => setCreditData({ ...creditData, agency: e.target.value })}
                  placeholder="Digite a agência"
                  className="w-full"
                />
                <Input
                  label="Operação *"
                  value={creditData.operation}
                  onChange={(e) => setCreditData({ ...creditData, operation: e.target.value })}
                  placeholder="Digite a operação"
                  className="w-full"
                />
                <Input
                  label="Número da Conta (com Dígito) *"
                  value={creditData.account}
                  onChange={(e) => setCreditData({ ...creditData, account: e.target.value })}
                  placeholder="Digite a conta com dígito"
                  className="w-full"
                />
              </div>
              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => setShowCreditForm(false)} className="flex-1 justify-center">
                  Voltar
                </Button>
                <Button variant="primary" onClick={handleSubmitCredit} disabled={isLoading} loading={isLoading} className="flex-1 justify-center">
                  {isLoading ? "Processando..." : "Confirmar Alteração"}
                </Button>
              </div>
            </div>
          )}

          {!showQRCode && !showCreditForm && (
            <Button
              variant="primary"
              onClick={handleContinue}
              disabled={!selectedOption || isLoading}
              loading={isLoading}
              className="w-full justify-center"
            >
              {isLoading ? "Processando..." : "Continuar"}
            </Button>
          )}
        </div>
      </Modal>

      <SendOptionsDialogOrq
        title={sendOptionsType === "boleto" ? "Enviar Boleto" : "Enviar QR Code PIX"}
        description={sendOptionsType === "boleto" ? "Selecione os canais para envio do boleto" : "Selecione os canais para envio do QR Code"}
        open={showSendOptions}
        onClose={() => setShowSendOptions(false)}
      />

      <CreditCardLinkDialogOrq
        proposal={proposal}
        open={showCreditCardDialog}
        onClose={() => setShowCreditCardDialog(false)}
      />
    </>
  );
}
