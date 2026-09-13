---
name: orq-login-identidade
description: Identidade ORQ e login com cinco capacidades, assets originais e fundo decorativo; prévia DEV aguardando avaliação visual.
metadata:
  type: project
  modified: 2026-09-13
---

## Escopo e estado

Usuário pediu aplicar marca/logo e visual do login a partir da referência,
com descrição e cinco capacidades exatas (brief em `docs/branding/orq-login.md`).
Arquivos originais recebidos pelo SFTP: `/dados/bi/logo_orq_nome.png` e
`/dados/bi/logo_orq_orbital.png`; bytes preservados em `ui-react/public/images/orq/`.
Fundo criado pela ferramenta integrada imagegen, prompt registrado no documento.

Branch `feat/orq-login-identidade`, derivada de main após PR #405 (`678496d`).
Prévia no DEV; sem autorização de merge desta nova identidade nesta etapa.
O checkout de preparação está em `/root/orquestra-clipboard-pr`.

## Decisões

- Marca ORQ → posicionamento → Pipelines/Chamados/Lineage/Desenvolvimento/IA.
- Fundo com onda só na faixa inferior reservada, decorativo, fora dos textos.
- Nome original tem letras escuras: CSS sobrepõe o mesmo PNG clareando apenas
  as letras a partir de 42% da largura; o símbolo mantém cores originais.
- Fontes Montserrat/Inter locais com OFL; nenhum recurso externo necessário.
- Componente Logo compartilhado também atualiza header, preservando CVP e versão.
- Login, permissões, sessão e transporte de auth mantidos. Sem API/migration.

## Validação e próximo passo

Build/TypeScript e lint sem erros novos; revisão adversarial aprovada.
Smoke `scripts/smoke_orq_login.py`: API simulada, desktop/mobile em 4 larguras,
claro/escuro, Enter, loading, erro, retry, Caps Lock, sessão e destino por permissão.
Capturas `/tmp/orq-login-{light,dark}-{1440,375}.png`.
Usuário avalia a prévia visual no DEV; PR e merge seguem autorização específica.
Produção ainda não recebe esta identidade.

Suíte completa: 5398 passed, 8 failed, 50 skipped — mesmas oito falhas do baseline, nenhuma nova. Lint: 195 apontamentos em ambas as versões.
