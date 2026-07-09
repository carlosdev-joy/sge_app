import { useState } from "react";
import { Dialog, DialogContent,
  DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Send, CheckCircle, Clock, XCircle, Loader2, Search } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import { useProfile } from "../contexts/ProfileContext";
import SensitizationHistoryDialog from "./SensitizationHistoryDialog";

interface Movement {
  id: string;
  proposalNumber: string;
  insuredName: string;
  type: "EMT" | "MAN" | "CAN" | "PEN";
  date: string;
  status: string;
}

interface SensitizationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SensitizationDialog = ({ open, onOpenChange }: SensitizationDialogProps) => {
  const { toast } = useToast();
  const { canSendSensitization } = useProfile();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedProposal] = useState<Movement | null>(null);
  const [isHistoryDialogOpen, setIsHistoryDialogOpen] = useState(false);
  const [movements, setMovements] = useState<Movement[]>([
    {
      id: "1",
      proposalNumber: "8047413032422-7",
      insuredName: "DIEBSON BITENCOURT DA SILVA",
      type: "EMT",
      date: "15/11/2025",
      status: "Enviado",
    },
    {
      id: "2",
      proposalNumber: "8047413032423-8",
      insuredName: "MARIA OLIVEIRA SANTOS",
      type: "MAN",
      date: "16/11/2025",
      status: "Enviado",
    },
    {
      id: "3",
      proposalNumber: "8047413032424-9",
      insuredName: "JOÃO CARLOS FERREIRA",
      type: "CAN",
      date: "17/11/2025",
      status: "Enviado",
    },
    {
      id: "4",
      proposalNumber: "8047413032425-0",
      insuredName: "ANA PAULA COSTA",
      type: "PEN",
      date: "18/11/2025",
      status: "Pendente",
    },
  ]);

  const [sendingId, setSendingId] = useState<string | null>(null);

  const handleSendMovement = (movementId: string) => {
    setSendingId(movementId);
    
    setTimeout(() => {
      setMovements(prev =>
        prev.map(m =>
          m.id === movementId
            ? { ...m, type: "EMT", status: "Enviado", date: new Date().toLocaleDateString('pt-BR') }
            : m
        )
      );
      setSendingId(null);
      toast({
        title: "Movimento enviado com sucesso",
        description: "O status foi atualizado de PEN para EMT",
      });
    }, 2000);
  };

  const getTypeColor = (type: Movement["type"]) => {
    const colors = {
      EMT: "bg-[hsl(211,70%,50%)] text-white",
      MAN: "bg-[hsl(211,60%,45%)] text-white",
      CAN: "bg-red-500 text-white",
      PEN: "bg-[hsl(45,90%,50%)] text-white",
    };
    return colors[type];
  };

  const getTypeIcon = (type: Movement["type"]) => {
    const icons = {
      EMT: <CheckCircle className="h-4 w-4" />,
      MAN: <Clock className="h-4 w-4" />,
      CAN: <XCircle className="h-4 w-4" />,
      PEN: <Clock className="h-4 w-4" />,
    };
    return icons[type];
  };

  const getTypeLabel = (type: Movement["type"]) => {
    const labels = {
      EMT: "Movimento de Emissão",
      MAN: "Movimento de Manutenção",
      CAN: "Movimento de Cancelamento",
      PEN: "Pendente de Envio",
    };
    return labels[type];
  };

  const filteredMovements = movements.filter(movement =>
    movement.proposalNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
    movement.insuredName.toLowerCase().includes(searchTerm.toLowerCase())
  );


  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-5xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-2xl">Movimentos de Sensibilização</DialogTitle>
          <DialogDescription className="sr-only">Movimentos de sensibilização das propostas em monitoramento.</DialogDescription>
          </DialogHeader>

          {/* Search Field */}
          <div className="mt-4 mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por número da proposta ou nome do segurado..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          <div className="mt-4">
            <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Proposta</TableHead>
                <TableHead>Segurado</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredMovements.map((movement) => (
                <TableRow key={movement.id}>
                  <TableCell className="font-medium">{movement.proposalNumber}</TableCell>
                  <TableCell>{movement.insuredName}</TableCell>
                  <TableCell>
                    <Badge className={`${getTypeColor(movement.type)} gap-1`}>
                      {getTypeIcon(movement.type)}
                      {movement.type}
                    </Badge>
                  </TableCell>
                  <TableCell>{movement.date}</TableCell>
                  <TableCell>
                    <Badge variant={movement.status === "Enviado" ? "default" : "outline"}>
                      {movement.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {movement.type === "PEN" && canSendSensitization() && (
                      <Button
                        size="sm"
                        onClick={() => handleSendMovement(movement.id)}
                        disabled={sendingId === movement.id}
                        className="bg-[hsl(211,70%,50%)] hover:bg-[hsl(211,70%,45%)]"
                      >
                        {sendingId === movement.id ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Enviando...
                          </>
                        ) : (
                          <>
                            <Send className="h-4 w-4 mr-2" />
                            Enviar Movimento
                          </>
                        )}
                      </Button>
                    )}
                    {movement.type === "PEN" && !canSendSensitization() && (
                      <span className="text-xs text-muted-foreground">Sem permissão</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="mt-6 p-4 bg-[hsl(211,85%,95%)] dark:bg-[hsl(211,50%,15%)] rounded-lg border border-[hsl(211,70%,80%)] dark:border-[hsl(211,50%,30%)]">
            <h3 className="font-semibold mb-2 text-[hsl(211,70%,25%)] dark:text-[hsl(211,70%,85%)]">Legenda:</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="flex items-center gap-2">
                <Badge className="bg-[hsl(211,70%,50%)] text-white gap-1">
                  <CheckCircle className="h-3 w-3" />
                  EMT
                </Badge>
                <span className="text-sm">{getTypeLabel("EMT")}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-[hsl(211,60%,45%)] text-white gap-1">
                  <Clock className="h-3 w-3" />
                  MAN
                </Badge>
                <span className="text-sm">{getTypeLabel("MAN")}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-red-500 text-white gap-1">
                  <XCircle className="h-3 w-3" />
                  CAN
                </Badge>
                <span className="text-sm">{getTypeLabel("CAN")}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-[hsl(45,90%,50%)] text-white gap-1">
                  <Clock className="h-3 w-3" />
                  PEN
                </Badge>
                <span className="text-sm">{getTypeLabel("PEN")}</span>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    {selectedProposal && (
      <SensitizationHistoryDialog
        open={isHistoryDialogOpen}
        onOpenChange={setIsHistoryDialogOpen}
        proposalNumber={selectedProposal.proposalNumber}
        insuredName={selectedProposal.insuredName}
      />
    )}
    </>
  );
};

export default SensitizationDialog;
