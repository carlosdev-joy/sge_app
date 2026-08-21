-- 091_chamado_conteudo.sql
-- O espelho passa a guardar o CONTEÚDO do chamado, e não só a ficha.
--
-- Até aqui dbo.etl_chamado tinha número, título, estado, prioridade,
-- responsável, grupo e datas — o suficiente para um kanban. Nada disso
-- responde à pergunta que o painel da estação responde todo dia:
-- **este chamado tem informação suficiente para alguém começar?**
--
-- Essa pergunta se responde lendo a DESCRIÇÃO e as WORK NOTES. Sem elas não
-- há triagem possível, nem por IA nem por heurística — e é por isso que esta
-- migration vem antes da agregação (F3) e da triagem (F4) da spec
-- docs/spec-chamados-triagem-ia.md.
--
-- ── O que entra, e por quê ────────────────────────────────────────────────
--   descricao     → o pedido em si; é onde estão (ou faltam) tabela de
--                   origem, campos do resultado e critério de aceite
--   work_notes    → o diálogo técnico; é de lá que sai a categoria
--                   "dia a dia - <algo>" que a equipe já usa na mão
--   catalogo      → cat_item: o tipo de demanda declarado na abertura
--   demandante    → requested_for: quem pediu. O painel usa o histórico de
--                   quem-atende-quem para sugerir responsável
--   prazo         → estimated_delivery, a data prometida
--   vencimento    → due_date, o limite acordado
--   sla_vencido   → u_sla_expired, o veredito do próprio ServiceNow
--
-- ── Por que NVARCHAR(4000) e não (MAX) ────────────────────────────────────
-- A triagem lê os primeiros milhares de caracteres (o painel usa 1500 da
-- descrição e 2000 das work notes). MAX convida o espelho a engordar sem
-- limite a cada ciclo de 15 min, com texto que ninguém lê. 4000 é folga de
-- mais de duas vezes sobre o uso real, e o corte é feito na ingestão COM
-- reticência visível — truncar calado já mordeu antes (PR #161).
--
-- ── NVARCHAR, nunca VARCHAR ───────────────────────────────────────────────
-- Descrição de chamado tem acento em toda linha e, com frequência, texto
-- colado do Teams com emoji. O incidente do título (088) e o do NUM_CPF_CNPJ
-- já cobraram esse pedágio.
--
-- ⚠️ PRIVACIDADE: work notes e descrição carregam nome de pessoa, dado de
-- cliente e conteúdo de negócio que o espelho NÃO guardava até agora. Por
-- isso a listagem da tela não devolve esses textos — ela serve as derivações
-- (tipo, categoria, objetos citados). O texto cru fica para o detalhe do
-- chamado, sob a mesma permissão tela_chamados.
--
-- Idempotente: cada ALTER só roda se a coluna faltar. Colunas NULL nas linhas
-- que já existem; o próximo ciclo do sync preenche (upsert por sys_id).

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
                     AND COLUMN_NAME='descricao')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD descricao NVARCHAR(4000) NULL;
        PRINT '[OK] Coluna descricao criada';
    END
    ELSE PRINT '[SKIP] descricao ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='work_notes')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD work_notes NVARCHAR(4000) NULL;
        PRINT '[OK] Coluna work_notes criada';
    END
    ELSE PRINT '[SKIP] work_notes ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='catalogo')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD catalogo NVARCHAR(200) NULL;
        PRINT '[OK] Coluna catalogo criada';
    END
    ELSE PRINT '[SKIP] catalogo ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='demandante')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD demandante NVARCHAR(120) NULL;
        PRINT '[OK] Coluna demandante criada';
    END
    ELSE PRINT '[SKIP] demandante ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='prazo')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD prazo DATETIME NULL;
        PRINT '[OK] Coluna prazo criada';
    END
    ELSE PRINT '[SKIP] prazo ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='vencimento')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD vencimento DATETIME NULL;
        PRINT '[OK] Coluna vencimento criada';
    END
    ELSE PRINT '[SKIP] vencimento ja existe';

    -- BIT NULL de propósito: NULL = a origem não informou, 0 = informou que
    -- não venceu. Colapsar os dois em 0 diria "está no prazo" sobre chamado
    -- de tabela que nem tem o campo.
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='sla_vencido')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD sla_vencido BIT NULL;
        PRINT '[OK] Coluna sla_vencido criada';
    END
    ELSE PRINT '[SKIP] sla_vencido ja existe';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- Nota de operação
-- ═══════════════════════════════════════════════════════════════════════════
-- As colunas nascem NULL para o que já está no espelho. O sync roda a cada
-- 15 min e faz MERGE por sys_id, então a fila viva se completa sozinha no
-- próximo ciclo. Chamado JÁ ENCERRADO antes desta migration continua sem
-- descrição para sempre: ele não volta na consulta do grupo (o filtro é por
-- assignment_group e a fila ativa), e o espelho não reprocessa histórico.
-- Para a triagem isso é indiferente — ela olha a fila viva.
--
-- ⚠️ DEPOIS DO DEPLOY: esta migration acompanha mudança em dags/utils/. O
-- worker do Airflow CACHEIA esse módulo — sem restart do worker, o ciclo
-- segue gravando as colunas antigas e as novas ficam NULL, com a task VERDE
-- (o mesmo falso verde documentado na PR #313).
