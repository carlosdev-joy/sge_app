import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'

interface Status { configured: boolean; readiness: string; delivery_enabled: boolean }
interface Lookup { readiness: string; delivery_enabled: boolean }

const readiness: Record<string, string> = {
  ready: 'Configuração verificada. O envio permanece desativado.',
  tenant_app_missing: 'Cadastre o tenant e o aplicativo corporativo.',
  admin_approval_missing: 'Confirme a aprovação administrativa.',
  permissions_unverified: 'Confirme as permissões mínimas no tenant.',
  gateway_unverified: 'Confirme a integração aprovada.',
  connector_reference_missing: 'Cadastre a referência Connector aprovada para este destinatário.',
  user_not_found: 'Usuário não encontrado no diretório corporativo.',
  user_ambiguous: 'Mais de um usuário encontrado. Confira o endereço corporativo.',
  app_not_installed: 'O aplicativo precisa estar instalado para o destinatário.',
  teams_forbidden: 'O tenant recusou o acesso. Confira as permissões aprovadas.',
  teams_throttled: 'O Teams limitou a consulta. Tente novamente mais tarde.',
}

export function TeamsPessoal() {
  const status = useQuery<Status>({ queryKey: ['teams-personal-admin'],
    queryFn: () => apiFetch('/teams-personal/admin/config'), retry: false })
  const [action, setAction] = useState<'config' | 'reference' | 'lookup'>('config')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [checks, setChecks] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const update = (key: string, value: string) => setFields(old => ({ ...old, [key]: value }))
  const labels: [string, string][] = action === 'config' ? [
    ['tenant_id', 'Tenant ID'], ['app_id', 'Application ID'], ['catalog_app_id', 'ID do aplicativo no catálogo Teams'],
    ['client_secret', 'Credencial do aplicativo'],
  ] : action === 'reference' ? [
    ['tenant_id', 'Tenant ID'], ['app_id', 'Application ID'], ['user_id', 'Object ID do usuário'],
    ['conversation_id', 'ID da conversa resolvida'], ['service_url', 'Service URL do Connector'],
    ['connector_conversation_id', 'ID da conversa no Connector'],
  ] : [['email', 'E-mail corporativo do destinatário']]
  const confirmations: [string, string][] = action === 'config' ? [
    ['admin_approved', 'Aprovação administrativa obtida'],
    ['permissions_verified', 'Permissões mínimas verificadas no tenant'],
    ['gateway_verified', 'Integração corporativa aprovada e verificada'],
  ] : action === 'reference' ? [['reference_verified', 'Referência Connector conferida e aprovada']] : []

  async function submit() {
    if (busy) return
    setBusy(true)
    setMessage('')
    const body: Record<string, string | boolean> = {}
    for (const [key] of labels) body[key] = fields[key] ?? ''
    for (const [key] of confirmations) body[key] = checks[key] === true
    // Credenciais não entram no cache de queries/mutações, storage ou mensagens.
    setFields({})
    setChecks({})
    try {
      const result = await apiFetch<Lookup>(`/teams-personal/admin/${action}`, {
        method: 'POST', body: JSON.stringify(body),
      })
      setMessage(action === 'lookup'
        ? (readiness[result.readiness] ?? 'Destinatário indisponível. Confira o cadastro, as permissões e a instalação do aplicativo.')
        : 'Cadastro salvo. Envios permanecem desativados; consentimento e recebimento exigem validação própria.')
      await status.refetch()
    } catch {
      setMessage('Não foi possível concluir. Confira os campos e os gates administrativos; se persistir, consulte a sustentação.')
    } finally {
      for (const key of Object.keys(body)) delete body[key]
      setBusy(false)
    }
  }

  return <section className="flex flex-col gap-4 border-t border-edge pt-6" aria-label="Teams pessoal corporativo">
    <div>
      <h2 className="text-sm font-bold text-ink">Teams pessoal corporativo</h2>
      <p className="mt-1 text-sm text-dim">Cadastre a integração aprovada, vincule a referência da conversa e confira o destinatário. Estas ações não enviam mensagens nem concedem consentimento no tenant.</p>
    </div>
    <p role="status" className="text-sm text-ink">
      {status.isLoading ? 'Consultando configuração…' : status.isError
        ? 'Configuração indisponível. Verifique o serviço e as migrations com a sustentação.'
        : readiness[status.data?.readiness ?? ''] ?? 'Configuração exige verificação administrativa.'}
    </p>
    <form className="flex flex-col gap-4" autoComplete="off" onSubmit={event => { event.preventDefault(); void submit() }}>
      <Select label="Ação" value={action} disabled={busy} onChange={event => {
        setAction(event.target.value as typeof action); setFields({}); setChecks({}); setMessage('')
      }}>
        <option value="config">Cadastrar ou substituir integração</option>
        <option value="reference">Vincular referência Connector</option>
        <option value="lookup">Verificar destinatário</option>
      </Select>
      {action === 'config' && status.data?.configured && <p className="text-sm text-dim">Existe uma integração cadastrada. Para substituir, preencha novamente todos os campos; valores salvos ficam ocultos.</p>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {labels.map(([key, label]) => <Input key={key} label={label} required disabled={busy}
          type={key === 'client_secret' || key === 'service_url' ? 'password' : key === 'email' ? 'email' : 'text'}
          autoComplete="off" value={fields[key] ?? ''} onChange={event => update(key, event.target.value)} />)}
      </div>
      {confirmations.map(([key, label]) => <label key={key} className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" disabled={busy} checked={checks[key] === true}
          onChange={event => setChecks(old => ({ ...old, [key]: event.target.checked }))} />{label}
      </label>)}
      {message && <p role="status" className="text-sm text-ink">{message}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy} disabled={busy || status.isError || labels.some(([key]) => !fields[key]?.trim())}>
          {action === 'lookup' ? 'Verificar destinatário' : action === 'reference' ? 'Salvar referência' : 'Salvar integração'}
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={() => { setFields({}); setChecks({}); setMessage('') }}>Limpar campos</Button>
      </div>
    </form>
  </section>
}
