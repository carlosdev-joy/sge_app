// "Gerenciamento de Devolução" no DS nativo — porte do RefundManagementDialog
// shadcn sobre Modal + Select/Input nativos (F8). Mesma validação (instituição,
// agência, conta e dígito obrigatórios), banco "outro" com campo livre e
// callback onStatusChange no sucesso.
import { useState } from "react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Input, Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";

interface RefundManagementDialogOrqProps {
  proposal: {
    number: string;
    insuredName: string;
    cpf: string;
    product: string;
    policy: string;
    value: string;
  };
  open: boolean;
  onClose: () => void;
  onStatusChange?: () => void;
}

const DADOS_INICIAIS = {
  institution: "",
  customInstitution: "",
  agency: "",
  agencyDigit: "",
  account: "",
  accountDigit: "",
  operation: "",
};

export default function RefundManagementDialogOrq({ proposal, open, onClose, onStatusChange }: RefundManagementDialogOrqProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [bankData, setBankData] = useState(DADOS_INICIAIS);
  const showCustomBank = bankData.institution === "outro";

  const handleClose = () => {
    setIsLoading(false);
    setBankData(DADOS_INICIAIS);
    onClose();
  };

  const handleSubmit = () => {
    const finalInstitution = showCustomBank ? bankData.customInstitution : bankData.institution;
    if (!finalInstitution || !bankData.agency || !bankData.account || !bankData.accountDigit) {
      toast.error("Preencha todos os campos obrigatórios para continuar.");
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      toast.success("Dados bancários registrados — a devolução foi programada com sucesso.");
      onStatusChange?.();
      handleClose();
    }, 2000);
  };

  return (
    <Modal open={open} onClose={handleClose} title="Gerenciamento de Devolução" size="xl">
      <div className="space-y-6">
        {/* Dados da proposta */}
        <div className="bg-canvas border border-edge p-4 rounded-lg">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-sm text-dim">Nome:</span>
              <p className="font-semibold text-ink">{proposal.insuredName}</p>
            </div>
            <div>
              <span className="text-sm text-dim">CPF:</span>
              <p className="font-semibold text-ink">{proposal.cpf}</p>
            </div>
            <div>
              <span className="text-sm text-dim">Proposta:</span>
              <p className="font-semibold text-ink">{proposal.number}</p>
            </div>
            <div>
              <span className="text-sm text-dim">Produto:</span>
              <p className="font-semibold text-ink">{proposal.product}</p>
            </div>
            <div>
              <span className="text-sm text-dim">Apólice:</span>
              <p className="font-semibold text-ink">{proposal.policy}</p>
            </div>
            <div>
              <span className="text-sm text-dim">Valor:</span>
              <p className="font-semibold text-[#1A5FA8] dark:text-blue-400">{proposal.value}</p>
            </div>
          </div>
        </div>

        {/* Dados bancários */}
        <div className="space-y-4">
          <h3 className="font-semibold text-lg text-ink">Dados Bancários para Devolução</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <Select
                label="Instituição Bancária *"
                value={bankData.institution}
                onChange={(e) => setBankData({ ...bankData, institution: e.target.value })}
                className="w-full"
              >
                <option value="">Selecione o banco</option>
                <option value="001">001 - Banco do Brasil</option>
                <option value="104">104 - Caixa Econômica Federal</option>
                <option value="237">237 - Bradesco</option>
                <option value="341">341 - Itaú</option>
                <option value="033">033 - Santander</option>
                <option value="outro">Outro</option>
              </Select>
            </div>

            {showCustomBank && (
              <div className="md:col-span-2">
                <Input
                  label="Nome da Instituição *"
                  value={bankData.customInstitution}
                  onChange={(e) => setBankData({ ...bankData, customInstitution: e.target.value })}
                  placeholder="Digite o nome do banco"
                  className="w-full"
                />
              </div>
            )}

            <Input
              label="Agência *"
              value={bankData.agency}
              onChange={(e) => setBankData({ ...bankData, agency: e.target.value })}
              placeholder="Digite a agência"
            />
            <Input
              label="Dígito da Agência"
              value={bankData.agencyDigit}
              onChange={(e) => setBankData({ ...bankData, agencyDigit: e.target.value })}
              placeholder="Digite o dígito (se houver)"
            />
            <Input
              label="Número da Conta *"
              value={bankData.account}
              onChange={(e) => setBankData({ ...bankData, account: e.target.value })}
              placeholder="Digite a conta"
            />
            <Input
              label="Dígito da Conta *"
              value={bankData.accountDigit}
              onChange={(e) => setBankData({ ...bankData, accountDigit: e.target.value })}
              placeholder="Digite o dígito"
            />
            <div className="md:col-span-2">
              <Input
                label="Operação"
                value={bankData.operation}
                onChange={(e) => setBankData({ ...bankData, operation: e.target.value })}
                placeholder="Digite a operação (se aplicável)"
                className="w-full"
              />
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleClose} className="flex-1 justify-center">
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={isLoading} loading={isLoading} className="flex-1 justify-center">
            {isLoading ? "Processando..." : "Programar Devolução"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
