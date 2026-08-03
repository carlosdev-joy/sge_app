-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 075 — Nós especiais da malha: Início · Aguarde · Notificação · Fim
--                 (F10 do desenho docs/malha-componentes-desenho.md §1)
--
-- O QUE É: o DESENHO dos componentes de malha — nós por malha (etl_malha_no) e
--   as arestas do desenho que envolvem nós (etl_malha_aresta), mais as colunas
--   de ASSINATURA que a compilação (F11/F13) usará como proveniência.
--
-- O QUE NÃO É: orquestração. Os componentes são AÇÚCAR DE COMPILAÇÃO sobre os
--   primitivos existentes — Aguarde compila para linhas NORMAIS da 067
--   (etl_pipeline_dependencia), Início compila para as colunas de agendamento
--   de etl_pipeline, Notificação/Fim viram eventos da guardiã. Nenhuma tabela
--   nova guarda dependência (Decisão 1); nada aqui é lido pelo motor.
--   NESTA fase (F10) nenhuma linha da 067 nasce — a compilação é a F11.
--
-- DECISÕES DE MODELO (§1.2–§1.4 do desenho):
--   • Aresta pipeline→pipeline NÃO entra em etl_malha_aresta (Decisão 2): o
--     CHECK CK_malha_ar_tem_no declara no MODELO que esta não é tabela de
--     dependência — a aresta direta continua sendo o F8, gravada na 067.
--   • FKs e o erro 1785 (lição da 067): o SQL Server recusa DOIS caminhos de
--     cascade para a mesma tabela. Distribuição CONSCIENTE (§1.3):
--       - etl_malha_aresta → etl_malha em NO ACTION (o CASCADE chegaria por
--         dois caminhos: direto e via etl_malha_no → 1785). Exclusão de malha
--         não tem endpoint hoje (inativa-se); se nascer um, a API apaga
--         arestas → nós → membros → malha na MESMA transação, explícito.
--       - origem_no/destino_no → etl_malha_no em NO ACTION nos DOIS (dois
--         cascades para a mesma tabela = 1785): excluir nó é gesto da API que
--         remove as arestas PRIMEIRO — um DELETE de nó por SQL direto com
--         arestas penduradas falha ALTO, nunca leva desenho junto em silêncio.
--       - origem_pipeline CASCADE / destino_pipeline NO ACTION (1 CASCADE +
--         1 NO ACTION é aceito): excluir pipeline que é perna de ENTRADA limpa
--         a aresta (como o membro some da malha, 070); excluir pipeline que é
--         SAÍDA de Aguarde é bloqueado — coerente com FK_dep_predecessor da
--         067, que já bloqueia excluir predecessor referenciado.
--   • Assinaturas origem_no/agenda_no em NO ACTION, nunca SET NULL nem CASCADE
--     (§1.4): CASCADE apagaria dependências reais como efeito colateral mudo;
--     SET NULL transformaria linha compilada em linha "manual" órfã (adoção
--     silenciosa). NO ACTION obriga a descompilação explícita (F11) a remover/
--     transferir as linhas na MESMA transação da exclusão do nó — a ordem
--     certa vira obrigatória no MODELO, não promessa da API.
--
-- Idempotente (OBJECT_ID/COL_LENGTH) — seguro para rodar mais de uma vez.
-- Aplicada na etapa 6c do deploy.sh. Lembrete D40: sql/migrate.py descarta
-- PRINT — a conferência pós-deploy é por SELECT, nunca pelo relatório.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) Nós especiais — DESENHO por malha (não são orquestração) ────────────
IF OBJECT_ID('dbo.etl_malha_no', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_no (
        id          INT IDENTITY(1,1) NOT NULL
                    CONSTRAINT PK_etl_malha_no PRIMARY KEY,
        -- NVARCHAR(200) casa exatamente com etl_malha.malha_name, senão o
        -- SQL Server recusa a FK (mesma lição da 067/070).
        malha_name  NVARCHAR(200) NOT NULL
            CONSTRAINT FK_malha_no_malha REFERENCES dbo.etl_malha (malha_name)
            ON DELETE CASCADE,               -- nó não vive sem a malha (padrão 070)
        tipo        VARCHAR(20)  NOT NULL,   -- 'inicio' | 'aguarde' | 'notificacao' | 'fim'
        -- Configuração por tipo (§5/§6 do desenho); validada na API, padrão do
        -- aguarde_json da 068. A validação RICA do agendamento é a F13.
        config_json NVARCHAR(MAX) NULL,
        layout_x    FLOAT NULL,
        layout_y    FLOAT NULL,
        criado_em   DATETIME2 NOT NULL CONSTRAINT DF_malha_no_criado_em DEFAULT SYSDATETIME(),
        criado_por  NVARCHAR(100) NULL
    );
    PRINT '[OK] Tabela etl_malha_no criada';
END
ELSE
    PRINT '[--] etl_malha_no ja existe';
GO

-- Um Início e um Fim por malha, garantidos no MODELO (índice filtrado), não só
-- na API: o 2º Início leva 422 na API e, num INSERT por SQL direto, estoura
-- aqui — o desenho nunca fica ambíguo sobre quem agenda/conclui a malha.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_malha_no_inicio'
               AND object_id = OBJECT_ID('dbo.etl_malha_no'))
BEGIN
    CREATE UNIQUE INDEX ux_malha_no_inicio ON dbo.etl_malha_no (malha_name)
        WHERE tipo = 'inicio';
    PRINT '[OK] indice ux_malha_no_inicio criado';
END
ELSE
    PRINT '[--] indice ux_malha_no_inicio ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_malha_no_fim'
               AND object_id = OBJECT_ID('dbo.etl_malha_no'))
BEGIN
    CREATE UNIQUE INDEX ux_malha_no_fim ON dbo.etl_malha_no (malha_name)
        WHERE tipo = 'fim';
    PRINT '[OK] indice ux_malha_no_fim criado';
END
ELSE
    PRINT '[--] indice ux_malha_no_fim ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_malha_no_malha'
               AND object_id = OBJECT_ID('dbo.etl_malha_no'))
BEGIN
    CREATE INDEX ix_malha_no_malha ON dbo.etl_malha_no (malha_name);
    PRINT '[OK] indice ix_malha_no_malha criado';
END
ELSE
    PRINT '[--] indice ix_malha_no_malha ja existe';
GO

-- ── (B) Arestas do desenho que envolvem nós ─────────────────────────────────
-- Aresta pipeline→pipeline NÃO entra aqui (Decisão 2 — é o F8, direto na 067);
-- o CHECK CK_malha_ar_tem_no torna isso impossível no modelo.
IF OBJECT_ID('dbo.etl_malha_aresta', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_aresta (
        id               INT IDENTITY(1,1) NOT NULL
                         CONSTRAINT PK_etl_malha_aresta PRIMARY KEY,
        -- NO ACTION (§1.3): o CASCADE viria por DOIS caminhos (direto e via
        -- etl_malha_no) e o SQL Server recusaria com o erro 1785.
        malha_name       NVARCHAR(200) NOT NULL
            CONSTRAINT FK_malha_ar_malha REFERENCES dbo.etl_malha (malha_name),
        -- NO ACTION nos dois lados de nó (dois cascades para a MESMA tabela =
        -- 1785): a exclusão de nó é gesto da API que remove as arestas primeiro.
        origem_no        INT NULL
            CONSTRAINT FK_malha_ar_ono  REFERENCES dbo.etl_malha_no (id),
        -- CASCADE consciente: excluir pipeline que é perna de ENTRADA limpa a
        -- aresta, como o membro some da malha (070).
        origem_pipeline  NVARCHAR(200) NULL
            CONSTRAINT FK_malha_ar_opipe REFERENCES dbo.etl_pipeline (pipeline_name)
            ON DELETE CASCADE,
        destino_no       INT NULL
            CONSTRAINT FK_malha_ar_dno  REFERENCES dbo.etl_malha_no (id),
        -- NO ACTION (1785 — já existe 1 CASCADE para etl_pipeline nesta
        -- tabela): excluir pipeline que é SAÍDA de Aguarde é bloqueado, como o
        -- FK_dep_predecessor da 067 bloqueia excluir predecessor referenciado.
        destino_pipeline NVARCHAR(200) NULL
            CONSTRAINT FK_malha_ar_dpipe REFERENCES dbo.etl_pipeline (pipeline_name),
        -- Cada ponta é exatamente UMA coisa: nó XOR pipeline. (O desenho §1.1
        -- escreve "(a IS NULL) <> (b IS NULL)"; T-SQL não compara predicados
        -- com <>, então o XOR vai expandido — MESMA semântica.)
        CONSTRAINT CK_malha_ar_origem  CHECK (
            (origem_no IS NULL AND origem_pipeline IS NOT NULL) OR
            (origem_no IS NOT NULL AND origem_pipeline IS NULL)),
        CONSTRAINT CK_malha_ar_destino CHECK (
            (destino_no IS NULL AND destino_pipeline IS NOT NULL) OR
            (destino_no IS NOT NULL AND destino_pipeline IS NULL)),
        -- A tabela declara no próprio modelo que NÃO é tabela de dependência:
        -- aresta sem nó nenhum (pipeline→pipeline) é o F8, mora na 067.
        CONSTRAINT CK_malha_ar_tem_no  CHECK (origem_no IS NOT NULL OR destino_no IS NOT NULL)
    );
    PRINT '[OK] Tabela etl_malha_aresta criada';
END
ELSE
    PRINT '[--] etl_malha_aresta ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_malha_aresta'
               AND object_id = OBJECT_ID('dbo.etl_malha_aresta'))
BEGIN
    CREATE UNIQUE INDEX ux_malha_aresta ON dbo.etl_malha_aresta
        (malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline);
    PRINT '[OK] indice ux_malha_aresta criado';
END
ELSE
    PRINT '[--] indice ux_malha_aresta ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_malha_ar_ono'
               AND object_id = OBJECT_ID('dbo.etl_malha_aresta'))
BEGIN
    CREATE INDEX ix_malha_ar_ono ON dbo.etl_malha_aresta (origem_no);
    PRINT '[OK] indice ix_malha_ar_ono criado';
END
ELSE
    PRINT '[--] indice ix_malha_ar_ono ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_malha_ar_dno'
               AND object_id = OBJECT_ID('dbo.etl_malha_aresta'))
BEGIN
    CREATE INDEX ix_malha_ar_dno ON dbo.etl_malha_aresta (destino_no);
    PRINT '[OK] indice ix_malha_ar_dno criado';
END
ELSE
    PRINT '[--] indice ix_malha_ar_dno ja existe';
GO

-- ── (C) Assinatura de proveniência na 067: quem compilou esta dependência ───
-- NULL = linha manual (F1/F5/F8), como todas as de hoje. NO ACTION de
-- propósito (§1.4): a descompilação (F11) remove/transfere as linhas na MESMA
-- transação da exclusão do nó — nunca CASCADE (apagaria dependência real em
-- silêncio) nem SET NULL (adoção silenciosa de linha compilada como manual).
IF COL_LENGTH('dbo.etl_pipeline_dependencia', 'origem_no') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_dependencia ADD origem_no INT NULL
        CONSTRAINT FK_dep_origem_no REFERENCES dbo.etl_malha_no (id);
    PRINT '[OK] etl_pipeline_dependencia.origem_no criada';
END
ELSE
    PRINT '[--] etl_pipeline_dependencia.origem_no ja existe';
GO

-- Filtrado: a maioria das linhas é manual (origem_no NULL) — o índice só
-- carrega as assinadas, que é o que a descompilação e o GET do detalhe leem.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dep_origem_no'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_dependencia'))
BEGIN
    CREATE INDEX ix_dep_origem_no ON dbo.etl_pipeline_dependencia (origem_no)
        WHERE origem_no IS NOT NULL;
    PRINT '[OK] indice ix_dep_origem_no criado';
END
ELSE
    PRINT '[--] indice ix_dep_origem_no ja existe';
GO

-- ── (D) Assinatura de agendamento na raiz: qual Início agenda este pipeline ─
-- Mesmo racional do origem_no (§1.4): NO ACTION — excluir o Início exige a
-- descompilação explícita (F13: raiz vira on_demand + carimbo, Decisão 10).
IF COL_LENGTH('dbo.etl_pipeline', 'agenda_no') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD agenda_no INT NULL
        CONSTRAINT FK_pipe_agenda_no REFERENCES dbo.etl_malha_no (id);
    PRINT '[OK] etl_pipeline.agenda_no criada';
END
ELSE
    PRINT '[--] etl_pipeline.agenda_no ja existe';
GO

-- ── (E) Agendamento da malha — FONTE DE COMPILAÇÃO ──────────────────────────
-- O MOTOR NUNCA LÊ DAQUI: o agendamento real continua sendo as colunas de
-- etl_pipeline (que o gerador de DAGs lê). Este JSON é a cópia-mestre que a
-- compilação do Início (F13) COPIA para as colunas reais das raízes — schema
-- validado pelas MESMAS funções do register (padrão aguarde_json/068).
IF COL_LENGTH('dbo.etl_malha', 'agendamento_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha ADD agendamento_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_malha.agendamento_json criada';
END
ELSE
    PRINT '[--] etl_malha.agendamento_json ja existe';
GO
