-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 073 — etl_pipeline.dag_config_pendente_em: pendência de publicação
--
-- F5 da retomada (docs/retomada-f5-desenho.md §7, Decisão 6 / D30): quando o
-- cadastro que AFETA a DAG muda (agendamento, janela/virada, dependências…) e
-- a DAG já foi publicada (dag_criada=1), a versão no Airflow continua rodando
-- a configuração ANTERIOR até o operador clicar em "Publicar nova versão".
-- Esta coluna persiste a marca no banco, ligada pelo SERVIDOR nas portas de
-- escrita (register e POST/DELETE /dependencias) e limpa pelo reconciliador
-- (services/dag_reconcile) ao concluir a publicação.
--
-- CARIMBO, não bit (achado 2 da revisão adversarial da F5 — TOCTOU): com um
-- BIT, uma edição feita DURANTE uma publicação em voo era apagada pelo clear
-- incondicional do reconciliador — pendência NOVA sumia sem publicar. Com
-- DATETIME2 NULL, quem liga grava GETDATE() (QUANDO a pendência nasceu) e o
-- clear só apaga carimbos <= início da publicação concluída.
--   NULL  = sem pendência;
--   valor = pendente desde este instante.
-- O contrato com o front NÃO muda: a API expõe o booleano derivado
-- (dag_config_pendente_em IS NOT NULL) sob o nome dag_config_pendente.
--
-- Idempotente em TRÊS estados — seguro para rodar mais de uma vez:
--   1. coluna nova já existe                  → pula o ADD;
--   2. coluna BIT antiga dag_config_pendente  → migra (versão anterior DESTA
--      migration, nunca deployada — aplicada só no dev): ADD da nova, quem
--      estava bit=1 vira carimbo GETDATE(), DROP da default constraint e da
--      coluna BIT (UPDATE/checagem de tipo via SQL dinâmico/sys.columns —
--      referenciar a coluna morta em batch estático quebraria a compilação
--      nas execuções seguintes);
--   3. nada existe                            → só o ADD.
-- Sem a coluna, API degrada (guard por try/except, padrão do register) e o
-- GET devolve NULL — o front simplesmente não renderiza o badge.
-- Nenhum PRINT decisório: migrate.py descarta PRINT (D40).
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente_em') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD dag_config_pendente_em DATETIME2 NULL;
    PRINT '[OK] etl_pipeline.dag_config_pendente_em criada';
END
ELSE
    PRINT '[--] etl_pipeline.dag_config_pendente_em ja existe';
GO

-- Estado 2: converte e remove a coluna BIT da versão anterior desta migration.
IF COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente') IS NOT NULL
   AND EXISTS (SELECT 1
               FROM sys.columns c
               JOIN sys.types t ON t.user_type_id = c.user_type_id
               WHERE c.object_id = OBJECT_ID('dbo.etl_pipeline')
                 AND c.name = 'dag_config_pendente'
                 AND t.name = 'bit')
BEGIN
    -- Pendência ligada no formato antigo vira carimbo "agora" (conservador:
    -- sobrevive a qualquer clear com início de publicação anterior à
    -- conversão). SQL dinâmico: a coluna não existe mais nos estados 1/3.
    EXEC sp_executesql N'UPDATE dbo.etl_pipeline
                         SET dag_config_pendente_em = GETDATE()
                         WHERE dag_config_pendente = 1
                           AND dag_config_pendente_em IS NULL';
    IF OBJECT_ID('dbo.DF_etl_pipeline_dag_config_pendente', 'D') IS NOT NULL
        ALTER TABLE dbo.etl_pipeline DROP CONSTRAINT DF_etl_pipeline_dag_config_pendente;
    ALTER TABLE dbo.etl_pipeline DROP COLUMN dag_config_pendente;
    PRINT '[OK] BIT dag_config_pendente convertida para dag_config_pendente_em';
END
ELSE
    PRINT '[--] sem coluna BIT antiga para converter';
GO
