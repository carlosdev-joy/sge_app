// Admin — casca fina (docs/spec-admin-reestruturacao.md, F2). Cada aba tem
// endereço próprio /admin/<grupo>/<aba>; o registro central (lib/adminNav.ts)
// diz quais existem, em que grupo e qual componente (lazy) renderiza cada uma.
// A rota /admin/* é curinga (App.tsx, WILDCARD_ROUTES): o resto do caminho
// chega aqui como o splat `*` do useParams.
//
// Redirecionamentos (sempre com replace, para o Voltar não cair no endereço velho):
//   /admin                → última aba visitada, senão Acesso › Usuários
//   /admin/<grupo>        → 1ª aba do grupo
//   /admin/<idAntigo>     → endereço novo (config, regen, notificacoes, …)
//   /admin/<g>/<idAntigo> → idem (ex.: /admin/sistema/config)
import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AdminShell } from '../components/admin/AdminShell'
import {
  ABA_PADRAO, caminhoDaAba, gravarUltimaAba, interpretarCaminhoAdmin, lerUltimaAba,
} from '../lib/adminNav'

export default function Admin() {
  const splat = useParams()['*']
  const navigate = useNavigate()
  const destino = interpretarCaminhoAdmin(splat)

  const redirecionarPara = destino.tipo === 'inicio'
    ? (lerUltimaAba() ?? caminhoDaAba(ABA_PADRAO))
    : destino.tipo === 'redirecionar' ? destino.para : null
  // Durante um redirect para uma aba (ex.: clicar "Admin" na sidebar estando
  // dentro dela: /admin → última aba) a casca segue montada COM a aba de
  // destino — devolver null desmontava a aba e apagava o formulário em edição.
  const abaDoRedirect = redirecionarPara
    ? interpretarCaminhoAdmin(redirecionarPara.replace(/^\/admin\/?/, ''))
    : null
  const abaAtual = destino.tipo === 'aba' ? destino.aba
    : abaDoRedirect?.tipo === 'aba' ? abaDoRedirect.aba : null

  useEffect(() => {
    if (redirecionarPara) navigate(redirecionarPara, { replace: true })
  }, [redirecionarPara, navigate])

  useEffect(() => {
    if (abaAtual) gravarUltimaAba(abaAtual)
  }, [abaAtual])

  if (redirecionarPara && !abaAtual) return null
  return <AdminShell aba={abaAtual} />
}
