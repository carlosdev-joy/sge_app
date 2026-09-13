"""Regressão F2: teclado, notificações, perfil e contratos existentes; APIs simuladas."""
import asyncio
import json
from playwright.async_api import async_playwright
from smoke_orq_login import BASE, OUTPUT, RAIZ


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 850})
        await ctx.add_init_script('''
            if (!sessionStorage.getItem('seeded')) {
                const user = {matricula:'ORQ_TESTE', primeiro_nome:'Maria', ultimo_nome:'Teste',
                    perfil:'consulta',email:'teste@example.invalid',area:'Dados',permissoes:['tela_chamados']};
                localStorage.setItem('orquestra_token','token-ficticio');
                localStorage.setItem('orquestra-auth',JSON.stringify({state:{user,token:'token-ficticio'},version:0}));
                sessionStorage.setItem('seeded','1');
            }
        ''')
        page = await ctx.new_page()
        errors, calls = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        async def serve(route):
            if route.request.resource_type == 'document':
                await route.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'),content_type='text/html')
            else:
                await route.continue_()
        await page.route('**/*',serve)
        notifs = [dict(id=1,tipo='info',titulo='Aviso sem ação',mensagem='<script>conteudo seguro</script>',link=None,lida=False,created_at='2026-09-13T15:00:00'),
                  dict(id=2,tipo='info',titulo='Abrir avisos',mensagem=None,link='/avisos',lida=False,created_at='2026-09-13T14:00:00')]
        coms = [dict(id=3,tipo='info',titulo='Confirmar comunicado',mensagem='Somente confirmação',formato='simples',link=None,visto=False,confirmado=False,created_at='2026-09-13T16:00:00')]
        banners = []
        async def api(route):
            path = route.request.url.split('/orquestra')[-1]
            method = route.request.method
            if method == 'POST':
                payload = route.request.post_data_json
                calls.append((path,payload))
                if path == '/auth/logout':
                    await route.fulfill(status=500,json={'detail':'falha simulada'})
                    return
                if path == '/comunicados/visto':
                    for c in coms + banners:
                        if c['id'] in payload['ids']: c['visto'] = True
                if path == '/comunicados/3/confirmar': coms[0]['confirmado'] = True
                if path == '/comunicados/4/confirmar': banners.clear()
                if path == '/notificacoes/read':
                    for n in notifs: n['lida'] = True
                await route.fulfill(json={'ok':True})
            elif path.startswith('/notificacoes?'):
                await route.fulfill(json={'data':notifs,'unread':sum(not n['lida'] for n in notifs)})
            elif path == '/comunicados/inbox':
                await route.fulfill(json={'data':coms,'unread':sum(not c['confirmado'] for c in coms),'banners':banners})
            elif path == '/versao':
                await route.fulfill(json={'data':[{'id':1,'versao':'2.10','titulo':'Versão teste'}]})
            else:
                await route.fulfill(json={'data':[],'total':0})
        await page.route('**/orquestra/**',api)
        await page.goto(BASE + '/avisos',wait_until='networkidle')
        header = page.get_by_role('banner')
        bell = header.get_by_role('button',name='Notificações',exact=False)
        await bell.focus()
        await page.keyboard.press('Enter')
        assert await bell.get_attribute('aria-expanded') == 'true'
        await page.keyboard.press('Escape')
        assert await bell.get_attribute('aria-expanded') == 'false', 'Escape não fechou notificações'
        assert await bell.evaluate('e=>e===document.activeElement')
        assert await bell.get_attribute('aria-label') == 'Notificações, 3 não lidas'
        assert await bell.get_attribute('aria-haspopup') == 'dialog'
        await bell.press('Space')
        feed = page.get_by_role('dialog',name='Notificações',exact=True)
        await feed.wait_for()
        assert await feed.get_by_role('button',name='Aviso sem ação',exact=False).count() == 0
        assert await feed.get_by_text('<script>conteudo seguro</script>',exact=True).is_visible()
        confirm = feed.get_by_role('button',name='Confirmar comunicado',exact=False)
        await confirm.focus(); await page.keyboard.press('Space')
        await header.get_by_role('button',name='Notificações, 2 não lidas',exact=True).wait_for()
        assert sum(path=='/comunicados/3/confirmar' for path,_ in calls) == 1
        assert ('/comunicados/visto',{'ids':[3]}) in calls
        assert await feed.get_by_role('button',name='Confirmar comunicado',exact=False).count() == 0
        await feed.get_by_role('button',name='Marcar todas como lidas').focus()
        await page.keyboard.press('Enter')
        await header.get_by_role('button',name='Notificações, 0 não lidas',exact=True).wait_for()
        assert ('/notificacoes/read',{'all':True}) in calls
        await feed.get_by_role('button',name='Abrir avisos',exact=False).focus()
        await page.keyboard.press('Enter')
        assert await bell.get_attribute('aria-expanded') == 'false'
        profile = header.get_by_role('button',name='Abrir perfil de Maria Teste')
        await profile.focus(); await page.keyboard.press('Enter')
        panel = page.get_by_role('dialog',name='Perfil do usuário')
        await panel.wait_for()
        assert await panel.get_by_text('ORQ v2.10',exact=True).is_visible()
        assert await panel.get_by_text('teste@example.invalid',exact=True).is_visible()
        await panel.get_by_role('button',name='Sair',exact=True).focus()
        await page.keyboard.press('Escape')
        assert await profile.get_attribute('aria-expanded') == 'false'
        assert await profile.evaluate('e=>e===document.activeElement')
        for theme in ['light','dark']:
            await page.evaluate("t=>document.documentElement.classList.toggle('dark',t==='dark')",theme)
            for width in [1440,768,360,320]:
                await page.set_viewport_size({'width':width,'height':568 if width<768 else 800})
                triggers=[bell,profile,header.get_by_role('button',name='Alternar tema',exact=True)]
                for trigger in triggers:
                    box=await trigger.bounding_box()
                    assert box['width']>=36 and box['height']>=36 and box['x']>=0 and box['x']+box['width']<=width, (width,box)
                    assert await trigger.get_attribute('type')=='button'
                for trigger, name in [(bell,'Notificações'),(profile,'Perfil do usuário')]:
                    await trigger.click()
                    dialog=page.get_by_role('dialog',name=name,exact=True)
                    if name == 'Perfil do usuário':
                        assert await dialog.evaluate("e=>getComputedStyle(e).backgroundColor === 'rgb(4, 20, 60)' && getComputedStyle(e).backgroundImage === 'none'")
                    box=await dialog.bounding_box()
                    assert box['x']>=0 and box['x']+box['width']<=width and box['y']+box['height']<=page.viewport_size['height'],(width,name,box)
                    await page.screenshot(path=str(OUTPUT / f'orq-header-f2-{theme}-{width}-{name.split()[0]}.png'))
                    await trigger.press('Escape')
                    assert not await dialog.count()
        await page.keyboard.press('Control+k')
        search = page.get_by_placeholder('Buscar pipelines, jobs, catálogo…')
        await search.wait_for()
        await page.wait_for_function("document.activeElement?.getAttribute('placeholder') === 'Buscar pipelines, jobs, catálogo…'")
        await page.keyboard.press('Escape')
        await search.wait_for(state='hidden')
        await page.keyboard.press('Meta+k')
        search = page.get_by_placeholder('Buscar pipelines, jobs, catálogo…')
        await search.wait_for()
        await page.wait_for_function("document.activeElement?.getAttribute('placeholder') === 'Buscar pipelines, jobs, catálogo…'")
        await page.keyboard.press('Escape')
        await search.wait_for(state='hidden')
        # Sincroniza o estado do componente antes de verificar o toggle persistido.
        await page.reload(wait_until='networkidle')
        before=await page.evaluate("document.documentElement.classList.contains('dark')")
        await header.get_by_role('button',name='Alternar tema',exact=True).click()
        assert await page.evaluate("document.documentElement.classList.contains('dark')") != before
        assert await page.evaluate("localStorage.getItem('theme')") == ('light' if before else 'dark')
        # Banner mantém marcação de visto e exige confirmação explícita.
        banners.append(dict(id=4,tipo='info',titulo='Banner exige confirmação',mensagem='Leia o comunicado',formato='banner',link=None,visto=False,confirmado=False,created_at='2026-09-13T17:00:00'))
        await page.reload(wait_until='networkidle')
        await page.get_by_role('heading',name='Banner exige confirmação').wait_for()
        await page.keyboard.press('Escape')
        assert await page.get_by_role('heading',name='Banner exige confirmação').is_visible()
        assert not any(path=='/comunicados/4/confirmar' for path,_ in calls)
        await page.get_by_role('button',name='Entendi',exact=True).click()
        await page.get_by_role('heading',name='Banner exige confirmação').wait_for(state='hidden')
        assert ('/comunicados/visto',{'ids':[4]}) in calls
        await profile.click()
        await page.get_by_role('button',name='Sair',exact=True).click()
        await page.wait_for_url('**/login')
        await page.locator('#login_user').wait_for()
        assert any(path=='/auth/logout' for path,_ in calls)
        assert await page.evaluate("localStorage.getItem('orquestra_token')") is None
        assert await page.evaluate("JSON.parse(localStorage.getItem('orquestra-auth')).state.user") is None
        assert not errors, errors
        print(json.dumps({'resultado':'OK','teclado_perfil_feed_aria':'OK','responsivo_temas':'OK','leitura_confirmacao_banner_logout':'OK'}))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
