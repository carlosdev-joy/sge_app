// Prévia do corpo do e-mail (spec docs/spec-email-modelos-e-navegacao.md, F1).
//
// ⚠️ O corpo é HTML escrito por uma pessoa e renderizado na tela de outra. Ele
// vai para dentro de um <iframe sandbox> SEM `allow-scripts` e SEM
// `allow-same-origin`: script no corpo não executa, e nada ali alcança a sessão
// de quem está vendo. É a única defesa que existe — o produto não tem CSP.
//
// O isolamento também é o que torna a prévia HONESTA: dentro do iframe não
// entra o CSS do Orquestra, então o que aparece é o que um leitor de e-mail
// mostraria, e não o corpo já influenciado pelo estilo do aplicativo.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { interpolarExemplo, montarDocumento, VALORES_EXEMPLO } from './previaEmailDados'

export interface PreviaEmailProps {
  /** O corpo como está no campo, com marcadores. */
  corpo: string
  /** Corpo em HTML ligado no nó. Desligado, a prévia mostra texto puro. */
  html: boolean
  /** Altura da área de prévia. O conteúdo rola dentro dela. */
  altura?: number
  /** Rótulo acima da moldura. */
  titulo?: string
}

/** Espera o texto parar de mudar antes de recarregar o iframe. Sem isso, cada
 *  tecla digitada troca o `srcdoc`, o frame navega para um documento novo, a
 *  prévia pisca e volta ao topo — e toda imagem remota é baixada de novo. */
function useTextoEstavel(texto: string, ms = 400): string {
  const [estavel, setEstavel] = useState(texto)
  useEffect(() => {
    const t = setTimeout(() => setEstavel(texto), ms)
    return () => clearTimeout(t)
  }, [texto, ms])
  return estavel
}

export function PreviaEmail({ corpo, html, altura = 220, titulo = 'Prévia' }: PreviaEmailProps) {
  const [comValores, setComValores] = useState(true)
  const molduraRef = useRef<HTMLDivElement>(null)
  const corpoEstavel = useTextoEstavel(corpo)

  const conteudo = useMemo(
    () => (comValores ? interpolarExemplo(corpoEstavel) : corpoEstavel),
    [corpoEstavel, comValores],
  )

  const documento = useMemo(() => montarDocumento(conteudo, html), [conteudo, html])

  const vazio = !corpo.trim()

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-ink">{titulo}</span>
        <span className="text-[10px] text-dim/70">como chega a quem recebe</span>
        {/* `span role="button"`, não `<button>`: o painel inteiro vive dentro de
            um <fieldset disabled> em modo consulta e com o fluxo rodando, e
            `fieldset[disabled]` desliga todo controle de formulário
            descendente. Alternar a prévia é VISUALIZAÇÃO — tem de continuar
            funcionando justamente no perfil em que ela é o único valor da tela. */}
        <span
          role="button"
          tabIndex={0}
          onClick={() => setComValores(v => !v)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              setComValores(v => !v)
            }
          }}
          className="ml-auto flex cursor-pointer select-none items-center gap-1 rounded border border-edge px-1.5 py-0.5 text-[10px] text-dim hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          title={comValores
            ? 'Mostrar os marcadores como estão no campo'
            : 'Mostrar com valores de exemplo, como no e-mail enviado'}
        >
          {comValores ? <Eye size={11} /> : <EyeOff size={11} />}
          {comValores ? 'com valores de exemplo' : 'com marcadores'}
        </span>
      </div>

      <div
        ref={molduraRef}
        tabIndex={-1}
        // O foco dentro de um iframe de origem opaca não devolve os eventos de
        // teclado ao documento pai: enquanto ele estiver lá, os atalhos do
        // editor (Ctrl+Enter salva, Esc fecha) ficam mudos. Trazer o foco de
        // volta quando o ponteiro sai da prévia restaura os atalhos sem
        // atrapalhar quem clicou ali para ler ou copiar.
        onMouseLeave={() => {
          const dentro = document.activeElement
          if (dentro && molduraRef.current?.contains(dentro)) molduraRef.current.focus()
        }}
        className="overflow-hidden rounded-lg border border-edge bg-panel focus:outline-none"
        style={{ height: altura }}
      >
        {vazio ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-[11px] text-dim">
            Escreva o corpo ao lado para ver aqui como o e-mail vai chegar.
          </div>
        ) : (
          <iframe
            // `sandbox=""` (vazio) é o mais restritivo que existe: sem scripts,
            // sem formulários, sem navegação, sem acesso à origem do app.
            sandbox=""
            srcDoc={documento}
            title="Prévia do e-mail"
            className="h-full w-full border-0 bg-white"
          />
        )}
      </div>

      {!vazio && (
        <p className="text-[10px] text-dim/70">
          {comValores
            ? `Valores de exemplo: ${VALORES_EXEMPLO.pipeline} · ${VALORES_EXEMPLO.linhas} linhas · ${VALORES_EXEMPLO.status}. `
            : ''}
          Imagem de endereço externo aparece aqui, mas costuma vir bloqueada no Outlook.
        </p>
      )}
    </div>
  )
}
