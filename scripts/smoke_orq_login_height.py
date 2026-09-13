"""Regressão de altura do login; usa o servidor e mocks do smoke ORQ."""
import asyncio
import json
from playwright.async_api import async_playwright
from smoke_orq_login import BASE, OUTPUT, RAIZ


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page()
        await page.route('**/login', lambda r: r.fulfill(path=str(RAIZ / 'ui-react/dist/index.html'), content_type='text/html'))
        await page.route('**/orquestra/versao/publica', lambda r: r.fulfill(json={'versao': '2.10.3'}))
        await page.route('**/orquestra/auth/login', lambda r: r.fulfill(status=401, json={'detail': 'Não autorizado'}))
        results = []
        for theme in ['light', 'dark']:
            for width, height in [(1580, 730), (1366, 650), (1024, 600), (768, 600), (390, 664), (360, 640), (320, 568), (667, 375), (800, 300)]:
                await page.set_viewport_size({'width': width, 'height': height})
                await page.goto(BASE + '/login', wait_until='networkidle')
                await page.evaluate("theme => {document.documentElement.classList.toggle('dark', theme === 'dark'); localStorage.setItem('theme', theme)}", theme)
                await page.evaluate('document.fonts.ready')
                await page.evaluate('window.scrollTo(0, 0)')
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, height)
                # Em janelas usuais, formulário completo sem rolar; extremos continuam navegáveis.
                if height >= 568:
                    for selector in ['#login_user', '#login_pass', '.orq-login-submit']:
                        box = await page.locator(selector).bounding_box()
                        assert box['y'] >= 0 and box['y'] + box['height'] <= height, (theme, width, height, selector, box)
                        assert box['x'] >= 0 and box['x'] + box['width'] <= width - 14, (width, selector, box)
                    if width >= 768:
                        assert await page.evaluate('document.documentElement.scrollHeight <= innerHeight'), (width, height)
                await page.screenshot(path=str(OUTPUT / f'orq-height-{theme}-{width}x{height}.png'))
                await page.locator('#login_user').fill('ORQ_TESTE')
                await page.locator('#login_pass').fill('senha-ficticia')
                await page.locator('#login_pass').evaluate("e=>e.dispatchEvent(new KeyboardEvent('keyup',{key:'CapsLock',modifierCapsLock:true,bubbles:true}))")
                await page.locator('#login_user').focus()
                for selector in ['#login_pass', '.orq-login-password-toggle', '.orq-login-submit']:
                    await page.keyboard.press('Tab')
                    assert await page.locator(selector).evaluate('e=>e===document.activeElement')
                    box = await page.locator(selector).bounding_box()
                    assert box['y'] >= 0 and box['y'] + box['height'] <= height, (width, height, selector, box)
                await page.keyboard.press('Enter')
                await page.get_by_role('alert').wait_for()
                await page.get_by_role('alert').scroll_into_view_if_needed()
                box = await page.get_by_role('alert').bounding_box()
                assert box['y'] >= 0 and box['y'] + box['height'] <= height
                await page.locator('.orq-login-submit').scroll_into_view_if_needed()
                box = await page.locator('.orq-login-submit').bounding_box()
                assert box['y'] >= 0 and box['y'] + box['height'] <= height
                results.append(f'{theme} {width}x{height}')
        print(json.dumps({'resultado': 'OK', 'viewports': results, 'teclado_erro_capslock': 'OK'}))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
