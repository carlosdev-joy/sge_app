'use strict'
const fs=require('fs'),path=require('path'),assert=require('assert/strict')
const root=path.resolve(__dirname,'../..'),{transform}=require(root+'/ui-react/node_modules/sucrase'),m={exports:{}}
new Function('require','module','exports',transform(fs.readFileSync(root+'/ui-react/src/lib/workspaceAlerts.ts','utf8'),{transforms:['typescript','imports']}).code)(require,m,m.exports)
const x=m.exports,p={...x.emptyAlertPolicy(),events:['success'],recipients:['a@example.test','A@example.test','b@example.test'],email:true,teamsPersonal:true,teamsChannel:{groupId:1}}
assert(x.editableAlertPolicy(p));assert.deepEqual(x.alertCounts(p,'success'),{email:2,teamsPersonal:2,teamsChannel:1});assert.deepEqual(x.alertCounts(p,'warning'),{email:0,teamsPersonal:0,teamsChannel:0})
assert.deepEqual(x.alertCounts({...p,recipients:['a@example.test']},'success'),{email:1,teamsPersonal:1,teamsChannel:1})
for(const raw of [null,{}, {...p,recipients:[null]}, {...p,extra:'future'}, {...p,schemaVersion:2}, {...p,teamsChannel:{groupId:1,secretReference:'protected'}}, {...p,events:['future']}, {...p,teamsChannel:{groupId:0}}])assert.equal(x.editableAlertPolicy(raw),false)
assert.match(x.alertError({status:422,detail:{field:'recipients',code:'alert_policy_invalid'}}).message,/e-mails válidos/)
assert.match(x.alertError({status:409}).message,/posse/)
assert(!x.alertError({status:500,detail:'private secret'}).message.includes('private'))
console.log('F8 fan-out, futuro/null/reference preservation and structured errors PASS')
