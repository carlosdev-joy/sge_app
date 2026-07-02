-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 052 — Módulo "Cópia de Dados" (cópia de tabelas entre servidores)
--   etl_copy_job        — definição da cópia (origem/destino, mapeamento de
--                         colunas em colunas_json e SQL compilado pela API).
--   etl_copy_exec       — uma execução da cópia (DAG etl_copy_exec), com
--                         status/progresso persistidos para polling da UI.
--   etl_copy_exec_range — faixas (streams) de uma execução particionada.
--   etl_copy_catalogo   — cache da introspecção via DAG etl_copy_introspect
--                         (databases/tables/columns por connection do Airflow).
--   RBAC                — recurso tela_copia_dados p/ admin/desenvolvedor/operador.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_copy_job', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_copy_job (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        nome             NVARCHAR(200) NOT NULL,
        src_conn_id      VARCHAR(100)  NOT NULL,
        src_database     NVARCHAR(128) NOT NULL,
        src_schema       NVARCHAR(128) NOT NULL DEFAULT 'dbo',
        src_table        NVARCHAR(256) NOT NULL,
        src_filtro       NVARCHAR(MAX) NULL,       -- WHERE opcional (sem a palavra WHERE)
        dst_conn_id      VARCHAR(100)  NOT NULL,
        dst_database     NVARCHAR(128) NOT NULL,
        dst_schema       NVARCHAR(128) NOT NULL DEFAULT 'dbo',
        dst_table        NVARCHAR(256) NOT NULL,
        criar_tabela     BIT           NOT NULL DEFAULT 0,
        truncar_antes    BIT           NOT NULL DEFAULT 0,
        particao_coluna  NVARCHAR(128) NULL,
        streams          INT           NOT NULL DEFAULT 4,      -- 1..8 (validado na API)
        batch_size       INT           NOT NULL DEFAULT 50000,  -- 1000..200000
        colunas_json     NVARCHAR(MAX) NULL,       -- fonte da verdade do mapeamento
        select_sql       NVARCHAR(MAX) NULL,       -- compilado pela API ao salvar
        count_sql        NVARCHAR(MAX) NULL,       -- compilado pela API ao salvar
        dst_columns_json NVARCHAR(MAX) NULL,       -- ["col1","col2",...] ordem do SELECT
        ativo            BIT           NOT NULL DEFAULT 1,
        criado_por       NVARCHAR(64)  NULL,
        criado_em        DATETIME      NOT NULL DEFAULT GETDATE(),
        atualizado_por   NVARCHAR(64)  NULL,
        atualizado_em    DATETIME      NULL
    );
    -- Nome único apenas entre as cópias ATIVAS (índice filtrado): o soft
    -- delete (ativo=0) libera o nome para uma nova cópia.
    CREATE UNIQUE NONCLUSTERED INDEX UX_copy_job_nome
        ON dbo.etl_copy_job (nome)
        WHERE ativo = 1;
    PRINT '[OK] Tabela dbo.etl_copy_job criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_copy_job ja existe';
GO

IF OBJECT_ID('dbo.etl_copy_exec', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_copy_exec (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        copy_job_id   INT           NOT NULL,
        dag_run_id    NVARCHAR(250) NULL,
        status        NVARCHAR(16)  NOT NULL DEFAULT 'pendente',
            -- pendente | executando | cancelando | concluido | erro | cancelado
        rows_total    BIGINT        NULL,
        rows_copied   BIGINT        NOT NULL DEFAULT 0,
        streams       INT           NULL,
        engine        NVARCHAR(32)  NULL,           -- bulk_copy | fast_executemany | executemany
        erro_msg      NVARCHAR(MAX) NULL,
        matricula     NVARCHAR(64)  NULL,           -- quem disparou (p/ notificar)
        iniciado_em   DATETIME      NULL,
        concluido_em  DATETIME      NULL,
        criado_em     DATETIME      NOT NULL DEFAULT GETDATE()
    );
    CREATE NONCLUSTERED INDEX IX_copy_exec_job
        ON dbo.etl_copy_exec (copy_job_id, criado_em DESC);
    CREATE NONCLUSTERED INDEX IX_copy_exec_status
        ON dbo.etl_copy_exec (status);
    PRINT '[OK] Tabela dbo.etl_copy_exec criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_copy_exec ja existe';
GO

IF OBJECT_ID('dbo.etl_copy_exec_range', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_copy_exec_range (
        id           BIGINT IDENTITY(1,1) PRIMARY KEY,
        exec_id      BIGINT        NOT NULL,
        range_index  INT           NOT NULL,
        -- valor_ini/valor_fim NULL/NULL = faixa única;
        -- ambos NULL com range_index = -1 = faixa "coluna IS NULL".
        valor_ini    NVARCHAR(100) NULL,
        valor_fim    NVARCHAR(100) NULL,
        status       NVARCHAR(16)  NOT NULL DEFAULT 'pendente',
            -- pendente | executando | concluido | erro | cancelado
        rows_copied  BIGINT        NOT NULL DEFAULT 0,
        erro_msg     NVARCHAR(MAX) NULL,
        iniciado_em  DATETIME      NULL,
        concluido_em DATETIME      NULL
    );
    CREATE NONCLUSTERED INDEX IX_copy_exec_range_exec
        ON dbo.etl_copy_exec_range (exec_id);
    PRINT '[OK] Tabela dbo.etl_copy_exec_range criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_copy_exec_range ja existe';
GO

IF OBJECT_ID('dbo.etl_copy_catalogo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_copy_catalogo (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        conn_id       VARCHAR(100)  NOT NULL,
        database_name NVARCHAR(128) NOT NULL DEFAULT '',
        payload_tipo  NVARCHAR(16)  NOT NULL,   -- databases | tables | columns
        objeto        NVARCHAR(400) NOT NULL DEFAULT '',  -- 'schema.tabela' quando columns
        payload_json  NVARCHAR(MAX) NOT NULL,
        atualizado_em DATETIME      NOT NULL DEFAULT GETDATE()
    );
    CREATE UNIQUE NONCLUSTERED INDEX UX_copy_catalogo_chave
        ON dbo.etl_copy_catalogo (conn_id, database_name, payload_tipo, objeto);
    PRINT '[OK] Tabela dbo.etl_copy_catalogo criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_copy_catalogo ja existe';
GO

-- Recurso RBAC 'tela_copia_dados' (tela Cópia de Dados) para os perfis
-- operacionais que editam/executam. MERGE só insere o que faltar (padrão 047).
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_copia_dados'),
        ('desenvolvedor', 'tela_copia_dados'),
        ('operador',      'tela_copia_dados')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-052');
    PRINT '[OK] Recurso tela_copia_dados garantido para admin/desenvolvedor/operador';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
