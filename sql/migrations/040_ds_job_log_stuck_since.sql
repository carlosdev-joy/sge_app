-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 040 — Carência para espelhar ABORT de filho (monitor central)
--   etl_ds_job_log.stuck_since: instante (UTC) em que o job entrou no estado
--   "travado" — há filho ABORTED e NENHUM filho ainda em execução (a sequence
--   parou de progredir) com o pai ainda RUNNING. O monitor central só propaga o
--   ABORTED depois de DS_ABORT_GRACE_SECONDS nesse estado; qualquer progresso
--   (filho voltou a rodar / novo filho) zera a coluna.
--   O operador usa estado em memória; esta coluna é só para o monitor (stateless
--   entre ciclos). Tudo degrada: sem a coluna, o monitor não propaga (o operador
--   continua cobrindo).
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_ds_job_log', 'stuck_since') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_job_log ADD stuck_since DATETIME NULL;
    PRINT '[OK] etl_ds_job_log.stuck_since adicionada';
END
GO
