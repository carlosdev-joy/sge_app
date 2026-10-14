#!/usr/bin/env python3
"""Bancada Chromium do Pipeline: build real, dados sintéticos, sem API real.

Requer Playwright e Chromium instalados no ambiente de QA (não no produto).
Método e limites: docs/eoc-f6-aceite-pipeline.md.
"""
import argparse,json,gzip,math,time,hashlib,urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
p=argparse.ArgumentParser();p.add_argument('--dist',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();ROOT=a.dist;BASE='http://127.0.0.1:8090';NAME='__eoc_f6_synthetic';CAP={'enabled':True,'contractVersion':1,'environment':'dev','environmentLabel':'Desenvolvimento','actions':{key:True for key in ['consultDefinition','consultStages','consultLogs','consultVersions','contextualNavigation']}};CAP['actions'].update({key:False for key in ['editDraft','administer','execute','reprocess','pauseStages','publish']})
user={'matricula':'F6_SYNTHETIC','primeiro_nome':'Bancada','perfil':'consulta','permissoes':['tela_pipelines','tela_jobs','tela_logs']};results=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
 for count in [50,100,300]:
  definition={'schemaVersion':1,'identity':{'pipelineName':NAME,'displayName':'Benchmark sintético F6'},'metadata':{'legacyPipeline':{'project_name':'WORKSPACE_F6','domain':'SMOKE','schedule_type':'on_demand'}},'nodes':[{'id':f'Etapa_{i:03d}','type':'sql','configuration':{'legacyJob':{'sql_json':{'sql':'SELECT 1','mssql_conn_id':'synthetic'}},'etl_job_lineage':[]}} for i in range(count)],'edges':[{'source':f'Etapa_{i-1:03d}','target':f'Etapa_{i:03d}'} for i in range(1,count)]};layout={'schemaVersion':1,'nodes':{f'Etapa_{i:03d}':{'x':(i%10)*210,'y':(i//10)*120} for i in range(count)}}
  context={'pipelineName':NAME,'environment':'dev','environmentLabel':'Desenvolvimento','published':{'versionId':'0f8fad5b-d9cb-469f-a165-70867728950e','contentHash':'a'*64,'definition':definition,'layout':layout,'readOnlyReasons':[]},'draft':None,'summary':{}}
  ctx=browser.new_context(viewport={'width':1440,'height':1000},service_workers='block');ctx.add_init_script('localStorage.setItem("orquestra-auth",'+json.dumps(json.dumps({'state':{'user':user,'token':'synthetic-F6-no-real-token'},'version':0}))+');window.f6Vitals={lcp:0,cls:0};new PerformanceObserver(l=>l.getEntries().forEach(e=>window.f6Vitals.lcp=e.startTime)).observe({type:"largest-contentful-paint",buffered:true});new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)window.f6Vitals.cls+=e.value})).observe({type:"layout-shift",buffered:true});')
  page=ctx.new_page();errors=[];assets=set();page.on('pageerror',lambda e:errors.append(str(e)[:160]));cdp=ctx.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
  def route(r):
   path=urllib.parse.urlparse(r.request.url).path
   if path.startswith('/orquestra/'):
    if path.endswith('/workspace/capabilities'):body=CAP
    elif path.endswith('/workspace/pipeline-context'):body=context
    elif path.endswith('/versao/publica'):body={'versao':'2.24.0'}
    elif path.endswith('/versao'):body={'total':0,'data':[]}
    elif path.endswith('/config'):body={}
    elif 'notificacoes' in path:body={'data':[],'total':0,'nao_lidas':0}
    else:body={'connections':[],'databases':[],'data':[],'total':0,'enabled':False,'projects':[],'domains':[]}
    r.fulfill(status=200,content_type='application/json',body=json.dumps(body));return
   if path.startswith('/assets/'):
    f=ROOT/path.lstrip('/');assert f.is_file(),path
    if f.suffix in ['.js','.css']:assets.add(path)
    r.fulfill(path=str(f));return
   if r.request.is_navigation_request():r.fulfill(path=str(ROOT/'index.html'),content_type='text/html');return
   f=ROOT/path.lstrip('/');r.fulfill(path=str(f)) if f.is_file() else r.fulfill(status=404,body='')
  page.route(BASE+'/**',route);start=time.perf_counter();page.goto(BASE+'/pipelines/'+NAME+'/montagem?experiencia=consulta&fonte=publicado');expect(page.locator('.react-flow__node')).to_have_count(count,timeout=30000);page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');ready=(time.perf_counter()-start)*1000
  cold=sorted(assets);cold_sizes=[{'path':x,'gzipBytes':len(gzip.compress((ROOT/x.lstrip('/')).read_bytes(),mtime=0))} for x in cold];samples=[]
  for i in range(25):
   start=time.perf_counter();page.get_by_label('Localizar etapa no fluxo',exact=True).select_option(f'Etapa_{(i*11)%count:03d}');page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');samples.append((time.perf_counter()-start)*1000)
  assert not errors,errors;vitals=page.evaluate('window.f6Vitals');row=dict(nodes=count,coldGzipBytes=sum(x['gzipBytes'] for x in cold_sizes),coldAssets=cold_sizes,readyMs=ready,selectionSamplesMs=samples,selectionP95Ms=sorted(samples)[math.ceil(len(samples)*.95)-1],lcpMs=vitals['lcp'],cls=vitals['cls'],javascriptErrors=errors);results.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ['coldAssets','selectionSamplesMs']}),flush=True);ctx.close()
 browser.close()
r=dict(scope='Build produção; API/usuário/grafo sintéticos; browser1440 Chromium sem throttling; 25seleções até2frames por tamanho; cache vazio; não equivale a INP/piloto humano',sourceIndexSha256=hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),samples=results,budgets=dict(coldGzipBytes=307200,selectionP95Ms=200),passed=all(x['coldGzipBytes']<307200 and x['selectionP95Ms']<200 for x in results));a.output.write_text(json.dumps(r,indent=2)+'\n');print('Budget pass',r['passed'])
