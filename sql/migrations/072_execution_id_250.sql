-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 072 — etl_pipeline_execucao.execution_id: VARCHAR(50) → VARCHAR(250)
--
-- ACHADO (análise da retomada F2, docs/retomada-f2-desenho.md §8): o run_id do
-- Airflow tem até 250 chars e a coluna nasceu com 50 na migration 067.
--   • `dataset_triggered__<iso com microssegundos>` = 51 chars — e o modo
--     Dataset está ATIVO em produção como contorno recomendado;
--   • o futuro `dep__<pai até 200>__<data>` da F3 chega a ~217 chars.
-- Com VARCHAR(50), o INSERT da F2 estoura "string would be truncated", cai no
-- except de degradação do registro e vira um BURACO SISTEMÁTICO E SILENCIOSO
-- exatamente nos runs disparados por dependência. Truncar no código ([:50])
-- colidiria prefixos no índice único — inaceitável.
--
-- O índice ux_pipe_exec (pipeline_name, data_referencia, execution_id) cobre a
-- coluna, então o ALTER exige DROP + recriação. Chave resultante ≈ 653 bytes
-- (400 + 3 + 250) < limite de 1700 do SQL Server.
--
-- Contrato de leitura da tabela (F3): a liberação pergunta
--   EXISTS (pipeline_name=P AND data_referencia=D AND status='SUCESSO')
-- — nunca "a linha mais recente", nunca COALESCE(inicio, criado_em).
--
-- Idempotente — seguro para rodar mais de uma vez (etapa 6c do deploy).
-- ═══════════════════════════════════════════════════════════════════════════

DECLARE @len INT = (
    SELECT max_length FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline_execucao')
      AND name = 'execution_id'
);

IF @len IS NOT NULL AND @len < 250
BEGIN
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_pipe_exec'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
    BEGIN
        DROP INDEX ux_pipe_exec ON dbo.etl_pipeline_execucao;
        PRINT '[OK] indice ux_pipe_exec removido para o ALTER';
    END

    ALTER TABLE dbo.etl_pipeline_execucao ALTER COLUMN execution_id VARCHAR(250) NULL;
    PRINT '[OK] execution_id ampliado para VARCHAR(250)';

    CREATE UNIQUE INDEX ux_pipe_exec ON dbo.etl_pipeline_execucao
        (pipeline_name, data_referencia, execution_id);
    PRINT '[OK] indice ux_pipe_exec recriado';
END
ELSE IF @len IS NULL
    PRINT '[--] etl_pipeline_execucao/execution_id inexistente (migration 067 ausente?) — nada a fazer';
ELSE
    PRINT '[--] execution_id ja comporta 250 chars — nada a fazer';
GO

-- Rede de segurança para reexecução após falha parcial (queda entre o DROP e o
-- CREATE): garante o índice único de volta mesmo quando o ALTER já foi feito.
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_pipe_exec'
                   AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
BEGIN
    CREATE UNIQUE INDEX ux_pipe_exec ON dbo.etl_pipeline_execucao
        (pipeline_name, data_referencia, execution_id);
    PRINT '[OK] indice ux_pipe_exec recriado (recuperacao de execucao parcial)';
END
ELSE
    PRINT '[--] indice ux_pipe_exec presente';
GO
