import { useState } from "react";
import { Upload } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { useToast } from "../hooks/use-toast";

interface DocumentUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proposalNumber: string;
  insuredName: string;
}

const DocumentUploadDialog = ({
  open,
  onOpenChange,
  proposalNumber,
  insuredName,
}: DocumentUploadDialogProps) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { toast } = useToast();

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleUpload = () => {
    if (!selectedFile) {
      toast({
        title: "Erro",
        description: "Por favor, selecione um arquivo.",
        variant: "destructive",
      });
      return;
    }

    // Simulate upload
    toast({
      title: "Upload realizado com sucesso!",
      description: `O documento foi enviado para a proposta ${proposalNumber}.`,
    });

    setSelectedFile(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload de Documento</DialogTitle>
          <DialogDescription>
            Proposta: {proposalNumber} - {insuredName}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-primary transition-colors">
            <Upload className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <input
              type="file"
              id="file-upload"
              className="hidden"
              onChange={handleFileChange}
              accept=".pdf,.jpg,.jpeg,.png"
            />
            <label
              htmlFor="file-upload"
              className="cursor-pointer text-primary hover:underline"
            >
              Clique para selecionar um arquivo
            </label>
            <p className="text-sm text-muted-foreground mt-2">
              PDF, JPG ou PNG (máx. 10MB)
            </p>
            {selectedFile && (
              <p className="mt-4 text-sm font-medium">
                Arquivo selecionado: {selectedFile.name}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleUpload}>Enviar Documento</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DocumentUploadDialog;
