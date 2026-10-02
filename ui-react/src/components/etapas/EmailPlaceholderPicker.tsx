import { useState, type RefObject } from 'react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import {
  aliasColunaValido, DESCRICAO_COLUNA, emailPlaceholderCatalogo, inserirEmailPlaceholder,
  marcadorDeColuna, nomeSqlParaPlaceholderValido, type EmailPlaceholderCampo,
} from '../../lib/emailPlaceholders'

const OPCAO_COLUNA = 'coluna:informar'

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
  const [alias, setAlias] = useState('')
  const [noColuna, setNoColuna] = useState('')
  const catalogo = emailPlaceholderCatalogo(campo)
  const nomesSql = [...new Set(sqlNames)].filter(nomeSqlParaPlaceholderValido)
  const tabelaPermitida = campo !== 'anexo'
  const personalizado = tabelaPermitida && allowCustomSqlName && selecionado === 'tabela:informar nome'
  // A coluna segue a regra da tabela: não vale no nome do anexo.
  const coluna = tabelaPermitida && selecionado === OPCAO_COLUNA
  // Com vários SQL ligados, a forma curta não escolhe — o worker a deixaria
  // literal. O botão só libera depois de escolher o nó.
  // Nó escolhido que saiu do fluxo (ligação desfeita) volta a "nenhum".
  const noEscolhido = nomesSql.length > 0 && !nomesSql.includes(noColuna) ? '' : noColuna
  const colunaAmbigua = coluna && nomesSql.length > 1 && !noEscolhido
  const marcadorColuna = coluna && !colunaAmbigua ? marcadorDeColuna(alias, noEscolhido) : null
  const nome = coluna ? (marcadorColuna ?? '') : personalizado ? `tabela:${nomeSql}` : selecionado
  const disponivel = catalogo.some(item => item.nome === selecionado)
    || (tabelaPermitida && nomesSql.some(sql => selecionado === `tabela:${sql}`))
    || (personalizado && nomeSqlParaPlaceholderValido(nomeSql))
    || marcadorColuna !== null
  const detalhe = coluna
    ? { descricao: DESCRICAO_COLUNA, exemplo: `{coluna:total} → 17.326.307` }
    : catalogo.find(item => item.nome === (nome.startsWith('tabela:') ? 'tabela' : nome))
  // Nó da coluna: lista quando o fluxo é conhecido; campo livre no modelo do
  // Admin (que não sabe em qual fluxo vai entrar); nada quando não há o quê.
  const noLivre = coluna && nomesSql.length === 0 && allowCustomSqlName
  const erroNo = noLivre && noColuna && !nomeSqlParaPlaceholderValido(noColuna)
    ? 'Use de 1 a 128 letras sem acento, números, ponto, hífen ou sublinhado.' : undefined

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
            {tabelaPermitida && <option value={OPCAO_COLUNA}>Coluna de um SQL: informar alias…</option>}
          </Select>
        </div>
        <Button type="button" size="sm" variant="secondary" disabled={!disponivel} onClick={inserir}
          aria-label={`Inserir marcador no ${campo === 'anexo' ? 'nome do anexo' : campo}`}>Inserir</Button>
      </div>
      {personalizado && <Input label="Nome exato do nó SQL" value={nomeSql} maxLength={128}
        onChange={e => setNomeSql(e.target.value)} placeholder="CONSULTA_SQL"
        error={nomeSql && !nomeSqlParaPlaceholderValido(nomeSql) ? 'Use de 1 a 128 letras sem acento, números, ponto, hífen ou sublinhado.' : undefined}
        ajuda="A disponibilidade depende do fluxo que usar este texto: o SQL com esse nome deve estar ligado diretamente ao e-mail." />}
      {coluna && (
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <Input label="Coluna (alias do SELECT)" value={alias} maxLength={64}
              onChange={e => setAlias(e.target.value)} placeholder="total"
              error={alias && !aliasColunaValido(alias) ? 'Use letras sem acento, números ou sublinhado — o mesmo nome do AS no SELECT.' : undefined} />
          </div>
          {nomesSql.length > 0 && (
            <div className="min-w-0 flex-1">
              <Select className="min-w-0 w-full" label="Nó SQL" value={noEscolhido} onChange={e => setNoColuna(e.target.value)}>
                <option value="">{nomesSql.length === 1 ? `O único ligado (${nomesSql[0]})` : 'Escolha o nó SQL…'}</option>
                {nomesSql.map(sql => <option key={sql} value={sql}>{sql}</option>)}
              </Select>
            </div>
          )}
          {noLivre && (
            <div className="min-w-0 flex-1">
              <Input label="Nó SQL (opcional)" value={noColuna} maxLength={128}
                onChange={e => setNoColuna(e.target.value)} placeholder="CONSULTA_SQL" error={erroNo}
                ajuda="Em branco: vale o único SQL ligado ao e-mail. Com vários, informe o nome exato." />
            </div>
          )}
        </div>
      )}
      {colunaAmbigua && (
        <p className="text-[11px] leading-snug text-dim">Há {nomesSql.length} SQL ligados a este e-mail: escolha de qual nó vem a coluna.</p>
      )}
      {detalhe && <p className="text-[11px] leading-snug text-dim">{detalhe.descricao} Exemplo ilustrativo: {detalhe.exemplo}.</p>}
      {campo === 'anexo' && <p className="text-[11px] leading-snug text-dim">Para uma data no nome do anexo, use {'{odate}'} (AAAAMMDD). {'{data}'} e {'{inicio}'} contêm barras, que não são permitidas em nomes de arquivo.</p>}
    </div>
  )
}
