// FAB de chat dos assistentes (Diego/Lari/Léo) no visual NATIVO do Orquestra —
// chat único de todas as telas da seção desde a F9 da migração; substituiu os
// assistentes shadcn da POC. Mesmo backend da POC
// (POST /caixa/chat/{assistente} + /historico, gate useAssistentesIA), mas UI
// com tokens panel/edge/ink e Button do Orquestra.
import { useState, useEffect, useRef } from "react";
import { X, Send, Download, History } from "lucide-react";
import jsPDF from "jspdf";
import { Button } from "../../components/ui/Button";
import { toast } from "../../components/ui/Toast";
import { apiFetch } from "../../lib/api";
import { useAssistentesIA, CHAT_ENDPOINT, type ConversaHistorico } from "../lib/config";
import MensagemMarkdown from "./MensagemMarkdown";
import { montarConversaPdf } from "../lib/conversaPdf";

type Assistente = "diego" | "lari" | "leo";

interface Message {
  id: number;
  text: string;
  sender: "user" | "assistant";
  timestamp: Date;
}

interface Props {
  assistente: Assistente;
  nome: string;
  avatar: string;
  pageContext: string;
  suggestedQuestions?: string[];
}

const defaultQuestions = [
  "Quais são as principais pendências de propostas?",
  "Analise os casos de declínio",
  "Qual o valor total em emissões?",
  "Gere um relatório de performance",
];

export default function ChatAssistant({ assistente, nome, avatar, pageContext, suggestedQuestions = defaultQuestions }: Props) {
  const ativos = useAssistentesIA();
  const [isOpen, setIsOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { id: 1, text: `Olá! Sou o ${nome}, seu assistente virtual. Posso ajudar a entender os dados da página, gerar análises e exportar a conversa em PDF. Como posso ajudar?`, sender: "assistant", timestamp: new Date() },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<ConversaHistorico[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, isLoading]);

  useEffect(() => {
    if (!showHistory) return;
    apiFetch<{ conversas: ConversaHistorico[] }>(`${CHAT_ENDPOINT(assistente)}/historico`)
      .then((d) => setConversationHistory(d.conversas ?? []))
      .catch((e) => console.error("Erro ao carregar histórico:", e));
  }, [showHistory, assistente]);

  if (!ativos) return null;

  const getContext = () => ({
    page: pageContext,
    availableData: ["Status de propostas", "Emissões e declínios", "Motivos de declínio", "Comparativo de produtos", "Evolução temporal"],
  });

  const send = async () => {
    if (!inputValue.trim() || isLoading) return;
    const pergunta = inputValue;
    setMessages((prev) => [...prev, { id: prev.length + 1, text: pergunta, sender: "user", timestamp: new Date() }]);
    setInputValue("");
    setIsLoading(true);
    try {
      const data = await apiFetch<{ response: string }>(CHAT_ENDPOINT(assistente), {
        method: "POST",
        body: JSON.stringify({ message: pergunta, context: getContext() }),
      });
      setMessages((prev) => [...prev, { id: prev.length + 1, text: data.response, sender: "assistant", timestamp: new Date() }]);
    } catch (e) {
      // apiFetch anexa .status ao erro e põe o detail do backend na .message.
      const err = e as Error & { status?: number };
      let texto: string;
      if (err.status === 429) texto = "Limite de requisições excedido. Aguarde um momento e tente novamente.";
      else if (err.status === 402) texto = "Créditos insuficientes no provedor de IA.";
      else if (err.status === 503) texto = "Assistentes IA temporariamente indisponíveis — contate o administrador.";
      else texto = err.message || "Desculpe, ocorreu um erro ao processar sua mensagem.";
      setMessages((prev) => [...prev, { id: prev.length + 1, text: texto, sender: "assistant", timestamp: new Date() }]);
      toast.error(texto);
    } finally {
      setIsLoading(false);
    }
  };

  // O PDF desenha os MESMOS blocos que a bolha (markdown.ts), e não o texto
  // cru: antes ele exportava `## Status`, `**Emitida**` e as tabelas em canos,
  // e os emoji viravam lixo ("📋" saía "Ø=ÜË") porque as fontes padrão do
  // jsPDF escrevem em WinAnsi. O desenho mora em conversaPdf.ts — de lá ele
  // pode ser PROVADO gerando um arquivo de verdade, coisa que dentro de um
  // onClick não dava.
  const exportPDF = () => {
    try {
      const doc = new jsPDF();
      montarConversaPdf(doc, { nome, mensagens: messages });
      doc.save(`${assistente}-conversa-${Date.now()}.pdf`);
      toast.success("Conversa exportada em PDF.");
    } catch (e) {
      console.error(e);
      toast.error("Não foi possível exportar a conversa.");
    }
  };

  // FAB fechado
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 h-16 w-16 rounded-full overflow-hidden shadow-lg ring-2 ring-[#1A5FA8] hover:scale-105 transition-transform bg-panel"
        title={`Falar com ${nome}`}
        aria-label={`Abrir chat com ${nome}`}
      >
        <img src={avatar} alt={nome} className="h-full w-full object-cover" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-96 max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-3rem)] bg-panel border border-edge rounded-xl shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1A5FA8] text-white">
        <div className="flex items-center gap-3 min-w-0">
          <img src={avatar} alt={nome} className={`h-10 w-10 rounded-full bg-white/90 p-0.5 object-cover ${isLoading ? "animate-pulse" : ""}`} />
          <div className="min-w-0">
            <h3 className="font-semibold leading-tight">{nome}</h3>
            <p className="text-[11px] text-white/80">{isLoading ? "Pensando..." : "Assistente virtual"}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowHistory((v) => !v)} title="Histórico" className="p-1.5 rounded hover:bg-white/15 transition-colors"><History size={16} /></button>
          <button onClick={exportPDF} title="Exportar PDF" className="p-1.5 rounded hover:bg-white/15 transition-colors"><Download size={16} /></button>
          <button onClick={() => setIsOpen(false)} title="Fechar" className="p-1.5 rounded hover:bg-white/15 transition-colors"><X size={16} /></button>
        </div>
      </div>

      {/* Corpo: histórico OU conversa */}
      {showHistory ? (
        <div className="flex-1 overflow-y-auto p-4">
          <p className="text-xs text-dim font-medium mb-3">Conversas anteriores</p>
          {conversationHistory.length === 0 ? (
            <p className="text-sm text-dim text-center py-8">Nenhuma conversa anterior.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {conversationHistory.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setMessages([
                      { id: 1, text: c.message, sender: "user", timestamp: new Date(c.created_at) },
                      { id: 2, text: c.response, sender: "assistant", timestamp: new Date(c.created_at) },
                    ]);
                    setShowHistory(false);
                  }}
                  className="text-left bg-canvas border border-edge rounded-lg p-3 hover:border-blue-400 transition-colors"
                >
                  <p className="text-sm text-ink truncate">{c.message}</p>
                  <p className="text-xs text-dim mt-0.5">{new Date(c.created_at).toLocaleString("pt-BR")}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
          {messages.map((mm) => (
            <div key={mm.id} className={`flex ${mm.sender === "user" ? "justify-end" : "justify-start gap-2"}`}>
              {mm.sender === "assistant" && <img src={avatar} alt={nome} className="h-7 w-7 rounded-full bg-edge/60 p-0.5 object-cover shrink-0" />}
              <div className={`min-w-0 max-w-[80%] rounded-lg p-3 ${mm.sender === "user" ? "bg-canvas border border-edge text-ink" : "bg-[#1A5FA8] text-white"}`}>
                {/* Markdown só na resposta do assistente. O que a pessoa
                    digitou aparece como digitou — interpretar o texto DELA
                    esconderia caracteres que ela quis mandar. */}
                {mm.sender === "assistant"
                  ? <MensagemMarkdown texto={mm.text} />
                  : <p className="text-sm whitespace-pre-wrap">{mm.text}</p>}
                <p className={`text-[10px] mt-1 ${mm.sender === "user" ? "text-dim" : "text-white/70"}`}>
                  {mm.timestamp.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start gap-2">
              <img src={avatar} alt={nome} className="h-7 w-7 rounded-full bg-edge/60 p-0.5 object-cover animate-pulse" />
              <div className="bg-[#1A5FA8] text-white rounded-lg p-3 flex items-center gap-2">
                <span className="flex gap-1">
                  <span className="h-2 w-2 rounded-full bg-white/80 animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="h-2 w-2 rounded-full bg-white/80 animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="h-2 w-2 rounded-full bg-white/80 animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
                <span className="text-xs text-white/80">{nome} está digitando...</span>
              </div>
            </div>
          )}
          {messages.length <= 1 && !isLoading && (
            <div className="flex flex-col gap-2 mt-2">
              <p className="text-xs text-dim font-medium">Perguntas sugeridas:</p>
              {suggestedQuestions.map((q) => (
                <button
                  key={q}
                  onClick={() => setInputValue(q)}
                  className="text-left text-xs bg-canvas border border-edge rounded-md px-3 py-2 text-ink hover:border-blue-400 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Input */}
      {!showHistory && (
        <div className="p-3 border-t border-edge flex gap-2">
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !isLoading) send(); }}
            placeholder="Digite sua pergunta..."
            disabled={isLoading}
            className="flex-1 bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          />
          <Button variant="primary" size="md" onClick={send} disabled={isLoading || !inputValue.trim()} aria-label="Enviar">
            <Send size={15} />
          </Button>
        </div>
      )}
    </div>
  );
}
