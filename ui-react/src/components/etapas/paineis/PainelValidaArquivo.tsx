import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Edge, Node } from '@xyflow/react'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { catalogoFromApi, erroCatalogo, type CatalogoApi } from '../../../lib/pipelineCatalogo'
import { decisaoLabel, grafoValidacao, novaEntrada, ordenarEntradas, type EntradaArquivo, type ValidaConfig } from '../../../lib/validaArquivo'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { NomeField } from './shared'
import { ParametroCatalogoSelect } from '../../pipelines/ParametroCatalogoSelect'

interface Previa {
  entradas: { entrada_id: string; caminho: string; origem: string; alvo: string;
    dependentes_transitivos: string[]; convergencias: string[]; cenarios: Record<string, string> }[]
  combinacao: string; contagem: string; aviso: string
}
export function PainelValidaArquivo({ node, pipeline, nodes, edges, sshConns, onPatchData, onRename, onDelete }: {
  node: Node; pipeline: string; nodes: Node[]; edges: Edge[]; sshConns: { conn_id: string; host: string }[]
  onPatchData: (id: string, patch: Record<string, unknown>) => void
  onRename: (id: string, nome: string) => boolean; onDelete: (id: string) => void
}) {
  const cfg = node.data.valida_arquivo as ValidaConfig
  const [previa, setPrevia] = useState<{ assinatura: string; resultado: Previa } | null>(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const catalogo = useQuery<{ parametros: CatalogoApi[] }>({ queryKey: ['valida-catalogo', pipeline],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/parametros?parametros_versao=2`) })
  const params = catalogoFromApi(catalogo.data?.parametros).filter(p => ['String', 'Pathname'].includes(p.param_type) && p.param_source === 'fixo')
  const assinatura = JSON.stringify({ config: cfg, nodes: grafoValidacao(nodes, edges) })
  const patch = (p: Partial<ValidaConfig>) => { onPatchData(node.id, { valida_arquivo: { ...cfg, ...p } }); setErro('') }
  const entrada = (id: string, p: Partial<EntradaArquivo>) => patch({ entradas: cfg.entradas.map(e => e.entrada_id === id ? { ...e, ...p } : e) })
  const mover = (i: number, delta: number) => {
    const lista = [...cfg.entradas]; [lista[i], lista[i + delta]] = [lista[i + delta], lista[i]]
    patch({ entradas: ordenarEntradas(lista) })
  }
  async function consultar() {
    setOcupado(true); setErro(''); setPrevia(null)
    try {
      const resultado = await apiFetch<Previa>(`/pipelines/${encodeURIComponent(pipeline)}/valida-arquivo/${encodeURIComponent(node.id)}/previa`, { method: 'POST', body: assinatura })
      setPrevia({ assinatura, resultado })
    } catch (e) { setErro(erroCatalogo(e)) } finally { setOcupado(false) }
  }
  const resultado = previa?.assinatura === assinatura ? previa.resultado : null
  return <div className="flex min-w-0 flex-col gap-5 overflow-y-auto p-4 text-sm text-ink">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="font-semibold">Valida Arquivo</h3><p className="mt-1 text-xs text-dim">Configure, conecte os destinos e confira o impacto antes de salvar o fluxo.</p></div>
      <Button size="sm" variant="danger" onClick={() => onDelete(node.id)}><Trash2 size={14} />Excluir nó</Button>
    </div>
    <div className="grid gap-4 md:grid-cols-3">
      <NomeField id={node.id} name={node.id} isNew={!!node.data.isNew} placeholder="VALIDA_ARQUIVO" onRename={onRename} />
      <Select label="Conexão SSH" value={cfg.ssh_conn_id} onChange={e => patch({ ssh_conn_id: e.target.value })}>
        <option value="">Selecione uma conexão</option>
        {cfg.ssh_conn_id && !sshConns.some(c => c.conn_id === cfg.ssh_conn_id) && <option value={cfg.ssh_conn_id}>{cfg.ssh_conn_id} (não listada)</option>}
        {sshConns.map(c => <option key={c.conn_id} value={c.conn_id}>{c.conn_id}</option>)}
      </Select>
      <Input label="Tempo máximo (segundos)" type="number" min={1} max={600} value={cfg.timeout_segundos} onChange={e => patch({ timeout_segundos: Number(e.target.value) })} />
    </div>
    <p className="text-xs leading-relaxed text-dim">A ordem abaixo é a ordem das verificações. A ordem de execução dos destinos é definida pelas conexões do canvas. Erro técnico sempre falha e bloqueia todos os destinos deste validador.</p>
    {catalogo.isError && <p role="alert" className="text-sm text-red-700 dark:text-red-300">Catálogo indisponível. <Button variant="ghost" size="sm" onClick={() => catalogo.refetch()}>Tentar novamente</Button></p>}
    {cfg.entradas.map((e, i) => <fieldset key={e.entrada_id} className="min-w-0 border-t border-edge pt-4">
      <legend className="px-1 font-medium">Arquivo {i + 1}{e.arquivo ? ` · ${e.arquivo}` : ''}</legend>
      <div className="mb-3 flex flex-wrap justify-end gap-1">
        <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => mover(i, -1)} aria-label={`Mover arquivo ${i + 1} para cima`}><ArrowUp size={15} /></Button>
        <Button size="sm" variant="ghost" disabled={i === cfg.entradas.length - 1} onClick={() => mover(i, 1)} aria-label={`Mover arquivo ${i + 1} para baixo`}><ArrowDown size={15} /></Button>
        <Button size="sm" variant="ghost" disabled={cfg.entradas.length === 1} onClick={() => patch({ entradas: ordenarEntradas(cfg.entradas.filter(x => x.entrada_id !== e.entrada_id)) })}>Remover arquivo {i + 1}</Button>
      </div>
      <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Select label="Formato" value={e.tipo} onChange={v => entrada(e.entrada_id, { tipo: v.target.value as EntradaArquivo['tipo'], ignorar_cabecalho: false })}>
          <option value="arquivo">Arquivo de texto</option><option value="dataset">Dataset DataStage</option>
        </Select>
        <Input label="Nome real do arquivo" value={e.arquivo} maxLength={300} onChange={v => entrada(e.entrada_id, { arquivo: v.target.value })} ajuda="Preserve a extensão e as letras maiúsculas/minúsculas." />
        <Select label="Destino controlado" value={e.alvo} onChange={v => entrada(e.entrada_id, { alvo: v.target.value })} ajuda="Conecte o destino após este validador. Qualquer tipo de etapa é aceito.">
          <option value="">Selecione um destino</option>
          {e.alvo && !nodes.some(n => n.id === e.alvo) && <option value={e.alvo}>{e.alvo} (removido — escolha outro)</option>}
          {nodes.filter(n => n.id !== node.id && n.type !== 'valida_arquivo').map(n => <option key={n.id} value={n.id}>{n.id} · {n.type === 'etapa' ? String(n.data.type) : n.type}</option>)}
        </Select>
        <ParametroCatalogoSelect label="Parâmetro de diretório (opcional)" params={params} value={e.param_name ?? ''} disabled={catalogo.isLoading || catalogo.isError} onChange={name => entrada(e.entrada_id, { param_name: name || null })} />
        <Input label="Diretório direto (opcional)" value={e.diretorio_literal} maxLength={2000} onChange={v => entrada(e.entrada_id, { diretorio_literal: v.target.value })} ajuda="Caminho absoluto. Preenchido aqui, substitui o parâmetro; vazio usa o parâmetro selecionado." />
        <Select label="Se o arquivo não existir" value={e.se_nao_existe} onChange={v => entrada(e.entrada_id, { se_nao_existe: v.target.value as EntradaArquivo['se_nao_existe'] })}>
          <option value="falhar">Falhar e bloquear destinos</option><option value="pular">Pular este destino</option>
        </Select>
        <Select label="Se não houver registros" value={e.se_zero_linhas} onChange={v => entrada(e.entrada_id, { se_zero_linhas: v.target.value as EntradaArquivo['se_zero_linhas'] })}>
          <option value="falhar">Falhar e bloquear destinos</option><option value="pular">Pular este destino</option><option value="executar">Liberar este destino</option>
        </Select>
        {e.tipo === 'arquivo' ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={e.ignorar_cabecalho} onChange={v => entrada(e.entrada_id, { ignorar_cabecalho: v.target.checked })} />Pular a primeira linha (cabeçalho)</label> : <p className="text-xs leading-relaxed text-dim">Contagem via orchadmin. A compatibilidade com os arquivos reais será validada no ambiente Caixa.</p>}
      </div>
    </fieldset>)}
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={cfg.entradas.length >= 100} onClick={() => patch({ entradas: ordenarEntradas([...cfg.entradas, novaEntrada()]) })}><Plus size={15} />Adicionar arquivo</Button>
      <Button loading={ocupado} onClick={consultar}>Conferir impacto</Button>
    </div>
    {erro && <p role="alert" className="text-red-700 dark:text-red-300">{erro}</p>}
    {previa && !resultado && <p role="status" className="text-dim">Configuração alterada. Confira o impacto novamente.</p>}
    {resultado && <section aria-label="Prévia de impacto" className="space-y-3 border-t border-edge pt-4">
      <h4 className="font-semibold">Impacto da configuração</h4>
      <p className="text-xs text-dim">{resultado.aviso}</p>
      {resultado.entradas.map(e => <div key={e.entrada_id} className="space-y-1 border-b border-edge pb-3 text-xs">
        <p className="break-all font-medium">{e.caminho} → {e.alvo}</p><p>Origem do diretório: {e.origem}</p>
        <p>Após o destino: {e.dependentes_transitivos.join(', ') || 'nenhum nó'}</p><p>Convergências: {e.convergencias.join(', ') || 'nenhuma'}</p>
        <p>Ausente: {decisaoLabel[e.cenarios.ausente]} · Vazio: {decisaoLabel[e.cenarios.vazio]} · Com dados: {decisaoLabel[e.cenarios.dados]}</p>
      </div>)}
      <p className="text-xs text-dim">{resultado.combinacao} {resultado.contagem}</p>
    </section>}
    <p className="border-t border-edge pt-3 text-xs leading-relaxed text-dim">Salve pelo botão “Salvar fluxo”. Alterar nós, conexões, servidor SSH ou destinos exige publicar a DAG. Caminho, cabeçalho e políticas valem para novas execuções. Retomar uma execução preserva sua revisão original; para usar mudanças, inicie uma nova execução.</p>
  </div>
}
