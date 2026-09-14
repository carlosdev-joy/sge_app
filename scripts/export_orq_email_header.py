"""Exporta o header HTML existente para proteger suas cores no modo escuro.
Não gera marca nova; captura o logo aprovado + assinatura sobre Navy.
"""
import asyncio
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width':600, 'height':208}, device_scale_factor=2)
        await page.goto((ROOT/'docs/branding/orq-email-header.html').as_uri())
        await page.wait_for_function('document.images[0].complete && document.images[0].naturalWidth > 0')
        target = ROOT/'api/services/assets/orq-email-header.png'
        await page.locator('header').screenshot(path=str(target))
        for name in ['dags/utils/assets/orq-email-header.png', 'ui-react/public/images/orq/email-header.png']:
            shutil.copyfile(target, ROOT/name)
        print('Header exportado: 1200×416 px;', target.stat().st_size, 'bytes')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
