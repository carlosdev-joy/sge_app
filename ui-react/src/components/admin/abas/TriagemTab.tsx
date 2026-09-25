import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { Save } from 'lucide-react'

// ── IA › Triagem de chamados ────────────────────────────────────
// Decisão explícita da spec (docs/spec-admin-reestruturacao.md, F3): este
// bloco (interruptor + lote) ficava DENTRO do card "Credencial executora" da
// aba Integrações › ServiceNow (abas/SondaServiceNowTab.tsx), entre
// "Sincronização agendada habilitada" e os botões, e era gravado pelo mesmo
// "Salvar configuração". Veio para o grupo IA com o conteúdo intacto — não
// devolver.
//
// ⚠️ Gravação: não existe action própria da triagem. Ela vai pelo MESMO
// `servicenow_set` da credencial, que SEMPRE regrava url/usuário/grupos/proxy/
// habilitado (api/routers/admin.py) e só grava chamados_triagem_* quando o
// campo vem no corpo. Por isso o salvar daqui:
//   • relê o servicenow_get NA HORA de gravar (não o cache da tela) e devolve
//     exatamente esses cinco valores — uma edição feita na aba ServiceNow
//     depois que esta aba abriu não é desfeita;
//   • NÃO manda `senha` (ausente = manter a atual; mesma regra de
//     lib/servicenowConfig), então a senha cifrada não é tocada.
// Sem URL válida o backend recusa (422) — igual a antes, quando os dois
// blocos eram salvos juntos; a tela avisa e não deixa tentar.
interface CfgServiceNow {
  url: string; usuario: string; grupos: string; proxy: string; habilitado: boolean
  triagem_habilitada: boolean; triagem_lote: string
}

export function TriagemTab() {
  // Mesma chave da aba ServiceNow: salvar em qualquer uma das duas atualiza a outra.
  const cfgSalva = useQuery<{ config: CfgServiceNow }>({
    queryKey: ['servicenow-cfg'],
    queryFn: () => adminPost('servicenow_get'),
  })
  const cfg = cfgSalva.data?.config
  const [edits, setEdits] = useState<Partial<{ triagem_habilitada: boolean; triagem_lote: string }>>({})
  const cfgForm = {
    triagem_habilitada: edits.triagem_habilitada ?? cfg?.triagem_habilitada ?? false,
    triagem_lote: edits.triagem_lote ?? cfg?.triagem_lote ?? '20',
  }
  const setCfgForm = (patch: Partial<typeof cfgForm>) => setEdits(e => ({ ...e, ...patch }))

  const salvar = useMutation({
    mutationFn: async () => {
      const { config: atual } = await adminPost<{ config: CfgServiceNow }>('servicenow_get')
      return adminPost<{ mensagem?: string }>('servicenow_set', {
        url: atual.url, usuario: atual.usuario, grupos: atual.grupos,
        proxy: atual.proxy, habilitado: atual.habilitado,
        triagem_habilitada: cfgForm.triagem_habilitada,
        triagem_lote: cfgForm.triagem_lote,
      })
    },
    onSuccess: () => {
      toast.success('Triagem de chamados salva.')
      setEdits({})
      queryClient.invalidateQueries({ queryKey: ['servicenow-cfg'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (cfgSalva.isLoading) return <PageSpinner />
  const semInstancia = !cfg?.url
  const sujo = Object.keys(edits).length > 0

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3">
        {/* Triagem por IA — interruptor SEPARADO do provedor. Desligar aqui
            não desliga os assistentes do Caixa Seguro, e vice-versa. */}
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-1.5 text-xs text-ink">
            <input type="checkbox" checked={cfgForm.triagem_habilitada}
              onChange={e => setCfgForm({ triagem_habilitada: e.target.checked })} />
            Triagem dos chamados por IA
          </label>
          <p className="text-[11px] text-dim">
            Classifica cada chamado em <strong>pode iniciar</strong> ou{' '}
            <strong>retornar ao solicitante</strong>, com as lacunas e as perguntas
            a devolver. Usa o provedor configurado em <em>IA</em>.
            {' '}Desligada, a fila continua sendo classificada por regra de texto —
            e a tela marca esses vereditos como automáticos, para ninguém confundir
            com análise de IA.
          </p>
          <Input label="Chamados analisados por ciclo" type="number" className="w-56"
            value={cfgForm.triagem_lote}
            ajuda="A triagem roda dentro do ciclo de 15 min, que tem teto de 10 min. Lote grande demais faz o sync estourar o tempo."
            onChange={e => setCfgForm({ triagem_lote: e.target.value })} />
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-edge pt-3">
          {semInstancia && (
            <p className="mr-auto text-xs text-dim">
              Preencha a instância em Integrações › ServiceNow antes: a triagem é gravada junto com a integração.
            </p>
          )}
          <Button size="sm" onClick={() => salvar.mutate()} loading={salvar.isPending} disabled={semInstancia || !sujo}>
            <Save size={11} /> Salvar
          </Button>
        </div>
      </div>
    </div>
  )
}
