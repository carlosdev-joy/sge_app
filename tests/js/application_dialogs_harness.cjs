const assert=require('node:assert/strict')
const fs=require('node:fs')
const {transform}=require('../../ui-react/node_modules/sucrase')
const source=transform(fs.readFileSync('ui-react/src/lib/dialogs.ts','utf8'),{transforms:['typescript','imports']}).code
const mod={exports:{}};new Function('exports','module',source)(mod.exports,mod)
const d=mod.exports
;(async()=>{
 let calls=0;const unsubscribe=d.subscribeDialogs(()=>calls++)
 let acted=false;const one=d.confirmAction('confirmar').then(value=>{acted=value;return value})
 assert.equal(d.currentDialog().message,'confirmar');await Promise.resolve();assert.equal(acted,false)
 d.finishDialog(null);assert.equal(await one,false);assert.equal(d.currentDialog(),null)
 const first=d.requestText('nome','anterior');const second=d.confirmAction('seguinte')
 assert.equal(d.currentDialog().initialValue,'anterior');d.finishDialog('novo');assert.equal(await first,'novo');assert.equal(d.currentDialog().message,'seguinte');d.finishDialog(true);assert.equal(await second,true)
 const routeA=d.confirmAction('tela antiga');const routeB=d.requestText('fila antiga');d.cancelDialogs();assert.equal(await routeA,false);assert.equal(await routeB,null);assert.equal(d.currentDialog(),null)
 let allowed=true;const expired=d.confirmAction('lease',()=>allowed);allowed=false;d.finishDialog(true);assert.equal(await expired,false)
 const staleText=d.requestText('renomear','etapa',()=>false);d.finishDialog('novo');assert.equal(await staleText,null)
 assert.ok(calls>=9);unsubscribe();console.log('Application dialogs: cancel/confirm/text/FIFO/route cancel/live gate PASS')
})().catch(error=>{console.error(error);process.exitCode=1})
