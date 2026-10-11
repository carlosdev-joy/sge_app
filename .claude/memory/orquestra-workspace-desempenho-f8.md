---
name: Workspace desempenho F8
description: F8 entregue em DEV2.16.1; F9 em andamento
type: project
---
F8: carregamento sob demanda das rotas/abas e memoização do renderer após perfil CPU. Hipóteses isoladas nos commits0d54ddd e3381cf3. Baseline555af58a. Scripts da rota fria879418→239084bytesgzip; canvas50/100/300p95 65,6/99,9/113,3ms, proxy de laboratório. Pytest7326PASS8falhas conhecidas51skip; lint73/73/0NEW; buildPASS; browser7, drag20, Delete15, migrations166PASS; QA/security sem bloqueador, finishSHIP/documenter. Migration161patch2.16.1; imagem .NET F7D reutilizada por fonte idêntica. PR495 integrada em develop; DEVc71337dd1a205ba891969c7217c6c85310f02ce7/2.16.1/161migrations. Saúde/assets15PASS; migration161 reexecutada2xPASS; APIp95máximo35,7ms; browser nativo save/reload/versões publicadas intactas, nenhum diálogo Chrome e rascunho próprio descartado. F9 segue a matriz completa. Main/produção não autorizados.

Why: desempenho sem alterar autoridade, permissões, edição ou estrutura visual da referência.
How to apply: conferir SHA/saúde/smoke DEV e registro final antes de declarar entregue; não apresentar proxy como INP de campo.
