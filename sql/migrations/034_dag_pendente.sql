-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 034 — Fila de ativação de DAGs recém-geradas (Gerar-DAG)
--   etl_dag_pendente persiste a intenção de "despausar + notificar" quando a
--   DAG aparecer no Airflow. Um reconciliador (loop na API, iniciado no lifespan)
--   varre a fila e conclui cada item de forma idempotente — tornando o passo
--   resiliente a restart da API (a intenção sobrevive no banco).
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_dag_pendente', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_dag_pendente (
        id             BIGINT IDENTITY(1,1) PRIMARY KEY,
        pipeline_name  NVARCHAR(200) NOT NULL,
        desired_paused BIT           NOT NULL,            -- estado-alvo no Airflow
        matricula      NVARCHAR(64)  NULL,                -- quem disparou (p/ notificar)
        status         NVARCHAR(16)  NOT NULL DEFAULT 'pendente',  -- pendente | concluido | timeout | superseded
        tentativas     INT           NOT NULL DEFAULT 0,
        criado_em      DATETIME      NOT NULL DEFAULT GETDATE(),
        atualizado_em  DATETIME      NULL,
        concluido_em   DATETIME      NULL
    );
    CREATE NONCLUSTERED INDEX IX_dag_pendente_status
        ON dbo.etl_dag_pendente (status, criado_em);
    PRINT '[OK] Tabela dbo.etl_dag_pendente criada';
END
GO
