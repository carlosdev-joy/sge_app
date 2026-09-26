-- sql/migrations/127_backlog_admin_reestruturacao.sql
-- Pendências da reestruturação do Admin (docs/spec-admin-reestruturacao.md) no
-- Backlog de PRODUÇÃO (Admin › Sistema › Backlog) — decisão §9.4: pendência
-- identificada vai para dbo.etl_backlog por migration, não para a memória.
-- Os itens vêm do OUT da spec e dos achados de QA/segurança das fases F1–F6.
--
--   • Idempotente (roda 2×): cada INSERT só acontece se ainda não há item com o
--     mesmo título — editar/concluir/descartar depois continua pela aba e a
--     migration nunca recria nem duplica.
--   • Sem a tabela (migration 035), não faz nada.
--   • Etapa 6c do deploy.sh.
SET NOCOUNT ON;

IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — pendências não registradas';
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'ServiceNow: url_valida aceita outro host via # ou ? e manda a senha por Basic auth')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'ServiceNow: url_valida aceita outro host via # ou ? e manda a senha por Basic auth',
                N'`api/services/servicenow.py:44-50` (`url_valida`) só confere o prefixo `https://` e se o trecho até a primeira `/` termina em `.service-now.com`. `https://evil.example#.service-now.com` ou `https://evil.example?.service-now.com` passam — e o GET autenticado leva a senha salva (Basic auth) para o host de fora.

**Pronto quando:** a validação usa `urllib.parse.urlsplit` — `scheme == "https"`, `hostname` termina em `.service-now.com`, sem `username`/`password`/`query`/`fragment` — e o valor gravado é reconstruído como `scheme://host[:port]`; teste pytest com os dois exemplos acima recusados (422) e uma instância legítima aceita.',
                N'bug', N'backend', N'P2', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Teams: /admin/test-webhook sem allowlist de host, com trecho da URL (sig) e traceback na resposta')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Teams: /admin/test-webhook sem allowlist de host, com trecho da URL (sig) e traceback na resposta',
                N'`api/routers/admin.py` — `_teams_webhook_valido` (~175) aceita qualquer https; o diagnóstico devolve e publica no card `url_usada` com os 20 últimos caracteres da URL (~1488/1508, contém o `sig`); em erro, a resposta traz `traceback.format_exc()` (~1532-1540). `api/routers/execucoes.py` (~200 e ~282) também faz `httpx.post` no webhook sem allowlist.

**Pronto quando:** `_teams_webhook_valido` só aceita `*.webhook.office.com`, `*.logic.azure.com`, `*.powerautomate.com` e `*.environment.api.powerplatform.com` (o mesmo filtro antes dos POSTs de `execucoes.py`); `url_usada` mostra só o host; a falha devolve mensagem curta (o traceback vai para o log); testes prendendo host recusado e ausência de `sig`/traceback na resposta.',
                N'debt', N'backend', N'P2', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'DAG etl_admin_manage confia em conf.requested_by para decidir se o requisitante é admin')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'DAG etl_admin_manage confia em conf.requested_by para decidir se o requisitante é admin',
                N'`dags/etl_admin_manage.py:58-65` valida `conf.requested_by` contra o banco, mas esse valor vem de quem dispara a DAG. O proxy da API já exige admin (F5 da reestruturação do Admin), porém o rerun de execução antiga via `clearTaskInstances` (`api/routers/execucoes.py` ~1132 e ~1580) reaproveita o `conf` original, e quem tem role Op no Airflow dispara a DAG direto com qualquer matrícula.

**Pronto quando:** a DAG só aceita disparo originado pela API (ex.: token/assinatura no `conf` verificável pela DAG, ou a API grava a intenção no banco e a DAG consome), ou a DAG deixa de existir e a operação vira rota da API; rerun por `clearTaskInstances` e disparo manual pelo Airflow recusados em teste.',
                N'bug', N'backend', N'P2', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'DAGs geradas ainda citam Admin > Acessos e Comunicacao > Notificacoes')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'DAGs geradas ainda citam Admin > Acessos e Comunicacao > Notificacoes',
                N'`dags/etl_dag_factory.py:1437` (e as DAGs em `dags/generated/`) mandam o operador conferir o webhook em "Admin > Acessos e Comunicacao > Notificacoes", caminho que não existe mais desde a reestruturação do Admin.

**Pronto quando:** o texto diz "Admin › Comunicação › Teams" (ASCII-safe se o log exigir), as DAGs são republicadas (Admin › Pipelines & Ambiente › Publicar DAGs) e a exceção para `etl_dag_factory.py`/`dags/generated` em `tests/test_admin_nav_registro.py::test_f4_backend_nao_cita_caminho_velho_do_admin` é removida — o teste passa sem ela.',
                N'debt', N'datastage', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Admin: RBAC por aba — esconder ou sinalizar abas que exigem acao_admin')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Admin: RBAC por aba — esconder ou sinalizar abas que exigem acao_admin',
                N'Quem tem `tela_admin` sem `acao_admin` vê todas as 23 abas do Admin e só descobre na hora de gravar, com 403 da API (OUT da `docs/spec-admin-reestruturacao.md` §2). O registro `ui-react/src/lib/adminNav.ts` (`ABAS_ADMIN`) não sabe quais abas o backend protege com `acao_admin`.

**Pronto quando:** cada entrada do registro declara a permissão que o backend exige; o sub-menu, a busca e o ⌘K escondem (ou marcam como somente leitura) as abas sem permissão; teste prende o registro contra os `require_perm` do backend; usuário só com `tela_admin` não recebe 403 navegando pelo Admin.',
                N'feature', N'frontend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Agentes: concessão de acesso em dois lugares sobrescreve a lista inteira de permissões')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Agentes: concessão de acesso em dois lugares sobrescreve a lista inteira de permissões',
                N'O acesso a um agente é concedido em Acesso › Usuários (permissões extras, `ui-react/src/components/admin/abas/UsuariosTab.tsx:95`) e em IA › Agentes › Acesso (`ui-react/src/components/admin/AgentesTab.tsx:158-173`). Os dois chamam `user_perm_set`, que SUBSTITUI a lista inteira: dois admins editando ao mesmo tempo, ou as duas telas abertas, fazem uma gravação apagar a outra.

**Pronto quando:** uma ação de acréscimo/remoção de uma permissão só (ex.: `user_perm_add`/`user_perm_remove`) substitui o `user_perm_set` nas duas telas — ou a concessão fica num lugar só com link no outro; teste de concorrência (duas gravações seguidas não perdem permissão).',
                N'debt', N'frontend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Admin: clicar em Admin na sidebar dentro de uma aba empilha entrada no histórico')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Admin: clicar em Admin na sidebar dentro de uma aba empilha entrada no histórico',
                N'Estando em `/admin/<grupo>/<aba>`, clicar "Admin" na sidebar principal (`ui-react/src/components/layout/Sidebar.tsx:83`, `NavLink` para `/admin`) empilha `/admin`, que `ui-react/src/pages/Admin.tsx` troca (replace) pela última aba — a mesma. O estado da tela é preservado, mas o histórico fica com a aba duas vezes: o primeiro Voltar do navegador parece não fazer nada.

**Pronto quando:** o clique em "Admin" estando já no Admin não cria entrada nova (ex.: redirecionamento com `replace` ou o link da sidebar apontando direto para a última aba); conferido no Chrome com o Voltar.',
                N'bug', N'frontend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Admin: chunk lazy removido por deploy cai no ErrorBoundary global com erro cru')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Admin: chunk lazy removido por deploy cai no ErrorBoundary global com erro cru',
                N'`ui-react/src/App.tsx:41` carrega o Admin com `lazy()`. Depois de um deploy, quem está com o bundle antigo aberto e clica em Admin pede um chunk que não existe mais e cai no `ErrorBoundary` global (`ui-react/src/components/ErrorBoundary.tsx`) com "Failed to fetch dynamically imported module" cru. O `AbaErrorBoundary` (`components/admin/casca/AbaErrorBoundary.tsx`) já trata isso só DENTRO da casca, por aba.

**Pronto quando:** o ErrorBoundary global reconhece falha de import dinâmico (mesma regra do `AbaErrorBoundary`) e mostra "O Orquestra foi atualizado. Recarregue a página." com botão Recarregar; bancada JS prende a detecção.',
                N'bug', N'frontend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Teams: badge Canal padrão diz não configurado mesmo com a env TEAMS_WEBHOOK_URL_CVP')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Teams: badge Canal padrão diz não configurado mesmo com a env TEAMS_WEBHOOK_URL_CVP',
                N'O card "Webhook padrão" de Comunicação › Teams (`ui-react/src/components/admin/abas/NotificacoesTab.tsx:238`) mostra "Canal padrão: não configurado" quando `teams_webhook_url` está vazio no banco, mas o envio usa o fallback da variável de ambiente `TEAMS_WEBHOOK_URL_CVP` (`api/routers/execucoes.py` ~143; `api/routers/admin.py` ~1473 no teste). O admin conclui que não há canal quando há.

**Pronto quando:** a API informa a origem do canal padrão (banco, env ou nenhum) sem expor a URL, e o badge diz "configurado pela variável de ambiente" nesse caso; teste da rota com e sem a env.',
                N'bug', N'frontend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'ServiceNow: servicenow_proxy sai em claro e aceita usuário e senha na URL')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'ServiceNow: servicenow_proxy sai em claro e aceita usuário e senha na URL',
                N'`api/services/servicenow.py:54` (`proxy_valido`) aceita `http://usuario:senha@proxy:porta`, e o valor de `servicenow_proxy` é devolvido sem máscara por `config_list` (Parâmetros avançados) e pelo `servicenow_get` da aba ServiceNow (`api/routers/admin.py` ~681).

**Pronto quando:** se o proxy corporativo usar credencial na URL, o userinfo é mascarado (`http://•••@proxy:porta`) em toda leitura (config_list, servicenow_get) e preservado na gravação quando o admin não o redigitar; caso contrário, `proxy_valido` recusa userinfo com 422. Teste prende as duas leituras.',
                N'debt', N'backend', N'P3', N'ideia', N'admin-reestruturacao', N'spec-admin-reestruturacao');

    -- PRINT não aceita subconsulta (erro 1046): conta numa variável antes.
    DECLARE @itens INT = (SELECT COUNT(*) FROM dbo.etl_backlog WHERE tags = N'admin-reestruturacao');
    PRINT CONCAT('[OK] backlog admin-reestruturacao: ', @itens, ' itens');
END
GO
