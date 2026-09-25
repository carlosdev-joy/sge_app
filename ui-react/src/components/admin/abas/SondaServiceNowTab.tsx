import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { toast } from '../../ui/Toast'
import { senhaParaEnviar } from '../../../lib/servicenowConfig'
import { adminPost } from '../comum'
import { Zap } from 'lucide-react'
import { InfoBanner } from '../../ui/InfoBanner'

// ── Sonda ServiceNow (bancada pré-spec dos chamados, PR #297) ────
// Valida credencial, tabelas, grupos e volumetria ANTES de a F1 existir.
// A credencial vive só na chamada: não é gravada nem logada em lugar nenhum.
interface SnAuth { status: number | null; ok: boolean; motivo?: string }
interface SnTabela { acessivel: boolean; status: number | null; total_ativos: number | null; estados_exemplo: string[]; erro?: string }
interface SnDiagnostico {
  url: string
  auth: SnAuth | null
  grupos: { name: string; sys_id: string; active: string }[]
  tabelas: Record<string, SnTabela>
  grupo_contagem: { grupo: string; por_tabela: Record<string, number | null> } | null
  proxy: { em_uso: string | null; motivo: string | null } | null
  origem_credencial: string
}

interface SnConfig {
  url: string; usuario: string; grupos: string; proxy: string
  habilitado: boolean; tem_senha: boolean; configurado: boolean
  // Triagem por IA (migration 093): interruptor PRÓPRIO, separado do
  // caixa_ia_enabled, que governa só os assistentes do Caixa Seguro.
  triagem_habilitada: boolean; triagem_lote: string
}

export function SondaServiceNowTab() {
  // Config EXECUTORA salva: é a credencial que a DAG de sync usa. A senha
  // nunca volta do servidor — `tem_senha` só diz se existe uma guardada.
  const cfgSalva = useQuery<{ config: SnConfig }>({
    queryKey: ['servicenow-cfg'],
    queryFn: () => adminPost('servicenow_get'),
  })
  const cfg = cfgSalva.data?.config
  // Instância da sonda: a salva manda; o ambiente (SERVICENOW_URL) é o default.
  const { data: cfgEnv } = useQuery<{ url: string }>({
    queryKey: ['servicenow-config'],
    queryFn: () => apiFetch('/admin/servicenow/config'),
  })
  // Os dois formulários são DERIVADOS de (servidor + edições locais), em vez
  // de copiados para dentro de um estado por useEffect. Assim o valor salvo
  // aparece assim que a query responde, sem render intermediário com campo
  // vazio e sem o efeito de sincronização que o lint (com razão) recusa.
  const [edits, setEdits] = useState<Partial<{
    url: string; usuario: string; senha: string; grupos: string
    proxy: string; habilitado: boolean
    triagem_habilitada: boolean; triagem_lote: string
  }>>({})
  const cfgForm = {
    url:        edits.url        ?? cfg?.url        ?? cfgEnv?.url ?? '',
    usuario:    edits.usuario    ?? cfg?.usuario    ?? '',
    senha:      edits.senha      ?? '',
    grupos:     edits.grupos     ?? cfg?.grupos     ?? '',
    proxy:      edits.proxy      ?? cfg?.proxy      ?? '',
    habilitado: edits.habilitado ?? cfg?.habilitado ?? false,
    triagem_habilitada: edits.triagem_habilitada ?? cfg?.triagem_habilitada ?? false,
    triagem_lote: edits.triagem_lote ?? cfg?.triagem_lote ?? '20',
  }
  const setCfgForm = (patch: Partial<typeof cfgForm>) =>
    setEdits(e => ({ ...e, ...patch }))

  const [sondaEdits, setSondaEdits] = useState<Partial<{
    url: string; usuario: string; senha: string; grupo_busca: string; grupo_nome: string
  }>>({})
  const form = {
    url:         sondaEdits.url         ?? cfg?.url ?? cfgEnv?.url ?? '',
    usuario:     sondaEdits.usuario     ?? '',
    senha:       sondaEdits.senha       ?? '',
    grupo_busca: sondaEdits.grupo_busca ?? 'engenharia',
    grupo_nome:  sondaEdits.grupo_nome  ?? '',
  }
  const setForm = (patch: Partial<typeof form>) =>
    setSondaEdits(e => ({ ...e, ...patch }))

  const [trocarSenha, setTrocarSenha] = useState(false)

  const salvar = useMutation({
    mutationFn: () => adminPost<{ mensagem?: string }>('servicenow_set', {
      url: cfgForm.url, usuario: cfgForm.usuario, grupos: cfgForm.grupos,
      proxy: cfgForm.proxy, habilitado: cfgForm.habilitado,
      triagem_habilitada: cfgForm.triagem_habilitada,
      triagem_lote: cfgForm.triagem_lote,
      // string vazia = manter a senha atual. A regra e o porquê estão em
      // `lib/servicenowConfig` — inclusive o caso da PRIMEIRA senha, que sem
      // ela nunca saía daqui.
      senha: senhaParaEnviar(cfgForm.senha, trocarSenha, !!cfg?.tem_senha),
    }),
    onSuccess: (d: { mensagem?: string }) => {
      toast.success(d.mensagem ?? 'Configuração salva.')
      setTrocarSenha(false)
      // Descarta as edições locais: a partir daqui o formulário volta a
      // espelhar o que o servidor confirmou ter gravado.
      setEdits({})
      cfgSalva.refetch()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const sonda = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiFetch<SnDiagnostico>('/admin/servicenow/diagnostico', {
        method: 'POST', body: JSON.stringify(payload),
      }),
    onError: (e: Error) => toast.error(e.message),
  })
  const r = sonda.data
  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      {/* ── Credencial executora ─────────────────────────────────────── */}
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Credencial executora</h3>
          <Badge value={cfg?.configurado ? 'success' : 'warning'}>
            {cfg?.configurado ? 'configurada' : 'incompleta'}
          </Badge>
        </div>
        <p className="text-xs text-dim">
          É esta credencial que a sincronização dos chamados usa para executar.
          A senha é cifrada com a mesma chave das Conexões de Dados
          (ORQUESTRA_CONN_KEY) e nunca volta para a tela.
        </p>
        <Input label="Instância" value={cfgForm.url} className="w-full"
          placeholder="https://suainstancia.service-now.com"
          onChange={e => setCfgForm({ url: e.target.value })} />
        <div className="flex flex-wrap gap-3">
          <Input label="Usuário de integração" value={cfgForm.usuario} className="w-56" autoComplete="off"
            onChange={e => setCfgForm({ usuario: e.target.value })} />
          {cfg?.tem_senha && !trocarSenha ? (
            <div className="flex flex-col justify-end pb-0.5">
              <span className="text-xs text-dim mb-1">Senha</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink">••••••••</span>
                <Button size="sm" variant="ghost" onClick={() => setTrocarSenha(true)}>
                  Trocar senha
                </Button>
              </div>
            </div>
          ) : (
            <Input label="Senha" type="password" value={cfgForm.senha} className="w-56"
              autoComplete="new-password"
              onChange={e => setCfgForm({ senha: e.target.value })} />
          )}
        </div>
        <Input label="Grupo(s) de atribuição — separe por ;" value={cfgForm.grupos}
          className="w-full" placeholder="Engenharia de Dados; Sustentação"
          onChange={e => setCfgForm({ grupos: e.target.value })} />
        {/* A sincronização roda no worker do Airflow, que NÃO herda o proxy do
            container da API — por isso a rota é campo aqui, e não variável de
            ambiente: mudar não exige recriar container nem derrubar job. */}
        <Input label="Proxy de saída da sincronização" value={cfgForm.proxy}
          className="w-full" placeholder="http://webproxy.empresa.intranet:8080"
          ajuda="Vazio = conexão direta. Preencha em rede com firewall de saída — sem isto o sync falha com 'Connection reset by peer' nas quatro tabelas, enquanto o teste de credencial aqui embaixo continua passando (ele roda em outro container, que já tem proxy)."
          onChange={e => setCfgForm({ proxy: e.target.value })} />
        <label className="flex items-center gap-1.5 text-xs text-ink">
          <input type="checkbox" checked={cfgForm.habilitado}
            onChange={e => setCfgForm({ habilitado: e.target.checked })} />
          Sincronização agendada habilitada
        </label>

        {/* Triagem por IA — interruptor SEPARADO do provedor. Desligar aqui
            não desliga os assistentes do Caixa Seguro, e vice-versa. */}
        <div className="border-t border-edge pt-3 flex flex-col gap-2">
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

        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" loading={sonda.isPending}
            disabled={!cfg?.configurado}
            onClick={() => sonda.mutate({ usar_config: true, grupo_nome: cfgForm.grupos.split(';')[0]?.trim() ?? '' })}>
            <Zap size={13} /> Testar credencial salva
          </Button>
          <Button size="sm" onClick={() => salvar.mutate()} loading={salvar.isPending}
            disabled={!cfgForm.url || !cfgForm.usuario}>
            Salvar configuração
          </Button>
        </div>
      </div>

      {/* ── Sonda de descoberta ──────────────────────────────────────── */}
      <InfoBanner>
        Sonda de diagnóstico: use para DESCOBRIR uma credencial ou o nome exato
        do grupo antes de salvar acima. A credencial digitada aqui vale só nesta
        chamada — não é gravada em banco, config nem log. Fluxo: valide a
        conexão, ache o nome exato do grupo na busca, cole-o no campo
        "Grupo (nome exato)" e rode de novo para ver a volumetria.
      </InfoBanner>
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-3">
        <Input label="Instância" value={form.url} className="w-full"
          onChange={e => setForm({ url: e.target.value })} />
        <div className="flex flex-wrap gap-3">
          <Input label="Usuário" value={form.usuario} className="w-56" autoComplete="off"
            onChange={e => setForm({ usuario: e.target.value })} />
          <Input label="Senha" type="password" value={form.senha} className="w-56" autoComplete="new-password"
            onChange={e => setForm({ senha: e.target.value })} />
        </div>
        <div className="flex flex-wrap gap-3">
          <Input label="Buscar grupos contendo…" value={form.grupo_busca} className="w-56"
            onChange={e => setForm({ grupo_busca: e.target.value })} />
          <Input label="Grupo (nome exato, p/ volumetria)" value={form.grupo_nome} className="w-72"
            onChange={e => setForm({ grupo_nome: e.target.value })} />
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => sonda.mutate(form)} loading={sonda.isPending}
            disabled={!form.usuario || !form.senha}>
            <Zap size={13} /> Validar conexão
          </Button>
        </div>
      </div>

      {r && (
        <div className="flex flex-col gap-3">
          {/* Auth */}
          <div className="bg-panel border border-edge rounded-lg p-3 flex items-center gap-2 text-sm">
            <Badge value={r.auth?.ok ? 'success' : 'error'}>
              {r.auth?.ok ? 'autenticado' : 'falhou'}
            </Badge>
            <span className="text-ink">
              {r.auth?.ok ? `Conexão OK com ${r.url}` : (r.auth?.motivo ?? `HTTP ${r.auth?.status ?? '—'}`)}
            </span>
            {/* Testar a credencial digitada e testar a que EXECUTA o sync são
                perguntas diferentes — o resultado precisa dizer qual foi. */}
            <Badge value="neutral">credencial: {r.origem_credencial}</Badge>
          </div>

          {/* Rota da chamada — sem isto, "com proxy" e "sem proxy" têm a
              mesma cara na tela e a falha de rede vira adivinhação. */}
          {r.proxy && (
            <div className="bg-panel border border-edge rounded-lg p-3 flex items-center gap-2 text-sm">
              <Badge value={r.proxy.em_uso ? 'info' : 'warning'}>
                {r.proxy.em_uso ? 'via proxy' : 'conexão direta'}
              </Badge>
              <span className="text-ink font-mono text-xs">
                {r.proxy.em_uso ?? r.proxy.motivo ?? '—'}
              </span>
            </div>
          )}

          {/* Grupos encontrados */}
          {r.grupos.length > 0 && (
            <div className="bg-panel border border-edge rounded-lg p-3">
              <p className="text-xs font-semibold text-dim uppercase tracking-wider mb-2">
                Grupos que casam com a busca — copie o nome EXATO
              </p>
              <ul className="flex flex-col gap-1 text-xs text-ink">
                {r.grupos.map(g => (
                  <li key={g.sys_id} className="flex items-center gap-2">
                    <span className="font-mono">{g.name}</span>
                    {String(g.active) !== 'true' && <Badge value="warning">inativo</Badge>}
                    <button className="text-blue-600 dark:text-blue-400 underline underline-offset-2"
                      onClick={() => setForm({ grupo_nome: g.name })}>
                      usar na volumetria
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {r.auth?.ok && r.grupos.length === 0 && (
            <p className="text-xs text-dim">Nenhum grupo casou com a busca — tente outro termo.</p>
          )}

          {/* Tabelas */}
          {r.auth?.ok && (
            <div className="bg-panel border border-edge rounded-lg overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-dim text-left border-b border-edge/60">
                    <th className="font-medium px-3 py-2">Tabela</th>
                    <th className="font-medium px-3 py-2">Acesso</th>
                    <th className="font-medium px-3 py-2">Ativos (total)</th>
                    <th className="font-medium px-3 py-2">Estados vistos na amostra</th>
                    {r.grupo_contagem && <th className="font-medium px-3 py-2">Do grupo</th>}
                  </tr>
                </thead>
                <tbody className="text-ink">
                  {Object.entries(r.tabelas).map(([nome, t]) => (
                    <tr key={nome} className="border-b border-edge/40 last:border-0 align-top">
                      <td className="px-3 py-2 font-mono">{nome}</td>
                      <td className="px-3 py-2">
                        <Badge value={t.acessivel ? 'success' : 'error'}>
                          {t.acessivel ? 'ok' : `negado (${t.erro ?? t.status ?? '—'})`}
                        </Badge>
                      </td>
                      <td className="px-3 py-2">{t.total_ativos ?? 'n/d'}</td>
                      <td className="px-3 py-2">{t.estados_exemplo.join(' · ') || '—'}</td>
                      {r.grupo_contagem && (
                        <td className="px-3 py-2 font-semibold">
                          {r.grupo_contagem.por_tabela[nome] ?? 'n/d'}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.grupo_contagem && (
            <p className="text-xs text-dim">
              Volumetria do grupo <span className="font-mono text-ink">{r.grupo_contagem.grupo}</span> —
              chamados ativos por tabela (coluna "Do grupo").
            </p>
          )}
        </div>
      )}
    </div>
  )
}
