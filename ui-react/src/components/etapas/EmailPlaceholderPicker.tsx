import { useState, type RefObject } from 'react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import {
  emailPlaceholderCatalogo, inserirEmailPlaceholder, nomeSqlParaPlaceholderValido,
  type EmailPlaceholderCampo,
} from '../../lib/emailPlaceholders'

interface EmailPlaceholderPickerProps {
  campo: EmailPlaceholderCampo
  targetRef: RefObject<HTMLInputElement | HTMLTextAreaElement | null>
  value: string
  onChange: (next: string) => void
  sqlNames?: string[]
  allowCustomSqlName?: boolean
}

export function EmailPlaceholderPicker({
  campo, targetRef, value, onChange, sqlNames = [], allowCustomSqlName = true,
}: EmailPlaceholderPickerProps) {
  const [selecionado, setSelecionado] = useState('pipeline')
  const [nomeSql, setNomeSql] = useState('')
  const catalogo = emailPlaceholderCatalogo(campo)
  const nomesSql = [...new Set(sqlNames)].filter(nomeSqlParaPlaceholderValido)
  const tabelaPermitida = campo !== 'anexo'
  const personalizado = tabelaPermitida && allowCustomSqlName && selecionado === 'tabela:informar nome'
  const nome = personalizado ? `tabela:${nomeSql}` : selecionado
  const disponivel = catalogo.some(item => item.nome === selecionado)
    || (tabelaPermitida && nomesSql.some(sql => selecionado === `tabela:${sql}`))
    || (personalizado && nomeSqlParaPlaceholderValido(nomeSql))
  const detalhe = catalogo.find(item => item.nome === (nome.startsWith('tabela:') ? 'tabela' : nome))

  function inserir() {
    const el = targetRef.current
    if (!el || !disponivel) return
    // Inputs/textarea conservam a seleção quando o usuário foca o seletor.
    const resultado = inserirEmailPlaceholder(value, nome, el.selectionStart ?? value.length, el.selectionEnd ?? value.length)
    onChange(resultado.value)
    requestAnimationFrame(() => {
      if (targetRef.current !== el) return
      el.focus()
      el.setSelectionRange(resultado.cursor, resultado.cursor)
    })
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-edge p-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1">
          <Select className="min-w-0 w-full" label={`Marcador para ${campo === 'anexo' ? 'nome do anexo' : campo}`} value={selecionado}
            onChange={e => setSelecionado(e.target.value)}>
            {catalogo.map(item => <option key={item.nome} value={item.nome}>{`{${item.nome}} — ${item.descricao}`}</option>)}
            {!disponivel && !personalizado && selecionado.startsWith('tabela:') && (
              <option value={selecionado} disabled>{`{${selecionado}} — origem não disponível`}</option>
            )}
            {tabelaPermitida && nomesSql.map(sql => <option key={sql} value={`tabela:${sql}`}>{`{tabela:${sql}}`}</option>)}
            {tabelaPermitida && allowCustomSqlName && <option value="tabela:informar nome">Tabela de um SQL: informar nome…</option>}
          </Select>
        </div>
        <Button type="button" size="sm" variant="secondary" disabled={!disponivel} onClick={inserir}
          aria-label={`Inserir marcador no ${campo === 'anexo' ? 'nome do anexo' : campo}`}>Inserir</Button>
      </div>
      {personalizado && <Input label="Nome exato do nó SQL" value={nomeSql} maxLength={128}
        onChange={e => setNomeSql(e.target.value)} placeholder="CONSULTA_SQL"
        error={nomeSql && !nomeSqlParaPlaceholderValido(nomeSql) ? 'Use de 1 a 128 letras sem acento, números, ponto, hífen ou sublinhado.' : undefined}
        ajuda="A disponibilidade depende do fluxo que usar este texto: o SQL com esse nome deve estar ligado diretamente ao e-mail." />}
      {detalhe && <p className="text-[11px] leading-snug text-dim">{detalhe.descricao} Exemplo ilustrativo: {detalhe.exemplo}.</p>}
      {campo === 'anexo' && <p className="text-[11px] leading-snug text-dim">Para uma data no nome do anexo, use {'{odate}'} (AAAAMMDD). {'{data}'} e {'{inicio}'} contêm barras, que não são permitidas em nomes de arquivo.</p>}
    </div>
  )
}
