"""F3: histórico autenticado, identidade ORQ, diálogo e teclado; dados simulados."""
import asyncio
import json
from playwright.async_api import async_playwright
from smoke_orq_login import BASE, OUTPUT, RAIZ


async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        ctx=await browser.new_context(viewport={'width':1440,'height':850})
        await ctx.add_init_script('''
            localStorage.setItem('orquestra_token','token-ficticio');
            localStorage.setItem('orquestra-auth',JSON.stringify({state:{token:'token-ficticio',user:{matricula:'ORQ_TESTE',primeiro_nome:'Maria',ultimo_nome:'Teste',perfil:'consulta',permissoes:['tela_chamados']}},version:0}));
        ''')
        page=await ctx.new_page()
        errors, version_calls=[],[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        async def serve(route):
            if route.request.resource_type=='document':
                await route.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'),content_type='text/html')
            else: await route.continue_()
        await page.route('**/*',serve)
        await page.route('**/orquestra/**',lambda r:r.fulfill(json={'data':[],'banners':[],'total':0,'unread':0}))
        rows=[dict(id=1,versao='2.10',titulo='Entrega ORQ',descricao_md='Histórico interno <script>texto seguro</script>',criado_em='2026-09-13T12:00:00',criado_por='ORQ_TESTE'),
              dict(id=2,versao='2.9',titulo='Entrega anterior',descricao_md='Descrição anterior',criado_em=None,criado_por=None)]
        async def versions(route):
            version_calls.append((route.request.url,route.request.headers.get('authorization')))
            await route.fulfill(json={'data':rows,'total':len(rows)})
        await page.route('**/orquestra/versao',versions)
        await page.goto(BASE+'/avisos',wait_until='networkidle')
        profile=page.get_by_role('button',name='Abrir perfil de Maria Teste')
        async def open_history():
            await profile.click()
            await page.get_by_role('button',name='ORQ v2.10',exact=True).click()
        await open_history()
        dialog=page.get_by_role('dialog',name='Histórico de versões',exact=True)
        assert await dialog.count()==1, 'Histórico sem semântica de diálogo'
        assert await dialog.get_attribute('aria-modal')=='true'
        assert await dialog.get_by_text('ORQ',exact=True).is_visible()
        assert await dialog.get_by_text('Plataforma de Orquestração de Dados, Processos e Inteligência',exact=True).is_visible()
        assert await dialog.get_by_text('Histórico interno <script>texto seguro</script>',exact=True).is_visible()
        assert len(version_calls)==1, version_calls
        assert version_calls[0][1]=='Bearer token-ficticio'
        assert await dialog.evaluate('e=>e.contains(document.activeElement)')
        close=dialog.get_by_role('button',name='Fechar',exact=True)
        cross=dialog.get_by_role('button',name='Fechar histórico de versões',exact=True)
        for button in [close,cross]: assert await button.get_attribute('type')=='button'
        await cross.focus(); await page.keyboard.press('Shift+Tab')
        assert await close.evaluate('e=>e===document.activeElement')
        await page.keyboard.press('Tab')
        assert await cross.evaluate('e=>e===document.activeElement')
        await page.keyboard.press('Escape')
        await dialog.wait_for(state='hidden')
        assert await profile.evaluate('e=>e===document.activeElement')
        for theme in ['light','dark']:
            await page.evaluate("t=>document.documentElement.classList.toggle('dark',t==='dark')",theme)
            for width,height in [(1440,850),(768,650),(360,640),(320,568),(667,375)]:
                await page.set_viewport_size({'width':width,'height':height})
                await open_history()
                box=await dialog.bounding_box()
                assert box['x']>=0 and box['x']+box['width']<=width and box['y']>=0 and box['y']+box['height']<=height,(width,height,box)
                for button in [close,cross]:
                    b=await button.bounding_box()
                    assert b['x']>=box['x'] and b['x']+b['width']<=box['x']+box['width'] and b['y']>=0 and b['y']+b['height']<=height,(width,b)
                assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth')
                await page.screenshot(path=str(OUTPUT/f'orq-header-f3-{theme}-{width}x{height}.png'))
                await close.click()
                await dialog.wait_for(state='hidden')
                assert await profile.evaluate('e=>e===document.activeElement')
        await open_history(); await cross.click(); await dialog.wait_for(state='hidden')
        assert await profile.evaluate('e=>e===document.activeElement')
        # Busca global pode sobrepor o modal; Escape fecha somente a camada de cima.
        await open_history(); await page.keyboard.press('Control+k')
        search=page.get_by_placeholder('Buscar pipelines, jobs, catálogo…')
        await search.wait_for()
        await page.wait_for_function("document.activeElement?.getAttribute('placeholder') === 'Buscar pipelines, jobs, catálogo…'")
        await page.keyboard.press('Escape'); await search.wait_for(state='hidden')
        assert await dialog.is_visible()
        await cross.focus(); await page.keyboard.press('Escape'); await dialog.wait_for(state='hidden')
        # Sem registros mantém mensagem e fallback do header/perfil.
        rows.clear()
        await page.reload(wait_until='networkidle')
        await profile.click(); await page.get_by_role('button',name='ORQ v1.0',exact=True).click()
        assert await dialog.get_by_text('Nenhum registro de versão cadastrado.',exact=True).is_visible()
        await cross.click()
        assert not errors,errors
        print(json.dumps({'resultado':'OK','branding_dialogo_foco_tab_escape':'OK','versao_autenticada_cache_fallback':'OK','responsivo_temas':'OK'}))
        await browser.close()


if __name__=='__main__': asyncio.run(main())
