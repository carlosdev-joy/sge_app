import { useState, Fragment } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { Save, CheckCircle2, Zap, XCircle } from 'lucide-react'
import { InfoBanner } from '../../ui/InfoBanner'

// ── IA (provedor compartilhado: Maestro, triagem, assistentes do Caixa
// Seguro — Diego/Lari/Léo — e agentes; até 21/09/2026 esta aba só falava do
// Caixa. Ver docs/spec-agentes-datastage.md, F0.) ────────────────
interface IAVerificacao {
  quando?: string; ok?: boolean; etapa?: string; provedor?: string
  modelo?: string; latencia_ms?: number | null; por?: string; mensagem?: string
}
interface IADiagnostico {
  ok: boolean; etapa: string; mensagem: string; provedor: string; modelo: string
  endpoint: string; proxy_ambiente: string; usa_proxy: boolean; formato: string
  proxy_em_uso: string | null; proxy_motivo: string | null
  resposta: string; http_status: number | null; latencia_ms: number | null
  verificado_em?: string; verificado_por?: string; persistido?: boolean
}
interface IAConfig {
  enabled: boolean; provider: string; model: string; base_url: string
  api_key_set: boolean; usa_proxy: boolean; proxy_ambiente: string
  ultima_verificacao: IAVerificacao | null
}

// Cada etapa nomeia QUEM resolve. "Falhou" sozinho manda o operador procurar
// no lugar errado — rede e chave de API têm donos diferentes.
const ETAPA_IA: Record<string, string> = {
  config: 'Configuração incompleta',
  rede: 'Não chegou ao host',
  http: 'Host respondeu, mas recusou',
  formato: 'Respondeu em formato inesperado',
  provedor: 'O provedor recusou',
  inesperado: 'Erro inesperado',
  ok: 'Conectado',
}

// Painel do resultado. Fica na tela, com data e hora: um toast some, e a
// pergunta "isso está conectando?" precisa de resposta que sobreviva ao F5.
function DiagnosticoIA({ d }: { d: IADiagnostico }) {
  const linhas: Array<[string, string]> = [
    ['Provedor', d.provedor],
    ['Modelo', d.modelo || '—'],
    ['Endpoint', d.endpoint || '—'],
    ['Latência', d.latencia_ms != null ? `${d.latencia_ms} ms` : '—'],
    ['HTTP', d.http_status != null ? String(d.http_status) : '—'],
    ['Formato da resposta', d.formato || '—'],
    // O proxy é a armadilha desta integração, e o valor vem do transporte que
    // o httpx montou — não de deduzir pela configuração. As duas leituras
    // divergem: NO_PROXY isenta o host mesmo com o proxy ligado, e os outros
    // provedores atravessam o proxy mesmo com a opção desmarcada.
    ['Proxy', d.proxy_em_uso ? `${d.proxy_em_uso} (em uso)` : (d.proxy_motivo || 'conexão direta')],
  ]
  return (
    <div className={`rounded-lg border p-3 flex flex-col gap-2 ${d.ok
      ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40'
      : 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40'}`}>
      <div className="flex items-center gap-2 text-sm font-semibold">
        {d.ok ? <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" />
              : <XCircle size={15} className="text-red-600 dark:text-red-400" />}
        <span className={d.ok ? 'text-emerald-800 dark:text-emerald-300' : 'text-red-800 dark:text-red-300'}>
          {ETAPA_IA[d.etapa] ?? d.etapa}
        </span>
        {d.verificado_em && <span className="text-xs font-normal text-dim ml-auto">{d.verificado_em}</span>}
      </div>
      {d.mensagem && <p className="text-xs text-ink leading-relaxed">{d.mensagem}</p>}
      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-xs">
        {linhas.map(([k, v]) => (
          <Fragment key={k}>
            <dt className="text-dim">{k}</dt>
            <dd className="text-ink break-all">{v}</dd>
          </Fragment>
        ))}
      </dl>
      {d.resposta && (
        <div className="text-xs">
          <span className="text-dim">Resposta do modelo: </span>
          <code className="text-ink break-all">{d.resposta}</code>
        </div>
      )}
      {d.persistido === false && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          O resultado não pôde ser gravado — ele some ao recarregar a página.
        </p>
      )}
    </div>
  )
}
export function IATab() {
  const { data, isLoading, isError, error } = useQuery<{ config: IAConfig }>({ queryKey: ['admin-ia'], queryFn: () => adminPost('ia_get') })
  if (isLoading) return <PageSpinner />
  if (isError || !data) return (
    <p className="text-sm text-red-600 dark:text-red-400">
      Falha ao carregar a configuração de IA: {error?.message}
    </p>
  )
  return <IAForm cfg={data.config} />
}

// Componente separado para o form nascer já inicializado da config carregada
// (edições do usuário sobrevivem ao refetch; só api_key é limpa após salvar).
function IAForm({ cfg }: { cfg: IAConfig }) {
  const [form, setForm] = useState(() => ({ enabled: cfg.enabled, provider: cfg.provider, model: cfg.model, base_url: cfg.base_url, usa_proxy: cfg.usa_proxy, api_key: '' }))
  const [diag, setDiag] = useState<IADiagnostico | null>(null)

  const salvar = useMutation({
    mutationFn: (f: typeof form) =>
      adminPost('ia_set', { enabled: f.enabled, provider: f.provider, model: f.model, base_url: f.base_url, usa_proxy: f.usa_proxy, ...(f.api_key.trim() ? { api_key: f.api_key.trim() } : {}) }),
    onSuccess: () => {
      toast.success('Configuração salva')
      queryClient.invalidateQueries({ queryKey: ['admin-ia'] })
      // visibilidade dos assistentes do Caixa na sessão atual (src/caixa/lib/config.ts)
      queryClient.invalidateQueries({ queryKey: ['caixa-ia-status'] })
      setForm(f => ({ ...f, api_key: '' }))
      // O laudo descreve a configuração que foi verificada. Depois de salvar
      // outra, ele passa a descrever algo que não existe mais — e um painel
      // vermelho sobre a configuração já corrigida assusta à toa.
      setDiag(null)
    },
    onError: (e: Error) => toast.error(e.message),
  })
  // Verificar NÃO usa toast como resultado: o laudo fica na tela. O toast
  // sobraria só para o caso de a própria requisição não chegar ao servidor.
  const verificar = useMutation({
    mutationFn: () => adminPost<{ diagnostico: IADiagnostico }>('ia_verificar'),
    onSuccess: r => {
      setDiag(r.diagnostico)
      queryClient.invalidateQueries({ queryKey: ['admin-ia'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const isOpenAI = form.provider === 'openai_compat'
  const isGateway = form.provider === 'caixa_gateway'
  const precisaBaseUrl = isOpenAI || isGateway
  const ultima = cfg.ultima_verificacao

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <InfoBanner>
        Provedor de IA compartilhado (Maestro, triagem de chamados, assistentes do Caixa Seguro —
        Diego, Lari e Léo — e agentes). Para o Caixa Seguro, desativados aqui, os assistentes não
        aparecem para os usuários. Para ativar é obrigatório configurar a chave de API do provedor —
        a chave é armazenada cifrada (mesmo mecanismo das Conexões de Dados) e nunca é reexibida.
      </InfoBanner>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-4">
        <label className="flex items-center gap-2 text-sm text-ink cursor-pointer">
          <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />
          Assistentes IA ativos
        </label>

        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Provedor" value={form.provider} onChange={e => { setDiag(null); setForm({ ...form, provider: e.target.value }) }} className="w-56">
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai_compat">OpenAI-compatível</option>
            <option value="caixa_gateway">Gateway de IA da Caixa (interno)</option>
          </Select>
          <Input label="Modelo" value={form.model} onChange={e => setForm({ ...form, model: e.target.value })} className="w-64"
            placeholder={isGateway ? 'padrão: claude-sonnet-4-6' : isOpenAI ? 'ex: gpt-4o-mini' : 'padrão: claude-opus-4-8'} />
        </div>

        {precisaBaseUrl && (
          <Input label="Base URL" value={form.base_url} onChange={e => { setDiag(null); setForm({ ...form, base_url: e.target.value }) }}
            placeholder={isGateway ? 'ex: http://servicos.empresa.intranet/api/claude' : 'ex: https://api.openai.com/v1'}
            ajuda={isGateway ? 'Sem /chat/completions no fim — o caminho é acrescentado na chamada.' : undefined}
            className="w-full" />
        )}

        <Input label="Chave de API" type="password" value={form.api_key} autoComplete="new-password"
          onChange={e => setForm({ ...form, api_key: e.target.value })} className="w-full"
          placeholder={cfg.api_key_set ? '•••• chave salva — preencha só para trocar' : isGateway ? 'chave do gateway (header x-api-key)' : isOpenAI ? 'sk-…' : 'sk-ant-…'} />

        {isGateway && (
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-sm text-ink cursor-pointer">
              <input type="checkbox" checked={form.usa_proxy} onChange={e => setForm({ ...form, usa_proxy: e.target.checked })} />
              Usar o proxy corporativo para alcançar o gateway
            </label>
            <p className="text-xs text-dim">
              {cfg.proxy_ambiente
                ? <>O servidor tem proxy configurado (<code>{cfg.proxy_ambiente}</code>). Gateway na intranet normalmente
                   exige esta opção <strong>desmarcada</strong> — com o proxy no caminho, a chamada volta como erro de
                   conexão, igualzinho a gateway fora do ar.</>
                : <>Nenhum proxy no ambiente do servidor: marcar esta opção não muda nada hoje.</>}
            </p>
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <Button variant="secondary" size="sm" onClick={() => verificar.mutate()} loading={verificar.isPending}
            disabled={!cfg.api_key_set} title={!cfg.api_key_set ? 'Salve a chave antes de verificar' : 'Verifica a configuração SALVA (salve antes se acabou de alterá-la)'}>
            <Zap size={13} /> Verificar conexão
          </Button>
          <Button size="sm" onClick={() => salvar.mutate(form)} loading={salvar.isPending}>
            <Save size={13} /> Salvar
          </Button>
        </div>

        {/* Laudo da verificação feita agora; sem ela, o registro da última que
            rodou — inclusive de outra sessão ou de outro administrador. */}
        {diag
          ? <DiagnosticoIA d={diag} />
          : ultima && (
            <div className="rounded-lg border border-edge bg-panel p-3 text-xs flex flex-wrap items-center gap-x-3 gap-y-1">
              {ultima.ok
                ? <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400" />
                : <XCircle size={14} className="text-red-600 dark:text-red-400" />}
              <span className="text-ink font-medium">
                Última verificação: {ultima.ok ? 'conectado' : (ETAPA_IA[ultima.etapa ?? ''] ?? 'falhou')}
              </span>
              <span className="text-dim">{ultima.quando}</span>
              {ultima.latencia_ms != null && <span className="text-dim">{ultima.latencia_ms} ms</span>}
              {ultima.modelo && <span className="text-dim">modelo {ultima.modelo}</span>}
              {ultima.por && <span className="text-dim">por {ultima.por}</span>}
              {!ultima.ok && ultima.mensagem && <span className="text-ink w-full">{ultima.mensagem}</span>}
            </div>
          )}
      </div>
    </div>
  )
}
