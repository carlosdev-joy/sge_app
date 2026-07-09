// Config da seção Caixa Seguro.
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../lib/api";

// Endpoint dos assistentes IA (backend em api/routers/caixa_chat.py).
export const CHAT_ENDPOINT = (assistente: "diego" | "lari" | "leo") =>
  `/caixa/chat/${assistente}`;

// Item do histórico de conversas (GET /caixa/chat/{assistente}/historico) —
// mesma shape que a POC consumia do Supabase.
export interface ConversaHistorico {
  id: number;
  message: string;
  response: string;
  context: Record<string, unknown> | null;
  created_at: string;
}

// Visibilidade dos assistentes decidida pelo backend
// (Admin > Caixa Seguro IA → GET /caixa/chat/status). Enquanto a resposta
// não chega — ou em erro — os assistentes ficam ocultos.
export function useAssistentesIA(): boolean {
  const { data } = useQuery<{ enabled: boolean }>({
    queryKey: ["caixa-ia-status"],
    queryFn: () => apiFetch("/caixa/chat/status"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  return data?.enabled ?? false;
}
