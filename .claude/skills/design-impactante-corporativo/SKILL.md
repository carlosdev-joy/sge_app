---
name: design-impactante-corporativo
description: Orquestra o processo de design visual impactante SEM perder o tom corporativo/profissional nos projetos do usuário (Orquestra, LC Decorações, NexxaFarma e frontends de automações). Use quando o usuário pedir para criar, redesenhar, estilizar, modernizar ou "deixar bonita/impressionante" uma tela, página, dashboard, landing, admin ou seção temática (ex.: /caixa-seguro), ou quando disser "visual", "tema", "identidade", "dark mode", "UI polida", "design system", "redesign", "make it look professional/impressive", "corporate design", "branding", "styling". Aplica-se a projetos web, app e telas de automação; NÃO substitui ui-ux-pro-max nem dataviz — coordena quando e como invocá-los e aplica as regras/armadilhas específicas deste ambiente.
---

# Design impactante e corporativo

Meta: visual que impressiona na primeira olhada e continua parecendo software enterprise sério — nunca "template genérico" nem "arte que não parece produto".

## Quando usar

- Tela/página/dashboard NOVA em qualquer projeto (Orquestra, LC Decorações, NexxaFarma).
- Redesign ou "elevar o nível visual" de tela existente.
- Seção com identidade de marca própria dentro de um app (padrão /caixa-seguro: tema shadcn/Radix escopado em `.caixa-theme`).
- Qualquer entrega com gráficos, KPIs ou dashboards.
- NÃO usar para: workflows n8n sem UI, banners/slides puros (delegar direto a ui-ux-pro-max:banner-design / :slides).

## Processo

1. **Decidir a IDENTIDADE antes de escrever código.** Duas rotas possíveis:
   - **Marca institucional** (ex.: CAIXA navy/laranja): tema próprio, ESCOPADO (classe raiz tipo `.caixa-theme`), sem vazar para o resto do app.
   - **Neutro enterprise** (padrão Orquestra): usar os tokens semânticos existentes `canvas/panel/edge/ink` (claro+escuro) de `components/ui/*` — NÃO inventar paleta paralela.
   Se houver dúvida ou o usuário quiser comparar: aplicar o **padrão piloto A/B em rota separada** (como `/acompanhamento` vs `/acompanhamento-orq`) para ele avaliar ao vivo antes de escolher. A decisão de identidade é do usuário; apresente as duas versões, não escolha por ele.
2. **Gerar direções visuais** invocando `ui-ux-pro-max:ui-styling` (componentes shadcn/Radix + Tailwind, dark mode, estados) ou `ui-ux-pro-max:design` (identidade/tokens do zero). Pedir 2–3 direções, filtrar pelo critério corporativo: densidade de informação alta, hierarquia tipográfica clara, cor com propósito (status/ação), zero decoração gratuita.
3. **Gráficos/KPIs/dashboards — sem exceção:** invocar `dataviz` ANTES da primeira linha de código de chart e **RODAR o validador de paleta** (`scripts/validate_palette.js`). Precedente real: verde/vermelho REPROVADO por CVD; azul `#3E96D1` / laranja `#DB6A1E` APROVADOS. Paleta que não passou no validador não entra no PR.
4. **Dark mode obrigatório** em tela nova do Orquestra: todo token novo nasce com par claro+escuro; testar nos dois temas antes de considerar pronto.
5. **Acessibilidade como parte do design, não pós-fix:** todo `Dialog` Radix com `DialogDescription` (ou `sr-only`) — warning real já corrigido neste ambiente; contraste validado (o validador do dataviz cobre charts; para UI, conferir texto sobre superfícies dos dois temas); estados de focus visíveis em tudo que é interativo.
6. **Validar como qualquer feature:** `tsc` + `eslint` (zero erros NOVOS vs baseline do HEAD) + `build` (+ `pytest` se tocou o back). Visual passa por **revisão adversarial multi-agente antes do PR** — é ela que pega os bugs de CSS listados abaixo. PR por fase; o usuário autoriza o merge.

## Checklist

- [ ] Identidade decidida (institucional escopada vs tokens neutros) ANTES do primeiro componente
- [ ] Se comparativo: rota piloto A/B criada e usuário viu as duas versões ao vivo
- [ ] Tema institucional 100% contido na classe de escopo (nada vaza para fora de `.caixa-theme` ou equivalente)
- [ ] `ui-ux-pro-max:ui-styling`/`:design` invocado para as direções visuais (não improvisado de memória)
- [ ] Se há chart/KPI: `dataviz` consultado e `scripts/validate_palette.js` executado com paleta APROVADA
- [ ] Tokens claro+escuro definidos e tela testada nos DOIS temas
- [ ] Dialogs com `DialogDescription`/`sr-only`; focus visível; contraste conferido nos dois temas
- [ ] Sticky/overlay/animação testados na tela real (não só no componente isolado)
- [ ] `tsc` + `eslint` sem erros novos vs baseline; `build` ok; `dist/` recommitada (Orquestra)
- [ ] Revisão adversarial rodada antes de abrir o PR

## Integrações

- **ui-ux-pro-max:ui-styling** — passo 2 para telas shadcn/Radix + Tailwind (caso Orquestra/caixa-seguro e admins Next.js).
- **ui-ux-pro-max:design / :design-system** — passo 1–2 quando a identidade nasce do zero (logo, tokens três camadas, CIP).
- **ui-ux-pro-max:brand** — quando existe marca institucional com voz/consistência a respeitar (caso CAIXA).
- **dataviz** — passo 3, SEMPRE que houver gráfico, KPI, stat tile ou dashboard; inclui rodar o validador de paleta.
- **/code-review** e **verify** — passo 6, antes do PR; verify exercita a tela de verdade (os dois temas, sticky, overlay).
- **ui-ux-pro-max:banner-design / :slides** — só para peças avulsas (banner, apresentação), fora deste fluxo de produto.

## Armadilhas conhecidas deste ambiente (todas já aconteceram)

- **Regra universal vence utility por ordem no bundle:** `.caixa-theme * { border-color: ... }` ganhou de utilities Tailwind porque aparece depois no CSS final. Fix: envolver em `:where()` para zerar a especificidade — foi assim que o overlay branco foi corrigido. Regra geral: seletor universal de tema SEMPRE em `:where()`.
- **`overflow-hidden` em ancestral mata `position: sticky`** silenciosamente. Usar `overflow-clip` no ancestral quando precisar cortar conteúdo sem quebrar sticky.
- **Comentário CSS contendo `*/` interno quebra o lightningcss** no build (ex.: colar um seletor `* /` dentro de comentário). Nunca escrever `*/` dentro de comentário CSS.
- **`@keyframes` com `animation-fill-mode: both` sobrescreve `transform` inline** — animação de entrada pode congelar/anular transform aplicado via style. Preferir animar propriedade que não conflita, ou compor o transform dentro do keyframe.
- **Tema escopado + portal:** conteúdo Radix via portal renderiza FORA da árvore `.caixa-theme` — checar se o tema alcança dialogs/dropdowns portados.
- **Pip offline no Orquestra:** se a solução visual puxar dependência Python nova (ex.: geração de imagem no back), exige wheel em `api/wheels/` versionada no git — sem isso o deploy quebra.
- **`dist/` do front é commitada** no Orquestra: build local faz parte da entrega; esquecer de rebuildar = produção sem o visual novo.

## O que NÃO fazer

- NÃO duplicar conteúdo de `ui-ux-pro-max` nem de `dataviz` — esta skill decide QUANDO chamá-los e cobra as regras locais.
- NÃO escolher paleta de chart "no olho": sem `validate_palette.js` aprovando, não entra.
- NÃO criar tela nova do Orquestra só no tema claro ("depois faço o escuro" = bug em produção).
- NÃO aplicar tema institucional global quando o pedido é uma seção (escopar sempre; o app hospedeiro mantém sua identidade).
- NÃO trocar impacto por caos: gradientes, glassmorphism e animação só onde reforçam hierarquia — o público é enterprise (CAIXA, farma, ERP interno).
- NÃO mergear nada: apresentar o PR e esperar a autorização do usuário.
- NÃO pular a revisão adversarial "porque é só CSS" — foi exatamente CSS que produziu os piores bugs deste ambiente.
