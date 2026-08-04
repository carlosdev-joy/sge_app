-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 080 — Pendente em MODO VERIFICAÇÃO (republicação de malha)
--   Republicar uma malha gera N DAGs num run só da etl_dag_factory. Quem
--   publica (e zera dag_config_pendente_em) é a própria factory; o que faltava
--   era alguém CONFERIR, depois do run, se cada DAG entrou de pé no Airflow —
--   um arquivo com erro de CARGA (NameError, import quebrado) faz o Airflow
--   manter a versão ANTERIOR ativa, e o Orquestra anunciaria "publicado e em
--   dia" com a DAG velha rodando.
--
--   `modo_verificacao = 1` marca o item da fila que existe só para essa
--   conferência: o reconciliador não notifica sucesso (seriam N avisos por
--   clique) e não mexe no carimbo de publicação pendente — mas continua
--   notificando ERRO e reacendendo o carimbo quando a DAG não é importável.
--   Default 0 = o comportamento de sempre do "Publicar nova versão".
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_dag_pendente', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_dag_pendente', 'modo_verificacao') IS NULL
BEGIN
    ALTER TABLE dbo.etl_dag_pendente
        ADD modo_verificacao BIT NOT NULL CONSTRAINT DF_dag_pendente_modo_verif DEFAULT 0;
    PRINT '[OK] Coluna dbo.etl_dag_pendente.modo_verificacao criada';
END
GO
