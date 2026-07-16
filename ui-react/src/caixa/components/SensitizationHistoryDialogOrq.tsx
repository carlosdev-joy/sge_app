// "Histórico de Sensibilização" no DS nativo — porte do
// SensitizationHistoryDialog shadcn sobre Modal + Table nativos (F8). Mesmo
// mock de movimentos EMT/MAN/CAN/PEN.
import { CheckCircle, Clock, XCircle } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/Table";

interface HistoryEntry {
  id: string;
  date: string;
  type: "EMT" | "MAN" | "CAN" | "PEN";
  description: string;
}

interface SensitizationHistoryDialogOrqProps {
  open: boolean;
  onClose: () => void;
  proposalNumber: string;
  insuredName: string;
}

// Mesmo mock da tela original.
const history: HistoryEntry[] = [
  { id: "1", date: "10/11/2025 14:30", type: "EMT", description: "Movimento de Emissão enviado" },
  { id: "2", date: "12/11/2025 09:15", type: "MAN", description: "Movimento de Manutenção enviado" },
  { id: "3", date: "15/11/2025 16:45", type: "EMT", description: "Movimento de Emissão reenviado" },
];

const TYPE_STYLE: Record<HistoryEntry["type"], { cor: string; rotulo: string; icone: React.ReactNode }> = {
  EMT: { cor: "bg-[#1A5FA8]", rotulo: "Emissão", icone: <CheckCircle className="h-4 w-4" /> },
  MAN: { cor: "bg-[#0F4C88]", rotulo: "Manutenção", icone: <Clock className="h-4 w-4" /> },
  CAN: { cor: "bg-red-500", rotulo: "Cancelamento", icone: <XCircle className="h-4 w-4" /> },
  PEN: { cor: "bg-amber-500", rotulo: "Pendente", icone: <Clock className="h-4 w-4" /> },
};

export default function SensitizationHistoryDialogOrq({ open, onClose, proposalNumber, insuredName }: SensitizationHistoryDialogOrqProps) {
  return (
    <Modal open={open} onClose={onClose} title="Histórico de Sensibilização" size="xl">
      <div className="text-sm text-dim mb-4">
        <p>
          <strong className="text-ink">Proposta:</strong> {proposalNumber}
        </p>
        <p>
          <strong className="text-ink">Segurado:</strong> {insuredName}
        </p>
      </div>

      <div className="rounded-lg border border-edge overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Data/Hora</TableHead>
              <TableHead>Tipo de Movimento</TableHead>
              <TableHead>Descrição</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {history.map((entry) => {
              const style = TYPE_STYLE[entry.type];
              return (
                <TableRow key={entry.id}>
                  <TableCell className="font-medium">{entry.date}</TableCell>
                  <TableCell>
                    <span className={`${style.cor} text-white inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium`}>
                      {style.icone}
                      {style.rotulo}
                    </span>
                  </TableCell>
                  <TableCell>{entry.description}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {history.length === 0 && (
        <div className="text-center py-8 text-dim">
          Nenhum movimento de sensibilização registrado para esta proposta.
        </div>
      )}
    </Modal>
  );
}
