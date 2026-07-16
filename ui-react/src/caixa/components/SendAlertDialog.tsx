// "Enviar Alertas por E-mail" no DS nativo — porte do SendAlertDialog shadcn
// sobre Modal + Checkbox nativos (F7). Mesmos estados (lista → enviando →
// sucesso), selecionar/desmarcar todos e toast de erro sem seleção.
import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Checkbox";
import { toast } from "../../components/ui/Toast";

interface AlertProposal {
  id: string;
  number: string;
  insuredName: string;
  broker: string;
  agency: string;
}

interface SendAlertDialogProps {
  proposals: AlertProposal[];
  open: boolean;
  onClose: () => void;
}

export default function SendAlertDialog({ proposals, open, onClose }: SendAlertDialogProps) {
  const [selectedProposals, setSelectedProposals] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  // Todo caminho de fechar passa aqui e zera o fluxo.
  const handleClose = () => {
    setSelectedProposals([]);
    setIsLoading(false);
    setIsSuccess(false);
    onClose();
  };

  const handleToggleProposal = (proposalId: string) => {
    setSelectedProposals((prev) =>
      prev.includes(proposalId) ? prev.filter((id) => id !== proposalId) : [...prev, proposalId]
    );
  };

  const handleSendAlerts = () => {
    if (selectedProposals.length === 0) {
      toast.error("Selecione ao menos uma proposta para enviar alertas.");
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      setIsSuccess(true);
      setTimeout(() => handleClose(), 2000);
    }, 2000);
  };

  return (
    <Modal open={open} onClose={handleClose} title="Enviar Alertas por E-mail" size="lg">
      {!isLoading && !isSuccess && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-sm text-dim">
              Selecione as propostas para enviar alertas aos responsáveis (agência/consultor)
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setSelectedProposals(selectedProposals.length === proposals.length ? [] : proposals.map((p) => p.id))
              }
            >
              {selectedProposals.length === proposals.length ? "Desmarcar Todos" : "Selecionar Todos"}
            </Button>
          </div>

          <div className="border border-edge rounded-lg max-h-[400px] overflow-y-auto">
            {proposals.map((proposal) => (
              <div
                key={proposal.id}
                className="flex items-center gap-3 p-4 border-b border-edge last:border-b-0 hover:bg-canvas/60"
              >
                <Checkbox
                  checked={selectedProposals.includes(proposal.id)}
                  onChange={() => handleToggleProposal(proposal.id)}
                  aria-label={`Selecionar proposta ${proposal.number}`}
                />
                <div className="flex-1">
                  <p className="font-semibold text-ink">{proposal.number}</p>
                  <p className="text-sm text-dim">{proposal.insuredName}</p>
                  <p className="text-xs text-dim">
                    Agência: {proposal.agency} | Corretor: {proposal.broker}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-3">
            <Button variant="secondary" onClick={handleClose} className="flex-1 justify-center">
              Cancelar
            </Button>
            <Button variant="primary" onClick={handleSendAlerts} className="flex-1 justify-center">
              Enviar Alertas ({selectedProposals.length})
            </Button>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-8 gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-[#F26B00]" />
          <p className="text-dim">Enviando alertas...</p>
        </div>
      )}

      {isSuccess && (
        <div className="flex flex-col items-center justify-center py-8 gap-4">
          <div className="rounded-full bg-emerald-600 p-3">
            <Check className="h-12 w-12 text-white" />
          </div>
          <p className="font-semibold text-lg text-center text-ink">Alertas enviados com sucesso!</p>
        </div>
      )}
    </Modal>
  );
}
