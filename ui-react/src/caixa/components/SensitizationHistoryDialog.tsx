import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Badge } from "./ui/badge";
import { CheckCircle, Clock, XCircle } from "lucide-react";

interface HistoryEntry {
  id: string;
  date: string;
  type: "EMT" | "MAN" | "CAN" | "PEN";
  description: string;
}

interface SensitizationHistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proposalNumber: string;
  insuredName: string;
}

const SensitizationHistoryDialog = ({ open, onOpenChange, proposalNumber, insuredName }: SensitizationHistoryDialogProps) => {
  // Mock history data
  const history: HistoryEntry[] = [
    {
      id: "1",
      date: "10/11/2025 14:30",
      type: "EMT",
      description: "Movimento de Emissão enviado",
    },
    {
      id: "2",
      date: "12/11/2025 09:15",
      type: "MAN",
      description: "Movimento de Manutenção enviado",
    },
    {
      id: "3",
      date: "15/11/2025 16:45",
      type: "EMT",
      description: "Movimento de Emissão reenviado",
    },
  ];

  const getTypeColor = (type: HistoryEntry["type"]) => {
    const colors = {
      EMT: "bg-[hsl(211,70%,50%)] text-white",
      MAN: "bg-[hsl(211,60%,45%)] text-white",
      CAN: "bg-red-500 text-white",
      PEN: "bg-[hsl(45,90%,50%)] text-white",
    };
    return colors[type];
  };

  const getTypeIcon = (type: HistoryEntry["type"]) => {
    const icons = {
      EMT: <CheckCircle className="h-4 w-4" />,
      MAN: <Clock className="h-4 w-4" />,
      CAN: <XCircle className="h-4 w-4" />,
      PEN: <Clock className="h-4 w-4" />,
    };
    return icons[type];
  };

  const getTypeLabel = (type: HistoryEntry["type"]) => {
    const labels = {
      EMT: "Emissão",
      MAN: "Manutenção",
      CAN: "Cancelamento",
      PEN: "Pendente",
    };
    return labels[type];
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl">Histórico de Sensibilização</DialogTitle>
          <div className="text-sm text-muted-foreground mt-2">
            <p><strong>Proposta:</strong> {proposalNumber}</p>
            <p><strong>Segurado:</strong> {insuredName}</p>
          </div>
        </DialogHeader>

        <div className="mt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data/Hora</TableHead>
                <TableHead>Tipo de Movimento</TableHead>
                <TableHead>Descrição</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-medium">{entry.date}</TableCell>
                  <TableCell>
                    <Badge className={`${getTypeColor(entry.type)} flex items-center gap-1 w-fit`}>
                      {getTypeIcon(entry.type)}
                      {getTypeLabel(entry.type)}
                    </Badge>
                  </TableCell>
                  <TableCell>{entry.description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {history.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              Nenhum movimento de sensibilização registrado para esta proposta.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SensitizationHistoryDialog;
