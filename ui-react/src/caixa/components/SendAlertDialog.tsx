import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Check, Loader2 } from "lucide-react";
import { useToast } from "../hooks/use-toast";

interface Proposal {
  id: string;
  number: string;
  insuredName: string;
  broker: string;
  agency: string;
}

interface SendAlertDialogProps {
  proposals: Proposal[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SendAlertDialog = ({ proposals, open, onOpenChange }: SendAlertDialogProps) => {
  const [selectedProposals, setSelectedProposals] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const { toast } = useToast();

  const handleToggleProposal = (proposalId: string) => {
    setSelectedProposals(prev =>
      prev.includes(proposalId)
        ? prev.filter(id => id !== proposalId)
        : [...prev, proposalId]
    );
  };

  const handleSendAlerts = async () => {
    if (selectedProposals.length === 0) {
      toast({
        title: "Nenhuma proposta selecionada",
        description: "Selecione ao menos uma proposta para enviar alertas.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    
    setTimeout(() => {
      setIsLoading(false);
      setIsSuccess(true);
      
      setTimeout(() => {
        onOpenChange(false);
        setSelectedProposals([]);
        setIsSuccess(false);
      }, 2000);
    }, 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-primary text-center">
            Enviar Alertas por E-mail
          </DialogTitle>
          <DialogDescription className="sr-only">Dispare alertas por e-mail para os responsáveis.</DialogDescription>
        </DialogHeader>

        {!isLoading && !isSuccess && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Selecione as propostas para enviar alertas aos responsáveis (agência/consultor)
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (selectedProposals.length === proposals.length) {
                    setSelectedProposals([]);
                  } else {
                    setSelectedProposals(proposals.map(p => p.id));
                  }
                }}
              >
                {selectedProposals.length === proposals.length ? "Desmarcar Todos" : "Selecionar Todos"}
              </Button>
            </div>

            <div className="border rounded-lg max-h-[400px] overflow-y-auto">
              {proposals.map((proposal) => (
                <div
                  key={proposal.id}
                  className="flex items-center gap-3 p-4 border-b last:border-b-0 hover:bg-accent/50"
                >
                  <Checkbox
                    checked={selectedProposals.includes(proposal.id)}
                    onCheckedChange={() => handleToggleProposal(proposal.id)}
                  />
                  <div className="flex-1">
                    <p className="font-semibold">{proposal.number}</p>
                    <p className="text-sm text-muted-foreground">{proposal.insuredName}</p>
                    <p className="text-xs text-muted-foreground">
                      Agência: {proposal.agency} | Corretor: {proposal.broker}
                    </p>
                  </div>
                </div>
              ))}
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
                onClick={handleSendAlerts}
                className="flex-1 bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90"
              >
                Enviar Alertas ({selectedProposals.length})
              </Button>
            </div>
          </div>
        )}

        {isLoading && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <Loader2 className="h-12 w-12 animate-spin text-[hsl(var(--orange))]" />
            <p className="text-muted-foreground">Enviando alertas...</p>
          </div>
        )}

        {isSuccess && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <div className="rounded-full bg-[hsl(var(--green))] p-3">
              <Check className="h-12 w-12 text-white" />
            </div>
            <p className="font-semibold text-lg text-center">
              Alertas enviados com sucesso!
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default SendAlertDialog;
