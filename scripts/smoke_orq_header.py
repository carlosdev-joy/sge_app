"""Header ORQ F1 em Chromium; APIs simuladas, sem credenciais reais.
ORQ_SMOKE_URL=http://127.0.0.1:8766 python3 scripts/smoke_orq_header.py
"""
import asyncio
import json
from playwright.async_api import async_playwright
from smoke_orq_login import BASE, OUTPUT, RAIZ


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context()
        await context.add_init_script('''
            const user = {matricula:'ORQ_TESTE', primeiro_nome:'OperadorComNomeMuitoLongo',
                perfil:'consulta', permissoes:['tela_avisos','tela_utilitarios']};
            localStorage.setItem('orquestra_token','token-ficticio');
            localStorage.setItem('orquestra-auth',JSON.stringify({state:{user,token:'token-ficticio'},version:0}));
        ''')
        page = await context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        async def serve(route):
            if route.request.resource_type == 'document':
                await route.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'), content_type='text/html')
            else:
                await route.continue_()
        await page.route('**/*', serve)
        await page.route('**/orquestra/**', lambda r: r.fulfill(json={'data': [], 'total': 0, 'unread': 0, 'banners': []}))
        await page.route('**/orquestra/utilitarios/config', lambda r: r.fulfill(json={'raizes': [], 'servidores': [], 'extensoes': [], 'pode_gravar': False}))
        await page.route('**/orquestra/versao', lambda r: r.fulfill(json={'data':[{'versao':'2.9'},{'versao':'2.10'}]}))
        # Força o fallback institucional que existe no ambiente DEV.
        await page.route('**/branding/logo-cvp.png', lambda r: r.fulfill(status=404))
        await page.goto(BASE + '/avisos', wait_until='networkidle')
        await page.evaluate('document.fonts.ready')
        header = page.get_by_role('banner')
        brand = header.locator('a[href="/"]')
        await page.evaluate('window.__headerDocumento = "preservado"')
        await brand.click()
        await page.wait_for_url('**/utilitarios')
        assert await page.evaluate('window.__headerDocumento') == 'preservado', 'Marca provocou reload completo'
        assert await brand.get_attribute('aria-label') == 'Ir para o início do ORQ'
        assert await brand.get_by_text('v2.10', exact=True).count() == 1
        assert not any('/versao/publica' in u for u in requests)
        for theme in ['light', 'dark']:
            await page.evaluate("t=>document.documentElement.classList.toggle('dark',t==='dark')", theme)
            for width in [1440, 1280, 1100, 1024, 900, 768, 767, 640, 360, 320]:
                await page.set_viewport_size({'width':width,'height':800})
                await page.evaluate('document.fonts.ready')
                dims = await header.evaluate('''e=>({height:e.getBoundingClientRect().height,
                    body:e.firstElementChild.getBoundingClientRect().height,
                    stripe:e.lastElementChild.getBoundingClientRect().height,
                    bg:getComputedStyle(e).backgroundImage,
                    controls:[...e.querySelectorAll('button,a')].filter(x=>x.getClientRects().length).map(x=>({label:x.title||x.textContent,x:x.getBoundingClientRect().x,right:x.getBoundingClientRect().right}))})''')
                assert (dims['height'], dims['body'], dims['stripe']) == (56,52,4), dims
                assert '135deg' in dims['bg'] and 'rgb(26, 95, 168)' in dims['bg'] and '55%' in dims['bg'], dims
                assert all(x['x'] >= 0 and x['right'] <= width for x in dims['controls']), (width,dims)
                assert all(a['right'] <= b['x'] for a,b in zip(dims['controls'],dims['controls'][1:])), (width,dims)
                assert await header.get_by_role('img',name='ORQ',exact=True).is_visible()
                institution = brand.get_by_role('img',name='Caixa Vida e Previdência')
                assert await institution.is_visible() == (width >= 768)
                if width >= 768:
                    assert await institution.evaluate("e=>e.complete && e.naturalWidth > 0 && e.src.endsWith('/images/logo-cvp.svg')")
                assert await header.get_by_title('Busca global (Ctrl+K)').is_visible() == (width >= 1280)
                assert await header.get_by_text('Utilitários',exact=True).is_visible() == (width >= 1024)
                assert await header.get_by_text('OperadorComNomeMuitoLongo',exact=True).is_visible() == (width >= 768)
                if width in [1440,768,360,320]:
                    await page.screenshot(path=str(OUTPUT / f'orq-header-f1-{theme}-{width}.png'))
        await header.get_by_role('button',name='Abrir menu').click()
        await page.get_by_role('button',name='Fechar menu').click()
        await page.keyboard.press('Control+k')
        await page.get_by_placeholder('Buscar pipelines, jobs, catálogo…').wait_for()
        await page.keyboard.press('Escape')
        assert not errors, errors
        print(json.dumps({'resultado':'OK','larguras':[1440,1280,1100,1024,900,768,767,640,360,320],
                          'temas':['light','dark'],'SPA_RBAC_fallback_versao_drawer_atalho':'OK'}))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
