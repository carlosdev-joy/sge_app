// "Gerar Link de Pagamento — Cartão de Crédito" no DS nativo — porte do
// CreditCardLinkDialog shadcn sobre Modal nativo (F7). Mesmo fluxo (gerar →
// copiar → enviar via canais); o SendOptionsDialogOrq é montado como IRMÃO
// (fora do Modal pai) para a pilha de modais e o trap de Tab não conflitarem.
// Consumidor chega na F8 (fluxo de pagamento) — sem montagem até lá.
import { useRef, useState } from "react";
import { Copy, Check, Mail } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import SendOptionsDialogOrq from "./SendOptionsDialogOrq";

interface CreditCardLinkDialogOrqProps {
  proposal: {
    number: string;
    insuredName: string;
    value: string;
  };
  open: boolean;
  onClose: () => void;
}

export default function CreditCardLinkDialogOrq({ proposal, open, onClose }: CreditCardLinkDialogOrqProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [linkGenerated, setLinkGenerated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showSendOptions, setShowSendOptions] = useState(false);

  const generatedLink = `https://pagamento.seguradora.com.br/cc/${proposal.number}`;
  const gerarTimer = useRef<number | null>(null);

  // Todo caminho de fechar (Esc/backdrop/X e os botões) passa aqui, zera o
  // fluxo e cancela o timer de geração (o antigo só zerava no clique em
  // Fechar/Cancelar — Esc deixava o estado para trás).
  const handleClose = () => {
    if (gerarTimer.current !== null) {
      clearTimeout(gerarTimer.current);
      gerarTimer.current = null;
    }
    setIsGenerating(false);
    setLinkGenerated(false);
    setCopied(false);
    setShowSendOptions(false);
    onClose();
  };

  const handleGenerateLink = () => {
    setIsGenerating(true);
    gerarTimer.current = window.setTimeout(() => {
      gerarTimer.current = null;
      setIsGenerating(false);
      setLinkGenerated(true);
      toast.success("O link de pagamento por cartão de crédito foi criado.");
    }, 2000);
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(generatedLink);
    setCopied(true);
    toast.success("O link foi copiado para a área de transferência.");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <Modal open={open} onClose={handleClose} title="Gerar Link de Pagamento - Cartão de Crédito" size="lg">
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
          </div>

          {!linkGenerated ? (
            <div className="space-y-4">
              <p className="text-sm text-dim text-center">
                O link de pagamento conterá um formulário seguro para captura dos dados do cartão:
              </p>
              <div className="bg-canvas border border-edge p-4 rounded-lg space-y-2 text-sm text-ink">
                <p>• Nome completo</p>
                <p>• CPF</p>
                <p>• Número do cartão</p>
                <p>• Data de validade</p>
                <p>• Código de segurança (CVV)</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800 p-4 rounded-lg">
                <p className="text-sm font-semibold text-ink mb-2">Link de Pagamento:</p>
                <div className="flex gap-2">
                  <div className="flex-1">
                    <Input value={generatedLink} readOnly className="w-full" aria-label="Link de pagamento gerado" />
                  </div>
                  <Button variant="secondary" onClick={handleCopyLink} aria-label="Copiar link" className="shrink-0">
                    {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <div className="space-y-3">
                <p className="text-sm font-semibold text-ink">Enviar link via:</p>
                <Button variant="primary" size="sm" onClick={() => setShowSendOptions(true)}>
                  <Mail className="h-4 w-4" />
                  Enviar por E-mail/SMS/WhatsApp
                </Button>
              </div>

              <p className="text-xs text-dim text-center">Compartilhe este link com o cliente para efetuar o pagamento</p>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={handleClose} className="flex-1 justify-center">
              {linkGenerated ? "Fechar" : "Cancelar"}
            </Button>
            {!linkGenerated && (
              <Button
                variant="primary"
                onClick={handleGenerateLink}
                disabled={isGenerating}
                loading={isGenerating}
                className="flex-1 justify-center"
              >
                {isGenerating ? "Gerando..." : "Gerar Link"}
              </Button>
            )}
          </div>
        </div>
      </Modal>

      <SendOptionsDialogOrq
        title="Enviar Link de Pagamento"
        description="Selecione os canais para envio do link"
        open={showSendOptions}
        onClose={() => setShowSendOptions(false)}
      />
    </>
  );
}
