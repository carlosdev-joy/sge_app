-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 067 — Dependências entre pipelines no modelo Control-M (F1)
--
-- PROBLEMA QUE RESOLVE (QA de 2026-07-31, docs/spec-dependencias-pipelines.md):
--   • Não existe NENHUMA noção de "a que dia de processamento uma execução
--     pertence". Um pipeline que começa 31/07 23:30 e outro que começa 01/08
--     00:40 podem ser a MESMA corrida de negócio — hoje não há como dizer isso.
--   • `depends_on` é um CSV sem integridade: nada impede depender de um pipeline
--     que não existe, e o typo vira espera infinita em produção.
--   • Não existe tabela de execução no nível PIPELINE (só etl_job_execution, que
--     é por job), então não dá para perguntar "o predecessor concluiu na data X?".
--
-- O QUE ESTA MIGRATION FAZ: só o MODELO. Nada muda na execução — a troca do
--   ExternalTaskSensor pelo disparo por condição é a F3 da spec.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) Execução no nível PIPELINE ──────────────────────────────────────────
-- Hoje só existe etl_job_execution (nível JOB) e o status de pipeline do
-- dashboard é agregação. Para "o predecessor concluiu na data de referência X?"
-- ser uma pergunta barata e sem ambiguidade, o pipeline precisa de execução
-- própria.
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_pipeline_execucao (
        id               BIGINT IDENTITY(1,1) NOT NULL
                         CONSTRAINT PK_etl_pipeline_execucao PRIMARY KEY,
        pipeline_name    NVARCHAR(200) NOT NULL,
        -- ODATE do Control-M: a que dia de processamento esta corrida pertence.
        -- NÃO é a data do relógio — ver dags/utils/data_referencia.py.
        data_referencia  DATE          NOT NULL,
        execution_id     VARCHAR(50)   NULL,   -- run_id do Airflow
        -- AGUARDANDO_DEPENDENCIA | EXECUTANDO | SUCESSO | FALHA | PULADO | NAO_LIBEROU
        status           VARCHAR(30)   NOT NULL,
        inicio           DATETIME2     NULL,
        fim              DATETIME2     NULL,
        -- pipeline pai que fez o push, ou 'agenda' | 'manual' | 'guardia'
        disparado_por    NVARCHAR(200) NULL,
        motivo           VARCHAR(500)  NULL,
        criado_em        DATETIME2     NOT NULL DEFAULT GETDATE(),
        atualizado_em    DATETIME2     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_pipe_exec_pipeline FOREIGN KEY (pipeline_name)
            REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_pipeline_execucao criada';
END
ELSE
    PRINT '[--] etl_pipeline_execucao ja existe';
GO

-- Um pipeline com horários específicos roda VÁRIAS vezes no mesmo dia: a chave
-- inclui o execution_id. A avaliação da condição usa a execução mais recente
-- daquela data de referência (regra documentada na spec §6, risco 6).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_pipe_exec'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
BEGIN
    CREATE UNIQUE INDEX ux_pipe_exec ON dbo.etl_pipeline_execucao
        (pipeline_name, data_referencia, execution_id);
    PRINT '[OK] indice ux_pipe_exec criado';
END
ELSE
    PRINT '[--] indice ux_pipe_exec ja existe';
GO

-- Leitura quente: "o predecessor P concluiu com sucesso na data D?"
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_pipe_exec_cond'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
BEGIN
    CREATE INDEX ix_pipe_exec_cond ON dbo.etl_pipeline_execucao
        (pipeline_name, data_referencia, status, inicio);
    PRINT '[OK] indice ix_pipe_exec_cond criado';
END
ELSE
    PRINT '[--] indice ix_pipe_exec_cond ja existe';
GO

-- ── (B) Dependência em tabela (sucessora do CSV etl_pipeline.depends_on) ────
-- As duas FKs são o ponto central: com elas fica IMPOSSÍVEL cadastrar
-- dependência para um pipeline que não existe — hoje isso é aceito e vira
-- espera infinita.
--
-- NVARCHAR(200) e não VARCHAR: precisa casar exatamente com o tipo de
-- etl_pipeline.pipeline_name, senão o SQL Server recusa a FK.
IF OBJECT_ID('dbo.etl_pipeline_dependencia', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_pipeline_dependencia (
        id            INT IDENTITY(1,1) NOT NULL
                      CONSTRAINT PK_etl_pipeline_dependencia PRIMARY KEY,
        pipeline_name NVARCHAR(200) NOT NULL,   -- o dependente
        depende_de    NVARCHAR(200) NOT NULL,   -- o predecessor
        -- ── Reservado para a feature FUTURA de dependência job → job entre
        -- pipelines (backlog garantido, spec §9). Nasce aqui de propósito: com
        -- as colunas prontas, aquela feature é preenchimento + UI, sem migration
        -- destrutiva nem retrabalho de modelo.
        tipo          VARCHAR(20)   NOT NULL
                      CONSTRAINT DF_dep_tipo DEFAULT 'PIPELINE',  -- PIPELINE | JOB
        job_origem    NVARCHAR(200) NULL,
        job_destino   NVARCHAR(200) NULL,
        criado_em     DATETIME2     NOT NULL DEFAULT GETDATE(),
        criado_por    VARCHAR(100)  NULL,
        CONSTRAINT FK_dep_pipeline FOREIGN KEY (pipeline_name)
            REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE,
        -- Sem ON DELETE CASCADE aqui de propósito: apagar um pipeline que é
        -- predecessor de alguém tem de FALHAR, não sumir com a dependência em
        -- silêncio. O cadastro trata o erro e diz quem depende dele.
        CONSTRAINT FK_dep_predecessor FOREIGN KEY (depende_de)
            REFERENCES dbo.etl_pipeline (pipeline_name),
        CONSTRAINT CK_dep_nao_self CHECK (pipeline_name <> depende_de)
    );
    PRINT '[OK] Tabela etl_pipeline_dependencia criada';
END
ELSE
    PRINT '[--] etl_pipeline_dependencia ja existe';
GO

-- job_origem/job_destino entram na chave para a feature futura não colidir:
-- hoje são sempre NULL e a unicidade recai sobre (dependente, predecessor).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_dep'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_dependencia'))
BEGIN
    CREATE UNIQUE INDEX ux_dep ON dbo.etl_pipeline_dependencia
        (pipeline_name, depende_de, tipo, job_origem, job_destino);
    PRINT '[OK] indice ux_dep criado';
END
ELSE
    PRINT '[--] indice ux_dep ja existe';
GO

-- Caminho inverso: "quem depende de mim?" — é a pergunta que o disparo (F3) faz
-- ao fim de cada pipeline.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dep_predecessor'
               AND object_id = OBJECT_ID('dbo.etl_pipeline_dependencia'))
BEGIN
    CREATE INDEX ix_dep_predecessor ON dbo.etl_pipeline_dependencia (depende_de);
    PRINT '[OK] indice ix_dep_predecessor criado';
END
ELSE
    PRINT '[--] indice ix_dep_predecessor ja existe';
GO

-- ── (C) Janela e virada do dia, por pipeline ────────────────────────────────
IF COL_LENGTH('dbo.etl_pipeline', 'hora_virada') IS NULL
BEGIN
    -- NULL = usa a virada global (etl_app_config). Override opt-in, só para
    -- pipeline que atravessa a meia-noite.
    ALTER TABLE dbo.etl_pipeline ADD hora_virada TIME NULL;
    PRINT '[OK] etl_pipeline.hora_virada criada';
END
ELSE
    PRINT '[--] etl_pipeline.hora_virada ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline', 'nao_iniciar_antes') IS NULL
BEGIN
    -- Janela FROM do Control-M: liberado antes disso, espera.
    ALTER TABLE dbo.etl_pipeline ADD nao_iniciar_antes TIME NULL;
    PRINT '[OK] etl_pipeline.nao_iniciar_antes criada';
END
ELSE
    PRINT '[--] etl_pipeline.nao_iniciar_antes ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline', 'hora_limite_dependencia') IS NULL
BEGIN
    -- Deadline OPT-IN (decisão do usuário 2026-07-31: nasce em branco). NULL =
    -- a guardiã não gera JANELA_ESTOUROU para este pipeline. Não herda
    -- sla_minutos: SLA é duração da execução, isto é o horário até o qual a
    -- liberação ainda faz sentido.
    ALTER TABLE dbo.etl_pipeline ADD hora_limite_dependencia TIME NULL;
    PRINT '[OK] etl_pipeline.hora_limite_dependencia criada';
END
ELSE
    PRINT '[--] etl_pipeline.hora_limite_dependencia ja existe';
GO

-- ── (D) Eventos de dependência (padrão da supervisão DataStage) ─────────────
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_dependencia_evento (
        id              BIGINT IDENTITY(1,1) NOT NULL
                        CONSTRAINT PK_etl_dependencia_evento PRIMARY KEY,
        pipeline_name   NVARCHAR(200) NOT NULL,
        data_referencia DATE          NOT NULL,
        -- JANELA_ESTOUROU | DATA_DIVERGENTE | PREDECESSOR_FALHOU
        tipo            VARCHAR(30)   NOT NULL,
        detalhe         VARCHAR(1000) NULL,
        detectado_em    DATETIME2     NOT NULL DEFAULT GETDATE(),
        notificado_em   DATETIME2     NULL,
        CONSTRAINT FK_dep_evento_pipeline FOREIGN KEY (pipeline_name)
            REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_dependencia_evento criada';
END
ELSE
    PRINT '[--] etl_dependencia_evento ja existe';
GO

-- Um evento por (pipeline, data, tipo): é o que impede o ciclo de 5 min da
-- guardiã de reenviar o mesmo card a cada passagem.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_dep_evento'
               AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    CREATE UNIQUE INDEX ux_dep_evento ON dbo.etl_dependencia_evento
        (pipeline_name, data_referencia, tipo);
    PRINT '[OK] indice ux_dep_evento criado';
END
ELSE
    PRINT '[--] indice ux_dep_evento ja existe';
GO

-- ── (E) Virada global do dia ────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'dependencia_hora_virada')
BEGIN
    -- 00:00 preserva EXATAMENTE o comportamento atual (data de referência = data
    -- do calendário). Decisão do usuário em 2026-07-31: nenhum pipeline muda de
    -- data ao subir esta migration; quem atravessa a meia-noite recebe override
    -- individual em etl_pipeline.hora_virada.
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('dependencia_hora_virada', '00:00',
            'Hora de virada do dia de processamento (ODATE). A partir dela, as execucoes passam a pertencer ao dia seguinte. 00:00 = data do calendario. Override por pipeline em etl_pipeline.hora_virada.');
    PRINT '[OK] config dependencia_hora_virada semeada com 00:00';
END
ELSE
    PRINT '[--] config dependencia_hora_virada ja existe';
GO

-- ── (F) Carga a partir do CSV depends_on existente ──────────────────────────
-- ÓRFÃOS SÃO IGNORADOS E LOGADOS, nunca fazem a migration falhar: um
-- depends_on apontando para pipeline inexistente é justamente o defeito que
-- esta migration existe para tornar impossível daqui em diante — abortar aqui
-- derrubaria a etapa 6c do deploy por causa de um dado ruim que já estava lá.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_dependencia)
BEGIN
    DECLARE @pares TABLE (dependente NVARCHAR(200), predecessor NVARCHAR(200));

    -- Split manual em vez de STRING_SPLIT: a função exige compatibility level
    -- >= 130 e NÃO é usada em nenhum outro ponto deste schema — descobrir aqui
    -- que o banco está abaixo disso abortaria a etapa 6c do deploy. O laço
    -- abaixo roda em qualquer versão.
    -- @csv com folga sobre o NVARCHAR(2000) de depends_on: a sentinela abaixo
    -- concatena uma vírgula, e no limite exato a truncagem silenciosa comeria o
    -- último predecessor da lista.
    DECLARE @nome NVARCHAR(200), @csv NVARCHAR(2100), @item NVARCHAR(200), @pos INT;
    DECLARE cp CURSOR LOCAL FAST_FORWARD FOR
        SELECT pipeline_name, depends_on FROM dbo.etl_pipeline
        WHERE depends_on IS NOT NULL AND LTRIM(RTRIM(depends_on)) <> '';
    OPEN cp;
    FETCH NEXT FROM cp INTO @nome, @csv;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @csv = @csv + ',';           -- sentinela: fecha o último item
        SET @pos = CHARINDEX(',', @csv);
        WHILE @pos > 0
        BEGIN
            SET @item = LTRIM(RTRIM(SUBSTRING(@csv, 1, @pos - 1)));
            -- Descarta vazio e auto-dependência (o CHECK da tabela recusaria).
            IF @item <> '' AND @item <> @nome
                INSERT INTO @pares (dependente, predecessor) VALUES (@nome, @item);
            SET @csv = SUBSTRING(@csv, @pos + 1, LEN(@csv));
            SET @pos = CHARINDEX(',', @csv);
        END
        FETCH NEXT FROM cp INTO @nome, @csv;
    END
    CLOSE cp; DEALLOCATE cp;

    -- Relatório de órfãos ANTES de inserir (o que não vai entrar, e por quê).
    DECLARE @orfaos INT = (
        SELECT COUNT(*) FROM @pares x
        WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline p2 WHERE p2.pipeline_name = x.predecessor));

    IF @orfaos > 0
    BEGIN
        PRINT '[!!] depends_on apontando para pipeline INEXISTENTE (ignorados):';
        DECLARE @d NVARCHAR(200), @p NVARCHAR(200);
        DECLARE c CURSOR LOCAL FAST_FORWARD FOR
            SELECT x.dependente, x.predecessor FROM @pares x
            WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline p2 WHERE p2.pipeline_name = x.predecessor);
        OPEN c; FETCH NEXT FROM c INTO @d, @p;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            PRINT '     ' + @d + ' -> ' + @p + '  (corrija no cadastro)';
            FETCH NEXT FROM c INTO @d, @p;
        END
        CLOSE c; DEALLOCATE c;
    END

    INSERT INTO dbo.etl_pipeline_dependencia (pipeline_name, depende_de, criado_por)
    SELECT DISTINCT x.dependente, x.predecessor, 'migration_067'
    FROM @pares x
    WHERE EXISTS (SELECT 1 FROM dbo.etl_pipeline p2 WHERE p2.pipeline_name = x.predecessor);

    PRINT '[OK] dependencias migradas do depends_on: ' + CAST(@@ROWCOUNT AS VARCHAR(10))
          + ' | ignoradas por predecessor inexistente: ' + CAST(@orfaos AS VARCHAR(10));
END
ELSE
    PRINT '[--] etl_pipeline_dependencia ja tem dados — carga nao repetida';
GO

-- O CSV etl_pipeline.depends_on CONTINUA sendo escrito em espelho até a F6:
-- Malha.tsx e o gerador de DAGs ainda leem dele. A tabela é a fonte da verdade
-- a partir de agora; a F6 aposenta o CSV.
PRINT '[--] depends_on mantido em espelho ate a F6 (Malha.tsx e dag_factory ainda leem)';
GO
