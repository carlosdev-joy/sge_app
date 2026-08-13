-- 090_chamado_parentesco.sql
-- O espelho passa a guardar DUAS coisas que ele deduzia ou não sabia:
--   1. o PAI do chamado (sc_task → sc_req_item) — pai_sys_id, pai_numero
--   2. o valor CRU do estado — estado_cru
--
-- ── 1. O parentesco ────────────────────────────────────────────────────────
-- No ServiceNow todo RITM gera uma sc_task filha, e o espelho trazia as duas
-- como cards independentes: a fila mostrava 113 itens para ~60 trabalhos —
-- cada pedido contado duas vezes. Dava para inferir pelo título (a task nasce
-- como "RITM0096880 - <assunto>"), mas isso é convenção de texto: quebra no
-- dia em que alguém mudar o padrão de nomenclatura da instância.
--
-- A API já mantém a ligação em `sc_task.request_item` (e `parent`). Como a
-- chamada usa sysparm_display_value=all, o campo volta COMPLETO na mesma
-- requisição — display_value é o número (RITM0096880) e value é o sys_id.
-- Guardamos os dois: o sys_id dá join exato, o número dá o que mostrar.
--
-- ── 2. O estado cru ────────────────────────────────────────────────────────
-- `estado_origem` guarda o RÓTULO ("Pendente"), mas o mapa do kanban é por
-- NÚMERO. Quando um chamado cai em 'outros', o dado necessário para corrigir
-- o mapa não está no banco — é preciso ir perguntar ao ServiceNow.
--
-- Foi exatamente o que travou o diagnóstico de 2026-08-13: em sc_task,
-- '-5' e '1' apontam ambos para 'novo', e dois rótulos distintos caíam lá
-- ("Em aberto", 36 · "Pendente", 3). Sem o número não dá para saber qual é
-- qual — e apostar errado moveria 36 chamados para a coluna errada.
-- Com esta coluna, uma consulta responde, sem palpite e sem ida à API.
--
-- Idempotente: cada ALTER só roda se a coluna faltar. Colunas NULL em linhas
-- já existentes; o próximo ciclo do sync preenche (upsert por sys_id).

-- ═══════════════════════════════════════════════════════════════════════════
-- Colunas
-- ═══════════════════════════════════════════════════════════════════════════
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado')
BEGIN
    PRINT '[SKIP] dbo.etl_chamado ainda nao existe (rode a 088 antes)';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='pai_sys_id')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD pai_sys_id VARCHAR(32) NULL;
        PRINT '[OK] Coluna pai_sys_id criada';
    END
    ELSE PRINT '[SKIP] pai_sys_id ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='pai_numero')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD pai_numero VARCHAR(20) NULL;
        PRINT '[OK] Coluna pai_numero criada';
    END
    ELSE PRINT '[SKIP] pai_numero ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='estado_cru')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD estado_cru VARCHAR(20) NULL;
        PRINT '[OK] Coluna estado_cru criada';
    END
    ELSE PRINT '[SKIP] estado_cru ja existe';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- Índice do parentesco — a tela vai buscar "os filhos deste RITM" a cada
-- montagem da fila; sem ele é varredura na tabela inteira por card.
--
-- ⚠️ NÃO é índice FILTRADO, e isso é deliberado. A primeira versão desta
-- migration usava `WHERE pai_sys_id IS NOT NULL` — mais enxuto, e funcionou.
-- Só que índice filtrado exige QUOTED_IDENTIFIER ON em TODA operação DML
-- sobre a tabela, para sempre, e o sqlcmd que aplica as migrations roda com
-- OFF. Medido no SQL Server do dev:
--   • o CREATE INDEX falhou com Msg 1934 DEPOIS de os três ALTER passarem —
--     migration pela metade, colunas sem índice;
--   • com o índice criado, um DELETE simples na tabela passou a falhar com o
--     MESMO erro. Toda migration futura que tocasse etl_chamado quebraria.
-- (O pymssql da DAG conecta com ON e não seria afetado — o que é pior: o
-- sync seguiria verde enquanto as migrations falhariam.)
-- Numa tabela da ordem de centenas de linhas o filtro não paga esse preço.
-- ═══════════════════════════════════════════════════════════════════════════
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
             AND COLUMN_NAME='pai_sys_id')
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_etl_chamado_pai'
                   AND object_id=OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE INDEX IX_etl_chamado_pai ON dbo.etl_chamado (pai_sys_id);
    PRINT '[OK] Indice IX_etl_chamado_pai criado';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- Conferência — rode DEPOIS do primeiro ciclo do sync (até 15 min).
-- É esta consulta que fecha o mapeamento de estados sem palpite: cada rótulo
-- ao lado do NÚMERO que o ServiceNow devolve.
-- ═══════════════════════════════════════════════════════════════════════════
SELECT tipo, estado_cru, estado_origem, estado_kanban, COUNT(*) AS qtd
FROM dbo.etl_chamado WHERE ativo = 1
GROUP BY tipo, estado_cru, estado_origem, estado_kanban
ORDER BY tipo, qtd DESC;
GO

-- Quantas tasks ativas têm o pai também na fila (a duplicação, medida).
SELECT COUNT(*) AS tasks_ativas,
       SUM(CASE WHEN pai_sys_id IS NOT NULL THEN 1 ELSE 0 END) AS com_pai_gravado
FROM dbo.etl_chamado WHERE ativo = 1 AND tipo = 'task';
GO
