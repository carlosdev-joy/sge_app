---
name: orquestra-spec-parametros-valida-arquivo
description: Spec consolidada de parâmetros e Valida Arquivo; requisitos funcionais fechados em 27/09/2026
type: project
---

Spec: `docs/spec-parametros-globais-valida-arquivo.md`, branch local `feat/parametros-globais-f2`, base origin/main c3f2b24 conferida em 27/09/2026. Requisitos funcionais fechados pelo usuário: histórico técnico obrigatório, notificação opcional e erro técnico sempre falha e bloqueia destinos. Não restam perguntas da entrevista; §8 registra as respostas finais. Início autorizado pelo usuário em 27/09/2026. F1 mergeada no [PR #455](https://github.com/carlosdev-joy/sge_app/pull/455), commit 8cf356b, mediante autorização. Próximo passo autorizado pelo usuário: F2a implementada no wizard e prévia DS, [PR #456 aberta](https://github.com/carlosdev-joy/sge_app/pull/456), aguardando autorização de merge. F2b referências nos nós/runtime e F3–F7 permanecem na spec. Sem deploy. Migration 129 ainda depende do fluxo de implantação no ambiente de destino.

**Why:** nó genérico de validação e parâmetros reutilizáveis, com ordem/políticas escolhidas pelo usuário e versão original preservada na retomada.

**How to apply:** ler a spec e as respostas seguintes antes de implementar. Documento de entrada v1.1 preservado no container SSH. Item futuro de frescor preparado em `sql/migrations/128_backlog_validacao_frescor_arquivo.sql` para o Backlog, ainda não aplicado; conferir numeração antes de PR. Não usar exemplos INS/UPD como semântica do produto.

Validação: `docs/validacao-parametros-globais-f1.md`; deploy e contrato: `docs/release-notes/parametros-globais-f1.md`. Build aprovado, zero regressões novas, 32 testes novos aprovados, SQL real isolado e revisão adversarial aprovados.


F2a: release e smoke em docs/release-notes/parametros-globais-f2a.md; evidências em docs/validacao-parametros-globais-f2a.md. Importação real dsjob ainda não certificada: saída da versão instalada deve ser validada, sem segredos. Parser recusa formato não reconhecido e multilinha; preview é somente leitura. Não habilitar referências de nós antes de F2b.
