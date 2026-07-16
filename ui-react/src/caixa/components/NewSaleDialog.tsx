// "Realizar Nova Venda" no DS nativo — porte do NewSaleDialog shadcn sobre
// Modal + Select/Input nativos (F8). Mesma validação e prefill do valor.
import { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Input, Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";

interface NewSaleDialogProps {
  open: boolean;
  onClose: () => void;
  receiptNumber: string;
  insuredName: string;
  prefillValue?: string;
}

export default function NewSaleDialog({ open, onClose, receiptNumber, insuredName, prefillValue }: NewSaleDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [product, setProduct] = useState("");
  const [value, setValue] = useState(prefillValue || "");

  const handleClose = () => {
    setIsLoading(false);
    setProduct("");
    setValue(prefillValue || "");
    onClose();
  };

  const handleSubmit = () => {
    if (!product || !value) {
      toast.error("Por favor, preencha todos os campos.");
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast.success(`Nova venda criada! Venda vinculada ao recibo ${receiptNumber}`);
      handleClose();
    }, 2000);
  };

  return (
    <Modal open={open} onClose={handleClose} title="Realizar Nova Venda" size="md">
      <div className="space-y-4">
        <div className="bg-canvas border border-edge p-4 rounded-lg space-y-2">
          <div className="flex justify-between gap-3">
            <span className="text-sm text-dim">Recibo Vinculado:</span>
            <span className="font-semibold text-ink">{receiptNumber}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-sm text-dim">Cliente:</span>
            <span className="font-semibold text-ink">{insuredName}</span>
          </div>
        </div>

        <Select label="Produto *" value={product} onChange={(e) => setProduct(e.target.value)} className="w-full">
          <option value="">Selecione o produto</option>
          <option value="vida_multipremiado">Vida Multipremiado Total</option>
          <option value="vida_mulher">Vida Mulher</option>
          <option value="vida_conforto">Vida Conforto</option>
          <option value="perda_renda">Perda de Renda</option>
        </Select>

        <Input
          label="Valor *"
          type="text"
          placeholder="R$ 0,00"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full"
        />

        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleClose} className="flex-1 justify-center">
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={isLoading} loading={isLoading} className="flex-1 justify-center">
            {isLoading ? "Criando..." : "Criar Venda"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
