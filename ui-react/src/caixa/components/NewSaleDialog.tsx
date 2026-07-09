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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Loader2 } from "lucide-react";
import { useToast } from "../hooks/use-toast";

interface NewSaleDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  receiptNumber: string;
  insuredName: string;
  prefillValue?: string;
}

const NewSaleDialog = ({ open, onOpenChange, receiptNumber, insuredName, prefillValue }: NewSaleDialogProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [product, setProduct] = useState("");
  const [value, setValue] = useState(prefillValue || "");
  const { toast } = useToast();

  const handleSubmit = () => {
    if (!product || !value) {
      toast({
        title: "Campos obrigatórios",
        description: "Por favor, preencha todos os campos.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast({
        title: "Nova venda criada!",
        description: `Venda vinculada ao recibo ${receiptNumber}`,
      });
      onOpenChange(false);
    }, 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Realizar Nova Venda
          </DialogTitle>
          <DialogDescription className="sr-only">Preencha os dados para iniciar uma nova venda de seguro.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="bg-accent/30 p-4 rounded-lg space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Recibo Vinculado:</span>
              <span className="font-semibold">{receiptNumber}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Cliente:</span>
              <span className="font-semibold">{insuredName}</span>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="product">Produto *</Label>
            <Select value={product} onValueChange={setProduct}>
              <SelectTrigger id="product">
                <SelectValue placeholder="Selecione o produto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="vida_multipremiado">Vida Multipremiado Total</SelectItem>
                <SelectItem value="vida_mulher">Vida Mulher</SelectItem>
                <SelectItem value="vida_conforto">Vida Conforto</SelectItem>
                <SelectItem value="perda_renda">Perda de Renda</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="value">Valor *</Label>
            <Input
              id="value"
              type="text"
              placeholder="R$ 0,00"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>

          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isLoading}
              className="flex-1 bg-[hsl(var(--green))] hover:bg-[hsl(var(--green))]/90"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Criando...
                </>
              ) : (
                "Criar Venda"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default NewSaleDialog;
