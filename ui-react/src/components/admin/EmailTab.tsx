// Admin › Acessos & Comunicação › E-mail — o container (F1 da spec
// docs/spec-notificacao-email.md): configuração global do canal (remetente
// único, interruptor, limite de anexo, raízes permitidas, domínios) e o botão
// Testar, cujo laudo fica NA TELA (um toast some, e "isso está mandando?"
// precisa de resposta que sobreviva ao F5 — mesmo desenho do Verificar da IA).
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { InfoBanner } from '../ui/InfoBanner'
import { Input, Textarea } from '../ui/Input'
import { PageSpinner } from '../ui/Spinner'
import { Switch } from '../ui/Switch'
import { toast } from '../ui/Toast'
import { EmailModelos } from './EmailModelos'
import {
  ETAPA_LAUDO, configParaApi, errosDaConfig, formDaConfig, mensagemErroEmail, migration111Pendente,
  type EmailConfigApi, type EmailConfigForm, type EmailLaudo, type EmailLogItem,
} from '../../lib/emailAdmin'

const Q_CONFIG = ['email-admin-config'] as const
const Q_LOG = ['email-log', '_teste_admin'] as const

export function EmailTab() {
  const config = useQuery<{ config: EmailConfigApi }>({ queryKey: Q_CONFIG, queryFn: () => apiFetch('/email/admin/config') })
  if (config.isLoading) return <PageSpinner />
  if (config.isError || !config.data) {
    return (
      <InfoBanner icon="⚠">
        {migration111Pendente(config.error)
          ? 'O e-mail exige a migration 111 (chaves email_* e a tabela etl_email_log). Aplique-a na etapa 6c do deploy e recarregue.'
          : `Falha ao carregar a configuração de e-mail: ${mensagemErroEmail(config.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }
  return <EmailForm cfg={config.data.config} />
}

// Separado para o form nascer da config carregada (edições sobrevivem ao refetch).
function EmailForm({ cfg }: { cfg: EmailConfigApi }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<EmailConfigForm>(() => formDaConfig(cfg))
  const [para, setPara] = useState('')
  const [laudo, setLaudo] = useState<EmailLaudo | null>(null)
  const erros = errosDaConfig(form)
  const log = useQuery<{ envios: EmailLogItem[] }>({ queryKey: Q_LOG, queryFn: () => apiFetch('/email/log?pipeline=_teste_admin&limite=10') })

  const salvar = useMutation({
    mutationFn: (f: EmailConfigForm) => apiFetch<{ config: EmailConfigApi }>('/email/admin/config', { method: 'POST', body: JSON.stringify(configParaApi(f)) }),
    onSuccess: async r => {
      toast.success('Configuração de e-mail salva')
      setForm(formDaConfig(r.config))
      setLaudo(null)   // o laudo descreve a configuração que foi testada
      await Promise.all([qc.invalidateQueries({ queryKey: Q_CONFIG }), qc.invalidateQueries({ queryKey: ['email-status'] })])
    },
    onError: (e: unknown) => toast.error(mensagemErroEmail(e, 'Não foi possível salvar')),
  })
  const testar = useMutation({
    mutationFn: () => apiFetch<{ laudo: EmailLaudo }>('/email/admin/testar', { method: 'POST', body: JSON.stringify(para.trim() ? { para: para.trim() } : {}) }),
    onSuccess: async r => { setLaudo(r.laudo); await qc.invalidateQueries({ queryKey: Q_LOG }) },
    onError: (e: unknown) => toast.error(mensagemErroEmail(e, 'Não foi possível testar')),
  })

  const mudou = JSON.stringify(configParaApi(form)) !== JSON.stringify(configParaApi(formDaConfig(cfg)))

  return (
    <div className="flex max-w-3xl flex-col gap-4" data-email-admin>
      <InfoBanner>
        Canal de e-mail do Orquestra. O envio sai do <strong>servidor do DataStage</strong> (Postfix, pelo SSH
        que o operador já usa) com um <strong>remetente único</strong>. Nada é enviado automaticamente: só o nó de
        e-mail que o usuário colocar no fluxo (próxima fase). Desligado, os nós de e-mail são pulados sem falhar.
      </InfoBanner>

      <section className="flex flex-col gap-4 rounded-lg border border-edge bg-panel p-4 shadow-sm" data-email-config>
        <div className="flex flex-wrap items-center gap-4">
          <Switch label={form.enabled ? 'Canal de e-mail ligado' : 'Canal de e-mail desligado'} checked={form.enabled}
                  onChange={e => setForm({ ...form, enabled: e.target.checked })}
                  hint="Ligar exige o remetente. Desligado, o nó de e-mail é pulado (skipped) sem falhar o pipeline." />
          <span className="text-xs text-dim">
            SSH do DataStage: {cfg.ssh_configurado
              ? <span className="text-emerald-700 dark:text-emerald-300">configurado ({cfg.ssh_host})</span>
              : <span className="text-amber-700 dark:text-amber-300">não configurado (DS_SSH_HOST/USER no ambiente da API)</span>}
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_10rem]">
          <Input label="Remetente (único para todos os envios)" value={form.remetente}
                 onChange={e => setForm({ ...form, remetente: e.target.value })} placeholder="ex.: orquestra@caixavidaeprevidencia.com.br"
                 ajuda="O endereço que aparece em From:. O relay não exige autenticação; o remetente validado em produção foi o do Orquestra." />
          <Input label="Limite de anexo (MB)" type="number" min={1} max={25} value={form.limite_mb}
                 onChange={e => setForm({ ...form, limite_mb: e.target.value })} ajuda="De 1 a 25 MB. Anexo maior que isso é descartado com aviso — o e-mail sai sem ele." />
        </div>
        <Textarea label="Raízes permitidas para anexos (uma por linha — caminhos no servidor do DataStage)" rows={3}
                  value={form.raizesTexto} onChange={e => setForm({ ...form, raizesTexto: e.target.value })}
                  placeholder={'/opt/IBM/dados/saida\n/dados/relatorios'}
                  ajuda="No nó de e-mail o usuário escolhe uma destas raízes e digita o nome do arquivo (livre — pode ainda não existir). Sem raiz cadastrada, o nó não aceita anexo." />
        <Textarea label="Domínios de destinatário permitidos (opcional, um por linha)" rows={2}
                  value={form.dominiosTexto} onChange={e => setForm({ ...form, dominiosTexto: e.target.value })}
                  placeholder="caixavidaeprevidencia.com.br"
                  ajuda="Vazio = qualquer domínio. O relay foi validado só para o domínio interno; um domínio externo que o relay recuse falha no envio, não no cadastro." />
        <div className="flex flex-col gap-1 rounded-lg border border-edge bg-canvas px-3 py-2">
          <Switch checked={form.exigirModelo}
                  onChange={e => setForm({ ...form, exigirModelo: e.target.checked })}
                  label="Exigir modelo do catálogo nos nós de e-mail" />
          <p className="text-[11px] text-dim">
            Ligado, a opção <em>Corpo livre</em> some da lista do nó: todo aviso passa a sair de um
            modelo. Os nós que já usam corpo livre continuam funcionando — a trava vale para a
            próxima escolha, não apaga o que existe.
          </p>
        </div>
        {erros.length > 0 && (
          <ul className="flex flex-col gap-0.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300" data-email-erros>
            {erros.map(e => <li key={e}>{e}</li>)}
          </ul>
        )}
        <div className="flex justify-end">
          <Button variant="primary" onClick={() => salvar.mutate(form)} disabled={salvar.isPending || erros.length > 0 || !mudou} data-email-salvar>
            {salvar.isPending ? 'Salvando…' : 'Salvar'}
          </Button>
        </div>
      </section>

      <EmailModelos />

      <section className="flex flex-col gap-3 rounded-lg border border-edge bg-panel p-4 shadow-sm" data-email-testar>
        <div>
          <h3 className="text-sm font-semibold text-ink">Testar o envio</h3>
          <p className="text-xs text-dim">Monta um e-mail de teste com o remetente <strong>salvo</strong> e o entrega ao sendmail do servidor do DataStage — o mesmo caminho da corrida. Sem destinatário informado, vai para o e-mail do seu usuário.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Input label="Destinatário do teste (opcional)" value={para} onChange={e => setPara(e.target.value)} placeholder="seu e-mail cadastrado" className="w-80" />
          <Button variant="secondary" onClick={() => testar.mutate()} disabled={testar.isPending || mudou || !cfg.remetente} data-email-botao-testar
                  title={mudou ? 'Salve a configuração antes de testar' : !cfg.remetente ? 'Informe e salve o remetente' : ''}>
            {testar.isPending ? 'Enviando…' : 'Testar'}
          </Button>
          {mudou && <span className="text-[11px] text-amber-700 dark:text-amber-300">salve antes de testar</span>}
        </div>
        {laudo && <Laudo l={laudo} />}
        {log.data && log.data.envios.length > 0 && (
          <div className="text-[11px] text-dim" data-email-ultimos-testes>
            Últimos testes:{' '}
            {log.data.envios.slice(0, 5).map(e => (
              <span key={e.id} className="mr-2">
                {e.criado_em} · <span className={e.status === 'enviado' ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}>{e.status}</span>
                {e.criado_por ? ` · ${e.criado_por}` : ''}
              </span>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function Laudo({ l }: { l: EmailLaudo }) {
  const linhas: Array<[string, string]> = [
    ['Servidor', l.host || '—'],
    ['Remetente', l.remetente],
    ['Para', l.destinatarios.join(', ')],
    ['rc do sendmail', l.exit_code != null ? String(l.exit_code) : '—'],
    ['Duração', l.duration_ms != null ? `${l.duration_ms} ms` : '—'],
  ]
  return (
    <div className={`flex flex-col gap-2 rounded-lg border p-3 ${l.ok
      ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40'
      : 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40'}`} data-email-laudo={l.etapa}>
      <div className="flex items-center gap-2 text-sm font-semibold">
        {l.ok ? <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" /> : <XCircle size={15} className="text-red-600 dark:text-red-400" />}
        <span className={l.ok ? 'text-emerald-800 dark:text-emerald-300' : 'text-red-800 dark:text-red-300'}>{ETAPA_LAUDO[l.etapa] ?? l.etapa}</span>
      </div>
      {l.mensagem && <p className="text-xs leading-relaxed text-ink">{l.mensagem}</p>}
      {l.ok && <p className="text-xs text-dim">O sendmail aceitou a mensagem: confira a caixa de entrada (e o spam). Se não chegar, o problema está no relay, não no Orquestra.</p>}
      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-xs">
        {linhas.map(([k, v]) => (<div key={k} className="contents"><dt className="text-dim">{k}</dt><dd className="break-all text-ink">{v}</dd></div>))}
      </dl>
      {l.stderr && <pre className="overflow-x-auto rounded bg-canvas p-2 text-[11px] text-ink">{l.stderr}</pre>}
      {l.persistido === false && <p className="text-xs text-amber-700 dark:text-amber-400">O resultado não pôde ser gravado no log — ele some ao recarregar a página.</p>}
    </div>
  )
}
