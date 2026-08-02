-- Migration 069 — normaliza a grafia de pipeline_name nas tabelas de etapa.
--
-- Incidente (2026-08-01): um pipeline registrado em dbo.etl_pipeline como
-- 'SEQSSDVIDA6SINISTRO' tinha 6 etapas gravadas como 'SeqSsdVida6Sinistro'
-- (grafia herdada do import da sequence .dsx) e 1 nó aguarde na grafia
-- maiúscula (gravado pelo canvas). A colação CI do SQL Server junta as duas
-- grafias em toda query; os dicionários Python da factory NÃO — resultado:
-- "pipeline sem nenhuma etapa — nada a gerar" com o canvas cheio de nós.
--
-- Esta migration alinha a grafia das tabelas-filhas à grafia OFICIAL (a da
-- linha de dbo.etl_pipeline). O código também foi corrigido para agrupar de
-- forma case-insensitive e para canonizar a grafia na gravação — a migration
-- limpa o estado que já nasceu divergente.
--
-- Idempotente: a comparação binária (COLLATE Latin1_General_BIN2) só encontra
-- linhas divergentes; na segunda execução, zero linhas casam. O DATALENGTH
-- cobre o caso de espaço à direita, que a comparação de igualdade do SQL
-- Server ignora até em colação binária (padding ANSI).
-- Sem risco de colisão de PK: a PK (pipeline_name, job_name) é CI, então as
-- grafias divergentes já ocupam a MESMA identidade lógica hoje.

-- 1) Parâmetros das etapas (filha de etl_pipeline_job — atualizar antes da mãe
--    é indiferente para a FK, que também compara CI; ordem escolhida só por
--    clareza de leitura dos PRINTs).
IF OBJECT_ID('dbo.etl_pipeline_job_param', 'U') IS NOT NULL
BEGIN
    UPDATE jp SET pipeline_name = p.pipeline_name
    FROM dbo.etl_pipeline_job_param jp
    INNER JOIN dbo.etl_pipeline p ON p.pipeline_name = jp.pipeline_name
    WHERE jp.pipeline_name COLLATE Latin1_General_BIN2
          <> p.pipeline_name COLLATE Latin1_General_BIN2
       OR DATALENGTH(jp.pipeline_name) <> DATALENGTH(p.pipeline_name);
    PRINT '[OK] etl_pipeline_job_param: ' + CAST(@@ROWCOUNT AS VARCHAR(10))
        + ' linha(s) normalizada(s)';
END
GO

-- 2) Lineage dos jobs (origens/transformações/destinos por etapa).
IF OBJECT_ID('dbo.etl_job_lineage', 'U') IS NOT NULL
BEGIN
    UPDATE jl SET pipeline_name = p.pipeline_name
    FROM dbo.etl_job_lineage jl
    INNER JOIN dbo.etl_pipeline p ON p.pipeline_name = jl.pipeline_name
    WHERE jl.pipeline_name COLLATE Latin1_General_BIN2
          <> p.pipeline_name COLLATE Latin1_General_BIN2
       OR DATALENGTH(jl.pipeline_name) <> DATALENGTH(p.pipeline_name);
    PRINT '[OK] etl_job_lineage: ' + CAST(@@ROWCOUNT AS VARCHAR(10))
        + ' linha(s) normalizada(s)';
END
GO

-- 3) As etapas em si — é esta tabela que a factory agrupa em Python.
IF OBJECT_ID('dbo.etl_pipeline_job', 'U') IS NOT NULL
BEGIN
    UPDATE j SET pipeline_name = p.pipeline_name
    FROM dbo.etl_pipeline_job j
    INNER JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name
    WHERE j.pipeline_name COLLATE Latin1_General_BIN2
          <> p.pipeline_name COLLATE Latin1_General_BIN2
       OR DATALENGTH(j.pipeline_name) <> DATALENGTH(p.pipeline_name);
    PRINT '[OK] etl_pipeline_job: ' + CAST(@@ROWCOUNT AS VARCHAR(10))
        + ' linha(s) normalizada(s)';
END
GO

-- Diagnóstico pós-migration (deve retornar VAZIO):
--   SELECT j.pipeline_name AS grafia_na_etapa, p.pipeline_name AS grafia_oficial
--   FROM dbo.etl_pipeline_job j
--   JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name
--   WHERE j.pipeline_name COLLATE Latin1_General_BIN2
--         <> p.pipeline_name COLLATE Latin1_General_BIN2
--      OR DATALENGTH(j.pipeline_name) <> DATALENGTH(p.pipeline_name);
--
-- Lembrete operacional (NÃO automatizado de propósito — é decisão humana):
-- pipelines pendentes SEM nenhuma etapa continuam pendentes para sempre e,
-- até o deploy desta correção, reprovavam qualquer run da factory. Listar:
--   SELECT p.pipeline_name, p.active, p.dag_criada
--   FROM dbo.etl_pipeline p
--   LEFT JOIN dbo.etl_pipeline_job j ON j.pipeline_name = p.pipeline_name
--   WHERE p.dag_criada = 0 AND p.active = 1
--   GROUP BY p.pipeline_name, p.active, p.dag_criada
--   HAVING COUNT(j.job_name) = 0;
-- Para cada um: inativar (active=0), excluir, ou desenhar o fluxo de verdade.
