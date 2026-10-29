// "Pendências" do Resumo do Seguro (Card 4): as mensagens de crítica do
// certificado, uma por linha — a lista tem o certificado UMA vez e as críticas
// dele aqui. Só leitura: o botão por tipo de crítica (Upload, reenvio à
// Samplemed) depende do mapa mensagem → ação, que o negócio ainda não definiu.
import { AlertTriangle } from "lucide-react";
import { dataBr } from "../lib/card1Foto";
import { usePendenciasCard4 } from "../lib/pioCard4";

export default function PendenciasCard4({ certificado, referencia }: { certificado: string; referencia: string | null }) {
  const q = usePendenciasCard4(certificado, referencia, true);
  const itens = q.data?.itens ?? [];

  return (
    <div className="bg-canvas p-6 rounded-lg border border-edge" data-testid="pendencias-card4">
      {q.isPending && <p className="text-sm text-dim">Consultando as pendências…</p>}
      {!q.isPending && !q.data?.disponivel && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Não foi possível ler as pendências. A lista não está vazia — ela é desconhecida.
        </p>
      )}
      {q.data?.disponivel && itens.length === 0 && (
        <p className="text-sm text-dim">Nenhuma pendência registrada nesta foto.</p>
      )}
      {itens.length > 0 && (
        <ul className="divide-y divide-edge">
          {itens.map((it, i) => (
            <li key={`${it.codigo ?? "s"}-${i}`} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <AlertTriangle className="h-4 w-4 mt-1 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
              <div className="min-w-0">
                <p className="font-semibold text-ink break-words">{it.descricao || "Crítica sem descrição"}</p>
                {it.complemento && (
                  <p className="text-sm text-dim whitespace-pre-line break-words mt-0.5">{it.complemento}</p>
                )}
                <p className="text-xs text-dim mt-1">
                  {it.codigo !== null && <>Crítica {it.codigo}</>}
                  {it.codigo !== null && it.data_critica && " · "}
                  {it.data_critica && <>registrada em {dataBr(it.data_critica)}</>}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
