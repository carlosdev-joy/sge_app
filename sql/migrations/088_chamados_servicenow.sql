-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 088 — Chamados da Engenharia (ServiceNow)
--
-- Espelho somente-leitura dos chamados do grupo da engenharia (incident,
-- sc_req_item, sc_task, change_request) sincronizado pela DAG
-- etl_servicenow_sync. Kanban na tela /chamados com filtros e indicadores.
--
-- Tabelas: dbo.etl_chamado (espelho), dbo.etl_chamado_sync (log de ciclos).
-- RBAC: recurso tela_chamados para admin, desenvolvedor e operador.
-- Config seeds: servicenow_url, servicenow_grupos, servicenow_usuario,
--               servicenow_senha (vazia — preenchida no Admin), servicenow_intervalo_horas.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. Tabela principal: espelho dos chamados ─────────────────────────────
IF OBJECT_ID('dbo.etl_chamado', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_chamado (
        id             INT IDENTITY(1,1) PRIMARY KEY,
        sys_id         VARCHAR(32)    NOT NULL,
        numero         VARCHAR(20)    NOT NULL,
        tipo           VARCHAR(20)    NOT NULL,  -- incident | ritm | task | change
        titulo         NVARCHAR(400)  NULL,
        estado_origem  VARCHAR(60)    NULL,       -- valor cru da API (display)
        estado_kanban  VARCHAR(20)    NOT NULL,   -- novo|andamento|aguardando|resolvido|outros
        prioridade     VARCHAR(20)    NULL,
        atribuido_a    NVARCHAR(120)  NULL,
        grupo          NVARCHAR(120)  NULL,
        aberto_em      DATETIME       NULL,
        atualizado_em  DATETIME       NULL,
        encerrado_em   DATETIME       NULL,
        ativo          BIT            NOT NULL DEFAULT 1,
        url            NVARCHAR(500)  NULL,
        sync_em        DATETIME       NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_etl_chamado_sys_id UNIQUE (sys_id)
    )
    CREATE INDEX IX_etl_chamado_kanban  ON dbo.etl_chamado (estado_kanban, ativo)
    CREATE INDEX IX_etl_chamado_atrib   ON dbo.etl_chamado (atribuido_a)
    PRINT '[088] etl_chamado criada.'
END
GO

-- ── 2. Tabela de log: um registro por ciclo da DAG ────────────────────────
IF OBJECT_ID('dbo.etl_chamado_sync', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_chamado_sync (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        iniciado_em      DATETIME      NOT NULL DEFAULT GETDATE(),
        terminado_em     DATETIME      NULL,
        status           VARCHAR(10)   NOT NULL DEFAULT 'RODANDO', -- OK | ERRO | RODANDO
        qtd_incident     INT           NULL,
        qtd_ritm         INT           NULL,
        qtd_task         INT           NULL,
        qtd_change       INT           NULL,
        qtd_desativados  INT           NULL,
        erro             NVARCHAR(1000) NULL
    )
    PRINT '[088] etl_chamado_sync criada.'
END
GO

-- ── 3. RBAC: recurso tela_chamados ───────────────────────────────────────
MERGE dbo.etl_perfil_permissao AS t
USING (VALUES
    ('admin',        'tela_chamados'),
    ('desenvolvedor','tela_chamados'),
    ('operador',     'tela_chamados')
) AS s (perfil_nome, recurso)
ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
    VALUES (s.perfil_nome, s.recurso, 'migration_088');
GO

-- ── 4. Config seeds (valores vazios — Admin preenche) ────────────────────
MERGE dbo.etl_app_config AS t
USING (VALUES
    ('servicenow_url',              '',                'URL da instância ServiceNow (ex: https://cvpsnprod.service-now.com)'),
    ('servicenow_grupos',           'TI_CVP_GERESD_ED','Nome(s) do grupo de atribuição separados por vírgula'),
    ('servicenow_usuario',          '',                'Usuário de integração ServiceNow'),
    ('servicenow_senha',            '',                'Senha do usuário de integração (cifrada)'),
    ('servicenow_intervalo_horas',  '3',               'Intervalo de sync em horas (padrão 3h — requer repause da DAG)')
) AS s (config_key, config_value, descricao)
ON t.config_key = s.config_key
WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at)
    VALUES (s.config_key, s.config_value, s.descricao, 'migration_088', GETDATE());
GO

PRINT '[088] Migration concluida.'
GO
