-- sql/migrations/108_pipeline_param.sql
-- Parâmetros DataStage no NÍVEL DO PIPELINE (spec docs/spec-parametros-job-datastage.md, F4).
--
-- Um Parameter Set vale para todos os jobs; aqui o pipeline guarda os DEFAULTS
-- (mesmo vocabulário da etapa: tipo DataStage, origem, cálculo de data,
-- Encrypted cifrado) e o operador os aplica SÓ às etapas cujo job DECLARA o
-- parâmetro (conferido no `dsjob -lparams`); a etapa sobrepõe por nome.
--
--   dbo.etl_pipeline_param — um por (pipeline_name, param_name); FK para
--   dbo.etl_pipeline (PK_etl_pipeline) com ON DELETE CASCADE, como a
--   etl_pipeline_job_param (026): apagar o pipeline apaga os defaults.
--   (200 x 2 + 128 = 528 bytes de chave, dentro do teto.)
--
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_pipeline_param', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_pipeline_param (
        id                 INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_param PRIMARY KEY,
        pipeline_name      NVARCHAR(200) NOT NULL,
        -- COLLATE binário: o DataStage distingue pData de pdata (spec §4, regra 7)
        -- e a API valida duplicata por caixa EXATA — com a colação CI do banco o
        -- UNIQUE abaixo recusaria o par como duplicata e viraria 500.
        param_name         VARCHAR(128)  COLLATE Latin1_General_BIN2 NOT NULL,
        param_type         VARCHAR(30)   NOT NULL,       -- vocabulário DataStage (String, Integer, …, Encrypted)
        param_value        NVARCHAR(MAX) NULL,           -- Encrypted: token Fernet (ORQUESTRA_CONN_KEY)
        param_source       VARCHAR(30)   NOT NULL CONSTRAINT DF_etl_pipeline_param_source DEFAULT 'fixo',
        param_offset_meses INT           NULL,
        param_ancora       VARCHAR(20)   NULL,
        param_offset_dias  INT           NULL,
        param_formato      VARCHAR(40)   NULL,
        param_order        INT           NOT NULL CONSTRAINT DF_etl_pipeline_param_order DEFAULT 0,
        created_at         DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_pipeline_param_em DEFAULT GETDATE(),
        CONSTRAINT UQ_etl_pipeline_param UNIQUE (pipeline_name, param_name),
        CONSTRAINT FK_etl_pipeline_param_pipeline FOREIGN KEY (pipeline_name)
            REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE,
        CONSTRAINT CK_etl_pipeline_param_source
            CHECK (param_source IN ('fixo', 'data_referencia', 'data_logica', 'data_execucao', 'run_id')),
        CONSTRAINT CK_etl_pipeline_param_ancora
            CHECK (param_ancora IS NULL OR param_ancora IN
                   ('inicio_mes', 'fim_mes', 'inicio_trimestre', 'fim_trimestre',
                    'inicio_ano', 'fim_ano', 'inicio_semana', 'fim_semana')),
        CONSTRAINT CK_etl_pipeline_param_faixas
            CHECK ((param_offset_meses IS NULL OR param_offset_meses BETWEEN -120 AND 120)
               AND (param_offset_dias  IS NULL OR param_offset_dias  BETWEEN -3660 AND 3660)),
        -- cálculo só com origem de data (mesma regra da 107)
        CONSTRAINT CK_etl_pipeline_param_calc
            CHECK (param_source IN ('data_referencia', 'data_logica', 'data_execucao')
                   OR (param_offset_meses IS NULL AND param_ancora IS NULL
                       AND param_offset_dias IS NULL AND param_formato IS NULL))
    );
    PRINT '[OK] Tabela dbo.etl_pipeline_param criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_pipeline_param ja existe';
GO
