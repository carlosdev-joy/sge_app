"""Exporta a renderização do Logo white existente para PNG compatível com e-mail.
Requer dist servido em ORQ_SMOKE_URL e Playwright. Não redesenha o asset.
"""
import asyncio
import shutil
from playwright.async_api import async_playwright
from smoke_orq_login import RAIZ, BASE

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=2)
        await page.route('**/login',lambda r:r.fulfill(path=str(RAIZ/'ui-react/dist/index.html'),content_type='text/html'))
        await page.route('**/orquestra/**',lambda r:r.fulfill(json={'versao':None}))
        await page.goto(BASE+'/login',wait_until='networkidle')
        logo=page.locator('.orq-login-logo .orq-logo-white')
        await logo.evaluate("e=>{e.style.width='180px';e.style.height='72px';e.style.position='fixed';e.style.left='0';e.style.top='0';e.style.background='rgb(var(--brand-navy))'}")
        await page.wait_for_function("Array.from(document.querySelectorAll('.orq-login-logo img')).every(i=>i.complete&&i.naturalWidth>0)")
        # PNG da composição já aprovada no login, incluindo fundo Navy para email.
        target=RAIZ/'api/services/assets/orq-email-logo.png'
        target.parent.mkdir(parents=True,exist_ok=True)
        await logo.screenshot(path=str(target))
        for relative in ['dags/utils/assets/orq-email-logo.png','ui-react/public/images/orq/email-logo.png']:
            dest=RAIZ/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,dest)
        print('Logo exportado:',target.stat().st_size,'bytes; 360×144px para exibição180×72')
        await browser.close()

if __name__=='__main__':asyncio.run(main())
