-- ============================================================================
-- Migration 078 — Tentativas acumuladas + reabertura de corrida do dependente
--                 (F4 de docs/spec-operacao-nivel-etapa.md, decisões 1 e 2 §7)
--
-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE A — TENTATIVAS ACUMULADAS (decisão 2 do §7: "ACUMULAR")
-- ─────────────────────────────────────────────────────────────────────────────
-- O problema: o `clear` do Airflow mantém o MESMO ts_nodash, e a SP de
-- telemetria faz `IF NOT EXISTS INSERT ELSE UPDATE` sobre a chave
-- (execution_id, pipeline, job_name, task_id) — a PK da migration 058. Logo a
-- reexecução SOBRESCREVE a linha da tentativa anterior e some com "falhou
-- 10:12, reexecutado 11:03, passou". A coluna `attempt` existe desde o schema
-- original (script/tabela/etl_job_execution.sql, DEFAULT 1) e NUNCA foi
-- preenchida por ninguém.
--
-- ⚠️ DESENHO — POR QUE A ACUMULAÇÃO NÃO ENTRA NA PRÓPRIA etl_job_execution
--
-- O caminho óbvio seria pôr `attempt` na PK e deixar N linhas por etapa. Foi
-- medido antes de escolher, e ele QUEBRA a leitura de produção em 17 consultas
-- (levantamento completo no relatório da fase). As três formas de quebra:
--
--   (A) `status_geral` GRUDA em FALHA. O padrão
--       `CASE WHEN SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) > 0 THEN
--       'FAILED'` existe em 8 lugares (dashboard, /execucoes, sla-report, card
--       do Teams do fim, relatório diário). Hoje o upsert apaga o FAILED
--       quando a tentativa 2 passa; com N linhas a linha da tentativa 1 nunca
--       some — uma execução RECUPERADA fica vermelha para sempre, inclusive na
--       Gestão de Falhas (`HAVING SUM(... 'FAILED' ...) > 0`).
--   (B) `COUNT(*) AS total_jobs` e `SUM(duration_seconds)` inflam ×N.
--   (C) `MIN(start_time)` deixa de ser o início da tentativa em curso e passa
--       a ser o da PRIMEIRA — o que dispara BREACH de SLA falso
--       (orquestra_sla_monitor) e alerta de ">3h executando" falso
--       (etl_performance_monitor).
--
-- E, decisivo: boa parte desse SQL está CONGELADA dentro de DAGs já
-- publicadas (`_notif_status_geral`, `teams_end`, `teams_error` são emitidos
-- como texto pela factory), nas DAGs-monitor avulsas e na DAG escrita à mão
-- `dag_datastage_flexibilizacao_cobranca_diario.py`. Corrigi-las exigiria
-- regerar TODAS as DAGs (`force_all`) e redeployar as avulsas ANTES de esta
-- migration valer — e todo pipeline que ficasse para trás passaria a mentir.
-- Migration e regeração de DAG não são atômicas entre si; esta é aplicada na
-- etapa 6c do deploy.sh, sozinha.
--
-- Segundo motivo, operacional: pôr `attempt` na PK obriga a RECONSTRUIR o PK
-- CLUSTERIZADO de etl_job_execution. A própria migration 058 registra que isso
-- exige janela ("a tabela é quente... aplicar SEM execuções em andamento; o
-- rebuild do PK clusterizado pode demorar em tabela grande"). A etapa 6c roda
-- desassistida.
--
-- ✅ O QUE ESTA MIGRATION FAZ, ENTÃO:
--   • `dbo.etl_job_execution` continua com UMA linha por
--     (execution_id, pipeline, job_name, task_id) — a tentativa CORRENTE —
--     com `attempt` finalmente preenchido (1, 2, 3…). PK intocada. Todos os
--     leitores de hoje enxergam exatamente o que enxergavam.
--   • Toda tentativa SUPERADA é arquivada INTEIRA em
--     `dbo.etl_job_execution_tentativa` pela própria SP, antes de a linha viva
--     ser reiniciada. Nada se perde: `corrente ∪ histórico` = a linha do tempo
--     real do dia, que é o que a decisão 2 pede.
--
-- A chave que "acomoda N tentativas" existe — é a da tabela de histórico,
-- (execution_id, pipeline, job_name, task_id, attempt).
--
-- ─────────────────────────────────────────────────────────────────────────────
-- PARTE B — REABERTURA DE CORRIDA (decisão 1 do §7: cascata é opção explícita)
-- ─────────────────────────────────────────────────────────────────────────────
-- Hoje o rerun é "sem cascata" por EFEITO COLATERAL, não por escolha: o
-- publish_dataset do pai roda de novo e tenta o push, mas o claim
-- (`reservar_corrida`, dags/utils/dependencias.py) barra a 2ª corrida do
-- dependente no mesmo ODATE — a barreira D14 contra redisparo N×/ODATE.
--
-- Furar o claim por fora (disparar o filho direto com trigger_dag) mataria a
-- barreira para todo mundo. O caminho explícito é o inverso: a reexecução
-- deliberada MARCA a corrida anterior do dependente como SUBSTITUÍDA, e o
-- claim passa a ignorar corrida substituída — exatamente como já ignora
-- 'PULADO' (`status <> 'PULADO'` no NOT EXISTS). O árbitro continua sendo o
-- claim; o que muda é que uma corrida foi explicitamente aposentada, com dono
-- e carimbo de hora.
--
-- Por que uma COLUNA e não um status novo ('REABERTA'): sobrescrever o status
-- apagaria o desfecho da corrida anterior ("esta rodou e deu SUCESSO"), que é
-- justamente o histórico que a fase existe para preservar. A linha antiga fica
-- intacta, com SUCESSO/FALHA e horários; `substituida_em` só conta que ela foi
-- aposentada por um reprocesso deliberado.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ⚠️ OPERAÇÃO — JANELA: LEIA ANTES DE APLICAR
--
-- O bloco 2 faz BACKFILL EM LOTE (`WHILE` + `UPDATE TOP (5000)`) na
-- `dbo.etl_job_execution`, que é a tabela mais QUENTE do sistema: toda etapa de
-- todo pipeline escreve nela duas vezes (log_start/log_end). A etapa 6c do
-- deploy.sh roda DESASSISTIDA — ninguém está olhando enquanto o loop anda.
--
-- Quantas linhas o loop toca depende de a coluna `attempt` já ter DEFAULT((1))
-- no banco. Se NÃO tiver (esta migration só o cria DEPOIS, no bloco seguinte —
-- sinal de que ele pode faltar), TODAS as linhas estão NULL e o loop reescreve
-- a tabela inteira, concorrendo com log_start/log_end.
--
-- DIMENSIONE ANTES, no banco de destino (a 058 registra a mesma cautela):
--
--     SELECT COUNT(*) AS total,
--            SUM(CASE WHEN attempt IS NULL THEN 1 ELSE 0 END) AS sem_attempt
--       FROM dbo.etl_job_execution;
--
-- Leitura do resultado:
--   • sem_attempt = 0            → no-op, aplique quando quiser.
--   • sem_attempt até ~100 mil   → segundos; aplicar fora do pico basta.
--   • sem_attempt acima de ~1 mi → EXIJA JANELA: aplicar SEM execuções em
--     andamento (scheduler/monitor pausados). São centenas de lotes de 5.000,
--     cada um bloqueando as linhas que a telemetria quer escrever.
-- O loop é retomável: se for interrompido, a próxima passada continua de onde
-- parou (o filtro é `WHERE attempt IS NULL`).
--
-- Este aviso está NO COMENTÁRIO e na documentação de deploy de propósito:
-- sql/migrate.py DESCARTA PRINT (D40) — um alerta em PRINT não chega a ninguém.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- IDEMPOTÊNCIA: roda 2× sem erro (etapa 6c do deploy.sh) — provado no dev.
-- Toda guarda é por OBJECT_ID/COL_LENGTH/sys.*; blocos com shape divergente
-- pulam com [SKIP] em vez de estourar. Para isso valer, todo comando que cita
-- uma coluna CONDICIONAL (`attempt`) está dentro de `EXEC()`: o SQL Server
-- valida nome de coluna em COMPILE-TIME do batch, então SQL estático guardado
-- só por `IF COL_LENGTH(...)` estoura (Msg 207) mesmo inalcançável — a mesma
-- armadilha que a migration 058 documentou e resolveu do mesmo jeito.
-- Conferência por SELECT ao final — sql/migrate.py descarta PRINT (D40).
--
-- QUOTED_IDENTIFIER ON: etl_job_execution tem índice filtrado herdado da 058, e
-- quem ESCREVE nela precisa da sessão com QI ON (a própria 058 registra o
-- apagão de telemetria que o contrário causa).
-- ============================================================================

SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 1) Tabela de histórico de tentativas.
--    Espelha as colunas de etl_job_execution que descrevem a EXECUÇÃO (não as
--    de identidade do desenho), mais o carimbo de arquivamento. `attempt` é
--    NOT NULL aqui de propósito: no histórico ela é chave, e uma tentativa sem
--    número não é uma tentativa — é dado sujo.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_job_execution_tentativa', 'U') IS NULL
BEGIN
    -- Tipos ESPELHADOS de dbo.etl_job_execution (script/tabela/etl_job_execution.sql):
    -- execution_id VARCHAR(50) — aqui ele é o ts_nodash (15 caracteres), não o
    -- run_id; quem foi para VARCHAR(250) na migration 072 é
    -- etl_pipeline_execucao.execution_id, que é outra coisa.
    CREATE TABLE dbo.etl_job_execution_tentativa (
        execution_id     VARCHAR(50)   NOT NULL,
        pipeline         VARCHAR(200)  NOT NULL,
        job_name         VARCHAR(200)  NOT NULL,
        task_id          VARCHAR(200)  NOT NULL,
        attempt          INT           NOT NULL,
        project          VARCHAR(100)  NULL,
        host             VARCHAR(200)  NULL,
        start_time       DATETIME2     NULL,
        end_time         DATETIME2     NULL,
        duration_seconds INT           NULL,
        status           VARCHAR(20)   NULL,
        status_code      INT           NULL,
        log_file         VARCHAR(500)  NULL,
        -- Quando a tentativa foi APOSENTADA (isto é, quando a seguinte
        -- começou). Não é o fim da tentativa — esse é `end_time`.
        arquivado_em     DATETIME2     NOT NULL CONSTRAINT DF_jobexec_tent_arq DEFAULT GETDATE(),
        CONSTRAINT PK_etl_job_execution_tentativa PRIMARY KEY CLUSTERED
            (execution_id, pipeline, job_name, task_id, attempt)
    );
    PRINT '[OK] tabela etl_job_execution_tentativa criada';
END
ELSE
    PRINT '[--] etl_job_execution_tentativa ja existe';
GO

-- Leitura quente do drill-down: "as tentativas anteriores desta execução".
IF OBJECT_ID('dbo.etl_job_execution_tentativa', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_job_execution_tentativa')
                     AND name = 'IX_jobexec_tent_execution_pipeline')
BEGIN
    CREATE NONCLUSTERED INDEX IX_jobexec_tent_execution_pipeline
        ON dbo.etl_job_execution_tentativa (execution_id, pipeline)
        INCLUDE (job_name, task_id, attempt, status, start_time, end_time,
                 duration_seconds);
    PRINT '[OK] indice IX_jobexec_tent_execution_pipeline criado';
END
ELSE
    PRINT '[--] IX_jobexec_tent_execution_pipeline ja existe (ou tabela ausente)';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) Backfill de `attempt` nas linhas JÁ existentes.
--    Toda linha gravada até aqui é, por definição, a tentativa que estava
--    valendo — e não há histórico de anteriores (elas foram sobrescritas e
--    perdidas; esta migration não inventa o que não existe). Marcar 1 é a
--    leitura honesta: "é a primeira que conhecemos".
--    UPDATE em lotes: a tabela é grande em produção e um UPDATE único
--    escalaria o lock para a tabela inteira, bloqueando log_start/log_end.
--    ⚠️ JANELA: veja o aviso de OPERAÇÃO no cabeçalho e RODE A CONSULTA DE
--    DIMENSIONAMENTO antes — a etapa 6c do deploy roda desassistida.
--
--    ⚠️ EXEC() OBRIGATÓRIO (padrão da migration 058): o `IF COL_LENGTH` só
--    protege de verdade se o comando que cita `attempt` não for compilado
--    junto com o batch. Com o UPDATE estático aqui, um banco no shape do
--    sql/deploy_full.sql (etl_job_execution sem attempt/task_id/pipeline)
--    aborta a migration INTEIRA com Msg 207 — e o [SKIP] do ELSE nunca sai.
-- ─────────────────────────────────────────────────────────────────────────────
IF COL_LENGTH('dbo.etl_job_execution', 'attempt') IS NOT NULL
BEGIN
    EXEC('
DECLARE @n INT = 1;
WHILE @n > 0
BEGIN
    UPDATE TOP (5000) dbo.etl_job_execution
       SET attempt = 1
     WHERE attempt IS NULL;
    SET @n = @@ROWCOUNT;
END');
    PRINT '[OK] backfill de attempt=1 concluido';
END
ELSE
    PRINT '[SKIP] etl_job_execution sem coluna attempt — shape divergente';
GO

-- DEFAULT 1 para `attempt` (o schema de produção tem; o do dev, nascido de
-- script/tabela/, também — mas o shape do deploy_full não). Garante que
-- qualquer INSERT que esqueça a coluna nasça como tentativa 1, nunca NULL.
IF COL_LENGTH('dbo.etl_job_execution', 'attempt') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.default_constraints
                   WHERE parent_object_id = OBJECT_ID('dbo.etl_job_execution')
                     AND parent_column_id = COLUMNPROPERTY(
                             OBJECT_ID('dbo.etl_job_execution'), 'attempt', 'ColumnId'))
BEGIN
    ALTER TABLE dbo.etl_job_execution
        ADD CONSTRAINT DF_etl_job_execution_attempt DEFAULT (1) FOR attempt;
    PRINT '[OK] default 1 para etl_job_execution.attempt criado';
END
ELSE
    PRINT '[--] etl_job_execution.attempt ja tem default (ou coluna ausente)';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3) Reabertura de corrida — colunas em etl_pipeline_execucao (PARTE B).
--    `substituida_em` NULL = corrida viva (o caso de 100% das linhas de hoje);
--    preenchida = corrida aposentada por reprocesso deliberado, e o claim de
--    dags/utils/dependencias.py passa a permitir uma nova no mesmo ODATE.
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NULL
    PRINT '[SKIP] etl_pipeline_execucao inexistente (migration 067 ausente) — cascata indisponivel';
ELSE
BEGIN
    IF COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em') IS NULL
    BEGIN
        ALTER TABLE dbo.etl_pipeline_execucao ADD substituida_em DATETIME2 NULL;
        PRINT '[OK] coluna etl_pipeline_execucao.substituida_em criada';
    END
    ELSE
        PRINT '[--] etl_pipeline_execucao.substituida_em ja existe';

    IF COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_por') IS NULL
    BEGIN
        ALTER TABLE dbo.etl_pipeline_execucao ADD substituida_por NVARCHAR(200) NULL;
        PRINT '[OK] coluna etl_pipeline_execucao.substituida_por criada';
    END
    ELSE
        PRINT '[--] etl_pipeline_execucao.substituida_por ja existe';
END
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 4) sp_etl_job_execution_log v3 — arquiva a tentativa superada.
--
-- A ASSINATURA NÃO MUDA (11 parâmetros, mesmos nomes e tipos). É deliberado:
-- as DAGs já publicadas chamam a SP com esses 11 parâmetros como TEXTO gerado
-- (dags/etl_dag_factory.py `_exec_telemetry`), e a acumulação passa a valer
-- para elas SEM regerar DAG nenhuma. Quem decide que houve nova tentativa é a
-- SP, com a informação que já recebe.
--
-- A REGRA (o único comportamento novo):
--   log_start (@status='RUNNING') sobre uma linha existente que JÁ CHEGOU AO
--   FIM  ⇒  é uma tentativa nova.
--       (a) arquiva a linha atual inteira em etl_job_execution_tentativa;
--       (b) reinicia a linha viva com attempt = attempt + 1.
--
-- ⚠️ A GUARDA "JÁ CHEGOU AO FIM" (`end_time IS NOT NULL OR status <> 'RUNNING'`)
-- é o que impede tentativa FANTASMA. A task `log_start_<job>` é uma task do
-- Airflow como outra qualquer e pode ela mesma ser repetida (retry do
-- operador, clear só dela, worker morto depois do INSERT). Sem a guarda, cada
-- repetição do log_start inventaria uma tentativa que nunca executou. Com ela,
-- linha ainda RUNNING e sem fim = MESMA tentativa, e o comportamento é o
-- byte-a-byte da v2 (reinicia o relógio).
--
-- ⚠️ SEM TRANSAÇÃO NOVA. A SP é o caminho mais quente do sistema (duas
-- chamadas por etapa de todo pipeline) e introduzir BEGIN TRAN aqui mudaria a
-- semântica transacional de quem a chama. Em vez disso o arquivamento é
-- IDEMPOTENTE por construção (`WHERE NOT EXISTS` sobre a PK do histórico): se
-- o processo morrer entre (a) e (b), a repetição não duplica — encontra a
-- linha arquivada, pula o INSERT e segue para o incremento.
--
-- `status_code` é LIMPO na nova tentativa: ele é preenchido depois, por
-- `_update_status_code`, e herdar o código da tentativa anterior faria a
-- tentativa 2 nascer carregando o resultado da 1.
--
-- Guarda de existência da tabela de histórico (@tem_hist): a SP nunca falha
-- por causa de um deploy parcial — sem a tabela ela se comporta como a v2, e
-- a telemetria continua de pé (só não acumula).
-- ─────────────────────────────────────────────────────────────────────────────
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NULL
   OR COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NULL
   OR COL_LENGTH('dbo.etl_job_execution', 'attempt') IS NULL
    PRINT '[SKIP] etl_job_execution com shape divergente — SP mantida como esta';
ELSE
BEGIN
    EXEC('
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_execution_log]
(
 @execution_id       VARCHAR(50),
 @project            VARCHAR(100),
 @job_name           VARCHAR(200),
 @pipeline           VARCHAR(200),
 @host               VARCHAR(200),
 @start_time         VARCHAR(30),
 @end_time           VARCHAR(30),
 @duration_seconds   INT,
 @status             VARCHAR(20),
 @log_file           VARCHAR(500),
 @task_id            VARCHAR(200)
)
AS
BEGIN
SET NOCOUNT ON;

DECLARE @start_dt DATETIME2
DECLARE @end_dt   DATETIME2

SET @start_dt = CASE WHEN @start_time IS NULL OR @start_time = '''' THEN NULL
                     ELSE CAST(@start_time AS DATETIME2) END
SET @end_dt   = CASE WHEN @end_time IS NULL OR @end_time = ''''
                       OR @end_time = ''1900-01-01 00:00:00'' THEN NULL
                     ELSE CAST(@end_time AS DATETIME2) END

IF NOT EXISTS (
    SELECT 1 FROM dbo.etl_job_execution
    WHERE execution_id = @execution_id AND pipeline = @pipeline
      AND job_name = @job_name AND task_id = @task_id
)
BEGIN
    INSERT INTO dbo.etl_job_execution
        (execution_id, project, job_name, pipeline, host, start_time, end_time,
         duration_seconds, status, log_file, task_id, attempt, created_at, updated_at)
    VALUES
        (@execution_id, @project, @job_name, @pipeline, @host, @start_dt, @end_dt,
         @duration_seconds, @status, @log_file, @task_id, 1, GETDATE(), GETDATE())
    RETURN
END

-- Reprocesso: log_start sobre linha que JA chegou ao fim = tentativa NOVA.
DECLARE @nova_tentativa BIT = 0
IF @status = ''RUNNING''
   AND EXISTS (
        SELECT 1 FROM dbo.etl_job_execution
        WHERE execution_id = @execution_id AND pipeline = @pipeline
          AND job_name = @job_name AND task_id = @task_id
          AND (end_time IS NOT NULL OR status <> ''RUNNING''))
    SET @nova_tentativa = 1

IF @nova_tentativa = 1
   AND OBJECT_ID(''dbo.etl_job_execution_tentativa'', ''U'') IS NOT NULL
BEGIN
    -- (a) arquiva a tentativa superada. Idempotente pela PK do historico.
    INSERT INTO dbo.etl_job_execution_tentativa
        (execution_id, pipeline, job_name, task_id, attempt, project, host,
         start_time, end_time, duration_seconds, status, status_code, log_file)
    SELECT e.execution_id, e.pipeline, e.job_name, e.task_id,
           ISNULL(e.attempt, 1), e.project, e.host, e.start_time, e.end_time,
           e.duration_seconds, e.status, e.status_code, e.log_file
    FROM dbo.etl_job_execution e
    WHERE e.execution_id = @execution_id AND e.pipeline = @pipeline
      AND e.job_name = @job_name AND e.task_id = @task_id
      AND NOT EXISTS (
            SELECT 1 FROM dbo.etl_job_execution_tentativa t
            WHERE t.execution_id = e.execution_id AND t.pipeline = e.pipeline
              AND t.job_name = e.job_name AND t.task_id = e.task_id
              AND t.attempt = ISNULL(e.attempt, 1))
END

UPDATE dbo.etl_job_execution
SET
    -- (b) tentativa nova: numero sobe e o resultado anterior nao e herdado.
    attempt = CASE WHEN @nova_tentativa = 1 THEN ISNULL(attempt, 1) + 1
                   ELSE ISNULL(attempt, 1) END,
    status_code = CASE WHEN @nova_tentativa = 1 THEN NULL ELSE status_code END,
    -- Reprocesso (log_start em linha existente): reinicia o relogio.
    start_time = CASE WHEN @status = ''RUNNING'' AND @start_dt IS NOT NULL
                      THEN @start_dt ELSE start_time END,
    host       = CASE WHEN @status = ''RUNNING'' AND @host IS NOT NULL
                      THEN @host ELSE host END,
    end_time = CASE WHEN @status = ''RUNNING'' THEN NULL
                    ELSE COALESCE(@end_dt, end_time) END,
    duration_seconds = CASE
        WHEN @status = ''RUNNING'' THEN NULL
        WHEN @end_dt IS NOT NULL THEN DATEDIFF(SECOND, start_time, @end_dt)
        ELSE duration_seconds END,
    status = @status,
    log_file = @log_file,
    updated_at = GETDATE()
WHERE execution_id = @execution_id AND pipeline = @pipeline
  AND job_name = @job_name AND task_id = @task_id
END
');
    PRINT '[OK] sp_etl_job_execution_log v3 (tentativa superada vai para o historico)';
END
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 5) Conferência por SELECT (sql/migrate.py descarta PRINT — D40).
--    Uma linha só, legível no log do deploy.
--
--    ⚠️ A contagem de `attempt IS NULL` vem por EXEC() pelo mesmo motivo do
--    bloco 2: escrita direto no SELECT, ela é resolvida em compile-time e
--    derruba a migration num banco sem a coluna. `NULL` em
--    `linhas_sem_attempt` = a coluna não existe neste banco (shape divergente),
--    e não "zero linhas pendentes".
-- ─────────────────────────────────────────────────────────────────────────────
DECLARE @sem_attempt INT = NULL;
IF COL_LENGTH('dbo.etl_job_execution', 'attempt') IS NOT NULL
BEGIN
    DECLARE @cnt TABLE (n INT);
    INSERT INTO @cnt (n)
        EXEC('SELECT COUNT(*) FROM dbo.etl_job_execution WHERE attempt IS NULL');
    SELECT @sem_attempt = n FROM @cnt;
END

SELECT
    CASE WHEN OBJECT_ID('dbo.etl_job_execution_tentativa', 'U') IS NOT NULL
         THEN 'OK' ELSE 'FALTA' END                         AS tabela_tentativa,
    CASE WHEN COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em') IS NOT NULL
         THEN 'OK' ELSE 'FALTA' END                         AS col_substituida_em,
    CASE WHEN EXISTS (SELECT 1 FROM sys.sql_modules
                      WHERE object_id = OBJECT_ID('dbo.sp_etl_job_execution_log')
                        AND definition LIKE '%etl_job_execution_tentativa%')
         THEN 'v3' ELSE 'ANTIGA' END                        AS sp_versao,
    @sem_attempt                                            AS linhas_sem_attempt;
GO
