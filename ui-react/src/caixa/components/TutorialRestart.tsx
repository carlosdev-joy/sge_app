import { Button } from "./ui/button";
import { RotateCcw } from "lucide-react";
import { useToast } from "../hooks/use-toast";

const TutorialRestart = () => {
  const { toast } = useToast();

  const handleRestart = () => {
    localStorage.removeItem("hasSeenTutorial");
    toast({
      title: "Tutorial reiniciado",
      description: "Recarregue a página para ver o tutorial novamente.",
    });
    setTimeout(() => {
      window.location.href = "/";
    }, 1500);
  };

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleRestart}
      className="gap-2"
    >
      <RotateCcw className="h-4 w-4" />
      Ver Tutorial Novamente
    </Button>
  );
};

export default TutorialRestart;
