import { useState, useEffect, useRef } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import { Send, X, History, FileDown } from "lucide-react";
import TypingIndicator from "./TypingIndicator";
import { apiFetch } from "../../lib/api";
import { ASSISTENTES_IA_ATIVOS, CHAT_ENDPOINT } from "../lib/config";
import { toast } from "sonner";
import jsPDF from "jspdf";
import lariAvatar from "../assets/lari-avatar.png";

interface Message {
  id: string;
  text: string;
  sender: "user" | "assistant";
  timestamp: Date;
}

interface LariAssistantProps {
  suggestedQuestions?: string[];
  pageContext?: string;
}

const defaultQuestions = [
  "Quais são as principais coberturas do Prestamista?",
  "Como funciona a análise de risco no Prestamista?",
  "Qual o perfil ideal de cliente para Prestamista?",
  "Como otimizar vendas de Prestamista?",
];

const LariAssistantInner = ({ suggestedQuestions = defaultQuestions, pageContext = "Prestamista" }: LariAssistantProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      text: "Olá! Sou a Lari, sua assistente virtual. Como posso ajudá-lo hoje?",
      sender: "assistant",
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (showHistory) {
      loadConversationHistory();
    }
  }, [showHistory]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const loadConversationHistory = async () => {
    // Histórico local desabilitado na F3 — na F4 passa a ler do log do
    // backend (etl_caixa_chat_log) no lugar do Supabase da POC.
    setConversationHistory([]);
  };

  const getContextData = () => {
    return {
      page: pageContext,
      availableData: "Dados contextuais da página",
    };
  };

  const saveConversation = async (_userMessage: string, _aiResponse: string) => {
    // F4: o backend registra a conversa em etl_caixa_chat_log.
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputValue,
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      const context = getContextData();

      const data = await apiFetch<{ response: string }>(CHAT_ENDPOINT("lari"), {
        method: "POST",
        body: JSON.stringify({ message: inputValue, context }),
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: data.response,
        sender: "assistant",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      await saveConversation(inputValue, data.response);
    } catch (error) {
      console.error('Error sending message:', error);
      toast.error("Erro ao enviar mensagem. Tente novamente.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestedQuestion = (question: string) => {
    setInputValue(question);
  };

  const exportToPDF = () => {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 20;
    const maxWidth = pageWidth - 2 * margin;
    let yPosition = 20;

    doc.setFontSize(16);
    doc.text("Conversa com Lari - Prestamista", margin, yPosition);
    yPosition += 10;

    doc.setFontSize(10);
    messages.forEach((message) => {
      const sender = message.sender === "user" ? "Você" : "Lari";
      const text = `${sender}: ${message.text}`;
      const lines = doc.splitTextToSize(text, maxWidth);

      if (yPosition + lines.length * 7 > doc.internal.pageSize.getHeight() - 20) {
        doc.addPage();
        yPosition = 20;
      }

      doc.text(lines, margin, yPosition);
      yPosition += lines.length * 7 + 5;
    });

    doc.save("conversa-lari-prestamista.pdf");
    toast.success("PDF exportado com sucesso!");
  };

  const loadHistoryConversation = (conversation: any) => {
    const newMessages: Message[] = [
      {
        id: "1",
        text: "Olá! Sou a Lari, sua assistente especializada em Prestamista. Como posso ajudá-lo hoje?",
        sender: "assistant",
        timestamp: new Date(),
      },
      {
        id: Date.now().toString(),
        text: conversation.message,
        sender: "user",
        timestamp: new Date(conversation.created_at),
      },
      {
        id: (Date.now() + 1).toString(),
        text: conversation.response,
        sender: "assistant",
        timestamp: new Date(conversation.created_at),
      },
    ];
    setMessages(newMessages);
    setShowHistory(false);
  };

  if (!isOpen) {
    return (
      <Button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 h-24 w-24 rounded-full shadow-2xl bg-primary hover:bg-primary/90 z-50 p-0 overflow-hidden hover:scale-110 transition-transform duration-300 animate-fade-in"
        size="icon"
      >
        <img 
          src={lariAvatar} 
          alt="Lari" 
          className="h-full w-full object-cover"
        />
      </Button>
    );
  }

  return (
    <Card className="fixed bottom-6 right-6 w-96 h-[600px] shadow-2xl flex flex-col z-50 animate-scale-in">
      <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-primary to-primary/80">
        <div className="flex items-center gap-3">
          <img 
            src={lariAvatar} 
            alt="Lari" 
            className="w-12 h-12 rounded-full object-cover border-2 border-white shadow-md"
          />
          <div>
            <h3 className="font-semibold text-white">Lari</h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowHistory(!showHistory)}
            className="text-white hover:bg-white/20"
          >
            <History className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={exportToPDF}
            className="text-white hover:bg-white/20"
          >
            <FileDown className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsOpen(false)}
            className="text-white hover:bg-white/20"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {showHistory ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          <h4 className="font-semibold mb-2">Histórico de Conversas</h4>
          {conversationHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma conversa anterior encontrada.</p>
          ) : (
            conversationHistory.map((conv) => (
              <Card
                key={conv.id}
                className="p-3 cursor-pointer hover:bg-accent transition-colors"
                onClick={() => loadHistoryConversation(conv)}
              >
                <p className="text-sm font-medium truncate">{conv.message}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {new Date(conv.created_at).toLocaleDateString('pt-BR')}
                </p>
              </Card>
            ))
          )}
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.sender === "user" ? "justify-end" : "justify-start"
                } animate-fade-in`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-3 transform transition-all duration-300 hover:scale-105 ${
                    message.sender === "user"
                      ? "bg-white text-black"
                      : "bg-primary text-white"
                  }`}
                >
                  <p className="text-sm">{message.text}</p>
                  <span className="text-xs opacity-70 mt-1 block">
                    {message.timestamp.toLocaleTimeString('pt-BR', {
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start animate-fade-in">
                <div className="bg-muted rounded-lg p-3 flex items-center gap-3">
                  <TypingIndicator />
                  <span className="text-sm text-muted-foreground">Lari está digitando...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {messages.length === 1 && (
            <div className="px-4 pb-2">
              <p className="text-xs text-muted-foreground mb-2">Perguntas sugeridas:</p>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((question, index) => (
                  <Button
                    key={index}
                    variant="outline"
                    size="sm"
                    onClick={() => handleSuggestedQuestion(question)}
                    className="text-xs"
                  >
                    {question}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="p-4 border-t">
            <div className="flex gap-2">
              <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                placeholder="Digite sua mensagem..."
                disabled={isLoading}
                className="flex-1"
              />
              <Button 
                onClick={handleSendMessage} 
                disabled={isLoading || !inputValue.trim()}
                size="icon"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
};

// Oculto enquanto os assistentes IA não estão ativos (a F4 liga via config).
const LariAssistant = (props: LariAssistantProps) =>
  ASSISTENTES_IA_ATIVOS ? <LariAssistantInner {...props} /> : null;

export default LariAssistant;
