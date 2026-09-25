// Dublê do <LinkAdmin> (ui-react/src/components/admin/LinkAdmin.tsx — F4 de
// docs/spec-admin-reestruturacao.md) para as bancadas que montam telas com
// migalha para o admin. O componente real lê a sessão (zustand) e usa o <Link>
// do roteador — nada disso existe nas bancadas. O dublê rende um <a> com o
// MESMO texto, tirado do registro real (lib/adminNav, já transpilado em `tmp`
// pelo `preparar` da bancada), e marca a aba de destino em data-link-admin.
// O registro declara as abas com React.lazy(): o shim de react da bancada
// ganha um `lazy` inerte (a bancada nunca renderiza aba do admin).
const fs = require('fs')
const path = require('path')

module.exports = function instalarDubleLinkAdmin(tmp) {
  const reactIdx = path.join(tmp, 'node_modules', 'react', 'index.js')
  fs.appendFileSync(reactIdx, '\nmodule.exports.lazy = module.exports.lazy || ((fn) => ({ __lazy: fn }))\n')
  const alvo = path.join(tmp, 'components', 'admin', 'LinkAdmin.js')
  fs.mkdirSync(path.dirname(alvo), { recursive: true })
  fs.writeFileSync(alvo, `
const mini = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))})
const nav = require('../../lib/adminNav.js')
exports.LinkAdmin = (p) => mini.criar('a', { 'data-link-admin': '/admin/' + p.grupo + '/' + p.aba }, nav.rotuloAdmin(p.grupo, p.aba, p.secao))
`)
}
