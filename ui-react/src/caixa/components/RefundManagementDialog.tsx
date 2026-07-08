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
import { Loader2 } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

interface RefundManagementDialogProps {
  proposal: {
    number: string;
    insuredName: string;
    cpf: string;
    product: string;
    policy: string;
    value: string;
  };
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStatusChange?: () => void;
}

const RefundManagementDialog = ({ proposal, open, onOpenChange, onStatusChange }: RefundManagementDialogProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [showCustomBank, setShowCustomBank] = useState(false);
  const [bankData, setBankData] = useState({
    institution: "",
    customInstitution: "",
    agency: "",
    agencyDigit: "",
    account: "",
    accountDigit: "",
    operation: "",
  });
  const { toast } = useToast();

  const handleBankChange = (value: string) => {
    setBankData({ ...bankData, institution: value });
    setShowCustomBank(value === "outro");
  };

  const handleSubmit = () => {
    const finalInstitution = showCustomBank ? bankData.customInstitution : bankData.institution;
    if (!finalInstitution || !bankData.agency || !bankData.account || !bankData.accountDigit) {
      toast({
        title: "Campos obrigatórios",
        description: "Preencha todos os campos obrigatórios para continuar.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast({
        title: "Dados bancários registrados",
        description: "A devolução foi programada com sucesso.",
      });
      onStatusChange?.();
      onOpenChange(false);
    }, 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Gerenciamento de Devolução
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Proposal Details */}
          <div className="bg-accent/30 p-4 rounded-lg space-y-2">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-sm text-muted-foreground">Nome:</span>
                <p className="font-semibold">{proposal.insuredName}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">CPF:</span>
                <p className="font-semibold">{proposal.cpf}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Proposta:</span>
                <p className="font-semibold">{proposal.number}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Produto:</span>
                <p className="font-semibold">{proposal.product}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Apólice:</span>
                <p className="font-semibold">{proposal.policy}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Valor:</span>
                <p className="font-semibold text-primary">{proposal.value}</p>
              </div>
            </div>
          </div>

          {/* Bank Details Form */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Dados Bancários para Devolução</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Label htmlFor="institution">Instituição Bancária *</Label>
                <Select value={bankData.institution} onValueChange={handleBankChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione o banco" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="001">001 - Banco do Brasil</SelectItem>
                    <SelectItem value="104">104 - Caixa Econômica Federal</SelectItem>
                    <SelectItem value="237">237 - Bradesco</SelectItem>
                    <SelectItem value="341">341 - Itaú</SelectItem>
                    <SelectItem value="033">033 - Santander</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              {showCustomBank && (
                <div className="md:col-span-2">
                  <Label htmlFor="customInstitution">Nome da Instituição *</Label>
                  <Input
                    id="customInstitution"
                    value={bankData.customInstitution}
                    onChange={(e) => setBankData({ ...bankData, customInstitution: e.target.value })}
                    placeholder="Digite o nome do banco"
                  />
                </div>
              )}

              <div>
                <Label htmlFor="agency">Agência *</Label>
                <Input
                  id="agency"
                  value={bankData.agency}
                  onChange={(e) => setBankData({ ...bankData, agency: e.target.value })}
                  placeholder="Digite a agência"
                />
              </div>
              <div>
                <Label htmlFor="agencyDigit">Dígito da Agência</Label>
                <Input
                  id="agencyDigit"
                  value={bankData.agencyDigit}
                  onChange={(e) => setBankData({ ...bankData, agencyDigit: e.target.value })}
                  placeholder="Digite o dígito (se houver)"
                />
              </div>
              <div>
                <Label htmlFor="account">Número da Conta *</Label>
                <Input
                  id="account"
                  value={bankData.account}
                  onChange={(e) => setBankData({ ...bankData, account: e.target.value })}
                  placeholder="Digite a conta"
                />
              </div>
              <div>
                <Label htmlFor="accountDigit">Dígito da Conta *</Label>
                <Input
                  id="accountDigit"
                  value={bankData.accountDigit}
                  onChange={(e) => setBankData({ ...bankData, accountDigit: e.target.value })}
                  placeholder="Digite o dígito"
                />
              </div>
              <div className="md:col-span-2">
                <Label htmlFor="operation">Operação</Label>
                <Input
                  id="operation"
                  value={bankData.operation}
                  onChange={(e) => setBankData({ ...bankData, operation: e.target.value })}
                  placeholder="Digite a operação (se aplicável)"
                />
              </div>
            </div>
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
                  Processando...
                </>
              ) : (
                "Programar Devolução"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default RefundManagementDialog;
