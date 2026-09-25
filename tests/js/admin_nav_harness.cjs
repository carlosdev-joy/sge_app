// Bancada do registro do Admin (ui-react/src/lib/adminNav.ts — F2 de
// docs/spec-admin-reestruturacao.md). Roda o TS REAL, transpilado pelo sucrase,
// sem navegador: o React é um stub (só `lazy`, que nunca é chamado aqui) e os
// import() dinâmicos das abas ficam dentro das funções do lazy — não executam.
// Imprime um JSON com o que a bancada observou; o pytest confere.
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const raiz = path.resolve(__dirname, '../..')
const { transform } = require(path.join(raiz, 'ui-react/node_modules/sucrase'))
const fonte = path.join(raiz, 'ui-react/src/lib/adminNav.ts')
const js = transform(fs.readFileSync(fonte, 'utf8'), { transforms: ['typescript', 'imports'] }).code

const armazenado = new Map()
let armazenamentoQuebrado = false
const localStorage = {
  getItem(k) { if (armazenamentoQuebrado) throw new Error('SecurityError'); return armazenado.has(k) ? armazenado.get(k) : null },
  setItem(k, v) { if (armazenamentoQuebrado) throw new Error('QuotaExceededError'); armazenado.set(k, String(v)) },
}
const modulo = { exports: {} }
const contexto = {
  module: modulo, exports: modulo.exports, Object, Promise, Map,
  window: { localStorage },
  require(nome) {
    if (nome === 'react') return { lazy: (fn) => ({ __lazy: fn }) }
    throw new Error('require inesperado na bancada: ' + nome)
  },
}
vm.runInNewContext(js, contexto)
const m = modulo.exports

const caminhos = (consulta) => m.buscarAbas(consulta).map((r) => m.caminhoDaAba(r.aba))
const primeiro = (consulta) => {
  const r = m.buscarAbas(consulta)[0]
  return r ? { caminho: m.caminhoDaAba(r.aba), campo: r.campo, trecho: r.trecho } : null
}
const destino = (splat) => {
  const d = m.interpretarCaminhoAdmin(splat)
  return d.tipo === 'aba' ? { tipo: 'aba', caminho: m.caminhoDaAba(d.aba) } : d
}

const saida = {
  abas: m.ABAS_ADMIN.map((a) => ({ grupo: a.grupo, id: a.id, rotulo: a.rotulo, descricao: a.descricao, idsAntigos: a.idsAntigos || [], chavesConfig: a.chavesConfig, lazy: !!(a.componente && a.componente.__lazy) })),
  grupos: m.GRUPOS_ADMIN.map((g) => g.id),
  gruposRotulos: Object.fromEntries(m.GRUPOS_ADMIN.map((g) => [g.id, g.rotulo])),
  idsAntigos: { ...m.IDS_ANTIGOS },
  // F4: abas que saíram do admin
  externos: { ...m.REDIRECIONAMENTOS_EXTERNOS },
  rotulos: {
    email: m.rotuloAdmin('comunicacao', 'email'),
    emailModelos: m.rotuloAdmin('comunicacao', 'email', 'Modelos'),
    sftp: m.rotuloAdmin('integracoes', 'servidor-datastage'),
    inexistente: m.rotuloAdmin('sistema', 'sla'),
    inexistenteComSecao: m.rotuloAdmin('sistema', 'sla', 'X'),
    todas: m.ABAS_ADMIN.map((a) => m.rotuloAdmin(a.grupo, a.id)),
  },
  busca: {
    teams_webhook: primeiro('teams_webhook'),
    TEAMS_WEBHOOK: primeiro('TEAMS_WEBHOOK'),
    xyz: caminhos('xyz'),
    vazio: caminhos('   '),
    email_remetente: primeiro('email_remetente'),
    'e-mail': primeiro('e-mail'),
    configuracao: primeiro('configuracao'),
    'CONFIGURAÇÃO': primeiro('CONFIGURAÇÃO'),
    inteligencia: caminhos('inteligencia'),
    calendario: primeiro('calendario'),
    'publicar dag': caminhos('publicar dag'),
    agentes: primeiro('agentes'),
    powerbi_client_secret: caminhos('powerbi_client_secret'),
    servicenow_: primeiro('servicenow_'),
    agentes_: primeiro('agentes_'),
    servicenow_admin_perfis: caminhos('servicenow_admin_perfis'),
    agentes_titulo_redigido_em: caminhos('agentes_titulo_redigido_em'),
    admin_perfis: caminhos('admin_perfis'),
    // F3
    perfil: caminhos('perfil'),
    triagem: caminhos('triagem'),
    chamados_triagem_lote: caminhos('chamados_triagem_lote'),
    monitor: caminhos('monitor'),
    // F4: o que saiu do admin não é aba — a busca não acha
    sla: caminhos('sla'),
    'fluxo ds': caminhos('fluxo ds'),
    'relatório': caminhos('relatório'),
    chaves: Object.fromEntries(['teams_webhook_url', 'teams_webhook_url_ack', 'teams_webhook_url_resolved']
      .map((k) => [k, (primeiro(k) || {}).caminho || null])),
  },
  destinos: Object.fromEntries(['', 'comunicacao/email', 'comunicacao', 'config', 'sistema/config', 'ia', 'foo',
    'foo/bar', 'comunicacao/inexistente', 'comunicacao/email/extra', '/comunicacao/email/', 'constructor', 'toString',
    'integracoes/monitoramento', 'servidor', 'monitor', 'integracoes/servidor',
    // F4: saídas (id antigo, slug da F2 com grupo e id antigo com grupo)
    'sla', 'sistema/sla', 'powerbi', 'sistema/powerbi-acessos', 'sistema/powerbi', 'fluxo_ds', 'sistema/fluxo-ds',
    'sistema/fluxo_ds', 'powerbi-acessos', 'fluxo-ds']
    .map((s) => [s, destino(s)])),
}

// Última aba: grava, lê, ignora lixo e sobrevive a armazenamento quebrado.
const email = m.ABAS_ADMIN.find((a) => a.id === 'email')
m.gravarUltimaAba(email)
saida.ultima = { gravada: armazenado.get(m.CHAVE_ULTIMA_ABA), lida: m.lerUltimaAba() }
armazenado.set(m.CHAVE_ULTIMA_ABA, '/admin/nao/existe')
saida.ultima.lixo = m.lerUltimaAba()
armazenado.set(m.CHAVE_ULTIMA_ABA, '/admin/integracoes/monitoramento')
saida.ultima.aposentada = m.lerUltimaAba()
// F4: última aba gravada antes da saída — /admin não pode mandar para fora
saida.ultima.saiuDoAdmin = {}
for (const v of ['/admin/sistema/sla', '/admin/sistema/powerbi-acessos', '/admin/sistema/fluxo-ds']) {
  armazenado.set(m.CHAVE_ULTIMA_ABA, v)
  saida.ultima.saiuDoAdmin[v] = m.lerUltimaAba()
}
armazenamentoQuebrado = true
saida.ultima.quebradoLer = m.lerUltimaAba()
let lancou = false
try { m.gravarUltimaAba(email) } catch { lancou = true }
saida.ultima.quebradoGravarLancou = lancou

process.stdout.write(JSON.stringify(saida))
