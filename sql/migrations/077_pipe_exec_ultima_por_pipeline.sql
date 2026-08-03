-- ============================================================================
-- Migration 077 — Índice de apoio da "última execução" do card da malha
--
-- A tela Malha passou a mostrar, em cada card, a corrida MAIS RECENTE entre os
-- pipelines membros (GET /malhas). A consulta é um ROW_NUMBER particionado por
-- malha sobre o JOIN etl_malha_pipeline × etl_pipeline_execucao, e ela NÃO tem
-- predicado de data de propósito: uma malha parada há meses precisa continuar
-- mostrando quando rodou pela última vez — recortar por janela apagaria
-- justamente a informação que o operador pediu.
--
-- Sem índice de apoio o plano varria a tabela inteira:
--
--     |--Sort(ORDER BY: mp.malha_name, <momento> DESC, e.id DESC)
--          |--Nested Loops(Inner Join)
--               |--Clustered Index Scan(PK_etl_pipeline_execucao AS e)   <<<<
--               |--Index Seek(ix_malha_pipe_pipeline AS mp)
--
-- etl_pipeline_execucao é tabela de HISTÓRICO, sem expurgo: no dev são 7
-- linhas, em produção ela só cresce — e o GET /malhas roda a cada abertura da
-- tela e a cada refetch de foco.
--
-- Por que os índices que já existiam não serviam:
--   • PK_etl_pipeline_execucao (clustered em id) — não ajuda a buscar por
--     pipeline_name;
--   • ux_pipe_exec (pipeline_name, data_referencia, execution_id) — não cobre
--     status/inicio/criado_em;
--   • ix_pipe_exec_cond (pipeline_name, data_referencia, status, inicio) — a
--     mais próxima, mas SEM criado_em: cada linha exigiria lookup no clustered
--     (o COALESCE(inicio, criado_em) do desempate), e o otimizador preferiu
--     varrer tudo.
--
-- Este índice fecha a cobertura: seek por pipeline_name (o lado pequeno,
-- etl_malha_pipeline, vira o motor do JOIN) com todas as colunas lidas no
-- leaf. `id` NÃO entra no INCLUDE de propósito: é a chave do clustered e já
-- viaja em todo índice não clusterizado.
--
-- Idempotente: roda 2x sem erro (etapa 6c do deploy.sh). Guarda também a
-- existência da TABELA — banco sem a migration 067 aplicada simplesmente pula,
-- em vez de estourar 'Invalid object name'. Conferência por SELECT —
-- sql/migrate.py descarta PRINT (D40).
-- ============================================================================

IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NULL
    PRINT '[--] etl_pipeline_execucao inexistente (migration 067 ausente?) — nada a fazer';
ELSE IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_pipe_exec_ultima'
                AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
    PRINT '[--] indice ix_pipe_exec_ultima ja existe';
ELSE
BEGIN
    CREATE INDEX ix_pipe_exec_ultima ON dbo.etl_pipeline_execucao (pipeline_name)
        INCLUDE (status, inicio, criado_em);
    PRINT '[OK] indice ix_pipe_exec_ultima criado';
END
GO
