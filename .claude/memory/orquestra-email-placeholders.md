# Seletores e origem da tabela SQL — 2026-09-14
Spec docs/spec-email-seletor-placeholders.md aprovada. F1 mergeada com autorização na PR #415, commit 20f3ea9.
F2 implementada na branch feat/email-placeholders-f2: FluxoEditor passa arestas reais ao painel; helper filtra SQL imediatamente anteriores (id = job_name) e ignora arestas de ramo. Lista usa nomes reais; opção removida desabilitada sem reescrever o texto.
Avisos analisam assunto e corpo efetivo (modelo quando selecionado); contexto/modelo desconhecidos não são tratados como ausência comprovada. Ajuda no SQL/e-mail e manual explicam publicação, execução e limite de 50 linhas/15 colunas.
QA aprovou. Ressalva preexistente identificada: email_operator._jobs_a_montante remove log_end_/log_start_ de SQL com esses nomes. F2 avisa quando usados; correção do worker fica no backlog, sem alterar runtime nesta fase.
Validação: pytest 5433 passaram, 50 ignorados, mesmas 8 falhas vs base F1 (5432 passaram). Smoke real PropriedadesPanel com APIs simuladas passou zero/um/dois SQL, Decisão, rename, modelo, ajuda SQL, claro/escuro/mobile. Nenhum envio ou gravação real.
Produção e merge F2 pendentes. Execução vazia do usuário ainda sem pipeline/run/ambiente informado.

TypeScript/build OK, lint 193 antes/depois zero novos. Fontes alterados sem NUL; lineageIsx.ts contém 2 NUL preexistentes e é idêntico à base. DEV atualizado com index-B5XZa4q_.js; patch /tmp/email-origem-f2-dev.patch.
Smoke do bundle via DEV :8090 passou (login, tema, layout e autenticação simulada).
