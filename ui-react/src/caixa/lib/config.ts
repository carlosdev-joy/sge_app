// Config da seção Caixa Seguro.
//
// Assistentes IA (Diego/Lari/Léo): a Fase 4 entrega o backend
// (POST /caixa/chat/{assistente}) e a config ativar/desativar no admin.
// Até lá o flag fica desligado e os assistentes não são renderizados.
export const ASSISTENTES_IA_ATIVOS = false;

// Endpoint que a Fase 4 implementa — os assistentes já falam com ele.
export const CHAT_ENDPOINT = (assistente: "diego" | "lari" | "leo") =>
  `/caixa/chat/${assistente}`;
