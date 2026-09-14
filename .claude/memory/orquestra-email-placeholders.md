# Seletores de placeholders — 2026-09-14
Spec aprovada: docs/spec-email-seletor-placeholders.md.
F1 implementada na branch feat/email-placeholders-f1: listas no assunto/corpo do modelo e nó, nome do anexo; descrição/exemplo e qualificador SQL informado.
QA corrigiu armadilha: data/inicio possuem barras e inviabilizam anexo; picker só oferece marcadores compatíveis e orienta odate.
Validação: pytest 5432 passed, 50 skipped, mesmas 8 falhas vs main (5427 passed); smoke com componentes reais/APIs simuladas validou seleção/cursor/foco, modelo selecionado, salvar/reabrir, claro/escuro/mobile. Revisão adversarial aprovada.
F2 pendente após merge F1: nomes SQL reais do grafo, avisos de origem e ajuda nos painéis. Execução relatada pelo usuário continua sem pipeline/run/ambiente identificados; SQL → Decisão → E-mail não transporta tabela atualmente.
TypeScript/build OK; lint 193 antes/depois, zero novos. DEV atualizado e HTML real :8090 aponta para index-CH1iHKP_.js. Deploy F1 só front, sem migration/worker. Produção pendente. Ver docs/release-notes/email-placeholders.md.
