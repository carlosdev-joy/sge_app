import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";
import { useToast } from "../hooks/use-toast";

interface NPSDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const NPSDialog = ({ open, onOpenChange }: NPSDialogProps) => {
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [isAnonymous, setIsAnonymous] = useState(false);
  const { toast } = useToast();

  const handleSubmit = () => {
    if (!rating) {
      toast({
        title: "Atenção",
        description: "Por favor, selecione uma nota.",
        variant: "destructive",
      });
      return;
    }

    toast({
      title: "Obrigado pelo feedback!",
      description: "Sua avaliação foi registrada com sucesso.",
    });

    // Reset and close
    setRating(null);
    setComment("");
    setIsAnonymous(false);
    onOpenChange(false);
  };

  const getQuestionText = () => {
    if (rating === null) return "Como você avalia o conteúdo e as funcionalidades do site?";
    if (rating === 5) return "Diga nos o que você mais gostou e como podemos melhorar ainda mais a sua experiência";
    return "Como podemos melhorar a sua experiência?";
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] bg-white">
        <DialogHeader>
          <DialogTitle className="text-2xl text-center text-[hsl(211,100%,25%)]">
            📊 Pesquisa de Satisfação
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="space-y-3">
            <Label className="text-base font-semibold text-[hsl(211,100%,25%)]">
              {getQuestionText()}
            </Label>
            
            <div className="flex justify-center gap-2">
              {[1, 2, 3, 4, 5].map((value) => (
                <Button
                  key={value}
                  variant={rating === value ? "default" : "outline"}
                  size="lg"
                  className={`w-16 h-16 text-xl font-bold transition-all ${
                    rating === value
                      ? "bg-[hsl(211,100%,50%)] text-white hover:bg-[hsl(211,100%,45%)] scale-110"
                      : "hover:scale-105"
                  }`}
                  onClick={() => setRating(value)}
                >
                  {value}
                </Button>
              ))}
            </div>
            
            <div className="flex justify-between text-xs text-muted-foreground px-2">
              <span>1 - Ruim</span>
              <span>5 - Ótimo</span>
            </div>
          </div>

          {rating !== null && (
            <div className="space-y-3 animate-fade-in">
              <Label htmlFor="comment" className="text-[hsl(211,100%,25%)]">
                Comentário (opcional)
              </Label>
              <Textarea
                id="comment"
                placeholder="Compartilhe sua opinião..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="min-h-[100px] resize-none"
              />
            </div>
          )}

          <div className="flex items-center justify-between space-x-2 bg-gray-50 p-4 rounded-lg">
            <Label htmlFor="anonymous" className="text-sm cursor-pointer">
              Enviar anonimamente
            </Label>
            <Switch
              id="anonymous"
              checked={isAnonymous}
              onCheckedChange={setIsAnonymous}
            />
          </div>

          <div className="flex gap-3">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
            >
              Fechar
            </Button>
            <Button
              className="flex-1 bg-[hsl(211,100%,50%)] hover:bg-[hsl(211,100%,45%)] text-white"
              onClick={handleSubmit}
              disabled={!rating}
            >
              Enviar Avaliação
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
