# Validação F6 — Canvas e acompanhamento

Escopo: integração da configuração revisada ao canvas e leitura da configuração original no acompanhamento. Validação local não certifica DataStage instalado na Caixa.

## Evidências

- SQL Server real em banco temporário: migrations 130–133 duas vezes; criação conjunta de grafo/configuração; CAS antigo recusado; rollback restaura os dois; troca de alvo respeita FKs; cliente antigo preserva configuração; exclusão do validador remove dependências na ordem correta. Banco temporário removido ao final. Catálogo vazio controlado no smoke; catálogo/precedência já cobertos nas fases anteriores.
- Navegador com componentes reais e API de teste: dez tipos de destino, erro que preserva preenchimento, filtro de parâmetros sem segredo, literal sobre referência, cabeçalho por formato, UUID estável ao reordenar, salvamento de política, histórico e revisão original. Teclado, 1280 claro/escuro, 390 claro e 320 escuro, sem overflow horizontal ou erro de JavaScript.
- Editor completo em fixture local: nó persistido carregado, edição e dois salvamentos com revisão retornada pelo servidor; alteração apenas de valor não abre pedido de publicação.
- Testes permanentes: plano transacional, CAS, exclusões, normalização e colação, compatibilidade do cliente antigo, proteção da rota legada e helper de publicação/rename/ordem/grafo.
- Revisão adversarial exigida pelo projeto encontrou bypass por normalização/colação e perda de acesso ao histórico após remoção; corrigidos e revistos. Segurança sem defeito confirmado restante.
- Acabamento Impeccable: detector sem achados; revisão independente **ship**, restrita às evidências visuais fornecidas. Extensão preserva componentes e tokens existentes; tile cyan-700/branco é superfície fixa de identificação nos dois temas (docs/ui-temas-cores.md, seção 4). Não houve redesign ou novo sistema visual.

Artefatos locais: `/root/orquestra-valida-f6-evidencias/` (`sql-smoke.json`, `browser.json`, `canvas.json`, capturas, logs de testes, tsc/lint/build). Fixtures de navegador não são publicadas. Resultados finais da regressão e do build são registrados no fechamento da PR.

## Pendência externa

Certificar `dsjob`, `orchadmin`, dsenv/APT e arquivos/datasets reais **somente na Caixa**, conforme decisão do usuário. Não foi conectado ambiente Caixa, executado job de negócio, enviado aviso externo, feito merge ou deploy.

## Fechamento local

Pytest final: **7094 passed, 51 skipped, mesmas 8 falhas preexistentes** (4 test_api_v2_4, 3 test_kanban_rodape_card, 1 test_smoke). Zero falha nova. TypeScript `tsc -b` e build aprovados; dist recompilada após o último ajuste de UI. ESLint: 71 achados distintos, idênticos ao baseline normalizado. Fontes sem NUL; git diff --check aprovado.
