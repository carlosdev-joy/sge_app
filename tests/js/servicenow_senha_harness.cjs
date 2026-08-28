// Bancada da regra de envio da senha do ServiceNow — `lib/servicenowConfig`.
//
// ⚠️ POR QUE ISTO, E NÃO `grep` NO `Admin.tsx`
// O defeito que este harness prende não é uma string ausente: é uma condição
// que, num ambiente sem senha gravada, faz a tela enviar '' no lugar do que o
// operador digitou. Um `grep` por `senhaParaEnviar` ficaria verde com a
// chamada existindo e a REGRA invertida.
//
// Como roda: o `sucrase` que o Vite já traz transpila o `.ts` para CJS num
// arquivo temporário; o módulo não importa React nem nada do DOM, então o
// `require` do Node basta.
//
// Saída: um JSON só no stdout, um campo por cenário.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))

const fonte = fs.readFileSync(
  path.join(UI, 'src', 'lib', 'servicenowConfig.ts'), 'utf8')
const js = transform(fonte, { transforms: ['typescript', 'imports'] }).code

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sn-senha-'))
const arquivo = path.join(tmp, 'servicenowConfig.cjs')
fs.writeFileSync(arquivo, js)
const { senhaParaEnviar } = require(arquivo)

const cenarios = {
  // O defeito: banco sem senha, operador digita, e a tela precisa ENVIAR.
  // Antes da correção este caso devolvia '' — e a tela dizia "Configuração
  // salva" com o banco intacto.
  primeira_senha_sem_trocar: senhaParaEnviar('nova-senha', false, false),

  // Banco sem senha e nada digitado: continua vazio, sem inventar valor.
  primeira_senha_campo_vazio: senhaParaEnviar('', false, false),

  // Já existe senha e o operador está só salvando o grupo/proxy: não pode
  // mandar '' embora... nem mandar o campo vazio por cima da senha boa.
  // '' aqui significa "mantenha a atual" — é o comportamento correto.
  senha_existente_sem_trocar: senhaParaEnviar('', false, true),

  // Mesma situação, mas com lixo no campo (estado residual do formulário):
  // sem clicar em "Trocar senha", NADA vai.
  senha_existente_campo_sujo: senhaParaEnviar('residuo', false, true),

  // Troca deliberada: o que foi digitado vai.
  troca_deliberada: senhaParaEnviar('outra-senha', true, true),
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
