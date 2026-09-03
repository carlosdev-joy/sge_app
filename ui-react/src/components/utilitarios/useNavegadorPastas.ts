// Estado do navegador de pastas (F6), reutilizado pelos dois formulários. O
// formulário continua apresentação: a rede entra por `onListar` (a página passa
// o `apiFetch`), e o hook cuida de abrir, descer, subir, ocultos e da resposta
// atrasada (número de série, como a leitura da F3).
import { useRef, useState } from 'react'
import { erroListagem, type Listagem } from '../../lib/utilitariosNavegador'

/** Lista uma pasta (null = nível zero, as raízes) do servidor. */
export type ListarPasta = (servidor: string, caminho: string | null, mostrarOcultos: boolean) => Promise<Listagem>

export function useNavegadorPastas(servidor: string, onListar?: ListarPasta) {
  const [aberto, setAberto] = useState(false)
  const [listagem, setListagem] = useState<Listagem | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [ocultos, setOcultos] = useState(false)
  // Série do pedido em curso: a resposta de um pedido já substituído (ou de um
  // navegador já fechado) não pode sobrescrever a lista atual.
  const serie = useRef(0)

  const navegar = async (caminho: string | null, mostrar: boolean = ocultos, voltarAoZeroSeFalhar = false) => {
    if (!onListar) return
    const listar = onListar
    const minha = ++serie.current
    setCarregando(true); setErro(null)
    try {
      const l = await listar(servidor, caminho, mostrar)
      if (serie.current === minha) { setListagem(l); setCarregando(false) }
      return
    } catch (e) {
      if (serie.current !== minha) return
      setErro(erroListagem(e))
      if (!voltarAoZeroSeFalhar || caminho === null) { setCarregando(false); return }
    }
    // A pasta digitada não serve (não existe, fora da raiz): o erro fica na
    // tela e o navegador abre nas raízes, que é de onde dá para navegar.
    try {
      const l = await listar(servidor, null, mostrar)
      if (serie.current === minha) setListagem(l)
    } catch { /* o erro da pasta digitada já está na tela */ }
    if (serie.current === minha) setCarregando(false)
  }

  /** Abre no caminho digitado (se houver) ou nas raízes. */
  const abrir = (inicial: string | null) => {
    setAberto(true); setListagem(null)
    void navegar(inicial, ocultos, true)
  }
  const fechar = () => { serie.current++; setAberto(false); setCarregando(false) }
  const mudarOcultos = (v: boolean) => {
    setOcultos(v)
    void navegar(listagem?.caminho_real ?? null, v)
  }

  return {
    disponivel: !!onListar,
    aberto, listagem, carregando, erro, ocultos,
    abrir, fechar, mudarOcultos,
    navegar: (caminho: string | null) => { void navegar(caminho) },
  }
}
