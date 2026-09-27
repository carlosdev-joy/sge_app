const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert/strict')
const root = path.resolve(__dirname, '../..'), ui = path.join(root, 'ui-react')
const {transform} = require(path.join(ui, 'node_modules/sucrase'))
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'catalogo-test-'))
try {
  for (const name of ['dsParams', 'pipelineCatalogo']) {
    fs.writeFileSync(path.join(dir, name + '.js'), transform(fs.readFileSync(path.join(ui, 'src/lib', name + '.ts'), 'utf8'), {transforms:['typescript','imports']}).code)
  }
  const c = require(path.join(dir,'pipelineCatalogo.js'))
  const ds = {param_name:'pA',param_type:'String',param_value:'personalizado',param_source:'fixo',...c.metaManual('datastage')}
  const orq = {...ds,param_name:'diretorio',param_value:'/dados',...c.metaManual('orquestra')}
  const imp = {...ds,param_value:'novo',param_procedencia:'datastage',param_import_project:'P',param_import_job:'J',aviso:null}
  const original = c.catalogoFromApi([ds,orq])
  assert.equal(c.aplicarImportacao(original,[imp],{},{}).params[0].param_value,'personalizado')
  assert.equal(c.aplicarImportacao(original,[imp],{pA:0},{}).erros.length,1)
  const applied = c.aplicarImportacao(original,[imp],{pA:0},{pA:true}).params
  assert.equal(applied.find(p=>p.param_name==='diretorio').param_destino,'orquestra')
  assert.equal(applied.find(p=>p.param_name==='pA').param_value,'novo')
  const changed = c.atualizarGrupo(applied,'datastage',applied.filter(p=>p.param_destino==='datastage').map(p=>({...p,param_value:'ajustado'})))
  assert.equal(c.catalogoToApi(changed).find(p=>p.param_name==='pA').param_import_job,'J')
  const encrypted = c.catalogoFromApi([{...orq,param_type:'Encrypted',param_value:'***',tem_valor:true}])
  assert.equal(encrypted[0].param_value,'')
  assert.equal(c.catalogoToApi(encrypted)[0].param_value,'***')
  assert.ok(!c.legendaParametro({...encrypted[0],param_value:'SEGREDO'}).includes('SEGREDO'))
  assert.equal(c.atualizarGrupo(original,'datastage',[]).length,1)
  assert.deepEqual(c.catalogoToApi([]),[])
  assert.equal(c.erroCatalogo({detail:{errors:['Nome repetido','Tipo inválido']}}),'Nome repetido; Tipo inválido')
  console.log('catálogo: preservação, colisões explícitas, remoção e segredos OK')
} finally {fs.rmSync(dir,{recursive:true,force:true})}
