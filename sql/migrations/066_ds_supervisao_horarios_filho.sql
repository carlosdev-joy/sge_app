-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 066 — Supervisão DataStage: horário de cada job da árvore
--
-- POR QUE:
--   A árvore de níveis já mostra QUEM rodou abaixo do job supervisionado e com
--   que status, mas não QUANDO. Sem hora, o diagrama responde "o que falhou" e
--   não responde "onde o fluxo travou" — que é a pergunta seguinte de quem
--   olha um processo que terminou 8h depois do previsto.
--
--   Com início e fim por job, o diagrama passa a mostrar a duração de cada
--   etapa e o gargalo aparece sozinho.
--
-- O QUE FICA NULO:
--   Tudo que foi coletado antes desta migration, e também os jobs cujo log não
--   traz o par de eventos (um filho que aparece só no "Waiting for job X to
--   finish" tem início aproximado e fim desconhecido). A tela trata NULL como
--   "—", nunca como zero: duração zero seria uma afirmação falsa.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_ds_supervisao_run_filho', 'inicio') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_run_filho ADD inicio DATETIME NULL;
    PRINT '[OK] etl_ds_supervisao_run_filho.inicio criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run_filho.inicio ja existe';
GO

IF COL_LENGTH('dbo.etl_ds_supervisao_run_filho', 'fim') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_run_filho ADD fim DATETIME NULL;
    PRINT '[OK] etl_ds_supervisao_run_filho.fim criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run_filho.fim ja existe';
GO

-- NÃO zera o aprendizado (diferente da 065): a estrutura aprendida é uma lista
-- de NOMES e não muda de significado por ganhar coluna de horário. Zerar aqui
-- só custaria mais 3 execuções de amostra sem devolver nada.
PRINT '[--] aprendizado preservado: horario nao altera a estrutura aprendida';
GO
