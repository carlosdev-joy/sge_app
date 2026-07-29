-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 062 — Supervisão de Jobs DataStage (F1: modelo de dados)
--
--   etl_ds_supervisao_job     → cadastro dos jobs supervisionados (janela de
--                               início esperada, dias da semana, vigência,
--                               canal do Teams e quais alertas ligar).
--   etl_ds_supervisao_run     → runs observados por dia (início/término).
--                               É a base histórica p/ sugerir SLA no futuro.
--   etl_ds_supervisao_evento  → alertas gerados (abortou, não executou,
--                               atraso, falha de estrutura) + o card de
--                               situação inicial da entrada em vigência.
--
-- A coleta (DAG etl_ds_supervisao_monitor) e o envio ao Teams entram nas fases
-- seguintes — esta migration só cria o modelo que o cadastro (F1) usa.
--
-- Os canais/templates do Teams NÃO são criados aqui: reusam dbo.etl_msg_grupo e
-- dbo.etl_msg_template (migrations 049/050) por referência lógica, no mesmo
-- padrão do nó de notificação do etl_dag_factory.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Cadastro ────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_job', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_job (
        id                  INT IDENTITY(1,1) NOT NULL,
        project             VARCHAR(128)  NOT NULL,   -- allowlist ^[A-Za-z0-9_.]+$
        job_name            VARCHAR(255)  NOT NULL,   -- idem
        descricao           VARCHAR(400)  NULL,
        janela_inicio       TIME(0)       NOT NULL,   -- ex.: 02:00:00
        janela_fim          TIME(0)       NOT NULL,   -- ex.: 03:00:00
        tolerancia_min      INT           NOT NULL DEFAULT 0,
        -- CSV ISO: 1=seg … 7=dom. Dias fora da lista não geram evento algum.
        dias_semana         VARCHAR(20)   NOT NULL DEFAULT '1,2,3,4,5',
        -- Nada anterior a esta data é avaliado. Ao entrar em vigência, o
        -- primeiro ciclo emite o evento SITUACAO_INICIAL p/ validação.
        vigencia_inicio     DATE          NOT NULL DEFAULT CAST(GETDATE() AS DATE),
        -- '-max' do dsjob -logsum, por job (mesmo cap de build_dsjob_command).
        max_linhas          INT           NOT NULL DEFAULT 200,
        grupo_id            INT           NULL,       -- ref. lógica a etl_msg_grupo.id
        template_id         INT           NULL,       -- ref. lógica a etl_msg_template.id
        alerta_abortou      BIT           NOT NULL DEFAULT 1,
        alerta_nao_executou BIT           NOT NULL DEFAULT 1,
        alerta_atraso       BIT           NOT NULL DEFAULT 1,
        alerta_estrutura    BIT           NOT NULL DEFAULT 1,
        -- Remoção é LÓGICA: o job sai da coleta mas o histórico continua
        -- consultável ao navegar para dias anteriores no dashboard.
        ativo               BIT           NOT NULL DEFAULT 1,
        created_by          VARCHAR(20)   NULL,       -- matrícula
        created_at          DATETIME      NOT NULL DEFAULT GETDATE(),
        updated_at          DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_ds_supervisao_job PRIMARY KEY (id),
        CONSTRAINT CK_ds_superv_max_linhas  CHECK (max_linhas BETWEEN 1 AND 2000),
        CONSTRAINT CK_ds_superv_tolerancia  CHECK (tolerancia_min BETWEEN 0 AND 1440)
    );
    CREATE UNIQUE INDEX ux_ds_superv_job
        ON dbo.etl_ds_supervisao_job (project, job_name);
    CREATE NONCLUSTERED INDEX ix_ds_superv_job_ativo
        ON dbo.etl_ds_supervisao_job (ativo, vigencia_inicio);
    PRINT '[OK] Tabela etl_ds_supervisao_job criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_job ja existe';
GO

-- ── Runs observados (base de SLA) ───────────────────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_run', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_run (
        id            INT IDENTITY(1,1) NOT NULL,
        supervisao_id INT          NOT NULL,
        data_ref      DATE         NOT NULL,   -- dia em que a janela COMEÇA
        run_inicio    DATETIME     NOT NULL,   -- normalizado em America/Sao_Paulo
        run_fim       DATETIME     NULL,       -- nulo enquanto executa
        duracao_seg   INT          NULL,
        -- ok | aborted | running | indefinido (espelha o resumo do logsum)
        resultado     VARCHAR(20)  NOT NULL,
        jobs_filhos   INT          NULL,       -- qtde de jobs da sequence no run
        coletado_em   DATETIME     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_ds_supervisao_run PRIMARY KEY (id),
        CONSTRAINT FK_ds_superv_run_job FOREIGN KEY (supervisao_id)
            REFERENCES dbo.etl_ds_supervisao_job (id)
    );
    -- O mesmo run é revisto a cada ciclo de 15 min: a chave natural garante
    -- upsert em vez de duplicata.
    CREATE UNIQUE INDEX ux_ds_superv_run
        ON dbo.etl_ds_supervisao_run (supervisao_id, run_inicio);
    CREATE NONCLUSTERED INDEX ix_ds_superv_run_data
        ON dbo.etl_ds_supervisao_run (data_ref, supervisao_id);
    PRINT '[OK] Tabela etl_ds_supervisao_run criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run ja existe';
GO

-- ── Eventos / alertas ───────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_evento', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_evento (
        id               INT IDENTITY(1,1) NOT NULL,
        supervisao_id    INT            NOT NULL,
        data_ref         DATE           NOT NULL,
        tipo             VARCHAR(20)    NOT NULL,
        -- Horário do run p/ ABORTOU (dois abortos no mesmo dia = dois eventos);
        -- string vazia p/ os demais, que são um por dia.
        chave_ocorrencia VARCHAR(64)    NOT NULL DEFAULT '',
        detalhe          NVARCHAR(1000) NULL,
        run_inicio       DATETIME       NULL,
        detectado_em     DATETIME       NOT NULL DEFAULT GETDATE(),
        -- Preenchido SÓ após o webhook responder: falha de envio deixa nulo e o
        -- ciclo seguinte tenta de novo.
        notificado_em    DATETIME       NULL,
        CONSTRAINT PK_etl_ds_supervisao_evento PRIMARY KEY (id),
        CONSTRAINT FK_ds_superv_evento_job FOREIGN KEY (supervisao_id)
            REFERENCES dbo.etl_ds_supervisao_job (id),
        CONSTRAINT CK_ds_superv_evento_tipo CHECK (tipo IN
            ('ABORTOU', 'NAO_EXECUTOU', 'ATRASO', 'ESTRUTURA', 'SITUACAO_INICIAL'))
    );
    -- Dedup: é este índice que garante 1 card por ocorrência, no mesmo espírito
    -- de UX_etl_sla_alert (migration 013).
    CREATE UNIQUE INDEX ux_ds_superv_evento
        ON dbo.etl_ds_supervisao_evento (supervisao_id, data_ref, tipo, chave_ocorrencia);
    CREATE NONCLUSTERED INDEX ix_ds_superv_evento_data
        ON dbo.etl_ds_supervisao_evento (data_ref, supervisao_id);
    -- Varredura do que ainda falta notificar (usada pela F4).
    CREATE NONCLUSTERED INDEX ix_ds_superv_evento_pendente
        ON dbo.etl_ds_supervisao_evento (notificado_em, detectado_em);
    PRINT '[OK] Tabela etl_ds_supervisao_evento criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_evento ja existe';
GO
