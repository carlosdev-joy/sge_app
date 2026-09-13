# Header ORQ — implementação da especificação aprovada

Fonte: [Notion](https://app.notion.com/p/3da9f9fc3e2281d1a138d4365eabff51).
Cópia recebida em `branding/orq-header-notion-spec.md`. Baseline: `e09fc76`.
O pedido de executar a especificação final aprovada autoriza a implementação.

## Fases (um PR por fase conforme CLAUDE.md)

1. F1 — Brand e Header: Link para `/`, nome acessível, divisor institucional,
   gradiente com tokens existentes, 52 + 4 px, compactação e breadcrumb NAV.
   Inclui somente classes responsivas dos controles/perfil necessárias à composição.
2. F2 — controles: tipos/ARIA, dimensões práticas dos triggers, Escape/foco,
   feed acionável por teclado e branding no perfil, preservando contratos.
3. F3 — changelog: marca ORQ, assinatura, diálogo e botões acessíveis; regressão
   integrada. Não migrar consulta autenticada de versão para endpoint público.

## Critérios F1

- Identidades independentes CAIXA | ORQ; ORQ presente em 320/360 px.
- CAIXA visível desde 768 px, fallback PNG → SVG preservado.
- Busca visual some abaixo de 1280, título abaixo de 1024, nome abaixo de 768.
- Versão secundária oculta abaixo de 640, continua no perfil.
- Gradiente idêntico (135°, mid em 55%), header em uma linha de 56 px.
- Clique na marca preserva documento e redirecionamento padrão por RBAC.
- Título derivado exclusivamente de NAV; truncado quando faltar espaço.
- Navegação pelo menu mobile e Ctrl/Cmd+K preservadas.

## Limites e riscos

Login, Logo, assets, Sidebar/AppShell, autenticação, NAV/RBAC e backend fora do
escopo. F1 não altera comportamento dos dropdowns (F2). Sem dependências ou
migrations. Breakpoints em pixels CSS se aplicam também ao viewport reduzido
pelo zoom. Não confundir responsividade do header com overflow interno de telas.

## Validação por PR

Build TypeScript/Vite e dist versionado; ESLint comparado por ocorrência;
pytest comparado à main; smoke real em Chromium com APIs simuladas e capturas
claro/escuro em desktop, tablet e 320/360 px. Revisão adversarial obrigatória.
O smoke F1 reproduz reload anterior e verifica limites/colisões dos controles,
altura, cores do gradiente, fallback, versão numérica, menu e atalho.

## Deploy e conferência manual

Frontend dist apenas. No DEV conferir: marca volta ao início sem piscar/reload;
CAIXA | ORQ no desktop; título trunca; controles acessíveis em 320/360 px;
atalho de busca funciona mesmo com botão oculto; login mantém layout da PR407.
Produção segue o processo existente após autorização; cada merge é autorizado
pelo usuário. F2/F3 começam após merge da fase anterior.

## Evidência F1 — 2026-09-13

- Baseline e alteração: pytest 5405 passed / 50 skipped / mesmas 8 falhas.
- ESLint: 193 ocorrências em ambos, zero novas; TypeScript/Vite aprovados.
- `smoke_orq_header.py`: 20 combinações (10 larguras × 2 temas) aprovadas;
  navegação sem reload, fallback PNG→SVG, versão2.10 acima de2.9, drawer e Ctrl+K.
- Inspeção visual das capturas desktop1440 e mobile320 aprovada.
- Revisão adversarial sem defeito no código de produção; mock de config
  Utilitários corrigido após apontamento e smoke passou no build final.
- Diff confirma Login/Logo/NAV/AppShell/App intactos.
