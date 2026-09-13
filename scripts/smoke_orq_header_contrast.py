"""Mede cores compostas (incluindo alpha) do header; APIs simuladas."""
import asyncio
import json
import os
import re
from playwright.async_api import async_playwright
from smoke_orq_login import BASE, OUTPUT, RAIZ


def rgba(value):
    parts=[float(x) for x in re.findall(r'[\d.]+',value)]
    return parts[:3]+[parts[3] if len(parts)>3 else 1]


def over(fg,bg):
    return [fg[i]*fg[3]+bg[i]*(1-fg[3]) for i in range(3)]


def ratio(a,b):
    def lum(c):
        v=[x/255 for x in c[:3]]
        v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
        return sum(x*y for x,y in zip(v,[.2126,.7152,.0722]))
    low,high=sorted([lum(a),lum(b)])
    return round((high+.05)/(low+.05),2)


async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':850})
        await page.add_init_script('''localStorage.setItem('orquestra_token','ficticio');localStorage.setItem('orquestra-auth',JSON.stringify({state:{token:'ficticio',user:{matricula:'ORQ_TESTE',primeiro_nome:'Maria',perfil:'consulta',permissoes:['tela_chamados']}},version:0}))''')
        await page.route('**/avisos',lambda r:r.fulfill(path=str(RAIZ/'ui-react/dist/index.html'),content_type='text/html'))
        await page.route('**/orquestra/**',lambda r:r.fulfill(json={'data':[],'unread':0,'banners':[]}))
        await page.route('**/orquestra/notificacoes?*',lambda r:r.fulfill(json={'data':[],'unread':3}))
        await page.goto(BASE+'/avisos',wait_until='networkidle')
        header=page.get_by_role('banner')
        output={}
        for theme in ['light','dark']:
            await page.evaluate("t=>document.documentElement.classList.toggle('dark',t==='dark')",theme)
            styles=await header.evaluate('''h=>{
                const all=[...h.querySelectorAll('span,button,img,a')].filter(e=>e.getClientRects().length);
                return {background:getComputedStyle(h).backgroundColor,gradient:getComputedStyle(h).backgroundImage,
                    elements:all.map(e=>({tag:e.tagName,text:(e.getAttribute('aria-label')||e.getAttribute('alt')||e.textContent||'').trim().slice(0,80),
                        color:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor,
                        border:getComputedStyle(e).borderTopColor,filter:getComputedStyle(e).filter,
                        font:getComputedStyle(e).fontSize,role:e.getAttribute('aria-hidden')}))};}''')
            # Navy: cor exata. Baseline gradiente: menor contraste nos três stops.
            backgrounds=([rgba(styles['background'])] if styles['gradient']=='none' else [rgba(c) for c in re.findall(r'rgba?\([^)]+\)',styles['gradient'])])
            rows=[]
            for e in styles['elements']:
                fg=rgba(e['color']); bg=rgba(e['bg'])
                ratios=[ratio(over(fg,over(bg,b)),over(bg,b)) for b in backgrounds]
                rows.append({**e,'min_text_contrast':min(ratios),'surface_contrast':min(ratio(over(bg,b),b) for b in backgrounds)})
            states=[]
            for button in [header.get_by_role('button',name='Abrir busca global'),header.get_by_role('button',name='Alternar tema'),header.get_by_role('button',name='Notificações, 3 não lidas'),header.get_by_role('button',name='Abrir perfil de Maria')]:
                await button.hover()
                await button.evaluate("e=>Promise.all(e.getAnimations().map(a=>a.finished))")
                hover=await button.evaluate('e=>({fg:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor})')
                await page.mouse.move(0,200)
                await button.focus()
                await page.keyboard.press('Tab')
                await page.keyboard.press('Shift+Tab')
                focus=await button.evaluate('e=>({color:getComputedStyle(e).outlineColor,width:getComputedStyle(e).outlineWidth,style:getComputedStyle(e).outlineStyle})')
                states.append({'name':await button.get_attribute('aria-label'),
                    'hover':min(ratio(over(rgba(hover['fg']),over(rgba(hover['bg']),b)),over(rgba(hover['bg']),b)) for b in backgrounds),
                    'focus':min(ratio(over(rgba(focus['color']),b),b) for b in backgrounds),'outline':focus})
            output[theme]={'background':styles['background'],'gradient':styles['gradient'],'elements':rows,'states':states}
            await page.screenshot(path=str(OUTPUT/f'orq-header-navy-{theme}.png'))
        target=OUTPUT/os.environ.get('ORQ_CONTRAST_REPORT','orq-header-contrast.json')
        target.write_text(json.dumps(output,ensure_ascii=False,indent=2))
        print(str(target))
        await browser.close()


if __name__=='__main__':asyncio.run(main())
