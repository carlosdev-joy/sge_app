# Padrões de cores — Tema claro e escuro (UI React)

Guia para manter **legibilidade nos dois temas**. O tema alterna pela classe
`html.dark` (ver `src/lib/theme.ts`); o Tailwind usa `darkMode: 'class'`.

> Regra de ouro: **cor de paleta do Tailwind nunca entra sozinha.** Toda
> `bg-*`/`text-*`/`border-*` de paleta (green, red, amber, blue…) precisa de um
> par `dark:`. Quem troca de tema sozinho são só os **tokens semânticos** abaixo.

---

## 1. Tokens semânticos (trocam de tema automaticamente)

Definidos como variáveis CSS em `src/index.css` e expostos no Tailwind
(`tailwind.config.js`). Use-os para **superfície e texto neutro** — eles já são
seguros nos dois temas, sem precisar de `dark:`.

| Token        | Classe                | Light (rgb)     | Dark (rgb)      | Uso                          |
|--------------|-----------------------|-----------------|-----------------|------------------------------|
| `--canvas`   | `bg-canvas`           | 248 250 252     | 15 17 23        | fundo da página              |
| `--panel`    | `bg-panel`            | 255 255 255     | 26 29 39        | cards / superfícies / modais |
| `--edge`     | `border-edge`         | 226 232 240     | 42 45 58        | bordas / divisores           |
| `--ink`      | `text-ink`            | 30 41 59        | 226 232 240     | texto principal              |
| `--dim`      | `text-dim`            | 100 116 139     | 148 163 184     | texto secundário             |

Exemplos seguros: `bg-panel`, `text-ink`, `text-dim`, `border-edge`,
`bg-canvas`, `hover:bg-edge/30`.

---

## 2. Padrões canônicos por status (info / sucesso / aviso / erro)

Sempre **claro + `dark:`**. Light usa fundo `-50/-100`, texto `-700/-800`, borda
`-200/-300`; dark usa fundo `-900/xx`, texto `-300/-400`, borda `-800`.

### Caixa de destaque (callout / alerta)
```
bg-{hue}-50  border border-{hue}-200  text-{hue}-800
dark:bg-{hue}-900/20  dark:border-{hue}-800  dark:text-{hue}-300
```
Título/ícone dentro da caixa: `text-{hue}-700 dark:text-{hue}-400`.

### Badge / pílula de status
```
bg-{hue}-100 text-{hue}-700 border border-{hue}-300
dark:bg-{hue}-900/40 dark:text-{hue}-300 dark:border-{hue}-800
```

### Texto colorido inline (sem fundo próprio, sobre panel/canvas)
```
text-{hue}-700 dark:text-{hue}-400
```

| Status   | hue              |
|----------|------------------|
| info     | `blue`           |
| sucesso  | `green`          |
| aviso    | `amber`/`yellow` |
| erro     | `red`            |

---

## 3. Anti-padrões (NÃO fazer)

Estes quebram a leitura no **tema claro** (fundo claro fica pálido, texto claro
some):

- ❌ `bg-{hue}-900/20` **como classe base** (sem `dark:`) → no claro vira fundo
  pálido; combinado com texto claro fica ilegível.
- ❌ `text-{hue}-300` / `text-{hue}-200` **como classe base** (sem `dark:`) →
  texto claro sobre fundo claro.
- ❌ Misturar fundo de paleta com texto da mesma família sem par `dark:`
  (ex.: `bg-green-900/20 text-green-300`).

✅ Correto:
```html
<!-- antes (ilegível no claro) -->
<div class="bg-green-900/20 border border-green-800 text-green-300">…</div>
<!-- depois -->
<div class="bg-green-50 border border-green-200 text-green-800
            dark:bg-green-900/20 dark:border-green-800 dark:text-green-300">…</div>
```

---

## 4. Exceções — superfícies sempre escuras

Quando o **fundo é fixo escuro** (não depende do tema), texto claro é correto e
**não** precisa de `dark:`:

- Visualizador de log estilo terminal: `bg-gray-950` (ex.: `ExecucaoDetailModal`)
  → `text-gray-300`, `text-blue-300`, `text-red-400` etc. são ok.
- Cabeçalho / dropdown de perfil com gradiente azul fixo (`Header`) →
  `text-white/80`, `text-blue-200` etc. são ok.

Se o fundo é fixo claro/escuro, documente no componente para não “consertar” à toa.

---

## 5. Bons exemplos de referência (copiar destes)

- `components/ui/Badge.tsx` — todas as variantes com par light/dark completo.
- `components/ui/InfoBanner.tsx` — callout azul com tokens + `dark:`.
- `pages/Dashboard.tsx` — mapa `STATUS` (success/failed/warning/running) no padrão.
- `components/MalhaTreeModal.tsx` — chips de status (OK/WARNING/ABORTED/RUNNING).

---

## 6. Checklist de revisão (PR)

- [ ] Toda cor de paleta tem par `dark:`? (ou está sobre superfície fixa documentada)
- [ ] Caixas de status seguem o padrão da seção 2?
- [ ] Nenhum `bg-*-900/*` ou `text-*-200/300` como **classe base**?
- [ ] Testado visualmente nos **dois temas** (botão de tema no header)?

Busca rápida por possíveis regressões:
```bash
# callouts dark-only (base) — revisar caso a caso
grep -rnoE "[^:]bg-(green|red|amber|yellow|blue|orange|emerald|purple)-900" ui-react/src --include=*.tsx
# texto claro como base
grep -rnoE "[^:]text-(green|red|amber|blue|purple)-(200|300)" ui-react/src --include=*.tsx
```

---

## 7. Follow-ups de consistência (baixa severidade)

Corrigidos nesta leva os casos **ilegíveis** (texto claro sobre fundo claro):
`Logs` (caixa Resolvida + lista de erros), `PipelineModals` (pílula ativa, caixa
de inativo, origens/destinos, erro ao gerar, aviso de execução), `Autocomplete`
(item ativo), `PowerBI` (erro no banner).

Ainda há callouts **dark-only de contraste médio** (fundo `bg-*-900/10–30` com
texto `text-*-400`/`text-ink`/`text-dim`) que são legíveis, porém não seguem o
padrão claro+escuro — em `pages/Jobs.tsx`, `components/pipelines/PipelineFormModal.tsx`
e `components/pipelines/PipelineRow.tsx`. Migrar para o padrão da seção 2 quando
tocar nesses arquivos.
