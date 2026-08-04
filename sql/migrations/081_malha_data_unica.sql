-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 081 — Data de referência ÚNICA por malha
--   (docs/spec-malha-data-unica.md, F2 e F3)
--
--   A hora de VIRADA decide a data de referência de quem roda por agenda. Com
--   membros de uma mesma malha em viradas diferentes, a corrida sai partida:
--   parte num ODATE, parte em outro — e o Aguarde libera com metade dos dados
--   do dia anterior (incidente da malha Carga_Vida, 2026-08-04).
--
--   `hora_virada` na MALHA é a régua do ciclo: a API a compila para todos os
--   membros, do mesmo jeito que o componente Início já compila o agendamento
--   para as raízes. NULL = a malha usa a virada global de etl_app_config —
--   o comportamento de hoje.
--
--   `equalizar_data` (F3) é a marca do "não pare para perguntar": ao encontrar
--   datas diferentes no ciclo, carimba todos com a data da malha e segue, em
--   vez de bloquear o disparo. Default 0 = bloqueia e alerta (a regra pedida
--   pelo usuário para o caso geral).
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'hora_virada') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha ADD hora_virada TIME NULL;
    PRINT '[OK] Coluna dbo.etl_malha.hora_virada criada';
END
GO

IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'equalizar_data') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha
        ADD equalizar_data BIT NOT NULL CONSTRAINT DF_malha_equalizar_data DEFAULT 0;
    PRINT '[OK] Coluna dbo.etl_malha.equalizar_data criada';
END
GO
