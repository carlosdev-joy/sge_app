-- 092_chamado_derivacoes.sql
-- O que se lê nas ENTRELINHAS do chamado, gravado como coluna.
--
-- O painel da estação (ritm_geresd_ed.html) já fazia três leituras que a tela
-- /chamados não tinha, e todas saem de texto que a migration 091 acabou de
-- trazer para o espelho:
--
--   tipo_demanda       → "Inclusão de coluna/campo", "Extração de dados"…
--                        deduzido do título e, em segunda mão, do catálogo
--   categoria_diaadia  → a marcação que a equipe JÁ escreve nas work notes
--                        ("dia a dia - bug"); era conhecimento preso no texto
--   objetos            → DMDB…, DM_…, TB_, VW_, PRC_ citados na descrição;
--                        o atalho para saber do que trata sem abrir o chamado
--
-- ── Por que coluna, e não cálculo na leitura ──────────────────────────────
-- Regex por linha a cada request faz a tela pagar o custo em toda abertura e,
-- pior, faz o resultado variar conforme a versão do código que respondeu.
-- Gravado na ingestão, o valor é estável, agregável em GROUP BY e igual para
-- todo mundo até o próximo ciclo do sync.
--
-- ── Estas colunas são PALPITE, e o desenho assume isso ────────────────────
-- Nenhuma delas vem da origem: são deduzidas. Por isso nada aqui sobrescreve
-- campo do ServiceNow, e `tipo_demanda` nunca fica vazio — quem não casa com
-- nenhum padrão recebe 'Demanda técnica'. Rótulo honesto no lugar de string
-- vazia: sem ele, a soma do gráfico por tipo não fecharia com o total da fila
-- e ninguém saberia dizer se faltou dado ou faltou classificação.
--
-- Idempotente: cada ALTER só roda se a coluna faltar. As linhas existentes
-- ficam NULL até o próximo ciclo do sync, que refaz o MERGE por sys_id.

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado')
BEGIN
    PRINT '[SKIP] dbo.etl_chamado ainda nao existe (rode a 088 antes)';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='tipo_demanda')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD tipo_demanda NVARCHAR(60) NULL;
        PRINT '[OK] Coluna tipo_demanda criada';
    END
    ELSE PRINT '[SKIP] tipo_demanda ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='categoria_diaadia')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD categoria_diaadia NVARCHAR(60) NULL;
        PRINT '[OK] Coluna categoria_diaadia criada';
    END
    ELSE PRINT '[SKIP] categoria_diaadia ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='objetos')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD objetos NVARCHAR(200) NULL;
        PRINT '[OK] Coluna objetos criada';
    END
    ELSE PRINT '[SKIP] objetos ja existe';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- Índice do histórico de resolvidos
-- ═══════════════════════════════════════════════════════════════════════════
-- A aba de histórico varre por encerrado_em nos últimos N dias. Sem índice é
-- table scan a cada abertura da tela.
--
-- ⚠️ Índice SEM filtro, de propósito. `CREATE INDEX ... WHERE` exige
-- QUOTED_IDENTIFIER ON e falha no sqlcmd com Msg 1934; pior, uma vez criado,
-- ele quebra TODO DML da tabela feito por sqlcmd enquanto o pymssql da DAG
-- segue verde — a combinação que já mordeu neste repo.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_chamado_encerrado'
               AND object_id = OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE INDEX IX_etl_chamado_encerrado ON dbo.etl_chamado (encerrado_em);
    PRINT '[OK] Indice IX_etl_chamado_encerrado criado';
END
ELSE PRINT '[SKIP] IX_etl_chamado_encerrado ja existe';
GO

-- ⚠️ DEPOIS DO DEPLOY: as derivações são calculadas em dags/utils/ e o worker
-- do Airflow CACHEIA esse módulo. Sem restart do worker, as colunas ficam
-- NULL com a task VERDE, e a tela mostra "Demanda técnica" para tudo.
