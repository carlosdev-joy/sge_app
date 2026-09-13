# Identidade ORQ e login — 2026-09-13

> Ajustes consolidados conforme Notion: ver [relatório final](orq-login-validacao.md).
> O texto e as decisões abaixo registram a primeira prévia; prevalece a especificação final.

Brief fornecido pelo usuário: ORQ → posicionamento → cinco capacidades.

Descrição institucional: **Plataforma de Orquestração de Dados, Processos e Inteligência.**

- **Pipelines** — Monitore e gerencie seus pipelines de dados em tempo real.
- **Chamados** — Centralize, acompanhe e resolva solicitações.
- **Lineage** — Visualize a origem e o fluxo dos dados entre sistemas.
- **Desenvolvimento** — Crie e gerencie ETL e integrações de forma colaborativa.
- **IA** — Automatize processos e gere insights com inteligência artificial.

## Assets e tratamento

- `ui-react/public/images/orq/logo-name.png`: original `/dados/bi/logo_orq_nome.png`,
  copiado sem alteração. A composição CSS clareia só as letras no fundo escuro;
  utiliza a mesma imagem sobreposta com clip a 42%, entre o símbolo e as letras.
- `ui-react/public/images/orq/logo-orbital.png`: original `/dados/bi/logo_orq_orbital.png`,
  sem alteração, usado na variante sem nome e no favicon.
- `ui-react/public/images/orq/login-wave.png`: gerado com a ferramenta integrada
  imagegen, apenas decorativo, reservado à faixa inferior sem passar pelos textos.
- Fontes locais Montserrat e Inter, obtidas do repositório oficial google/fonts,
  com licenças OFL em `ui-react/public/fonts/`. Não exigem internet no navegador.

O login mantém a matrícula, senha, Enter, indicador de envio, aviso de Caps Lock,
mensagem de erro, persistência da sessão e destino por permissão. A marca comum
atualiza também o cabeçalho, preservando o slot de versão e o logo institucional CVP.
A hierarquia textual aparece também no celular. O formulário acompanha o tema.

## Prompt final do fundo (ferramenta integrada imagegen)

Use case: stylized-concept. Asset type: production background image for the left branding panel of ORQ enterprise login. Create a refined abstract technology wave background, portrait aspect ratio 2:3, approximately 1024x1536. Background solid very deep midnight navy (#06163f), extremely clean, matte, no noise. Upper 75% almost flat navy empty negative space, must support HTML logo and five capability descriptions added later. Only in the bottom 22%: graceful thin luminous parallel flowing lines forming an undulating mesh ribbon across the full width, bright electric blue and cyan at the left, blending electric blue and restrained violet at the right. Waves sweep horizontally, sophisticated fine-line wireframe with elegant smooth low hills. Sparse, restrained glow, crisp premium corporate visual. Dark bottom edge. Flat front view, full bleed artwork only. No text, no letters, no logo, no icons, no charts, no UI, no border, no watermark. The wave is purely decorative; no functional meaning. Match the navy/cyan/blue/violet ORQ brand reference described in the conversation.

## Validação e entrega

Build inclui `tsc -b`. Lint comparado com baseline: nenhum apontamento novo.
Revisão adversarial independente sem defeitos confirmados. Smoke Chromium com
API simulada: 320/375/768/1440px, claro/escuro, textos, ausência de overflow,
Enter, payload, loading, erro, nova tentativa, Caps Lock, sessão e redirecionamento.
A imagem de fundo fica em faixa separada para não disputar contraste com as capacidades.

Deploy: somente frontend, incluindo `dist/`, imagens e fontes locais.
Sem alteração de API, migration ou configuração. Produção depende da aprovação
visual e do fluxo de PR/merge do usuário. Nesta etapa, prévia no DEV.

Suíte completa: 5398 passed, 8 failed, 50 skipped — mesmas oito falhas do baseline, nenhuma nova. Lint: 195 apontamentos em ambas as versões.
