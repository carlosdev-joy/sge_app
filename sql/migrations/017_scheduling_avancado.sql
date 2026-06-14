-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 017 — Fase 4: Scheduling avançado
--   1. etl_calendario  — calendários nomeados de datas BLOQUEADAS (feriados,
--      fechamento). O DAG pula a execução quando a data atual está no calendário.
--   2. etl_blackout    — janelas de exclusão (backup, freeze de ambiente).
--      escopo NULL = global; ou project_name; ou pipeline_name.
--   3. etl_pipeline    — novos campos:
--        calendario_nome        → calendário aplicado ao pipeline
--        somente_dias_uteis     → pula sábado/domingo
--        trigger_por_dependencia→ agenda por Datasets (roda quando os
--                                 pipelines de depends_on concluírem) em vez de cron
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_calendario', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_calendario (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        calendario_nome VARCHAR(100)  NOT NULL,
        data            DATE          NOT NULL,
        descricao       NVARCHAR(200) NULL,
        created_by      VARCHAR(100)  NULL,
        created_at      DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_etl_calendario UNIQUE (calendario_nome, data)
    );
    PRINT '[OK] Tabela dbo.etl_calendario criada';
END
GO

IF OBJECT_ID('dbo.etl_blackout', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_blackout (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        inicio      DATETIME      NOT NULL,
        fim         DATETIME      NOT NULL,
        escopo      NVARCHAR(200) NULL,          -- NULL = global | project_name | pipeline_name
        motivo      NVARCHAR(300) NOT NULL,
        ativo       BIT           NOT NULL DEFAULT 1,
        criado_por  VARCHAR(100)  NULL,
        created_at  DATETIME      NOT NULL DEFAULT GETDATE(),
        encerrado_por VARCHAR(100) NULL,
        encerrado_em  DATETIME     NULL
    );
    CREATE NONCLUSTERED INDEX IX_etl_blackout_ativo ON dbo.etl_blackout (ativo, inicio, fim);
    PRINT '[OK] Tabela dbo.etl_blackout criada';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='calendario_nome')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD calendario_nome VARCHAR(100) NULL;
    PRINT '[OK] Coluna calendario_nome adicionada em dbo.etl_pipeline';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='somente_dias_uteis')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD somente_dias_uteis BIT NOT NULL DEFAULT 0;
    PRINT '[OK] Coluna somente_dias_uteis adicionada em dbo.etl_pipeline';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='trigger_por_dependencia')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD trigger_por_dependencia BIT NOT NULL DEFAULT 0;
    PRINT '[OK] Coluna trigger_por_dependencia adicionada em dbo.etl_pipeline';
END
GO

-- Calendário exemplo: feriados nacionais BR 2026 (edite/adicione pela UI)
IF NOT EXISTS (SELECT 1 FROM dbo.etl_calendario WHERE calendario_nome = 'Feriados BR')
BEGIN
    INSERT INTO dbo.etl_calendario (calendario_nome, data, descricao, created_by) VALUES
        ('Feriados BR', '2026-01-01', N'Confraternização Universal', 'migration'),
        ('Feriados BR', '2026-02-16', N'Carnaval',                   'migration'),
        ('Feriados BR', '2026-02-17', N'Carnaval',                   'migration'),
        ('Feriados BR', '2026-04-03', N'Sexta-feira Santa',          'migration'),
        ('Feriados BR', '2026-04-21', N'Tiradentes',                 'migration'),
        ('Feriados BR', '2026-05-01', N'Dia do Trabalho',            'migration'),
        ('Feriados BR', '2026-06-04', N'Corpus Christi',             'migration'),
        ('Feriados BR', '2026-09-07', N'Independência',              'migration'),
        ('Feriados BR', '2026-10-12', N'Nossa Senhora Aparecida',    'migration'),
        ('Feriados BR', '2026-11-02', N'Finados',                    'migration'),
        ('Feriados BR', '2026-11-15', N'Proclamação da República',   'migration'),
        ('Feriados BR', '2026-11-20', N'Consciência Negra',          'migration'),
        ('Feriados BR', '2026-12-25', N'Natal',                      'migration');
    PRINT '[OK] Calendário "Feriados BR" 2026 populado';
END
GO
