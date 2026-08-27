# Dashboard UX Theme Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir o componente DshPanel para funcionar corretamente em tema claro e escuro, injetando a variável `--accent` no CSS compilado e substituindo todos os tokens CSS inválidos.

**Architecture:** Dois arquivos editados diretamente no dist compilado via Python byte-level replace. O CSS recebe a variável `--accent` nos blocos `:root` e `.dark` existentes. O JS bundle recebe um DshPanel reescrito com tokens CSS válidos e classes `dark:` para os cards.

**Tech Stack:** Python byte-level replace (único método confiável para bundle minificado), CSS custom properties, Tailwind CSS (classes já compiladas no CSS).

**Spec:** Diagnóstico UX registrado na conversa de 2026-08-22 — tokens inválidos `bg-accent`, `border-surface-3`, `bg-surface-1/2` causam invisibilidade no tema claro.

## Global Constraints

- Nunca usar Edit tool no bundle JS — falha em strings com backticks e `\n` embutidos
- Sempre usar `assert src.count(old) == 1` antes de cada replace
- Validar depth de chaves = 0 antes de gravar o componente
- Rodar QA (`docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/ -v --tb=short`) antes de considerar done
- Tokens CSS válidos no sistema: `bg-panel`, `bg-canvas`, `bg-edge`, `text-ink`, `text-dim`, `border-edge`
- Cor primária do sistema: `#1A5FA8` (usada em `qs.primary` e outros botões)
- Bundle JS: `/opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js`
- Bundle CSS: `/opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css`

---

### Task 1: Injetar `--accent` no CSS compilado

**Files:**
- Modify: `/opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css`

**Interfaces:**
- Produz: classes `.bg-accent`, `.text-accent`, `.border-accent` funcionais em claro e escuro

**Estado atual do CSS:**
```
:root{--canvas:248 250 252;--panel:255 255 255;--edge:226 232 240;--ink:30 41 59;--dim:100 116 139}
.dark{--canvas:15 17 23;--panel:26 29 39;--edge:42 45 58;--ink:226 232 240;--dim:148 163 184}
```

- [ ] **Step 1: Adicionar `--accent` ao `:root` e `.dark` + criar as 3 classes utility**

```python
css_path = '/opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css'
css = open(css_path).read()

# Injetar --accent na variável :root (cor primária claro: #1A5FA8 = 26 95 168)
old_root = ':root{--canvas:248 250 252;--panel:255 255 255;--edge:226 232 240;--ink:30 41 59;--dim:100 116 139}'
new_root = ':root{--canvas:248 250 252;--panel:255 255 255;--edge:226 232 240;--ink:30 41 59;--dim:100 116 139;--accent:26 95 168}'
assert css.count(old_root) == 1

# Injetar --accent no .dark (mesma cor, a primária do sistema é a mesma em claro e escuro)
old_dark = '.dark{--canvas:15 17 23;--panel:26 29 39;--edge:42 45 58;--ink:226 232 240;--dim:148 163 184}'
new_dark = '.dark{--canvas:15 17 23;--panel:26 29 39;--edge:42 45 58;--ink:226 232 240;--dim:148 163 184;--accent:26 95 168}'
assert css.count(old_dark) == 1

css = css.replace(old_root, new_root, 1)
css = css.replace(old_dark, new_dark, 1)

# Adicionar as classes utility ao final do CSS
utility_classes = (
    '.bg-accent{--tw-bg-opacity:1;background-color:rgb(var(--accent) / var(--tw-bg-opacity,1))}'
    '.text-accent{--tw-text-opacity:1;color:rgb(var(--accent) / var(--tw-text-opacity,1))}'
    '.border-accent{--tw-border-opacity:1;border-color:rgb(var(--accent) / var(--tw-border-opacity,1))}'
)
css = css + utility_classes

open(css_path, 'w').write(css)
print(f'CSS escrito: {len(css)} bytes')
assert '.bg-accent' in css
assert '.text-accent' in css
assert '.border-accent' in css
print('Validação OK')
```

- [ ] **Step 2: Verificar que as classes foram inseridas**

```bash
grep -c 'bg-accent\|text-accent\|border-accent' /opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css
# Esperado: 3 (uma linha por classe)
grep '--accent' /opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css
# Esperado: 3 linhas (root, dark, utility classes)
```

---

### Task 2: Reescrever DshPanel com tokens CSS válidos

**Files:**
- Modify: `/opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js`

**Interfaces:**
- Consome: as classes `.bg-accent`, `.text-accent`, `.border-accent` criadas na Task 1
- Produz: DshPanel funcionando visualmente em tema claro e escuro

**Mapeamento de substituições:**

| Antes (inválido) | Depois (válido) |
|---|---|
| `bg-accent text-white border-accent` (botão ativo) | `bg-accent text-white border-accent` ✅ (agora válido após Task 1) |
| `border-surface-3 text-dim hover:border-accent` (botão inativo) | `border-edge text-dim hover:border-accent` |
| `ring-2 ring-accent` (card selecionado) | `ring-2 ring-[#1A5FA8]` |
| `bg-purple-500/10 border-purple-500/30 text-purple-400` (card backlog) | `bg-purple-100 border-purple-300 text-purple-700 dark:bg-purple-900/30 dark:border-purple-700 dark:text-purple-300` |
| `bg-blue-500/10 border-blue-500/30 text-blue-400` (card abertas) | `bg-blue-100 border-blue-300 text-blue-700 dark:bg-blue-900/30 dark:border-blue-700 dark:text-blue-300` |
| `bg-yellow-500/10 border-yellow-500/30 text-yellow-400` (card andamento) | `bg-yellow-100 border-yellow-300 text-yellow-700 dark:bg-yellow-900/30 dark:border-yellow-700 dark:text-yellow-300` |
| `bg-orange-500/10 border-orange-500/30 text-orange-400` (card pendentes) | `bg-orange-100 border-orange-300 text-orange-700 dark:bg-orange-900/30 dark:border-orange-700 dark:text-orange-300` |
| `bg-red-500/10 border-red-500/30 text-red-400` (card sem_analista) | `bg-red-100 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300` |
| `bg-green-500/10 border-green-500/30 text-green-400` (card resolvidas) | `bg-green-100 border-green-300 text-green-700 dark:bg-green-900/30 dark:border-green-700 dark:text-green-300` |
| `bg-pink-500/10 border-pink-500/30 text-pink-400` (card vencem_hoje) | `bg-pink-100 border-pink-300 text-pink-700 dark:bg-pink-900/30 dark:border-pink-700 dark:text-pink-300` |
| `bg-rose-600/10 border-rose-600/30 text-rose-400` (card vencidas) | `bg-red-100 border-red-300 text-red-800 dark:bg-red-900/40 dark:border-red-700 dark:text-red-200` |
| `text-2xl font-bold` (número do card — herda cor inválida) | `text-2xl font-bold text-ink` |
| `rounded-lg border border-surface-3 bg-surface-2 p-4` (modal) | `rounded-lg border border-edge bg-panel p-4` |
| `rounded border border-surface-3 bg-surface-1 p-3` (item lista) | `rounded border border-edge bg-canvas p-3` |
| `hover:text-white` (botão Fechar) | `hover:text-ink` |
| `shrink-0 text-[11px] text-accent hover:underline` (link Abrir) | `shrink-0 text-[11px] text-accent hover:underline` ✅ (agora válido após Task 1) |

- [ ] **Step 1: Criar script de substituição**

```python
# /tmp/fix_dshpanel_ux.py
src = open('/opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js', 'rb').read()
print(f'Tamanho inicial: {len(src)}')

# Verificar que DshPanel existe
assert b'function DshPanel(' in src, 'DshPanel não encontrado!'

# SUBSTITUIÇÃO 1: Botão inativo — border-surface-3 → border-edge
old1 = b'border-surface-3 text-dim hover:border-accent'
new1 = b'border-edge text-dim hover:border-accent'
assert src.count(old1) == 2, f'Esperava 2, achou {src.count(old1)}'  # 2 botões (Geral + Meu painel)
src = src.replace(old1, new1)  # substitui AMBOS
print('Fix1: border-surface-3 → border-edge (2x)')

# SUBSTITUIÇÃO 2: ring-accent → ring-[#1A5FA8]
old2 = b'ring-2 ring-accent'
new2 = b'ring-2 ring-[#1A5FA8]'
assert src.count(old2) == 1
src = src.replace(old2, new2, 1)
print('Fix2: ring-accent → ring-[#1A5FA8]')

# SUBSTITUIÇÃO 3: cor do número do card (adicionar text-ink)
old3 = b'"text-2xl font-bold"'
new3 = b'"text-2xl font-bold text-ink"'
# Verificar que está no DshPanel e não em outro lugar
idx_dsh = src.find(b'function DshPanel(')
idx_vce = src.find(b'function Vce(')
count_in_dsh = src[idx_dsh:idx_vce].count(old3)
assert count_in_dsh == 1, f'text-2xl no DshPanel: {count_in_dsh}'
src = src.replace(old3, new3, 1)
print('Fix3: text-2xl font-bold → text-2xl font-bold text-ink')

# SUBSTITUIÇÃO 4: modal bg-surface-2 → bg-panel
old4 = b'"rounded-lg border border-surface-3 bg-surface-2 p-4"'
new4 = b'"rounded-lg border border-edge bg-panel p-4"'
assert src.count(old4) == 1
src = src.replace(old4, new4, 1)
print('Fix4: modal bg-surface-2 → bg-panel')

# SUBSTITUIÇÃO 5: item da lista bg-surface-1 → bg-canvas
old5 = b'"flex items-start justify-between gap-2 rounded border border-surface-3 bg-surface-1 p-3"'
new5 = b'"flex items-start justify-between gap-2 rounded border border-edge bg-canvas p-3"'
assert src.count(old5) == 1
src = src.replace(old5, new5, 1)
print('Fix5: item lista bg-surface-1 → bg-canvas')

# SUBSTITUIÇÃO 6: botão Fechar hover:text-white → hover:text-ink
old6 = b'"text-dim hover:text-white text-xs"'
new6 = b'"text-dim hover:text-ink text-xs"'
# Verificar que é apenas o botão Fechar do DshPanel
count_total = src.count(old6)
# Pode ter mais de um no bundle — precisamos só o do DshPanel
idx_dsh = src.find(b'function DshPanel(')
idx_vce = src.find(b'function Vce(')
count_in_dsh = src[idx_dsh:idx_vce].count(old6)
print(f'hover:text-white count total={count_total}, no DshPanel={count_in_dsh}')
if count_in_dsh == 1 and count_total == 1:
    src = src.replace(old6, new6, 1)
    print('Fix6: hover:text-white → hover:text-ink (botão Fechar)')
elif count_in_dsh == 1:
    # Substituir apenas na região do DshPanel
    dsh_region = src[idx_dsh:idx_vce]
    dsh_fixed = dsh_region.replace(old6, new6, 1)
    src = src[:idx_dsh] + dsh_fixed + src[idx_vce:]
    print(f'Fix6: hover:text-white → hover:text-ink (apenas DshPanel, total={count_total})')

# SUBSTITUIÇÕES 7-14: cores dos cards com dark: variants
card_fixes = [
    # (old_color, new_color)
    (b'"bg-purple-500/10 border-purple-500/30 text-purple-400"',
     b'"bg-purple-100 border-purple-300 text-purple-700 dark:bg-purple-900/30 dark:border-purple-700 dark:text-purple-300"'),
    (b'"bg-blue-500/10 border-blue-500/30 text-blue-400"',
     b'"bg-blue-100 border-blue-300 text-blue-700 dark:bg-blue-900/30 dark:border-blue-700 dark:text-blue-300"'),
    (b'"bg-yellow-500/10 border-yellow-500/30 text-yellow-400"',
     b'"bg-yellow-100 border-yellow-300 text-yellow-700 dark:bg-yellow-900/30 dark:border-yellow-700 dark:text-yellow-300"'),
    (b'"bg-orange-500/10 border-orange-500/30 text-orange-400"',
     b'"bg-orange-100 border-orange-300 text-orange-700 dark:bg-orange-900/30 dark:border-orange-700 dark:text-orange-300"'),
    (b'"bg-red-500/10 border-red-500/30 text-red-400"',
     b'"bg-red-100 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300"'),
    (b'"bg-green-500/10 border-green-500/30 text-green-400"',
     b'"bg-green-100 border-green-300 text-green-700 dark:bg-green-900/30 dark:border-green-700 dark:text-green-300"'),
    (b'"bg-pink-500/10 border-pink-500/30 text-pink-400"',
     b'"bg-pink-100 border-pink-300 text-pink-700 dark:bg-pink-900/30 dark:border-pink-700 dark:text-pink-300"'),
    (b'"bg-rose-600/10 border-rose-600/30 text-rose-400"',
     b'"bg-red-100 border-red-300 text-red-800 dark:bg-red-900/40 dark:border-red-700 dark:text-red-200"'),
]
for i, (old, new) in enumerate(card_fixes, 7):
    count = src.count(old)
    assert count == 1, f'Fix{i}: esperava 1, achou {count} para {old.decode()}'
    src = src.replace(old, new, 1)
    print(f'Fix{i}: card color atualizado')

# Validações finais
assert b'function DshPanel(' in src
assert b'function Vce(' in src
assert b'border-surface-3' not in src[src.find(b'function DshPanel('):src.find(b'function Vce(')]
assert b'bg-surface' not in src[src.find(b'function DshPanel('):src.find(b'function Vce(')]
print(f'\nTamanho final: {len(src)} bytes')
print('Todas as validações passaram.')
open('/opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js', 'wb').write(src)
print('Bundle gravado.')
```

- [ ] **Step 2: Executar o script**

```bash
python3 /tmp/fix_dshpanel_ux.py
```

Esperado: 14 fixes aplicados, sem assertion errors, bundle gravado.

- [ ] **Step 3: Verificar que nenhum token inválido restou no DshPanel**

```python
src = open('/opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js', 'rb').read()
idx_start = src.find(b'function DshPanel(')
idx_end = src.find(b'function Vce(')
dsh = src[idx_start:idx_end]

for bad in [b'bg-surface', b'border-surface', b'ring-accent', b'hover:text-white']:
    found = bad in dsh
    status = 'PROBLEMA' if found else 'OK'
    print(f'{status}: {bad.decode()}')
```

Todos devem imprimir `OK`.

---

### Task 3: Verificar dark: classes no CSS compilado

As classes `dark:bg-purple-900/30`, `dark:border-purple-700` etc. precisam existir no CSS para funcionar. Tailwind com JIT compila apenas classes usadas no source — como editamos o bundle compilado, essas classes podem não existir.

- [ ] **Step 1: Checar quais classes dark: dos cards já existem no CSS**

```python
css = open('/opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css').read()
needed = [
    'dark\\:bg-purple-900\\/30', 'dark\\:border-purple-700', 'dark\\:text-purple-300',
    'dark\\:bg-blue-900\\/30', 'dark\\:border-blue-700', 'dark\\:text-blue-300',
    'dark\\:bg-yellow-900\\/30', 'dark\\:border-yellow-700', 'dark\\:text-yellow-300',
    'dark\\:bg-orange-900\\/30', 'dark\\:border-orange-700', 'dark\\:text-orange-300',
    'dark\\:bg-red-900\\/30', 'dark\\:border-red-700', 'dark\\:text-red-300',
    'dark\\:bg-green-900\\/30', 'dark\\:border-green-700', 'dark\\:text-green-300',
    'dark\\:bg-pink-900\\/30', 'dark\\:border-pink-700', 'dark\\:text-pink-300',
    'dark\\:bg-red-900\\/40', 'dark\\:text-red-200',
    'bg-purple-100', 'bg-blue-100', 'bg-yellow-100', 'bg-orange-100',
    'bg-red-100', 'bg-green-100', 'bg-pink-100',
    'border-purple-300', 'border-blue-300', 'border-yellow-300',
    'text-purple-700', 'text-blue-700', 'text-yellow-700',
]
missing = [c for c in needed if c.replace('\\', '') not in css]
print(f'Missing ({len(missing)}):')
for m in missing:
    print(f'  {m}')
```

- [ ] **Step 2: Injetar as classes ausentes no CSS**

Para cada classe ausente, adicionar a regra CSS correspondente ao final do arquivo. Use o script abaixo que gera apenas as que faltam:

```python
css_path = '/opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css'
css = open(css_path).read()

# Mapa completo: classe → regra CSS
# Convenção Tailwind: .dark\:bg-purple-900\/30 { dentro .dark }
extra_rules = []

# Classes base (tema claro) — sem .dark prefix
base_classes = {
    'bg-purple-100': 'background-color:rgb(243 232 255)',
    'bg-blue-100': 'background-color:rgb(219 234 254)',
    'bg-yellow-100': 'background-color:rgb(254 249 195)',
    'bg-orange-100': 'background-color:rgb(255 237 213)',
    'bg-red-100': 'background-color:rgb(254 226 226)',
    'bg-green-100': 'background-color:rgb(220 252 231)',
    'bg-pink-100': 'background-color:rgb(252 231 243)',
    'border-purple-300': 'border-color:rgb(216 180 254)',
    'border-blue-300': 'border-color:rgb(147 197 253)',
    'border-yellow-300': 'border-color:rgb(253 224 71)',
    'border-orange-300': 'border-color:rgb(253 186 116)',
    'border-red-300': 'border-color:rgb(252 165 165)',
    'border-green-300': 'border-color:rgb(134 239 172)',
    'border-pink-300': 'border-color:rgb(249 168 212)',
    'text-purple-700': 'color:rgb(126 34 206)',
    'text-blue-700': 'color:rgb(29 78 216)',
    'text-yellow-700': 'color:rgb(161 98 7)',
    'text-orange-700': 'color:rgb(194 65 12)',
    'text-red-700': 'color:rgb(185 28 28)',
    'text-red-800': 'color:rgb(153 27 27)',
    'text-green-700': 'color:rgb(21 128 61)',
    'text-pink-700': 'color:rgb(190 24 93)',
}

# Classes dark: — precisam do seletor .dark
dark_classes = {
    'dark\\:bg-purple-900\\/30': 'background-color:rgb(88 28 135 / 0.3)',
    'dark\\:bg-blue-900\\/30': 'background-color:rgb(30 58 138 / 0.3)',
    'dark\\:bg-yellow-900\\/30': 'background-color:rgb(113 63 18 / 0.3)',
    'dark\\:bg-orange-900\\/30': 'background-color:rgb(124 45 18 / 0.3)',
    'dark\\:bg-red-900\\/30': 'background-color:rgb(127 29 29 / 0.3)',
    'dark\\:bg-red-900\\/40': 'background-color:rgb(127 29 29 / 0.4)',
    'dark\\:bg-green-900\\/30': 'background-color:rgb(20 83 45 / 0.3)',
    'dark\\:bg-pink-900\\/30': 'background-color:rgb(131 24 67 / 0.3)',
    'dark\\:border-purple-700': 'border-color:rgb(126 34 206)',
    'dark\\:border-blue-700': 'border-color:rgb(29 78 216)',
    'dark\\:border-yellow-700': 'border-color:rgb(161 98 7)',
    'dark\\:border-orange-700': 'border-color:rgb(194 65 12)',
    'dark\\:border-red-700': 'border-color:rgb(185 28 28)',
    'dark\\:border-green-700': 'border-color:rgb(21 128 61)',
    'dark\\:border-pink-700': 'border-color:rgb(190 24 93)',
    'dark\\:text-purple-300': 'color:rgb(216 180 254)',
    'dark\\:text-blue-300': 'color:rgb(147 197 253)',
    'dark\\:text-yellow-300': 'color:rgb(253 224 71)',
    'dark\\:text-orange-300': 'color:rgb(253 186 116)',
    'dark\\:text-red-300': 'color:rgb(252 165 165)',
    'dark\\:text-red-200': 'color:rgb(254 202 202)',
    'dark\\:text-green-300': 'color:rgb(134 239 172)',
    'dark\\:text-pink-300': 'color:rgb(249 168 212)',
}

injected = []

for cls, rule in base_classes.items():
    if cls not in css:
        extra_rules.append(f'.{cls}{{{rule}}}')
        injected.append(cls)

for cls, rule in dark_classes.items():
    clean = cls.replace('\\', '')
    if clean not in css:
        extra_rules.append(f'.dark .{cls}{{{rule}}}')
        injected.append(cls)

if extra_rules:
    css = css + ''.join(extra_rules)
    open(css_path, 'w').write(css)
    print(f'Injetadas {len(extra_rules)} regras CSS')
    for r in injected:
        print(f'  + {r}')
else:
    print('Nenhuma regra ausente — todas já existiam')
```

- [ ] **Step 3: Verificar resultado**

```bash
grep -c 'bg-purple-100\|bg-blue-100\|dark.*bg-purple-900' /opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css
# Esperado: >= 2
```

---

### Task 4: QA e validação final

**Files:**
- Nenhum arquivo modificado nesta task

- [ ] **Step 1: Rodar a suite de testes**

```bash
docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/ -v --tb=short
```

Esperado: `48 passed`. Qualquer falha = não fazer deploy, investigar.

- [ ] **Step 2: Verificar tamanho do bundle (sanidade)**

```bash
ls -la /opt/airflow/ui-react/dist/assets/index-CeXrH6tU.js
ls -la /opt/airflow/ui-react/dist/assets/index-D0O5JlCD.css
```

O bundle JS deve estar entre 2.800.000 e 2.820.000 bytes. O CSS deve estar maior que antes (classes injetadas).

- [ ] **Step 3: Confirmar no browser — tema claro**

1. Abrir `http://localhost:8090` (ou endereço do Orquestra)
2. Ativar tema claro (se não for o padrão)
3. Ir em Chamados → aba Dashboard
4. Verificar: botão "Geral" visível com fundo azul
5. Verificar: botão "Meu painel" visível com borda e texto cinza
6. Verificar: 8 cards com cores distintas e legíveis
7. Clicar em um card → modal abre com fundo branco, texto legível

- [ ] **Step 4: Confirmar no browser — tema escuro**

1. Ativar tema escuro
2. Repetir verificações do Step 3
3. Verificar: cards têm fundo escuro translúcido com borda colorida
