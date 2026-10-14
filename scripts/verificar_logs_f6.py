#!/usr/bin/env python3
"""Navegador de QA: logs e permissões, build real com todas as APIs sintéticas.
Requer Playwright/Chromium; não acessa contas, dispara jobs nem envia mensagens.
"""
import argparse, json, urllib.parse, re, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
parser=argparse.ArgumentParser();parser.add_argument('--dist',type=Path,default=Path('ui-react/dist'));parser.add_argument('--output',type=Path,default=Path('/tmp/eoc-f6-dashboard-logs.json'));parser.add_argument('--mode');args=parser.parse_args();ROOT=args.dist;BASE='http://127.0.0.1:8090'; NAME='F6_LOG_SINTETICO'; rows=[]
user={'matricula':'F6_SYNTHETIC','perfil':'consulta','permissoes':['tela_dashboard','tela_logs','tela_pipelines','tela_jobs']}
job=dict(execution_id='20261014T100000',pipeline=NAME,job_name='Etapa_F6',task_id='Etapa_F6',status='FAILED',inicio='2026-10-14 10:00:00',fim='2026-10-14 10:00:10',duration_seconds=10)
dash=dict(date_ref='2026-10-14',kpis=dict(total_execucoes=1,total_sucesso=0,total_falha=1,total_warning=0,taxa_sucesso_pct=0,duracao_media_segundos=10,fila_media_segundos=0,fila_max_segundos=0,fila_jobs=0,por_projeto=[],filter_project=''),pipeline_status=[dict(pipeline=NAME,project='F6_SINTETICO',ultimo_status='FAILED',ultimo_inicio=job['inicio'],duracao_segundos=10,total_jobs=1,execution_id=job['execution_id'],criticidade='NORMAL')],ultimas_falhas=[],executando_agora=[],alertas_perf=[])
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox'])
 for mode in ([args.mode] if args.mode else ['normal','cancel-button','cancel-escape','chunk-error','rbac-dev','rbac-consulta','rbac-sustentacao','rbac-sem-permissoes']):
  for theme in ['light','dark']:
   user['perfil']={'rbac-dev':'eoc_dev_sem_admin','rbac-consulta':'eoc_consulta','rbac-sustentacao':'eoc_sustentacao'}.get(mode,'consulta');user['permissoes']=['tela_dashboard','tela_logs','tela_pipelines','tela_jobs']+(['acao_executar'] if mode=='rbac-sustentacao' else ['acao_editar','acao_publicar'] if mode=='rbac-dev' else [])
   if mode=='rbac-sem-permissoes':user.pop('permissoes',None)
   ctx=b.new_context(viewport={'width':390 if theme=='dark' else 1440,'height':1000},service_workers='block');ctx.add_init_script('localStorage.setItem("orquestra-auth",'+json.dumps(json.dumps({'state':{'user':user,'token':'synthetic'},'version':0}))+');localStorage.setItem("theme",'+json.dumps(theme)+');')
   page=ctx.new_page();errors=[];native=[];held=[];chunk_requests=[];writes=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:(native.append(d.type),d.dismiss()))
   def route(r):
    path=urllib.parse.urlparse(r.request.url).path
    if r.request.method not in ['GET','HEAD']:writes.append(path)
    if path.startswith('/orquestra/'):
     if path=='/orquestra/dashboard':value=dash
     elif path=='/orquestra/dashboard/supervisao':value={'date_ref':'2026-10-14','data':[],'resumo':{'total':0,'com_alerta':0}}
     elif path=='/orquestra/dashboard/gantt':value={'date_ref':'2026-10-14','data':[]}
     elif path=='/orquestra/execucoes':value={'data':[job]}
     elif path=='/orquestra/execucoes/duracao-media':value={'data':{}}
     elif path=='/orquestra/email/log':value={'envios':[]}
     elif path=='/orquestra/datastage/log':value={'data':[]}
     elif path.endswith('/taskInstances'):value={'task_instances':[{'task_id':'Etapa_F6','state':'failed','try_number':1}]}
     elif path.endswith('/dagRuns'):value={'dag_runs':[]}
     elif path.endswith('/workspace/capabilities'):value={'enabled':False,'actions':{}}
     else:value={'data':[],'total':0,'nao_lidas':0,'connections':[],'valor':''}
     r.fulfill(status=200,content_type='application/json',body=json.dumps(value));return
    if path.startswith('/assets/'):
     f=ROOT/path.lstrip('/');assert f.is_file(),path
     if f.name.startswith('ExecucaoDetailModal-'):
      chunk_requests.append(path)
      if mode.startswith('cancel'):held.append((r,f));return
      if mode=='chunk-error':r.abort('failed');return
     r.fulfill(path=str(f));return
    if r.request.is_navigation_request():r.fulfill(path=str(ROOT/'index.html'),content_type='text/html');return
    f=ROOT/path.lstrip('/');r.fulfill(path=str(f)) if f.is_file() else r.fulfill(status=404,body='')
   page.route(BASE+'/**',route);page.goto(BASE+'/');trigger=page.get_by_text(NAME,exact=True);expect(trigger).to_be_visible(timeout=30000);assert not chunk_requests
   trigger.click();dialog=page.get_by_role('dialog',name='Execução: '+NAME,exact=True);expect(dialog).to_be_visible(timeout=15000)
   if mode.startswith('cancel'):
    expect(dialog.get_by_role('status')).to_have_text('Carregando detalhes…');assert held
    if mode=='cancel-button':dialog.get_by_role('button',name='Cancelar',exact=True).click()
    else:page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    for r,f in held:r.fulfill(path=str(f))
    page.wait_for_timeout(350);expect(dialog).not_to_be_visible();expect(trigger).to_be_visible();assert not errors
   elif mode=='chunk-error':
    expect(dialog.get_by_role('alert')).to_contain_text('Não foi possível carregar');dialog.get_by_role('button',name='Fechar',exact=True).last.click();expect(dialog).not_to_be_visible();expect(trigger).to_be_visible();expect(page.get_by_text('Algo deu errado',exact=True)).to_have_count(0);assert chunk_requests
   else:
    expect(dialog.get_by_text('Etapa_F6',exact=True)).to_be_visible(timeout=15000)
    expect(dialog.get_by_title('Reexecutar a partir daqui',exact=True)).to_have_count(1 if mode=='rbac-sustentacao' else 0);expect(dialog.get_by_role('button',name='Reconhecer falha',exact=True)).to_have_count(1 if mode=='rbac-sustentacao' else 0)
    dialog.get_by_title('Log Airflow',exact=True).click();air=page.get_by_role('dialog',name='Log Airflow — '+NAME,exact=True);expect(air).to_be_visible();page.keyboard.press('Escape');expect(air).not_to_be_visible();trigger.click();dialog.get_by_title('Log DataStage',exact=True).click();ds=page.get_by_role('dialog',name='Log DataStage — Etapa_F6',exact=True);expect(ds).to_be_visible();page.keyboard.press('Escape');expect(ds).not_to_be_visible();assert not errors,errors
   assert not native and not writes,(native,writes);rows.append(dict(mode=mode,theme=theme,width=390 if theme=='dark' else 1440,localModal=True,shellPreserved=True,noWrites=True,expectedChunkError=mode=='chunk-error'));ctx.close()
 b.close()
args.output.write_text(json.dumps(dict(passed=True,scope='Build real; APIs sintéticas; não envia mensagens nem executa jobs; normal/cancelar/Esc/rejeição local',sourceIndexSha256=hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),cases=rows),indent=2));print('Dashboard logs PASS:',len(rows),'casos')
