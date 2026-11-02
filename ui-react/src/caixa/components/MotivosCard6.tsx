// "Motivos da Rejeição" do Resumo do Seguro (Card 6): os motivos de declínio do
// certificado, um por linha, como ÚLTIMA informação de "Dados da Venda"
// (RITM0118511). A lista tem o certificado UMA vez e os motivos dele aqui. Só
// leitura: nenhuma ação é inferida do texto do motivo.
import { dataBr } from "../lib/card1Foto";
import { useMotivosCard6 } from "../lib/pioCard6";

export default function MotivosCard6({ certificado, referencia, total }: { certificado: string; referencia: string | null; total: number }) {
  const q = useMotivosCard6(certificado, referencia, true);
  const itens = q.data?.itens ?? [];

  return (
    <div data-testid="motivos-card6">
      <p className="text-sm text-dim mb-1">Motivos da Rejeição ({total}):</p>
      {q.isPending && <p className="text-sm text-dim">Consultando os motivos…</p>}
      {!q.isPending && !q.data?.disponivel && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Não foi possível ler os motivos. A lista não está vazia — ela é desconhecida.
        </p>
      )}
      {q.data?.disponivel && itens.length === 0 && (
        <p className="text-sm text-dim">Nenhum motivo registrado nesta foto.</p>
      )}
      {itens.length > 0 && (
        <ul className="divide-y divide-edge">
          {itens.map((it, i) => (
            <li key={`${it.codigo ?? "s"}-${i}`} className="py-2 first:pt-0 last:pb-0">
              <p className="font-semibold text-ink break-words">{it.descricao || "Motivo sem descrição"}</p>
              {it.complemento && (
                <p className="text-sm text-dim whitespace-pre-line break-words mt-0.5">{it.complemento}</p>
              )}
              <p className="text-xs text-dim mt-1">
                {it.codigo !== null && <>Motivo {it.codigo}</>}
                {it.codigo !== null && it.data_motivo && " · "}
                {it.data_motivo && <>registrado em {dataBr(it.data_motivo)}</>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
