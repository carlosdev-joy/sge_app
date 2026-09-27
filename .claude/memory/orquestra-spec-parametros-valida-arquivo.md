---
name: orquestra-spec-parametros-valida-arquivo
description: Spec consolidada de parâmetros e Valida Arquivo; requisitos funcionais fechados em 27/09/2026
type: project
---

**Estado atual (fechamento local):** F1 mergeada #455; F2a–F6 abertas #456–#461. Código e QA local preparados; F7 documental preparada em `docs/parametros-valida-arquivo-f7`. Aceite operacional DataStage depende exclusivamente da Caixa. Não houve deploy nem alteração de pipeline real. As notas abaixo preservam a sequência dos marcos, não substituem este estado.

Spec: `docs/spec-parametros-globais-valida-arquivo.md`, branch local `feat/parametros-globais-f2`, base origin/main c3f2b24 conferida em 27/09/2026. Requisitos funcionais fechados pelo usuário: histórico técnico obrigatório, notificação opcional e erro técnico sempre falha e bloqueia destinos. Não restam perguntas da entrevista; §8 registra as respostas finais. Início autorizado pelo usuário em 27/09/2026. F1 mergeada no [PR #455](https://github.com/carlosdev-joy/sge_app/pull/455), commit 8cf356b, mediante autorização. Próximo passo autorizado pelo usuário: F2a implementada no wizard e prévia DS, [PR #456 aberta](https://github.com/carlosdev-joy/sge_app/pull/456), aguardando autorização de merge. F2b referências nos nós/runtime e F3–F7 permanecem na spec. Sem deploy. Migration 129 ainda depende do fluxo de implantação no ambiente de destino.

**Why:** nó genérico de validação e parâmetros reutilizáveis, com ordem/políticas escolhidas pelo usuário e versão original preservada na retomada.

**How to apply:** ler a spec e as respostas seguintes antes de implementar. Documento de entrada v1.1 preservado no container SSH. Item futuro de frescor preparado em `sql/migrations/128_backlog_validacao_frescor_arquivo.sql` para o Backlog, ainda não aplicado; conferir numeração antes de PR. Não usar exemplos INS/UPD como semântica do produto.

Validação: `docs/validacao-parametros-globais-f1.md`; deploy e contrato: `docs/release-notes/parametros-globais-f1.md`. Build aprovado, zero regressões novas, 32 testes novos aprovados, SQL real isolado e revisão adversarial aprovados.


F2a: release e smoke em docs/release-notes/parametros-globais-f2a.md; evidências em docs/validacao-parametros-globais-f2a.md. Importação real dsjob ainda não certificada: saída da versão instalada deve ser validada, sem segredos. Parser recusa formato não reconhecido e multilinha; preview é somente leitura. Não habilitar referências de nós antes de F2b.


F2b preparada em `feat/parametros-globais-f2b`, sobre F2a ainda aberta. Referências DS/Python, migration 130 e snapshot imutável cifrado antecipado de F4. Release: `docs/release-notes/parametros-globais-f2b.md`; validação: `docs/validacao-parametros-globais-f2b.md`. QA adversarial e auditoria de segurança concluídos sem defeito confirmado restante. Testes de navegador e SQL Server isolado passaram. Não certifica DataStage real; sem deploy. Migrações planejadas de F3/F4 renumeradas para 131/132.

Autorização posterior do usuário em 27/09/2026: executar toda a spec com QA/docs e sinalizar ao terminar; não parar para pedir confirmação de implementação a cada fase. Manter PRs para decisão explícita de merge. Próximas fases F3–F7 continuam obrigatórias; este marco não conclui a spec.

F2b validação final: pytest 6957 passed/51 skipped/mesmas 8 falhas; 54 direcionados aprovados; tsc, lint comparado e build final aprovados; fonte sem NUL.

F2b: [PR #457 aberta](https://github.com/carlosdev-joy/sge_app/pull/457), base `feat/parametros-globais-f2` (#456). Commit de código 66bf33d. Sem merge/deploy.


F3 implementada em `feat/valida-arquivo-f3`, código fd50581, sobre F2b #457. Migration131, configuração/revisão/CAS, prévia de impacto, avaliação de arquivo texto e contrato estrito de dataset. Criação/publicação do nó ainda desabilitada. Pytest7024 passed/51skipped/mesmas8falhas; tsc/lint/build aprovados, dist inalterado; SQL real isolado (migration2x, concorrência, FK/rollback) e SSH/SFTP real de amostra passaram. QA adversarial/segurança aprovados com ressalva operacional. Docs: release-notes/valida-arquivo-f3.md e validacao-valida-arquivo-f3.md.

Usuário confirmou: teste de datasets reais somente no ambiente Caixa. Não há acesso local para certificação de parser/integração DataStage; preparar roteiro de aplicação assistida e manter essa validação explicitamente pendente. Continuação F4–F7 autorizada sem pedir confirmação de implementação por fase. F4 iniciada em `/root/orquestra-valida-f4`.

F3: [PR #458 aberta](https://github.com/carlosdev-joy/sge_app/pull/458), base `feat/parametros-globais-f2b` (#457). Sem merge/deploy. F4 segue em desenvolvimento.

F4 implementada: migration132, snapshot de validadores/política e diagnóstico durável por tentativa. 7043 passed/51 skipped/mesmas8 falhas; SQL isolado concorrência/rollback/migration2x aprovado; tsc/lint/build aprovados, dist inalterado; QA e segurança sem defeito restante. Docs: validacao-valida-arquivo-f4.md e release-notes/valida-arquivo-f4.md. Runtime F5 e interface F6 ainda pendentes.

F4: [PR #459 aberta](https://github.com/carlosdev-joy/sge_app/pull/459), sobre F3 #458. Revisão de integração encontrou consulta herdada de F2b usando e.run_id; corrigida para execution_id conforme migration067 e smoke atualizado para esquema efetivo. Não publicar F2b sem essa correção. Migration072 já amplia execution_id para VARCHAR(250); não criar ampliação redundante.

F5 implementada em feat/valida-arquivo-f5 sobre #459: guardas pre_execute (início+executor), proveniência durável migration133, encerramento rigoroso e políticas sem movimento. Aguarde protegido usa PythonOperator, pois Airflow2.11 otimiza EmptyOperator ignorando pre_execute. Filhos de decisão recebem guarda mesmo sem controle direto. QA/security concluídos;9cenários Airflow+SQL+SFTP reais e replay parcial passaram;7078passed/51skipped/mesmas8falhas;tsc/lint/build aprovados. Docs: validacao-valida-arquivo-f5.md, release-notes/valida-arquivo-f5.md. F6/F7 ainda pendentes; DataStage real somente Caixa; sem merge/deploy.

F5: PR #460 aberta sobre #459, head a2007fa. F6 em /root/orquestra-valida-f6: canvas/configuração atômica, política e histórico; smoke SQL e navegador aprovados, revisão adversarial e visual concluídas. Referências: docs/validacao-valida-arquivo-f6.md e release-notes/valida-arquivo-f6.md. F7 em preparação; DataStage real permanece exclusivo Caixa.

F6 gate final: 7094 passed/51 skipped/mesmas8falhas; tsc/lint/build aprovados, dist atualizada. SQL e navegador/canvas aprovados. QA adversarial e segurança sem defeito confirmado restante; acabamento independente ship. Sem merge/deploy.

F6: [PR #461 aberta](https://github.com/carlosdev-joy/sge_app/pull/461), head13f01ec, sobreF5#460. F7 documental em /root/orquestra-valida-f7, branch docs/parametros-valida-arquivo-f7; manual + release Caixa + matriz operacional pendente. Revisão documental sem defeito confirmado. Não declarar aceite operacional: somente Caixa pode certificar DataStage e configurar caso real. Sem merge/deploy.

F7 gate final: documentação revisada,7094passed/51skipped/mesmas8falhas;tsc/lint/build aprovados, dist idêntica àF6; links locais válidos. Código local e documentação preparados. Aceite operacional F7 continua pendente na Caixa, incluindo parser/arquivos reais e configuração do caso inicial.
