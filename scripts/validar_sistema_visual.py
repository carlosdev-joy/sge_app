#!/usr/bin/env python3
"""Amostra EOC-F4 com Playwright instalado no ambiente de QA, sem APIs/dados reais.

Uso: python scripts/validar_sistema_visual.py --url http://127.0.0.1:5173
Evidência: diretório passado em --evidencias (fora do repo recomendado).
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def run(url, out):
    out.mkdir(parents=True, exist_ok=True)
    cases, errors, dialogs = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        for width, touch, scale in [(1440, False, 1), (1280, False, 1), (947, False, 1), (390, True, 1), (720, False, 2)]:
            # 720 CSS px a DPR2 equivale a 1440 físicos ampliados em 200%.
            for theme in ['light', 'dark']:
                for density in ['comfortable', 'compact']:
                    ctx = browser.new_context(viewport={'width': width, 'height': 900}, device_scale_factor=scale, has_touch=touch)
                    ctx.add_init_script('if(localStorage.getItem("theme")===null)localStorage.setItem("theme",'+json.dumps(theme)+');if(localStorage.getItem("orquestra-ui-density-v1")===null)localStorage.setItem("orquestra-ui-density-v1",'+json.dumps(density)+');')
                    page = ctx.new_page()
                    page.on('pageerror', lambda err: errors.append(str(err)))
                    page.on('dialog', lambda dialog: (dialogs.append(dialog.type), dialog.dismiss()))
                    page.goto(url.rstrip('/')+'/examples/sistema-visual.html')
                    expect(page.get_by_role('heading', name='Sistema visual comum', exact=True)).to_be_visible()
                    page.evaluate('document.fonts.ready')
                    metrics = page.evaluate('''() => {
                      const input=document.querySelector('input.ui-control'),button=[...document.querySelectorAll('button')].find(x=>x.textContent==='Salvar rascunho');
                      return {overflow:document.documentElement.scrollWidth>innerWidth, font: getComputedStyle(input).fontFamily, input:input.getBoundingClientRect().height, button:button.getBoundingClientRect().height, density:document.documentElement.dataset.density,
                      colorScheme:getComputedStyle(document.body).colorScheme, loadedFont:document.fonts.check('14px Inter'), coarse:matchMedia('(pointer:coarse)').matches}
                    }''')
                    expected = 44 if touch else (32 if density == 'compact' else 40)
                    assert not metrics['overflow'], metrics
                    assert metrics['colorScheme'] == theme, metrics
                    assert metrics['loadedFont'] and 'Inter' in metrics['font'], metrics
                    assert metrics['input'] >= expected and metrics['button'] >= expected, metrics
                    assert metrics['input'] <= expected+2, metrics
                    field = page.get_by_label('Responsável', exact=True)
                    assert field.get_attribute('aria-invalid') == 'true'
                    description = field.get_attribute('aria-describedby').split()
                    assert len(description) == 2 and all(page.locator('[id="'+x+'"]').count() == 1 for x in description)
                    field.focus(); page.keyboard.press('Tab')
                    focus = page.evaluate('''() => { const s=getComputedStyle(document.activeElement);return {style:s.outlineStyle,width:s.outlineWidth} }''')
                    assert focus['style'] != 'none' and float(focus['width'].replace('px','')) >= 2, focus
                    busy = page.get_by_role('button', name='Salvando rascunho', exact=True)
                    expect(busy).to_be_disabled(); assert busy.get_attribute('aria-busy') == 'true'
                    name = f'{width}-{theme}-{density}-zoom{scale*100}'
                    # Teclado, foco e nome longo nos overlays reais, sem operação no servidor.
                    trigger = page.get_by_role('button', name='Abrir confirmação', exact=True)
                    trigger.focus(); page.keyboard.press('Enter')
                    modal = page.get_by_role('dialog', name='Confirmar exclusão de', exact=False)
                    expect(modal).to_be_visible()
                    assert modal.evaluate('(x)=>x.scrollWidth<=x.clientWidth+1')
                    close = modal.get_by_role('button',name='Fechar',exact=True).bounding_box()
                    assert close['width'] >= (44 if touch else 32) and close['height'] >= (44 if touch else 32), close
                    page.keyboard.press('Escape'); expect(modal).not_to_be_visible(); expect(trigger).to_be_focused()
                    page.get_by_role('button', name='Abrir propriedades', exact=True).click()
                    sheet = page.get_by_role('dialog', name='Propriedades de', exact=False)
                    expect(sheet).to_be_visible(); assert sheet.evaluate('(x)=>x.scrollWidth<=x.clientWidth+1')
                    page.keyboard.press('Escape'); expect(sheet).not_to_be_visible()
                    page.get_by_role('button', name='Mostrar notificação', exact=True).click()
                    expect(page.get_by_role('status')).to_contain_text('Rascunho da amostra salvo')
                    page.get_by_role('button', name='Fechar notificação', exact=True).click(); expect(page.get_by_role('status')).not_to_be_visible()
                    page.get_by_label('Densidade', exact=True).select_option('compact' if density=='comfortable' else 'comfortable')
                    page.reload(); expect(page.get_by_label('Densidade', exact=True)).to_have_value('compact' if density=='comfortable' else 'comfortable')
                    page.get_by_role('button', name='Restaurar densidade', exact=True).click(); expect(page.get_by_label('Densidade', exact=True)).to_have_value('comfortable')
                    page.screenshot(path=str(out/(name+'.png')), full_page=True)
                    cases.append({'case':name,**metrics,'keyboardAndOverlays':True,'densityPersisted':True})
                    ctx.close()
        browser.close()
    assert not errors and not dialogs, {'errors':errors,'dialogs':dialogs}
    (out/'resultado.json').write_text(json.dumps({'passed':True,'cases':cases,'errors':errors,'nativeDialogs':dialogs,'zoomMethod':'720 CSS px/DPR2: reflow equivalente a 1440 físicos em 200%; não usa transform'},indent=2)+'\n')
    print(f'PASS: {len(cases)} casos; temas, densidades, toque, reflow200%, foco, overlays e persistência')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5173')
    parser.add_argument('--evidencias', type=Path, default=Path('/tmp/orquestra-sistema-visual'))
    args = parser.parse_args()
    run(args.url,args.evidencias)
