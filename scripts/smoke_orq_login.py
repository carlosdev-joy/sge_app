"""Smoke ORQ com respostas simuladas; requer Playwright/Chromium e dist servido.
ORQ_SMOKE_URL=http://127.0.0.1:8766 python3 scripts/smoke_orq_login.py
Nenhuma credencial real; capturas em ORQ_SMOKE_OUTPUT (padrão /tmp).
"""
import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parents[1]
BASE = os.environ.get('ORQ_SMOKE_URL', 'http://127.0.0.1:8766').rstrip('/')
OUTPUT = Path(os.environ.get('ORQ_SMOKE_OUTPUT', '/tmp'))
OUTPUT.mkdir(parents=True, exist_ok=True)


def contraste(a, b):
    def luminancia(c):
        rgb = [float(n) / 255 for n in re.findall(r'[\d.]+', c)[:3]]
        linear = [n / 12.92 if n <= .04045 else ((n + .055) / 1.055) ** 2.4 for n in rgb]
        return sum(n * peso for n, peso in zip(linear, [.2126, .7152, .0722]))
    l1, l2 = sorted([luminancia(a), luminancia(b)])
    return (l2 + .05) / (l1 + .05)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.add_init_script("if(!localStorage.getItem('theme'))localStorage.setItem('theme','dark')")
        page = await context.new_page()
        errors, auth_calls, requests, bootstrap = [], [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        await page.route('**/login', lambda r: r.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'), content_type='text/html'))
        await page.route('**/orquestra/versao/publica', lambda r: r.fulfill(json={'versao': '2.10.3'}))

        async def before_bundle(route):
            bootstrap.append(await page.evaluate("({dark:document.documentElement.classList.contains('dark'),color:getComputedStyle(document.documentElement).backgroundColor})"))
            await route.continue_()
        await page.route('**/assets/index-*.js', before_bundle)
        await page.goto(BASE + '/login', wait_until='networkidle')
        await page.evaluate('document.fonts.ready')
        assert bootstrap and all(x['dark'] and x['color'] != 'rgb(255, 255, 255)' for x in bootstrap)
        await page.unroute('**/assets/index-*.js', before_bundle)
        assert await page.locator('#login_user').evaluate('e=>e===document.activeElement')
        assert await page.get_by_text('Versão 2.10.3', exact=True).is_visible()
        assert not any(u.endswith('/orquestra/versao') or u.endswith('/orquestra/config') for u in requests)
        ratios = {}
        for theme in ['light', 'dark']:
            if await page.evaluate("document.documentElement.classList.contains('dark')") != (theme == 'dark'):
                await page.get_by_role('button', name='Mudar para tema ' + ('claro' if theme == 'light' else 'escuro')).click()
            assert await page.evaluate("localStorage.getItem('theme')") == theme
            for width in [1440, 768, 360, 320]:
                await page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 850})
                await page.wait_for_timeout(80)
                dims = await page.evaluate('''() => ({width:innerWidth,body:document.documentElement.scrollWidth,
                    fields:[...document.querySelectorAll('input,button[type="submit"]')].map(e=>({x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})),
                    brand:document.querySelector('.orq-login-brand').getBoundingClientRect().width,
                    card:document.querySelector('.orq-login-card').getBoundingClientRect().width})''')
                assert dims['body'] <= width, (theme, width, dims)
                assert all(f['x'] >= 0 and f['right'] <= width and f['width'] >= 180 for f in dims['fields']), dims
                if width == 1440:
                    assert abs(dims['brand'] / dims['card'] - .48) < .01
                else:
                    if width <= 360:
                        assert await page.locator('.orq-login-brand').evaluate('e=>e.getBoundingClientRect().height') < 330
                for text in ['Pipelines', 'Chamados', 'Lineage', 'Desenvolvimento', 'IA']:
                    assert await page.get_by_role('heading', name=text, exact=True).is_visible()
                if width in [1440, 360, 320]:
                    await page.screenshot(path=str(OUTPUT / f'orq-login-{theme}-{width}.png'), full_page=True)
            colors = await page.locator('#login_user').evaluate('e=>({border:getComputedStyle(e).borderTopColor,bg:getComputedStyle(e).backgroundColor,text:getComputedStyle(e).color})')
            ratios[theme] = round(contraste(colors['border'], colors['bg']), 2)
            assert ratios[theme] >= 3, (theme, colors, ratios)
            assert contraste(colors['text'], colors['bg']) >= 4.5
            await page.locator('#login_user').focus()
            focus = await page.locator('#login_user').evaluate('e=>getComputedStyle(e).outlineColor')
            assert contraste(focus, colors['bg']) >= 3

        await page.set_viewport_size({'width': 1440, 'height': 1000})
        await page.locator('#login_user').focus()
        for target in ['#login_pass', '.orq-login-password-toggle', '.orq-login-submit']:
            await page.keyboard.press('Tab')
            assert await page.locator(target).evaluate('e=>e===document.activeElement'), target
        status = 401
        transport = False
        detail = 'Matrícula inexistente; informação que não pode ser exibida'
        release = asyncio.Event()
        called = asyncio.Event()

        async def reply(route):
            auth_calls.append(route.request.post_data_json)
            called.set()
            await release.wait()
            if transport:
                await route.abort('connectionrefused')
            else:
                await route.fulfill(status=status, json={'detail': detail})
        await page.route('**/orquestra/auth/login', reply)
        for value in ['', '   ']:
            await page.locator('#login_user').fill(value)
            await page.locator('#login_pass').fill('senha')
            await page.get_by_role('button', name='ENTRAR', exact=True).click()
            assert await page.get_by_role('alert').inner_text() == 'Preencha matrícula e senha.'
        assert not auth_calls
        await page.locator('#login_user').fill('  ORQ_TESTE  ')
        await page.locator('#login_pass').fill('  senha com espaços  ')
        assert await page.locator('#login_pass').get_attribute('type') == 'password'
        await page.get_by_role('button', name='Mostrar senha').click()
        assert await page.locator('#login_pass').get_attribute('type') == 'text'
        assert not auth_calls
        await page.get_by_role('button', name='Ocultar senha').click()
        await page.locator('#login_pass').evaluate("e=>e.dispatchEvent(new KeyboardEvent('keyup',{key:'CapsLock',modifierCapsLock:true,bubbles:true}))")
        assert await page.get_by_role('status').is_visible()
        await page.evaluate("window.__loginDocumento='preservado'")
        expected = {
            401: 'Matrícula ou senha incorreta. Use a mesma senha da sua rede corporativa',
            403: 'Sua matrícula não tem acesso liberado. Abra um chamado para a Engenharia de Dados',
            500: 'Não foi possível abrir sua sessão. O problema é do sistema, não da sua senha',
            502: 'Serviço de autenticação indisponível. Não é a sua senha — tente em alguns minutos',
            422: 'Preencha matrícula e senha.',
        }
        for status in [401, 401, 403, 500, 502, 422, 0]:
            transport = status == 0
            prior = len(auth_calls)
            release.clear()
            called.clear()
            detail = 'Senha incorreta' if prior else detail
            await page.get_by_role('button', name='Mostrar senha').click()
            width_before = (await page.locator('.orq-login-submit').bounding_box())['width']
            await page.locator('#login_pass').press('Enter')
            await asyncio.wait_for(called.wait(), 5)
            await page.get_by_role('button', name='Entrando…').wait_for()
            assert await page.get_by_role('button', name='Entrando…').is_disabled()
            assert await page.locator('#login_pass').get_attribute('type') == 'password'
            await page.locator('form').evaluate("e=>e.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
            await page.wait_for_timeout(100)
            assert len(auth_calls) == prior + 1
            release.set()
            await page.get_by_role('button', name='ENTRAR', exact=True).wait_for()
            assert (await page.locator('.orq-login-submit').bounding_box())['width'] == width_before
            assert auth_calls[-1] == {'usuario': 'ORQ_TESTE', 'senha': '  senha com espaços  '}
            msg = expected.get(status, 'Não foi possível conectar ao ORQ. Verifique sua conexão corporativa')
            assert await page.get_by_role('alert').inner_text() == msg
            assert await page.get_by_role('alert').get_attribute('aria-live') == 'polite'
            assert await page.locator('#login_user').input_value() == '  ORQ_TESTE  '
            assert await page.evaluate('window.__loginDocumento') == 'preservado'
        assert not errors, errors
        await page.screenshot(path=str(OUTPUT / 'orq-login-erro.png'), full_page=True)
        # Confere persistência real do tema no recarregamento, com bootstrap pré-bundle.
        await page.reload(wait_until='networkidle')
        assert await page.evaluate("document.documentElement.classList.contains('dark')")
        await context.close()

        # Valores derivados da ordem atual do NAV: /avisos vem ANTES de /chamados.
        for perms, destino in [([], '/dashboard'), (['tela_utilitarios'], '/utilitarios'), (['tela_chamados'], '/avisos')]:
            ctx = await browser.new_context(viewport={'width': 1440, 'height': 1000})
            pg = await ctx.new_page()
            await pg.route('**/login', lambda r: r.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'), content_type='text/html'))
            await pg.route('**/orquestra/**', lambda r: r.fulfill(json={'data': [], 'total': 0}))
            await pg.route('**/orquestra/auth/login', lambda r: r.fulfill(json={'token': 'token-ficticio-local', 'usuario': {'matricula': 'ORQ_TESTE', 'perfil': 'operador', 'permissoes': perms}}))
            await pg.goto(BASE + '/login', wait_until='networkidle')
            await pg.locator('#login_user').fill('ORQ_TESTE')
            await pg.locator('#login_pass').fill('senha-ficticia')
            await pg.locator('#login_user').press('Enter')
            await pg.wait_for_url('**' + destino)
            assert await pg.evaluate("localStorage.getItem('orquestra_token')") == 'token-ficticio-local'
            if destino == '/avisos':
                await pg.screenshot(path=str(OUTPUT / 'orq-header-contraste.png'), full_page=True)
            await ctx.close()
        icons = await browser.new_page(viewport={'width': 420, 'height': 210})
        await icons.set_content(f"""<body style='font:14px system-ui;margin:0'>
          <div style='padding:25px;background:white;color:#04143c'>Símbolo em 16 e 32 px
            <img src='{BASE}/images/orq/logo-orbital.png' width='16' height='16' style='object-fit:contain' alt='ORQ 16'>
            <img src='{BASE}/images/orq/logo-orbital.png' width='32' height='32' style='object-fit:contain' alt='ORQ 32'></div>
          <div style='padding:25px;background:#04143c;color:white'>Símbolo em 16 e 32 px
            <img src='{BASE}/images/orq/logo-orbital.png' width='16' height='16' style='object-fit:contain' alt='ORQ 16'>
            <img src='{BASE}/images/orq/logo-orbital.png' width='32' height='32' style='object-fit:contain' alt='ORQ 32'></div></body>""")
        await icons.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
        await icons.screenshot(path=str(OUTPUT / 'orq-simbolo-16-32.png'))
        await icons.close()
        print(json.dumps({'resultado': 'OK', 'contraste_bordas': ratios, 'layout': '1440/768/360/320, claro/escuro',
                          'auth': '401 sem reload, 403,422,500,502,transporte,spaces,toggle,Enter,loading,CapsLock,RBAC',
                          'tema': 'bootstrap anterior ao bundle e persistência verificados', 'screenshots': str(OUTPUT)}, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
