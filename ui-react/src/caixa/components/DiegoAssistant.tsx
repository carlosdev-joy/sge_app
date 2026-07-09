import { useState, useEffect, useRef } from "react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { ScrollArea } from "./ui/scroll-area";
import { X, Send, Download, History } from "lucide-react";
import TypingIndicator from "./TypingIndicator";
import diegoAvatar from "../assets/diego-avatar.png";
import { useToast } from "../hooks/use-toast";
import { apiFetch } from "../../lib/api";
import { useAssistentesIA, CHAT_ENDPOINT, type ConversaHistorico } from "../lib/config";
import jsPDF from "jspdf";

interface Message {
  id: number;
  text: string;
  sender: "user" | "assistant";
  timestamp: Date;
}

interface DiegoAssistantProps {
  suggestedQuestions?: string[];
  pageContext?: string;
}

const defaultQuestions = [
  "Quais são as principais pendências de propostas?",
  "Analise os casos de declínio",
  "Qual o valor total em emissões?",
  "Gere um relatório de performance",
];

const DiegoAssistantInner = ({ suggestedQuestions = defaultQuestions, pageContext = "Seguro de Vida" }: DiegoAssistantProps) => {
  const { toast } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Olá! Sou o Diego, seu assistente virtual. Posso te ajudar a entender os dados da página, gerar análises personalizadas e até exportar relatórios em PDF. Como posso ajudar?",
      sender: "assistant",
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<any[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (showHistory) {
      loadConversationHistory();
    }
  }, [showHistory]);

  const loadConversationHistory = async () => {
    try {
      const data = await apiFetch<{ conversas: ConversaHistorico[] }>(`${CHAT_ENDPOINT("diego")}/historico`);
      setConversationHistory(data.conversas ?? []);
    } catch (error) {
      console.error("Error loading history:", error);
    }
  };

  const saveConversation = async (_userMessage: string, _aiResponse: string) => {
    // F4: o backend registra a conversa em etl_caixa_chat_log.
  };

  const getContextData = () => {
    return {
      page: pageContext,
      availableData: [
        'Status de propostas (Assinatura, Pagamento, Documentação)',
        'Emissões e declínios',
        'Motivos de declínio',
        'Análise comparativa de produtos',
        'Evolução temporal de vendas',
      ],
      currentMetrics: {
        pendingSignature: 217,
        totalEmissions: 456,
        totalDeclines: 89,
      },
    };
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: messages.length + 1,
      text: inputValue,
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      const context = getContextData();
      
      const data = await apiFetch<{ response: string }>(CHAT_ENDPOINT("diego"), {
        method: "POST",
        body: JSON.stringify({ message: inputValue, context }),
      });

      const assistantMessage: Message = {
        id: messages.length + 2,
        text: data.response,
        sender: "assistant",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      await saveConversation(inputValue, data.response);

    } catch (error: any) {
      console.error('Error calling Diego:', error);
      
      let errorMessage = "Desculpe, ocorreu um erro ao processar sua mensagem.";
      
      if (error.message?.includes('429')) {
        errorMessage = "Limite de requisições excedido. Por favor, aguarde um momento e tente novamente.";
      } else if (error.message?.includes('402')) {
        errorMessage = "Créditos insuficientes. Por favor, adicione créditos ao seu workspace.";
      }

      const errorMsg: Message = {
        id: messages.length + 2,
        text: errorMessage,
        sender: "assistant",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMsg]);

      toast({
        title: "Erro",
        description: errorMessage,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestedQuestion = (question: string) => {
    setInputValue(question);
  };

  const exportToPDF = () => {
    try {
      const doc = new jsPDF();
      const pageWidth = doc.internal.pageSize.getWidth();
      const margin = 20;
      let yPosition = margin;

      // Header
      doc.setFontSize(18);
      doc.setTextColor(0, 85, 177);
      doc.text("Conversa com Diego - Assistente de Seguro de Vida", margin, yPosition);
      yPosition += 10;

      doc.setFontSize(10);
      doc.setTextColor(100);
      doc.text(`Exportado em: ${new Date().toLocaleString('pt-BR')}`, margin, yPosition);
      yPosition += 15;

      // Messages
      doc.setFontSize(11);
      messages.forEach((message) => {
        if (yPosition > 270) {
          doc.addPage();
          yPosition = margin;
        }

        // Sender label
        doc.setTextColor(message.sender === "user" ? 50 : 0, 85, 177);
        doc.setFont("helvetica", "bold");
        doc.text(message.sender === "user" ? "Você:" : "Diego:", margin, yPosition);
        yPosition += 6;

        // Message text
        doc.setFont("helvetica", "normal");
        doc.setTextColor(50);
        const lines = doc.splitTextToSize(message.text, pageWidth - 2 * margin);
        doc.text(lines, margin, yPosition);
        yPosition += lines.length * 6 + 8;
      });

      doc.save(`diego-conversa-${new Date().getTime()}.pdf`);

      toast({
        title: "PDF exportado com sucesso",
        description: "A conversa foi salva em PDF.",
      });
    } catch (error) {
      console.error('Error exporting PDF:', error);
      toast({
        title: "Erro ao exportar",
        description: "Não foi possível exportar a conversa para PDF.",
        variant: "destructive",
      });
    }
  };

  const loadHistoryConversation = (conversation: any) => {
    const historyMessages: Message[] = [
      {
        id: 1,
        text: conversation.message,
        sender: "user",
        timestamp: new Date(conversation.created_at),
      },
      {
        id: 2,
        text: conversation.response,
        sender: "assistant",
        timestamp: new Date(conversation.created_at),
      },
    ];
    setMessages(historyMessages);
    setShowHistory(false);
  };

  if (showHistory) {
    return (
      <Card className="fixed bottom-6 right-6 w-96 h-[600px] shadow-2xl flex flex-col z-50 bg-card">
        <div className="flex items-center justify-between p-4 border-b bg-primary text-primary-foreground rounded-t-lg">
          <h3 className="font-semibold">Histórico de Conversas</h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowHistory(false)}
            className="hover:bg-primary-foreground/20 text-primary-foreground"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1 p-4">
          {conversationHistory.length === 0 ? (
            <p className="text-muted-foreground text-sm text-center py-8">
              Nenhuma conversa anterior encontrada.
            </p>
          ) : (
            <div className="space-y-3">
              {conversationHistory.map((conv) => (
                <Card
                  key={conv.id}
                  className="p-3 hover:bg-accent cursor-pointer transition-colors"
                  onClick={() => loadHistoryConversation(conv)}
                >
                  <p className="text-sm font-medium mb-1">{conv.message.substring(0, 60)}...</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(conv.created_at).toLocaleString('pt-BR')}
                  </p>
                </Card>
              ))}
            </div>
          )}
        </ScrollArea>
      </Card>
    );
  }

  return (
    <>
      {!isOpen && (
        <Button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 h-24 w-24 rounded-full shadow-2xl bg-primary hover:bg-primary/90 z-50 p-0 overflow-hidden hover:scale-110 transition-transform duration-300 animate-fade-in"
          size="icon"
        >
          <img 
            src={diegoAvatar} 
            alt="Diego" 
            className="h-full w-full object-cover"
          />
        </Button>
      )}

      {isOpen && (
        <Card className="fixed bottom-6 right-6 w-96 h-[600px] shadow-2xl flex flex-col z-50 bg-card animate-scale-in">
          <div className="flex items-center justify-between p-4 border-b bg-primary text-primary-foreground rounded-t-lg">
            <div className="flex items-center gap-3">
              <div className={`relative ${isLoading ? 'animate-pulse' : ''}`}>
                <img 
                  src={diegoAvatar} 
                  alt="Diego" 
                  className="h-14 w-14 rounded-full bg-white p-1"
                />
                {isLoading && (
                  <div className="absolute inset-0 rounded-full border-2 border-white border-t-transparent animate-spin"></div>
                )}
              </div>
              <div>
                <h3 className="font-semibold">Diego</h3>
                {isLoading && <p className="text-xs opacity-90">Pensando...</p>}
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowHistory(true)}
                className="hover:bg-primary-foreground/20 text-primary-foreground"
                title="Ver histórico"
              >
                <History className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={exportToPDF}
                className="hover:bg-primary-foreground/20 text-primary-foreground"
                title="Exportar para PDF"
              >
                <Download className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsOpen(false)}
                className="hover:bg-primary-foreground/20 text-primary-foreground"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <ScrollArea className="flex-1 p-4" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex animate-fade-in ${
                    message.sender === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {message.sender === "assistant" && (
                    <img 
                      src={diegoAvatar} 
                      alt="Diego" 
                      className="h-8 w-8 rounded-full mr-2 bg-muted p-1 flex-shrink-0"
                    />
                  )}
                  <div
                    className={`max-w-[80%] rounded-lg p-3 transform transition-all duration-300 hover:scale-105 ${
                      message.sender === "user"
                        ? "bg-white text-black"
                        : "bg-primary text-white"
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{message.text}</p>
                    <p className="text-xs opacity-70 mt-1">
                      {message.timestamp.toLocaleTimeString("pt-BR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="flex justify-start animate-fade-in">
                  <img 
                    src={diegoAvatar} 
                    alt="Diego" 
                    className="h-8 w-8 rounded-full mr-2 bg-muted p-1 animate-pulse"
                  />
                  <div className="bg-muted rounded-lg p-3 flex items-center gap-3">
                    <TypingIndicator />
                    <span className="text-sm text-muted-foreground">Diego está digitando...</span>
                  </div>
                </div>
              )}

              {messages.length <= 1 && !isLoading && (
                <div className="space-y-2 mt-4 animate-fade-in">
                  <p className="text-xs text-muted-foreground font-medium">
                    Perguntas sugeridas:
                  </p>
                  {suggestedQuestions.map((question, index) => (
                    <Button
                      key={index}
                      variant="outline"
                      size="sm"
                      className="w-full text-left justify-start h-auto py-2 px-3 hover:scale-105 transition-transform duration-200"
                      onClick={() => handleSuggestedQuestion(question)}
                    >
                      <span className="text-xs">{question}</span>
                    </Button>
                  ))}
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="p-4 border-t">
            <div className="flex gap-2">
              <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && !isLoading && handleSendMessage()}
                placeholder="Digite sua pergunta..."
                className="flex-1"
                disabled={isLoading}
              />
              <Button 
                onClick={handleSendMessage} 
                size="icon"
                disabled={isLoading || !inputValue.trim()}
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
      )}
    </>
  );
};

// Visível só quando os assistentes estão ativos (Admin > Caixa Seguro IA).
const DiegoAssistant = (props: DiegoAssistantProps) => {
  const ativos = useAssistentesIA();
  return ativos ? <DiegoAssistantInner {...props} /> : null;
};

export default DiegoAssistant;
