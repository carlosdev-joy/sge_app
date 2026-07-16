// "Upload de Documento" no DS nativo — porte do DocumentUploadDialog shadcn
// sobre Modal nativo (F8). Mesmo fluxo mock (seleção de arquivo + toast).
import { useState } from "react";
import { Upload } from "lucide-react";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { toast } from "../../components/ui/Toast";

interface DocumentUploadDialogOrqProps {
  open: boolean;
  onClose: () => void;
  proposalNumber: string;
  insuredName: string;
}

export default function DocumentUploadDialogOrq({ open, onClose, proposalNumber, insuredName }: DocumentUploadDialogOrqProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleClose = () => {
    setSelectedFile(null);
    onClose();
  };

  const handleUpload = () => {
    if (!selectedFile) {
      toast.error("Por favor, selecione um arquivo.");
      return;
    }
    // Upload simulado (mock, como na tela original)
    toast.success(`O documento foi enviado para a proposta ${proposalNumber}.`);
    handleClose();
  };

  return (
    <Modal open={open} onClose={handleClose} title="Upload de Documento" size="md">
      <div className="space-y-4">
        <p className="text-sm text-dim">
          Proposta: {proposalNumber} - {insuredName}
        </p>

        <div className="border-2 border-dashed border-edge rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
          <Upload className="h-12 w-12 mx-auto mb-4 text-dim" />
          <input
            type="file"
            id="file-upload-orq"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) setSelectedFile(file);
            }}
            accept=".pdf,.jpg,.jpeg,.png"
          />
          <label htmlFor="file-upload-orq" className="cursor-pointer text-[#1A5FA8] dark:text-blue-400 hover:underline">
            Clique para selecionar um arquivo
          </label>
          <p className="text-sm text-dim mt-2">PDF, JPG ou PNG (máx. 10MB)</p>
          {selectedFile && <p className="mt-4 text-sm font-medium text-ink">Arquivo selecionado: {selectedFile.name}</p>}
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={handleClose}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={handleUpload}>
            Enviar Documento
          </Button>
        </div>
      </div>
    </Modal>
  );
}
