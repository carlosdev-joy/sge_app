-- sql/migrations/110_maestro.sql
-- Maestro — assistente conversacional de parâmetros DataStage
-- (spec docs/spec-maestro-parametros.md, F1).
--
-- O usuário descreve o cenário na seção "Parâmetros do job" (Etapas/Fluxos) e o
-- Maestro diz como preencher cada campo. Duas tabelas:
--
--   dbo.etl_maestro_cenario  — o CATÁLOGO do que o Maestro pode prometer,
--     mantido pelo administrador (F3). Semeado aqui com os cenários mais comuns;
--     `receita_json` são parâmetros-modelo no vocabulário de
--     services/job_params (nomes entre <> são marcadores que o Maestro troca
--     pelos nomes que o job declara). Fora do catálogo e do vocabulário →
--     "procure o administrador".
--   dbo.etl_maestro_conversa — uma linha por rodada de conversa: o que o
--     usuário pediu, o que o Maestro respondeu, o status (atendido |
--     nao_atendido | pergunta | erro) e a proposta validada. NUNCA guarda valor
--     de parâmetro Encrypted. `tratado_em` é o administrador marcando que viu
--     um pedido não atendido (F3).
--
-- Interruptor próprio em dbo.etl_app_config (`maestro_enabled`, padrão '0');
-- o provedor de IA é o já configurado em Admin › Caixa Seguro IA (caixa_ia_*).
--
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_maestro_cenario', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_maestro_cenario (
        id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_maestro_cenario PRIMARY KEY,
        codigo         VARCHAR(40)   NOT NULL,
        titulo         NVARCHAR(120) NOT NULL,
        descricao      NVARCHAR(600) NOT NULL,       -- quando usar (o Maestro lê)
        receita_json   NVARCHAR(MAX) NOT NULL,       -- {"params":[...], "exemplos":[...]}
        ativo          BIT           NOT NULL CONSTRAINT DF_etl_maestro_cenario_ativo DEFAULT 1,
        criado_em      DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_maestro_cenario_em DEFAULT GETDATE(),
        criado_por     NVARCHAR(100) NULL,
        atualizado_em  DATETIME2(0)  NULL,
        atualizado_por NVARCHAR(100) NULL,
        CONSTRAINT UQ_etl_maestro_cenario_codigo UNIQUE (codigo)
    );
    PRINT '[OK] Tabela dbo.etl_maestro_cenario criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_maestro_cenario ja existe';
GO

IF OBJECT_ID('dbo.etl_maestro_conversa', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_maestro_conversa (
        id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_maestro_conversa PRIMARY KEY,
        conversa_id    VARCHAR(36)   NOT NULL,       -- uuid gerado no front (agrupa as rodadas)
        matricula      VARCHAR(20)   NOT NULL,       -- largura de dbo.etl_usuario.matricula
        pipeline_name  NVARCHAR(200) NULL,           -- larguras da 109
        job_name       NVARCHAR(200) NULL,
        mensagem       NVARCHAR(MAX) NOT NULL,
        resposta       NVARCHAR(MAX) NULL,
        status         VARCHAR(20)   NOT NULL,       -- atendido | nao_atendido | pergunta | erro
        cenario_codigo VARCHAR(40)   NULL,
        proposta_json  NVARCHAR(MAX) NULL,           -- validada pela régua; sem valor Encrypted
        motivo         NVARCHAR(600) NULL,           -- por que não atendeu (ou o erro)
        modelo         VARCHAR(100)  NULL,
        duracao_ms     INT           NULL,
        tratado_em     DATETIME2(0)  NULL,           -- admin viu o pedido não atendido
        tratado_por    VARCHAR(20)   NULL,
        criado_em      DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_maestro_conversa_em DEFAULT GETDATE()
    );
    PRINT '[OK] Tabela dbo.etl_maestro_conversa criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_maestro_conversa ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_maestro_conversa_conversa'
               AND object_id = OBJECT_ID('dbo.etl_maestro_conversa'))
BEGIN
    CREATE INDEX IX_etl_maestro_conversa_conversa
        ON dbo.etl_maestro_conversa (conversa_id, criado_em);
    PRINT '[OK] IX_etl_maestro_conversa_conversa criado';
END
ELSE
    PRINT '[SKIP] IX_etl_maestro_conversa_conversa ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_maestro_conversa_usuario'
               AND object_id = OBJECT_ID('dbo.etl_maestro_conversa'))
BEGIN
    CREATE INDEX IX_etl_maestro_conversa_usuario
        ON dbo.etl_maestro_conversa (matricula, criado_em DESC);
    PRINT '[OK] IX_etl_maestro_conversa_usuario criado';
END
ELSE
    PRINT '[SKIP] IX_etl_maestro_conversa_usuario ja existe';
GO

-- A lista do administrador: pedidos não atendidos ainda sem tratamento.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_maestro_conversa_pedidos'
               AND object_id = OBJECT_ID('dbo.etl_maestro_conversa'))
BEGIN
    CREATE INDEX IX_etl_maestro_conversa_pedidos
        ON dbo.etl_maestro_conversa (status, tratado_em, criado_em DESC);
    PRINT '[OK] IX_etl_maestro_conversa_pedidos criado';
END
ELSE
    PRINT '[SKIP] IX_etl_maestro_conversa_pedidos ja existe';
GO

-- Interruptor (desligado até o administrador ligar — exige o provedor de IA
-- configurado, mesma regra dos assistentes do Caixa).
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'maestro_enabled')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('maestro_enabled', '0', 'Maestro — assistente de parâmetros DataStage (Etapas/Fluxos)', 'migration_110', GETDATE());
    PRINT '[OK] maestro_enabled = 0';
END
ELSE
    PRINT '[SKIP] maestro_enabled ja existe';
GO

-- ── Semente do catálogo ──────────────────────────────────────────────────────
-- Uma guarda por código: o administrador pode editar/desativar sem que uma
-- reexecução da migration desfaça a mudança. As receitas usam SÓ o vocabulário
-- de services/job_params (tests/test_maestro_servico.py valida cada uma).

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'mensal_anterior')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'mensal_anterior', N'Carga mensal do mês anterior',
        N'Dois parâmetros de data: o primeiro e o último dia do mês anterior à data de referência da corrida. Vale em qualquer dia do mês (o deslocamento de meses vem antes da âncora, então 31/03 vira 28/02).',
        N'{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-1,"param_ancora":"inicio_mes","param_offset_dias":0,"param_formato":"%Y-%m-%d"},{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-1,"param_ancora":"fim_mes","param_offset_dias":0,"param_formato":"%Y-%m-%d"}],"exemplos":["carga mensal do mês anterior com data inicial e final","processar o mês passado inteiro"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'mes_corrente')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'mes_corrente', N'Mês corrente até a referência',
        N'Acumulado do mês: do primeiro dia do mês da data de referência até a própria data de referência.',
        N'{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":"inicio_mes","param_offset_dias":0,"param_formato":"%Y-%m-%d"},{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":null,"param_offset_dias":0,"param_formato":"%Y-%m-%d"}],"exemplos":["do início do mês até a data de referência","acumulado do mês corrente"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'diario_referencia')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'diario_referencia', N'Carga diária da data de referência',
        N'Um parâmetro com a própria data de referência da corrida (a ODATE definida na agenda), sem deslocamento.',
        N'{"params":[{"param_name":"<DATA>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":null,"param_offset_dias":0,"param_formato":"%Y-%m-%d"}],"exemplos":["passar a data de referência para o job","carga diária do dia"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'diario_d1')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'diario_d1', N'Dia anterior (D-1)',
        N'A data de referência menos um dia — o "ontem" da corrida. Para D-2, dias = -2.',
        N'{"params":[{"param_name":"<DATA>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":null,"param_offset_dias":-1,"param_formato":"%Y-%m-%d"}],"exemplos":["processar o dia anterior","carga D-1"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'semanal_anterior')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'semanal_anterior', N'Semana anterior (segunda a domingo)',
        N'Segunda-feira e domingo da semana anterior à da data de referência (âncora na semana e depois -7 dias).',
        N'{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":"inicio_semana","param_offset_dias":-7,"param_formato":"%Y-%m-%d"},{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":0,"param_ancora":"fim_semana","param_offset_dias":-7,"param_formato":"%Y-%m-%d"}],"exemplos":["carga semanal da semana passada","segunda a domingo da semana anterior"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'trimestre_anterior')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'trimestre_anterior', N'Trimestre anterior',
        N'Primeiro e último dia do trimestre anterior ao da data de referência.',
        N'{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-3,"param_ancora":"inicio_trimestre","param_offset_dias":0,"param_formato":"%Y-%m-%d"},{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-3,"param_ancora":"fim_trimestre","param_offset_dias":0,"param_formato":"%Y-%m-%d"}],"exemplos":["fechamento do trimestre anterior","carga trimestral"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'ano_anterior')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'ano_anterior', N'Ano anterior',
        N'1º de janeiro e 31 de dezembro do ano anterior ao da data de referência.',
        N'{"params":[{"param_name":"<DATA_INICIAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-12,"param_ancora":"inicio_ano","param_offset_dias":0,"param_formato":"%Y-%m-%d"},{"param_name":"<DATA_FINAL>","param_type":"Date","param_source":"data_referencia","param_offset_meses":-12,"param_ancora":"fim_ano","param_offset_dias":0,"param_formato":"%Y-%m-%d"}],"exemplos":["carga anual do ano passado","fechamento do ano anterior"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'competencia_aaaamm')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'competencia_aaaamm', N'Competência AAAAMM do mês anterior',
        N'Um parâmetro String com ano e mês (AAAAMM) do mês anterior à referência — a competência. Para a competência do próprio mês, meses = 0.',
        N'{"params":[{"param_name":"<COMPETENCIA>","param_type":"String","param_source":"data_referencia","param_offset_meses":-1,"param_ancora":null,"param_offset_dias":0,"param_formato":"%Y%m"}],"exemplos":["competência do mês anterior no formato AAAAMM","ano e mês da competência"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'rastreio_run_id')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'rastreio_run_id', N'Run id da corrida',
        N'Parâmetro String que recebe o run_id do Airflow, para o job gravar de qual corrida veio cada linha (rastreabilidade).',
        N'{"params":[{"param_name":"<RUN_ID>","param_type":"String","param_source":"run_id"}],"exemplos":["gravar o identificador da execução nas linhas carregadas","passar o run id para o job"]}',
        'migration_110');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_maestro_cenario WHERE codigo = 'caminho_fixo')
BEGIN
    INSERT INTO dbo.etl_maestro_cenario (codigo, titulo, descricao, receita_json, criado_por) VALUES (
        'caminho_fixo', N'Caminho fixo de arquivo ou pasta',
        N'Parâmetro Pathname com um caminho absoluto, igual em toda execução (sem ~, sem espaços, sem aspas).',
        N'{"params":[{"param_name":"<CAMINHO>","param_type":"Pathname","param_source":"fixo","param_value":"/dados/entrada"}],"exemplos":["passar a pasta de entrada dos arquivos","caminho fixo do arquivo"]}',
        'migration_110');
END
GO
