"""Smoke do login ORQ com API simulada; requer Playwright/Chromium e build servido.
Uso: ORQ_SMOKE_URL=http://127.0.0.1:8766 python3 scripts/smoke_orq_login.py
Nenhuma credencial real é usada. Capturas ficam em ORQ_SMOKE_OUTPUT (padrão /tmp).
"""
import asyncio, json, os
from pathlib import Path
from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parents[1]
BASE = os.environ.get('ORQ_SMOKE_URL', 'http://127.0.0.1:8766').rstrip('/')
OUTPUT = Path(os.environ.get('ORQ_SMOKE_OUTPUT', '/tmp'))
OUTPUT.mkdir(parents=True, exist_ok=True)

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True, args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
  errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  await page.route('**/login',lambda r:r.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'),content_type='text/html'))
  await page.goto(BASE + '/', wait_until='networkidle')
  await page.evaluate('document.fonts.ready')
  await page.get_by_role('heading',name='Entrar no ORQ').wait_for()
  for text in ['Pipelines','Chamados','Lineage','Desenvolvimento','IA']:
   assert await page.get_by_role('heading',name=text,exact=True).count()==1
  for theme in ['light','dark']:
   await page.evaluate('(theme)=>document.documentElement.classList.toggle("dark",theme==="dark")',theme)
   for width in [1440,768,375,320]:
    await page.set_viewport_size({'width':width,'height':1000 if width==1440 else 850})
    await page.wait_for_timeout(100)
    dims=await page.evaluate('''() => ({width:innerWidth,body:document.documentElement.scrollWidth,
      fields:[...document.querySelectorAll('input,button[type="submit"]')].map(e=>({x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width}))})''')
    assert dims['body']<=width,(theme,width,dims)
    assert all(f['x']>=0 and f['right']<=width and f['width']>=180 for f in dims['fields']),(theme,width,dims)
    if width in [1440,375]:
     await page.screenshot(path=str(OUTPUT / f'orq-login-{theme}-{width}.png'),full_page=True)
  await page.evaluate('document.documentElement.classList.remove("dark")')
  await page.set_viewport_size({'width':1440,'height':1000})
  await page.get_by_label('Matrícula',exact=True).fill('ORQ_TESTE')
  await page.get_by_label('Senha',exact=True).fill('senha-ficticia')
  await page.get_by_label('Senha',exact=True).evaluate("e=>e.dispatchEvent(new KeyboardEvent('keyup',{key:'CapsLock',modifierCapsLock:true,bubbles:true}))")
  assert await page.get_by_role('status').is_visible()
  calls=[]
  async def deny(route):
   calls.append(route.request.post_data_json)
   await asyncio.sleep(.3)
   await route.fulfill(status=503,json={'detail':'Serviço temporariamente indisponível — teste local.'})
  await page.route('**/orquestra/auth/login',deny)
  await page.get_by_label('Senha',exact=True).press('Enter')
  await page.get_by_role('button',name='Entrando…').wait_for()
  assert await page.get_by_role('button',name='Entrando…').is_disabled()
  await page.get_by_role('alert').wait_for()
  assert 'Serviço temporariamente' in await page.get_by_role('alert').inner_text()
  assert calls==[{'usuario':'ORQ_TESTE','senha':'senha-ficticia'}]
  assert await page.get_by_role('button',name='ENTRAR',exact=True).is_enabled()
  assert not errors, errors
  await page.unroute('**/orquestra/auth/login',deny)
  await page.route('**/orquestra/**',lambda r:r.fulfill(json={}))
  await page.route('**/orquestra/auth/login',lambda r:r.fulfill(json={'token':'token-ficticio-local','usuario':{'matricula':'ORQ_TESTE','perfil':'operador','permissoes':['tela_utilitarios']}}))
  await page.get_by_label('Senha',exact=True).press('Enter')
  await page.wait_for_function("localStorage.getItem('orquestra_token')==='token-ficticio-local'")
  assert '/login' not in page.url
  print(json.dumps({'layout':'light/dark 1440,768,375,320 sem overflow','form':'Enter, payload, loading, erro, retry, caps lock e sessão/destino verificados com API simulada','screenshots':str(OUTPUT / 'orq-login-{light,dark}-{1440,375}.png')},ensure_ascii=False))
  await browser.close()
asyncio.run(main())
