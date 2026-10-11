# UX profissional do Pipeline
Data:2026-10-11 · Estado: especificação detalhada para revisão; produto não alterado.
Usuário pediu ferramenta bonita, funcional e fácil de utilizar e confirmou direção da reorganização após análise do repositório/mockups/DEV.
Base: develop df1a81caa3ef5400877bf3ab2f798011552143b2, DEV2.17.1.
Canônicos: docs/spec-ux-pipeline-profissional.md e docs/design/pipeline-experiencia.md.
Direção: cinco abas, editor principal por configuração, Montagem e Execução como abas principais, com histórico/logs dentro de Execução e visualizador operacional comum; Configuração fora do canvas; rascunhos descobertos na lista; sessão de edição contínua; estados reais e animações acessíveis.
DEV observado: QA5_A vazio; cabeçalho rascunho em Execuções com fonte publicada, formulário de governança/agenda dentro do Fluxo, orientação de editar no inspector operacional, ambiente aplicação/destino pouco distintos.
Não houve edição/publicação/disparo no DEV. Evidências F9 anteriores não são nova rodada de testes.
Elaboração da proposta autorizada; revisão do documento/protótipo precede implementação. Produção/main não autorizadas.
Próxima etapa: revisar spec, prototipar jornada com simulações identificadas e planejar fases contra develop; seguir CLAUDE.md, QA adversarial e gates vigentes. Não reabrir F1–F9 técnicos nem prometer50pipelines/IA integral.


## 2026-10-11 — protótipo autorizado e preparado
Usuário autorizou seguir com o protótipo navegável nesta conversa. Fonte em `docs/prototypes/pipeline-workspace/`, com HTML portátil, README, testes do modelo e evidências. Implementação no DEV não foi realizada. Antes de alterar o produto, obter a validação visual e adaptar a base React/.NET existente; não copiar motor, autenticação ou permissões simuladas para produção. A presença de Ana Lima e um rascunho em edição é fictícia e não demonstra lease multiusuário.


## Preservação funcional e revisão de navegação — 11/10/2026
Decisão do usuário: Montagem e Execução são abas principais. Histórico/logs integram Execução, sem uma segunda faixa de modos. O inventário dos 11 componentes, oito agendas, sessão, publicação e ações operacionais está na [matriz de preservação funcional](../../docs/matriz-paridade-pipeline.md). Essa matriz é requisito para implementação: reduzir densidade não autoriza perder campos, payloads, permissões ou funcionalidades. Integrações e campos especializados não cobertos pelo protótipo permanecem pendências explícitas.
