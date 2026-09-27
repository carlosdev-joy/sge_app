# Validação da F1 — 27/09/2026

Base: origin/main `c3f2b24`. Branch: `feat/parametros-globais-f1`.

| Verificação | Resultado |
|---|---|
| Pytest baseline | 6.855 aprovados, 8 falhas, 51 ignorados |
| Pytest fase | 6.888 aprovados, mesmas 8 falhas, 51 ignorados |
| Testes novos do catálogo (execução final isolada) | 32 aprovados, incluindo último caso 503 sem tabela |
| TypeScript / build | Build com `tsc -b` e Vite aprovado |
| ESLint por arquivo/regra/primeira linha/severidade | Mesmos 168 erros e 12 avisos preexistentes; zero novos |
| Migration 129 no SQL Server DEV isolado | Aplicada duas vezes; dados e destino preservados |
| Migration 128 no SQL Server DEV isolado | Aplicada duas vezes; somente um item de backlog |
| Runtime em schema108 e129 com driver real | Fallback de coluna ausente e filtro ORQ aprovados |
| CHECK destino no SQL Server | Valor inválido recusado |
| Limpeza da bancada SQL | Base temporária removida |
| Revisão adversarial delegada | Aprovada após correções |

As oito falhas herdadas são quatro em `test_api_v2_4.py`, três em `test_kanban_rodape_card.py` e uma em `test_smoke.py`. Primeira execução da fase também oscilou em quatro testes de frescor que capturam o relógio na coleta; execução isolada e repetição completa passaram. O dublê do teste de migration107 foi corrigido para simular ausência da coluna apenas na tabela da etapa, preservando as asserções; erro inesperado de schema do catálogo continua bloqueante.

Revisão adversarial encontrou e confirmou correção de: fallback destrutivo em schema129 parcial e mensagem de erro ilegível no formulário v1. A revisão final e o smoke SQL fecharam as ressalvas de idempotência e mensagens reais do driver.

Segurança exercitada: edição sem permissão retorna403 antes do banco; máscara de Encrypted, preservação de token, isolamento de parâmetros ORQ, SQL parametrizado, tipos/limites de metadados, rollback e recusa de esquema parcial. Não foram adicionadas dependências nem alterados componentes de frontend. O build da interface permaneceu idêntico ao versionado.

Limites: API verificada por TestClient com dublê estatal; serviço SQL e runtime verificados com banco temporário real. Nenhum dsjob real foi disparado, nenhuma migration foi aplicada à base do produto e nenhum deploy foi feito. Importação SSH, nó visual, snapshots e políticas de arquivo pertencem às fases seguintes. Roteiro do operador em `release-notes/parametros-globais-f1.md`.

Evidências da sessão: `/root/orquestra-parametros-evidencias/` (logs de baseline/fase, lint-comparison.json, sql-smoke.json). Não incluem credenciais de conexão nem dados reais de pipelines.
