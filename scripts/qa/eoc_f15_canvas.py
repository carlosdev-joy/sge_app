"""Capturas do catálogo compilado com APIs sintéticas; sem backend real."""
import argparse,hashlib,json,mimetypes,uuid,sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect
parser=argparse.ArgumentParser(description='QA F15: dist com APIs sintéticas, sem backend. Requer Playwright local.')
parser.add_argument('--dist',type=Path,default=Path(__file__).resolve().parents[2]/'ui-react/dist')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
E=args.output;D=args.dist;O=E/'browser';O.mkdir(parents=True,exist_ok=True)
pipe='PIPE_FIXTURE_'+'NOME_LONGO_'*12
names=['Carga financeira consolidada — conciliação e fechamento mensal','Carga sem execução registrada','Carga inativa de referência']
def cycle(i):
 return dict(id=i,malha_name=names[0],data_referencia='2026-10-12',sequencia=i-100,status='ABERTA',aberta_em='2026-10-12T02:00:00',fechada_em='2026-10-12T03:00:00',fechada_por=None,origem='manual',aberta_por='Fixture',ancora_pipeline=pipe,modo_fechamento='todos',teto_em=None,tentativas=0,reaberta_em=None,reaberta_por=None,motivo=None,saude=None,decorrido_min=60,apurado_em='2026-10-12T03:00:00',membros_total=1,membros_ok=1,membros_vivos=0,membros_dispensados=0,membros_travados=0,membros_inativos=0,membros_fora_do_odate=0,pendentes=[],ultimo_movimento_em=None,sem_sinal_min=None)
cards=[dict(malha_name=n,descricao='Fixture própria de QA',ativo=i!=2,criado_em='2026-10-12',qtd_pipelines=1,qtd_ativos=1,criticidade=None,**({'corrida':cycle(102)} if i==0 else {})) for i,n in enumerate(names)]
checks=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch()
 for width,theme in [(1440,'light'),(1440,'dark'),(947,'light'),(947,'dark'),(375,'light'),(375,'dark')]:
  errors=[];calls=[]
  def serve(route,request):
   u=urlsplit(request.url);p=u.path.removeprefix('/orquestra');q=parse_qs(u.query)
   if not u.path.startswith('/orquestra/'):
    f=D/u.path.lstrip('/');f=f if f.is_file() else D/'index.html';route.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream');return
   calls.append(p);assert request.method=='GET', (p,request.method)
   body={}
   if p=='/malhas':body={'malhas':cards,'corrida_suportada':True}
   elif p.endswith('/execucao'):
    i=int(q.get('corrida',['102'])[0]);body={'data_referencia':'2026-10-12','corrida':cycle(i),'execucoes':[{'pipeline_name':pipe,'run_id':f'fixture-run-{i}','status':'SUCESSO','inicio':'2026-10-12T02:00:00','fim':'2026-10-12T03:00:00','disparado_por':'Fixture','motivo':None}],'eventos':[],'eventos_no':[],'eventos_corrida':[]}
   elif p.endswith('/corridas'):body={'corridas':[cycle(102),cycle(101)]}
   elif p.startswith('/malhas/'):
    body={'malha_name':names[0],'descricao':'Fixture','ativo':True,'membros':[{'pipeline_name':pipe,'active':True,'criticidade':None,'schedule_type':None,'layout_x':0,'layout_y':0}],'arestas':[],'nos':[],'arestas_no':[],'avisos':[]}
   elif p=='/versao':body={'versao':'2.34.0','nome':'Fixture'}
   elif p.startswith('/pipelines'):body={'data':[],'total':0}
   elif p.startswith('/msg/') or p.startswith('/notificacoes') or p.startswith('/comunicados'):body={'data':[],'total':0,'nao_lidas':0}
   route.fulfill(content_type='application/json',body=json.dumps(body))
  token=uuid.uuid4().hex;user={'matricula':'EOC_FIXTURE','perfil':'consulta','is_admin':False,'primeiro_nome':'Fixture','permissoes':['tela_malha','tela_dashboard','tela_fluxos','tela_pipelines']}
  ctx=browser.new_context(viewport={'width':width,'height':667 if width==375 else 960},locale='pt-BR');ctx.add_init_script('localStorage.setItem("orquestra-auth",'+json.dumps(json.dumps({'state':{'user':user,'token':token},'version':0}))+');localStorage.setItem("orquestra_token",'+json.dumps(token)+');localStorage.setItem("theme",'+json.dumps(theme)+');')
  page=ctx.new_page();page.route('**/*',serve);page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://eoc-f14.local/malha');expect(page.get_by_role('heading',name='Malhas',exact=True)).to_be_visible();expect(page.get_by_text(names[0],exact=True)).to_be_visible()
  page.get_by_role('button',name='Definição',exact=True).first.click()
  expect(page.get_by_role('button',name='Montagem',exact=True)).to_be_visible()
  for modo in ['montagem','execucao']:
   if modo=='execucao':
    page.get_by_role('button',name='Execução',exact=True).click()
   page.get_by_text('Localizar / lista de nós',exact=False).click()
   campo=page.get_by_role('textbox',name='Localizar nó nesta visão')
   campo.fill('inexistente')
   expect(page.get_by_text('Nenhum nó corresponde à busca.',exact=False)).to_be_visible()
   campo.fill('pipe_fixture')
   alvo=page.get_by_role('list',name='Nós da malha').get_by_role('button')
   expect(alvo).to_have_count(1)
   alvo.focus();page.keyboard.press('Enter')
   expect(alvo).to_have_attribute('aria-pressed','true')
   expect(page.get_by_role('region',name='Propriedades do nó').get_by_text(pipe,exact=True)).to_be_visible()
   if modo=='execucao':
    antes=sum(p.endswith('/execucao') for p in calls)
    page.wait_for_timeout(16500)
    assert sum(p.endswith('/execucao') for p in calls)>antes, calls
    expect(alvo).to_have_attribute('aria-pressed','true')
   canvas=page.locator('.react-flow__controls')
   canvas.scroll_into_view_if_needed();expect(canvas).to_be_visible()
   realce=page.get_by_text('Cadeia de dependências',exact=True).filter(visible=True).locator('..').locator('..').locator('..')
   caixa_realce=realce.bounding_box();caixa_canvas=page.locator('.react-flow').bounding_box()
   if width!=375:
    caixa_acoes=page.locator('.react-flow__panel.top.right').bounding_box()
    assert caixa_acoes and caixa_realce and caixa_acoes['y']+caixa_acoes['height']<=caixa_realce['y'],(caixa_acoes,caixa_realce)
    caixa_controles=canvas.bounding_box()
    assert caixa_canvas and caixa_controles and caixa_realce['y']+caixa_realce['height']<=caixa_canvas['y']+caixa_canvas['height'],(caixa_realce,caixa_canvas)
    assert caixa_realce['y']+caixa_realce['height']<=caixa_controles['y'],(caixa_realce,caixa_controles)
   if width==375:
    assert caixa_realce and caixa_canvas and caixa_realce['y']+caixa_realce['height']<=caixa_canvas['y'],(caixa_realce,caixa_canvas)
   page.get_by_role('button',name='Para trás',exact=True).filter(visible=True).click()
   page.get_by_role('button',name='Isolar a cadeia',exact=True).filter(visible=True).click()
   page.get_by_role('button',name='Mostrar o desenho inteiro',exact=True).filter(visible=True).click()
   page.get_by_role('button',name='Ambos',exact=True).filter(visible=True).click()
   page.screenshot(path=str(O/f'canvas-{modo}-{width}-{theme}.png'),full_page=True)
   overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
   assert not overflow,(width,theme,modo)
   assert not errors,errors
   checks.append({'width':width,'theme':theme,'mode':modo,'overflow':overflow,'keyboardSelection':True,'noWrites':True,'pollingPreservesSelection':modo=='execucao','geometry':{'realce':caixa_realce,'canvas':caixa_canvas,'actions':caixa_acoes if width!=375 else None}})
   limpar=page.get_by_title('Limpar o realce (Esc, ou clique no fundo do canvas)',exact=True).filter(visible=True)
   expect(limpar).to_have_count(1);limpar.click();expect(limpar).to_have_count(0)
   checks[-1]['clearPointerReachable']=True
   page.get_by_text('Localizar / lista de nós',exact=False).click()
  ctx.close()
 browser.close()
report={'passed':all(not c['overflow'] for c in checks),'checks':checks,'distIndexSha256':hashlib.sha256((D/'index.html').read_bytes()).hexdigest(),'scope':'Chromium dist; API interceptada; fixtures próprias sem persistência'}
(E/'browser-candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));assert report['passed']
