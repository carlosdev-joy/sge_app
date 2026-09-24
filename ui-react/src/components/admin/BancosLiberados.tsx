// Admin › Agentes › Novo/Editar › "Bancos liberados" (C2 da spec
// docs/spec-agentes-ferramenta-banco.md §2).
//
// As conexões são as NATIVAS SQL Server já cadastradas no Orquestra
// (`GET /agentes/admin/conexoes` — nome e servidor, nunca login ou senha). Ao
// abrir uma conexão, a tela pede os bancos que o login dela alcança, com
// SHOWPLAN e o aviso de escrita por banco. Vários servidores e vários bancos.
//
// O que é regra do backend continua lá: ao salvar, a API confere cada par
// NOVO no servidor (abre, existe, tem SHOWPLAN) e devolve os avisos. Aqui só
// se antecipa o que já se sabe — banco sem SHOWPLAN não se marca.
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import {
  Q_CONEXOES_BANCO, alternarPar, mensagemDeErro, mesmoPar,
  type BancoLiberado, type BancosDaConexao, type ConexaoBanco,
} from '../../lib/agentes'
import { InfoBanner } from '../ui/InfoBanner'

const AVISO_ESCRITA = 'O login desta conexão pode gravar — o agente só executa SELECT, mas uma conexão só de '
  + 'leitura é a proteção extra recomendada.'

export function BancosLiberados({ pares, onPares }: {
  pares: BancoLiberado[]
  onPares: (p: BancoLiberado[]) => void
}) {
  const conexoes = useQuery<{ conexoes: ConexaoBanco[] }>({
    queryKey: Q_CONEXOES_BANCO, queryFn: () => apiFetch('/agentes/admin/conexoes'),
  })

  if (conexoes.isLoading) return <p className="text-xs text-dim">Carregando as conexões…</p>
  if (conexoes.isError || !conexoes.data) {
    return (
      <InfoBanner icon="⚠">
        {`Não foi possível carregar as conexões: ${mensagemDeErro(conexoes.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }
  const lista = conexoes.data.conexoes
  // Par de uma conexão que não existe mais (removida em Conexões): aparece
  // para ser DESMARCADO — senão o agente guardaria um par que sempre falha.
  const orfaos = pares.filter(p => !lista.some(c => c.conexao === p.conexao))

  return (
    <div className="flex flex-col gap-1.5" data-agentes-bancos>
      {lista.length === 0 && (
        <p className="text-xs text-dim">
          Nenhuma conexão SQL Server cadastrada. Cadastre em Conexões — os agentes usam as mesmas.
        </p>
      )}
      {lista.map(c => (
        <Conexao key={c.conexao} conexao={c} pares={pares} onPares={onPares}
                 aberta={pares.some(p => p.conexao === c.conexao)} />
      ))}
      {orfaos.map(p => (
        <label key={`${p.conexao}/${p.banco}`} className="flex items-center gap-2 text-xs text-ink"
               data-agentes-banco-orfao>
          <input type="checkbox" checked onChange={() => onPares(alternarPar(pares, p))} />
          {`${p.conexao}/${p.banco}`} <span className="text-dim">(a conexão não existe mais — desmarque)</span>
        </label>
      ))}
    </div>
  )
}

function Conexao({ conexao, pares, onPares, aberta: abertaInicial }: {
  conexao: ConexaoBanco
  pares: BancoLiberado[]
  onPares: (p: BancoLiberado[]) => void
  aberta: boolean
}) {
  const [aberta, setAberta] = useState(abertaInicial)
  const escolhidos = pares.filter(p => p.conexao === conexao.conexao)
  const Icone = aberta ? ChevronDown : ChevronRight
  return (
    <div className="rounded border border-edge" data-agentes-conexao={conexao.conexao}>
      <button type="button" onClick={() => setAberta(!aberta)} aria-expanded={aberta}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs text-ink hover:bg-canvas">
        <Icone className="w-3.5 h-3.5 shrink-0 text-dim" aria-hidden="true" />
        <span className="font-medium">{conexao.conexao}</span>
        <span className="text-dim truncate">{conexao.servidor}{conexao.descricao ? ` · ${conexao.descricao}` : ''}</span>
        {escolhidos.length > 0 && (
          <span className="ml-auto text-dim whitespace-nowrap">
            {escolhidos.length === 1 ? '1 banco' : `${escolhidos.length} bancos`}
          </span>
        )}
      </button>
      {aberta && <Bancos conexao={conexao.conexao} pares={pares} onPares={onPares} />}
    </div>
  )
}

function Bancos({ conexao, pares, onPares }: {
  conexao: string
  pares: BancoLiberado[]
  onPares: (p: BancoLiberado[]) => void
}) {
  const bancos = useQuery<BancosDaConexao>({
    queryKey: ['agentes-admin-conexao-bancos', conexao],
    queryFn: () => apiFetch(`/agentes/admin/conexoes/${encodeURIComponent(conexao)}/bancos`),
    // Rede até o servidor da conexão: não repetir sozinho a cada foco.
    staleTime: 60_000, retry: false,
  })
  if (bancos.isLoading) return <p className="px-2 pb-2 text-xs text-dim">Conectando para listar os bancos…</p>
  if (bancos.isError || !bancos.data) {
    // A conexão não abriu: os pares já salvos nela continuam visíveis, para o
    // admin poder desmarcá-los mesmo sem a lista de bancos (revisão da C2).
    const salvos = pares.filter(p => p.conexao === conexao)
    return (
      <div className="px-2 pb-2 flex flex-col gap-1.5">
        <p className="text-xs text-dim" data-agentes-conexao-erro>
          {mensagemDeErro(bancos.error, 'A conexão não abriu.')}
        </p>
        {salvos.map(p => (
          <label key={p.banco} className="flex items-center gap-2 text-xs text-ink" data-agentes-banco-sem-lista>
            <input type="checkbox" checked onChange={() => onPares(alternarPar(pares, p))} />
            {p.banco} <span className="text-dim">(liberado antes — desmarque para tirar)</span>
          </label>
        ))}
      </div>
    )
  }
  const dados = bancos.data
  const escolhidos = dados.bancos.filter(b => pares.some(p => mesmoPar(p, { conexao, banco: b.banco })))
  const escrita = dados.sysadmin || escolhidos.some(b => b.escrita)
  const outros = escolhidos.length ? dados.bancos.filter(b => !escolhidos.includes(b)).map(b => b.banco) : []
  // Par salvo cujo banco o login já não alcança: aparece para ser desmarcado.
  const sumidos = pares.filter(p => p.conexao === conexao
    && !dados.bancos.some(b => mesmoPar(p, { conexao, banco: b.banco })))

  return (
    <div className="px-2 pb-2 flex flex-col gap-1.5">
      {dados.bancos.length === 0 && <p className="text-xs text-dim">O login desta conexão não alcança nenhum banco.</p>}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5" role="group" aria-label={`Bancos de ${conexao}`}>
        {dados.bancos.map(b => {
          const par = { conexao, banco: b.banco }
          const marcado = pares.some(p => mesmoPar(p, par))
          return (
            <label key={b.banco} className="flex items-center gap-2 text-xs text-ink" data-agentes-banco={b.banco}>
              <input type="checkbox" checked={marcado} disabled={!b.showplan && !marcado}
                     onChange={() => onPares(alternarPar(pares, par))} />
              {b.banco}
              {!b.showplan && <span className="text-dim">(sem SHOWPLAN — indisponível)</span>}
            </label>
          )
        })}
        {sumidos.map(p => (
          <label key={p.banco} className="flex items-center gap-2 text-xs text-ink" data-agentes-banco-sumido>
            <input type="checkbox" checked onChange={() => onPares(alternarPar(pares, p))} />
            {p.banco} <span className="text-dim">(o login não alcança mais — desmarque)</span>
          </label>
        ))}
      </div>
      {escrita && <InfoBanner icon="⚠">{AVISO_ESCRITA}</InfoBanner>}
      {outros.length > 0 && (
        <p className="text-[11px] text-dim" data-agentes-banco-alcance>
          {`Este login também alcança: ${outros.join(', ')}.`}
        </p>
      )}
    </div>
  )
}
