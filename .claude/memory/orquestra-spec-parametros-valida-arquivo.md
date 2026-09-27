---
name: orquestra-spec-parametros-valida-arquivo
description: Spec consolidada de parâmetros e Valida Arquivo; requisitos funcionais fechados em 27/09/2026
type: project
---

Spec: `docs/spec-parametros-globais-valida-arquivo.md`, branch local `feat/parametros-globais-f1`, base origin/main c3f2b24 conferida em 27/09/2026. Requisitos funcionais fechados pelo usuário: histórico técnico obrigatório, notificação opcional e erro técnico sempre falha e bloqueia destinos. Não restam perguntas da entrevista; §8 registra as respostas finais. Início autorizado pelo usuário em 27/09/2026. F1 implementada e validada; [PR #455 aberto](https://github.com/carlosdev-joy/sge_app/pull/455), aguardando autorização de merge; F2–F7 pendentes. Sem merge/deploy. Migration validada somente em base temporária removida, não na base do produto.

**Why:** nó genérico de validação e parâmetros reutilizáveis, com ordem/políticas escolhidas pelo usuário e versão original preservada na retomada.

**How to apply:** ler a spec e as respostas seguintes antes de implementar. Documento de entrada v1.1 preservado no container SSH. Item futuro de frescor preparado em `sql/migrations/128_backlog_validacao_frescor_arquivo.sql` para o Backlog, ainda não aplicado; conferir numeração antes de PR. Não usar exemplos INS/UPD como semântica do produto.

Validação: `docs/validacao-parametros-globais-f1.md`; deploy e contrato: `docs/release-notes/parametros-globais-f1.md`. Build aprovado, zero regressões novas, 32 testes novos aprovados, SQL real isolado e revisão adversarial aprovados.
