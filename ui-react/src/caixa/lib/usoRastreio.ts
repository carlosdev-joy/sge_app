// Envio dos eventos de uso (spec docs/spec-uso-busca-vendas.md §4).
//
// Regras que a tela de Uso assume:
//   • acesso = abertura de uma tela do módulo; o mesmo usuário na mesma rota conta
//     UMA vez a cada 30 min — aqui no cliente E no servidor (`INSERT … NOT EXISTS`),
//     porque o StrictMode e a navegação rápida disparam o efeito duas vezes;
//   • presença = batimento a cada 4 min com a aba visível, para "online agora";
//   • falha é SILENCIOSA: medir nunca pode quebrar nem avisar quem está trabalhando.
// A matrícula NÃO vai no corpo: o servidor a lê do token.
import { apiFetch } from "../../lib/api";
import { useAuthStore } from "../../store/auth";
import { deveRegistrarAcesso, ehRotaDoModulo } from "./usoRegras";

export { INTERVALO_PRESENCA_MS } from "./usoRegras";

const vistosNaSessao = new Map<string, number>();

function enviar(caminho: string, rota: string): void {
  apiFetch(caminho, { method: "POST", body: JSON.stringify({ rota }) }).catch(() => undefined);
}

export function registrarAcesso(rota: string, agora: number = Date.now()): void {
  if (!ehRotaDoModulo(rota)) return;
  // A chave leva a MATRÍCULA: o logout não recarrega a página, e sem ela o primeiro
  // acesso de quem entra depois na mesma estação seria engolido pelo de quem saiu.
  const quem = useAuthStore.getState().user?.matricula ?? "";
  if (!deveRegistrarAcesso(`${quem}|${rota}`, agora, vistosNaSessao)) return;
  enviar("/caixa/uso/acesso", rota);
}

export function registrarPresenca(rota: string): void {
  if (!ehRotaDoModulo(rota)) return;
  enviar("/caixa/uso/presenca", rota);
}
