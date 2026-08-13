-- 088_chamados_servicenow.sql
-- Fundação dos chamados da engenharia (docs/spec-chamados-servicenow.md):
--   1. dbo.etl_chamado       — o espelho somente-leitura dos chamados
--   2. dbo.etl_chamado_sync  — um registro por ciclo da DAG (frescor e erro)
--   3. seeds de config em dbo.etl_app_config (servicenow_*)
--   4. recurso RBAC 'tela_chamados'
--
-- A credencial fica em servicenow_senha_enc, CIFRADA com o mesmo Fernet das
-- conexões (ORQUESTRA_CONN_KEY) — a mesma chave precisa estar no orquestra-api
-- e nos containers do Airflow, porque a DAG decifra para executar o sync.
--
-- Idempotente: IF NOT EXISTS em tabela/índice, MERGE nos seeds e no RBAC.
-- Rodar quantas vezes quiser; não sobrescreve valor já configurado.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. O espelho
-- ═══════════════════════════════════════════════════════════════════════════
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado')
BEGIN
    CREATE TABLE dbo.etl_chamado (
        id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_chamado PRIMARY KEY,
        sys_id         VARCHAR(32)   NOT NULL,   -- chave natural do ServiceNow
        numero         VARCHAR(20)   NOT NULL,   -- INC/RITM/SCTASK/CHG + dígitos
        tipo           VARCHAR(20)   NOT NULL,   -- incident · ritm · task · change
        -- NVARCHAR: título com acento/emoji já estourou VARCHAR antes (PR #161).
        -- O truncamento é explícito na DAG, com sufixo '…' — nunca silencioso.
        titulo         NVARCHAR(400) NULL,
        estado_origem  VARCHAR(60)   NULL,       -- valor cru da API (display)
        -- novo · andamento · aguardando · resolvido · outros.
        -- 'outros' é proposital: estado não mapeado APARECE em vez de sumir.
        estado_kanban  VARCHAR(20)   NOT NULL,
        prioridade     VARCHAR(20)   NULL,
        atribuido_a    NVARCHAR(120) NULL,
        grupo          NVARCHAR(120) NULL,
        aberto_em      DATETIME      NULL,
        atualizado_em  DATETIME      NULL,
        encerrado_em   DATETIME      NULL,
        ativo          BIT           NOT NULL CONSTRAINT DF_etl_chamado_ativo DEFAULT 1,
        url            NVARCHAR(500) NULL,       -- link direto no portal
        sync_em        DATETIME      NOT NULL CONSTRAINT DF_etl_chamado_sync_em DEFAULT GETDATE()
    );
    PRINT '[OK] Tabela dbo.etl_chamado criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_chamado ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_etl_chamado_sys_id'
               AND object_id = OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE UNIQUE INDEX UQ_etl_chamado_sys_id ON dbo.etl_chamado (sys_id);
    PRINT '[OK] Indice UQ_etl_chamado_sys_id criado (chave do upsert)';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_chamado_kanban'
               AND object_id = OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE INDEX IX_etl_chamado_kanban ON dbo.etl_chamado (estado_kanban, ativo);
    PRINT '[OK] Indice IX_etl_chamado_kanban criado';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_chamado_atribuido'
               AND object_id = OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE INDEX IX_etl_chamado_atribuido ON dbo.etl_chamado (atribuido_a);
    PRINT '[OK] Indice IX_etl_chamado_atribuido criado';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. O log de ciclos — a fonte do carimbo de frescor
--    Existe para separar "fila realmente vazia" de "grupo errado/credencial
--    negada": as duas mostram 0 chamados na tela, e só o log diz qual é.
-- ═══════════════════════════════════════════════════════════════════════════
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado_sync')
BEGIN
    CREATE TABLE dbo.etl_chamado_sync (
        id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_chamado_sync PRIMARY KEY,
        iniciado_em     DATETIME      NOT NULL CONSTRAINT DF_etl_chamado_sync_ini DEFAULT GETDATE(),
        terminado_em    DATETIME      NULL,
        status          VARCHAR(10)   NOT NULL,  -- OK · ERRO
        qtd_incident    INT           NULL,
        qtd_ritm        INT           NULL,
        qtd_task        INT           NULL,
        qtd_change      INT           NULL,
        qtd_desativados INT           NULL,
        erro            NVARCHAR(1000) NULL,
        disparado_por   VARCHAR(100)  NULL       -- 'schedule' ou a matrícula do Admin
    );
    PRINT '[OK] Tabela dbo.etl_chamado_sync criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_chamado_sync ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_chamado_sync_inicio'
               AND object_id = OBJECT_ID('dbo.etl_chamado_sync'))
BEGIN
    CREATE INDEX IX_etl_chamado_sync_inicio ON dbo.etl_chamado_sync (iniciado_em DESC);
    PRINT '[OK] Indice IX_etl_chamado_sync_inicio criado';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. Seeds de configuração — valores VAZIOS; a aba do Admin preenche.
--    MERGE só insere o que faltar: rodar de novo nunca apaga o que já foi
--    configurado em produção.
-- ═══════════════════════════════════════════════════════════════════════════
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_app_config')
BEGIN
    MERGE dbo.etl_app_config AS t
    USING (VALUES
        ('servicenow_url',        '', 'ServiceNow: URL da instancia (https://*.service-now.com)'),
        ('servicenow_usuario',    '', 'ServiceNow: usuario de integracao (executor do sync)'),
        ('servicenow_senha_enc',  '', 'ServiceNow: senha do executor, cifrada com ORQUESTRA_CONN_KEY'),
        ('servicenow_grupos',     '', 'ServiceNow: grupo(s) de atribuicao, separados por ;'),
        ('servicenow_habilitado', '0', 'ServiceNow: 1 liga o sync agendado, 0 desliga')
    ) AS s (k, v, d)
    ON t.config_key = s.k
    WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at)
        VALUES (s.k, s.v, s.d, 'migration-088', GETDATE());
    PRINT '[OK] Seeds servicenow_* garantidos em etl_app_config';
END
ELSE
    PRINT '[SKIP] dbo.etl_app_config ainda nao existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. RBAC da tela — sem isto a tela nova sobe invisível no menu (gotcha 6c)
-- ═══════════════════════════════════════════════════════════════════════════
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_chamados'),
        ('desenvolvedor', 'tela_chamados'),
        ('operador',      'tela_chamados')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-088');
    PRINT '[OK] Recurso tela_chamados garantido (admin/desenvolvedor/operador)';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
