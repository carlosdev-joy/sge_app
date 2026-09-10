-- sql/migrations/107_job_param_datastage.sql
-- Parâmetros de execução dos jobs DataStage (spec docs/spec-parametros-job-datastage.md, F1).
--
-- Hoje o Orquestra dispara todo job DataStage SEM nenhum `-param`; a tabela
-- dbo.etl_pipeline_job_param (026) e o editor da tela são só de storedproc.
-- Esta migration abre a mesma tabela para etapas `datastage`:
--
--   1. dbo.etl_pipeline_job_param — colunas de ORIGEM e de CÁLCULO de data:
--        param_source       'fixo' | 'data_referencia' | 'data_logica' | 'data_execucao' | 'run_id'
--        param_offset_meses passo 1: deslocamento em meses (dia truncado ao último válido)
--        param_ancora       passo 2: inicio_mes | fim_mes | inicio_trimestre | fim_trimestre
--                                    | inicio_ano | fim_ano | inicio_semana | fim_semana
--        param_offset_dias  passo 3: deslocamento em dias
--        param_formato      passo 4: strftime (NULL = '%Y-%m-%d')
--      Linhas existentes (storedproc) ficam 'fixo' com o cálculo todo NULL — o
--      CHECK CK_etl_pipeline_job_param_calc garante que cálculo só existe com
--      origem de data. param_type continua VARCHAR(30): o vocabulário é por
--      job_type (SQL para storedproc; String/Integer/…/Encrypted para datastage).
--      Encrypted guarda o token Fernet (ORQUESTRA_CONN_KEY) em param_value.
--   2. sp_etl_pipeline_job_param_insert — 5 parâmetros NOVOS, todos opcionais:
--      o chamador antigo (storedproc) continua funcionando byte a byte.
--   3. dbo.etl_ds_job_log.params_json — rastro do que FOI ENVIADO ao dsjob
--      ([{name, valor, fonte, descricao, mascarado}]), gravado pelo operador (F2).
--
-- sp_etl_pipelines_pendentes_criar NÃO muda: a SP é global e o operador lê os
-- parâmetros direto da tabela em runtime (decisão da spec, §3).
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. Colunas novas em etl_pipeline_job_param
-- ═══════════════════════════════════════════════════════════════════════════
IF COL_LENGTH('dbo.etl_pipeline_job_param', 'param_source') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD param_source VARCHAR(30) NOT NULL
        CONSTRAINT DF_etl_pipeline_job_param_source DEFAULT 'fixo';
    PRINT '[OK] etl_pipeline_job_param.param_source criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job_param.param_source ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline_job_param', 'param_offset_meses') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD param_offset_meses INT NULL;
    PRINT '[OK] etl_pipeline_job_param.param_offset_meses criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job_param.param_offset_meses ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline_job_param', 'param_ancora') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD param_ancora VARCHAR(20) NULL;
    PRINT '[OK] etl_pipeline_job_param.param_ancora criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job_param.param_ancora ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline_job_param', 'param_offset_dias') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD param_offset_dias INT NULL;
    PRINT '[OK] etl_pipeline_job_param.param_offset_dias criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job_param.param_offset_dias ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline_job_param', 'param_formato') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD param_formato VARCHAR(40) NULL;
    PRINT '[OK] etl_pipeline_job_param.param_formato criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job_param.param_formato ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. CHECKs (nomeados, para as próximas migrations acharem — padrão da 064)
--    Em lote SEPARADO das colunas: o lote é compilado antes de rodar, e uma
--    coluna criada no mesmo lote ainda "não existe" para o CHECK.
-- ═══════════════════════════════════════════════════════════════════════════
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_etl_pipeline_job_param_source')
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD CONSTRAINT CK_etl_pipeline_job_param_source
        CHECK (param_source IN ('fixo', 'data_referencia', 'data_logica', 'data_execucao', 'run_id'));
    PRINT '[OK] CK_etl_pipeline_job_param_source criado';
END
ELSE
    PRINT '[SKIP] CK_etl_pipeline_job_param_source ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_etl_pipeline_job_param_ancora')
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD CONSTRAINT CK_etl_pipeline_job_param_ancora
        CHECK (param_ancora IS NULL OR param_ancora IN
               ('inicio_mes', 'fim_mes', 'inicio_trimestre', 'fim_trimestre',
                'inicio_ano', 'fim_ano', 'inicio_semana', 'fim_semana'));
    PRINT '[OK] CK_etl_pipeline_job_param_ancora criado';
END
ELSE
    PRINT '[SKIP] CK_etl_pipeline_job_param_ancora ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_etl_pipeline_job_param_faixas')
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD CONSTRAINT CK_etl_pipeline_job_param_faixas
        CHECK ((param_offset_meses IS NULL OR param_offset_meses BETWEEN -120 AND 120)
           AND (param_offset_dias  IS NULL OR param_offset_dias  BETWEEN -3660 AND 3660));
    PRINT '[OK] CK_etl_pipeline_job_param_faixas criado';
END
ELSE
    PRINT '[SKIP] CK_etl_pipeline_job_param_faixas ja existe';
GO

-- Cálculo só com origem de data: fixo/run_id (e TODO o legado storedproc)
-- ficam com meses/âncora/dias/formato NULL.
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_etl_pipeline_job_param_calc')
BEGIN
    ALTER TABLE dbo.etl_pipeline_job_param ADD CONSTRAINT CK_etl_pipeline_job_param_calc
        CHECK (param_source IN ('data_referencia', 'data_logica', 'data_execucao')
               OR (param_offset_meses IS NULL AND param_ancora IS NULL
                   AND param_offset_dias IS NULL AND param_formato IS NULL));
    PRINT '[OK] CK_etl_pipeline_job_param_calc criado';
END
ELSE
    PRINT '[SKIP] CK_etl_pipeline_job_param_calc ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. sp_etl_pipeline_job_param_insert — 5 parâmetros novos, opcionais
--    (o EXEC antigo de 6 parâmetros do storedproc segue válido)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_param_insert
    @pipeline_name      VARCHAR(200),
    @job_name           VARCHAR(200),
    @param_name         VARCHAR(128),
    @param_type         VARCHAR(30),
    @param_value        NVARCHAR(MAX) = NULL,
    @param_order        INT           = 0,
    @param_source       VARCHAR(30)   = 'fixo',
    @param_offset_meses INT           = NULL,
    @param_ancora       VARCHAR(20)   = NULL,
    @param_offset_dias  INT           = NULL,
    @param_formato      VARCHAR(40)   = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.etl_pipeline_job_param
        (pipeline_name, job_name, param_name, param_type, param_value, param_order,
         param_source, param_offset_meses, param_ancora, param_offset_dias, param_formato)
    VALUES
        (@pipeline_name, @job_name, @param_name, @param_type, @param_value, @param_order,
         ISNULL(@param_source, 'fixo'), @param_offset_meses, @param_ancora,
         @param_offset_dias, @param_formato);
END
GO
PRINT '[OK] sp_etl_pipeline_job_param_insert com origem e calculo de data';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. Rastro do que foi enviado ao dsjob (preenchido pelo operador na F2)
-- ═══════════════════════════════════════════════════════════════════════════
IF COL_LENGTH('dbo.etl_ds_job_log', 'params_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_job_log ADD params_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_ds_job_log.params_json criada';
END
ELSE
    PRINT '[SKIP] etl_ds_job_log.params_json ja existe';
GO
