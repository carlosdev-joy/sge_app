-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 085 — CORRIDA DE MALHA (docs/spec-malha-execucao.md §5.3, fase F1)
--
--   O ciclo da malha deixa de ser inferido por quatro reguas incompativeis e
--   passa a ser UM REGISTRO: aberto pelo Inicio (ou pelo disparo), fechado
--   pelo Fim (ou por quiescencia/teto), carregando o ODATE do ciclo, o
--   instante de abertura e o desfecho.
--
--   Esta migration entrega SO O MODELO. Nenhum leitor, nenhum escritor: o
--   motor e a API so passam a usar estas colunas nas fases F2+, e sempre
--   atras do interruptor etl_app_config.malha_corrida_ativa, que nasce em 0.
--
--   Colunas que so a F7 usa (teto_em, teto_creditado_min, etl_malha.teto_horas)
--   nascem aqui DE PROPOSITO: migration aplicada nao se altera — migrate.py
--   registra por NOME em etl_schema_version e nunca revalida o checksum, entao
--   editar a 085 depois de aplicada e no-op silencioso em todo ambiente que ja
--   a rodou. Correcao vira 086.
--
--   Idempotente — seguro para rodar mais de uma vez (etapa 6c do deploy.sh).
--   Conferencia por SELECT (spec §12.1) — migrate.py descarta PRINT (D40).
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 0. As 7 SET options exigidas por INDICE FILTRADO ───────────────────────
-- Esta migration cria os PRIMEIROS indices filtrados do projeto, e um indice
-- filtrado impoe as opcoes abaixo tanto no CREATE quanto em todo INSERT/
-- UPDATE/DELETE da tabela (erro 1934, "SET options have incorrect settings").
--
-- Medido no dev (2026-08-04): sqlcmd e pyodbc/msodbcsql chegam com ARITHABORT
-- OFF; so o pymssql do worker chega com ele ON. As tres conexoes funcionam
-- assim mesmo porque ANSI_WARNINGS ON implica ARITHABORT ON a partir do
-- compatibility level 90 — o dev esta em 150. Este bloco existe para que a
-- migration NAO dependa do compatibility level do banco da Caixa: num banco
-- em nivel 80 o CREATE INDEX filtrado falharia, abortando a etapa 6c no meio
-- do deploy. As opcoes valem so para esta sessao.
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;
GO

-- ── 0b. A guarda que o SET acima NAO consegue dar ──────────────────────────
-- O bloco acima protege ESTA sessao. O que ele nao alcanca sao as conexoes de
-- RUNTIME: com um indice filtrado na tabela, TODO INSERT/UPDATE/DELETE dela
-- passa a exigir as mesmas 7 opcoes, e etl_pipeline_execucao e caminho quente
-- do motor E da API.
--
-- Medicao no dev (2026-08-04): o pymssql do worker chega com ARITHABORT ON;
-- o pyodbc/msodbcsql18 da API e o sqlcmd chegam com ARITHABORT OFF. As duas
-- ultimas so escrevem porque ANSI_WARNINGS ON implica ARITHABORT ON a partir
-- do compatibility level 90. Abaixo de 90 a implicacao some, e a 085 —
-- que deveria ser inerte — quebraria em producao TODA escrita de
-- etl_pipeline_execucao feita pela API, com o erro 1934, em features que ja
-- existem hoje. Preferimos abortar a etapa 6c nomeando a causa a descobrir
-- isso as 3h. NOEXEC impede que o resto do arquivo seja aplicado pela metade.
IF (SELECT compatibility_level FROM sys.databases WHERE database_id = DB_ID()) < 90
BEGIN
    RAISERROR ('085 ABORTADA: o compatibility level deste banco e menor que 90 e a 085 cria indices FILTRADOS. Abaixo de 90, ANSI_WARNINGS ON deixa de implicar ARITHABORT ON e toda escrita em etl_pipeline_execucao pela conexao pyodbc da API passaria a falhar com o erro 1934. Suba o compatibility level para 100 ou mais, ou faca a aplicacao emitir SET ARITHABORT ON na abertura da conexao, e rode a 085 de novo.', 16, 1);
    SET NOEXEC ON;
END
GO

-- ── 1. A corrida ───────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_execucao (
        id                  BIGINT IDENTITY(1,1) NOT NULL,
        -- SEM FK para etl_malha (Decisao 5): (i) etl_malha -> corrida ->
        -- etl_pipeline_execucao colidiria com o ON DELETE CASCADE que a 067 ja
        -- tem, e o SQL Server recusa com o erro 1785 (multiplos caminhos de
        -- cascade); (ii) a FK tornaria a malha indeletavel enquanto houvesse
        -- historico. Precedente literal na casa: a 076 DERRUBOU a FK de
        -- etl_dependencia_evento para que historico nao morra com cadastro.
        malha_name          NVARCHAR(200) NOT NULL,
        data_referencia     DATE          NOT NULL,  -- o ODATE, carimbado UMA vez
        sequencia           INT           NOT NULL,  -- rotulo humano: "2a corrida de 04/08"
        status              VARCHAR(20)   NOT NULL,
        aberta_em           DATETIME2     NOT NULL CONSTRAINT DF_mexec_ab DEFAULT SYSDATETIME(),
        fechada_em          DATETIME2     NULL,      -- NULL <=> ABERTA (CK abaixo)
        fechada_por         NVARCHAR(200) NULL,      -- 'guardia' | 'manual:C123456'
        origem              VARCHAR(20)   NOT NULL,  -- inicio|manual|implicita
        aberta_por          NVARCHAR(200) NULL,      -- 'inicio:#12' | 'manual:C123456'
        ancora_pipeline     NVARCHAR(200) NULL,      -- a raiz cuja linha ancorou a abertura
        -- VARCHAR, nao NVARCHAR: tem de casar com etl_pipeline_execucao.
        -- execution_id, que a 072 criou como varchar(250) (conferido em
        -- sys.columns, nao no papel). Com NVARCHAR de um lado, o
        -- `WHERE execution_id = @ancora` da F2 converteria a COLUNA — NVARCHAR
        -- tem precedencia — e o predicado deixaria de ser sargavel: scan da
        -- maior tabela do schema, num caminho que roda a cada 5 min por malha.
        ancora_execution_id VARCHAR(250)  NULL,      -- casa com etl_pipeline_execucao.execution_id (072)
        no_inicio           INT           NULL,      -- etl_malha_no.id (INT), sem FK: mesma razao da Decisao 5
        no_fim              INT           NULL,
        modo_fechamento     VARCHAR(20)   NOT NULL,  -- fim | quiescencia (§6.5)
        teto_em             DATETIME2     NULL,      -- aberta_em + teto_horas (§6.6)
        -- Fato acumulado e imutavel ("quanto tempo ja foi creditado por hold").
        -- "esta retido" e fato do AGORA e por isso NAO se materializa aqui:
        -- espelho dessincroniza — com dois Aguardes segurados, soltar UM
        -- limparia o espelho e o teto voltaria a correr com a malha travada.
        teto_creditado_min  INT           NOT NULL CONSTRAINT DF_mexec_cred DEFAULT 0,
        -- Memoria de EFEITO COLATERAL, nao estado: existem so para o ciclo de
        -- 5 min da guardia nao repetir o mesmo evento/card.
        falha_vista_em      DATETIME2     NULL,
        atraso_visto_em     DATETIME2     NULL,
        tentativas          INT           NOT NULL CONSTRAINT DF_mexec_tent DEFAULT 1,
        reaberta_em         DATETIME2     NULL,
        reaberta_por        NVARCHAR(200) NULL,
        motivo              NVARCHAR(500) NULL,
        criado_em           DATETIME2     NOT NULL CONSTRAINT DF_mexec_cri DEFAULT SYSDATETIME(),
        atualizado_em       DATETIME2     NOT NULL CONSTRAINT DF_mexec_atu DEFAULT SYSDATETIME(),
        CONSTRAINT PK_etl_malha_execucao PRIMARY KEY CLUSTERED (id),
        CONSTRAINT CK_mexec_status CHECK (status IN
            ('ABERTA','CONCLUIDA','FALHA','SEM_TRABALHO','EXPIRADA',
             'ABORTADA','CANCELADA')),
        -- A invariante em forma de CHECK: "aberta" e "sem fechada_em" sao a
        -- MESMA coisa. Sem ela, o indice filtrado abaixo e o status poderiam
        -- discordar — a trava de disparo leria um e a tela leria o outro.
        CONSTRAINT CK_mexec_coerente CHECK (
            (status =  'ABERTA' AND fechada_em IS     NULL) OR
            (status <> 'ABERTA' AND fechada_em IS NOT NULL)),
        CONSTRAINT CK_mexec_modo   CHECK (modo_fechamento IN ('fim','quiescencia')),
        CONSTRAINT CK_mexec_origem CHECK (origem IN ('inicio','manual','implicita'))
    );
    PRINT '[OK] Tabela dbo.etl_malha_execucao criada';
END
ELSE
    PRINT '[--] dbo.etl_malha_execucao ja existe';
GO

-- Um GO por indice, e nao um bloco so: erro no primeiro aborta o BATCH, e o
-- indice seguinte nunca seria criado — em silencio, porque migrate.py so ve a
-- excecao do batch inteiro.

-- A INVARIANTE "um ciclo aberto por malha" mora no MODELO, nao na API.
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_malha_exec_aberta'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_malha_exec_aberta
        ON dbo.etl_malha_execucao (malha_name) WHERE fechada_em IS NULL;
    PRINT '[OK] Indice ux_malha_exec_aberta criado';
END
ELSE
    PRINT '[--] Indice ux_malha_exec_aberta nao criado (ja existe ou tabela ausente)';
GO

-- Card da lista: um SEEK por malha (a composicao em Python some).
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ix_malha_exec_malha'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_malha_exec_malha
        ON dbo.etl_malha_execucao (malha_name, aberta_em DESC)
        INCLUDE (id, status, data_referencia, fechada_em, sequencia);
    PRINT '[OK] Indice ix_malha_exec_malha criado';
END
ELSE
    PRINT '[--] Indice ix_malha_exec_malha nao criado (ja existe ou tabela ausente)';
GO

-- Lente por data do painel + o rotulo humano da N-esima corrida do dia.
-- E um indice DIFERENTE do de abertura, e o tratamento da violacao e OPOSTO
-- (Decisao 7): ux_malha_exec_aberta = "outra ponta abriu primeiro, adira a
-- ela"; ux_malha_exec_seq = "recalcule a sequencia e tente de novo".
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_malha_exec_seq'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_malha_exec_seq
        ON dbo.etl_malha_execucao (malha_name, data_referencia, sequencia);
    PRINT '[OK] Indice ux_malha_exec_seq criado';
END
ELSE
    PRINT '[--] Indice ux_malha_exec_seq nao criado (ja existe ou tabela ausente)';
GO

-- ── 2. O snapshot do denominador ───────────────────────────────────────────
-- Congelado na abertura, FORA do caminho quente: "quem esta corrida espera
-- para fechar" e do desenho, e N:N, e muda quando alguem edita a malha. O
-- denominador do card nao pode mudar embaixo de uma corrida em andamento.
IF OBJECT_ID('dbo.etl_malha_execucao_membro', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_execucao_membro (
        malha_execucao_id BIGINT        NOT NULL,
        pipeline_name     NVARCHAR(200) NOT NULL,
        conta_para_fim    BIT           NOT NULL,  -- upstream expandido do no Fim
        ativo_na_abertura BIT           NOT NULL,  -- etl_pipeline.active na abertura
        eh_raiz           BIT           NOT NULL,  -- sem predecessor DENTRO da malha
        CONSTRAINT PK_etl_malha_exec_membro
            PRIMARY KEY CLUSTERED (malha_execucao_id, pipeline_name),
        -- A UNICA FK que fica (Decisao 5): o snapshot PERTENCE a corrida e
        -- morre com ela. Nao ha segundo caminho de cascade aqui.
        CONSTRAINT FK_mexec_membro_corrida FOREIGN KEY (malha_execucao_id)
            REFERENCES dbo.etl_malha_execucao (id) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela dbo.etl_malha_execucao_membro criada';
END
ELSE
    PRINT '[--] dbo.etl_malha_execucao_membro ja existe';
GO

-- "De quais corridas este pipeline e membro?" — a pergunta do membro
-- compartilhado entre N malhas. Em bloco PROPRIO, com guarda por sys.indexes:
-- dentro do CREATE TABLE ele nunca nasceria num banco que ja tem a tabela e
-- perdeu o indice (execucao parcial), e a perda seria silenciosa.
IF OBJECT_ID('dbo.etl_malha_execucao_membro', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ix_mexec_membro_pipe'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao_membro'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_mexec_membro_pipe
        ON dbo.etl_malha_execucao_membro (pipeline_name, malha_execucao_id);
    PRINT '[OK] Indice ix_mexec_membro_pipe criado';
END
ELSE
    PRINT '[--] Indice ix_mexec_membro_pipe nao criado (ja existe ou tabela ausente)';
GO

-- ── 3. O vinculo na corrida de PIPELINE ────────────────────────────────────
-- PROVENIENCIA, nao participacao (Decisao 1): "de onde veio o ODATE desta
-- linha". Nasce NULL, e NULL significa "fora de corrida" — literalmente
-- verdade para todo o legado, por isso nao ha backfill (Decisao 4).
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_pipeline_execucao', 'malha_execucao_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_execucao ADD malha_execucao_id BIGINT NULL;
    PRINT '[OK] Coluna dbo.etl_pipeline_execucao.malha_execucao_id criada';
END
ELSE
    PRINT '[--] dbo.etl_pipeline_execucao.malha_execucao_id nao criada (ja existe ou tabela ausente)';
GO

-- FILTRADO de proposito: todo o legado e NULL, entao o indice nasce VAZIO e
-- cresce so com o que a feature produz. Um indice nao-filtrado aqui indexaria
-- a historia inteira por um valor nulo.
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_pipeline_execucao', 'malha_execucao_id') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ix_pipe_exec_malha'
                     AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_pipe_exec_malha
        ON dbo.etl_pipeline_execucao (malha_execucao_id)
        INCLUDE (pipeline_name, status, data_referencia, inicio, fim,
                 substituida_em)
        WHERE malha_execucao_id IS NOT NULL;
    PRINT '[OK] Indice ix_pipe_exec_malha criado';
END
ELSE
    PRINT '[--] Indice ix_pipe_exec_malha nao criado (ja existe, coluna ou tabela ausente)';
GO

-- ── 4. Idempotencia do evento POR CORRIDA ──────────────────────────────────
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_dependencia_evento', 'malha_execucao_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_dependencia_evento ADD malha_execucao_id BIGINT NULL;
    PRINT '[OK] Coluna dbo.etl_dependencia_evento.malha_execucao_id criada';
END
ELSE
    PRINT '[--] dbo.etl_dependencia_evento.malha_execucao_id nao criada (ja existe ou tabela ausente)';
GO

-- O indice NOVO nasce ANTES de o velho sair: nunca existe instante sem
-- protecao. Em SQL Server os NULLs sao IGUAIS num indice unico, entao com
-- toda a historia em NULL o indice estendido e EXATAMENTE tao estrito quanto
-- o atual — nao ha de-dup a fazer, e a retrocompatibilidade e por construcao,
-- nao por sorte. (A ordem inversa — dropar e recriar — abriria uma janela em
-- que a guardia, que roda a cada 5 min, poderia inserir a duplicata que faz
-- o CREATE UNIQUE falhar e abortar o deploy na 6c.)
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_dependencia_evento', 'malha_execucao_id') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_dep_evento_corrida'
                     AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_dep_evento_corrida
        ON dbo.etl_dependencia_evento
           (pipeline_name, data_referencia, tipo, malha_execucao_id);
    PRINT '[OK] Indice ux_dep_evento_corrida criado';
END
ELSE
    PRINT '[--] Indice ux_dep_evento_corrida nao criado (ja existe, coluna ou tabela ausente)';
GO

-- O DROP so acontece com o substituto JA presente — a condicao e sobre o
-- indice NOVO, nao sobre o antigo.
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ux_dep_evento_corrida'
                 AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
   AND EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ux_dep_evento'
                 AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    DROP INDEX ux_dep_evento ON dbo.etl_dependencia_evento;
    PRINT '[OK] Indice ux_dep_evento substituido por ux_dep_evento_corrida';
END
ELSE
    PRINT '[--] Indice ux_dep_evento ja substituido (ou tabela ausente)';
GO

-- ── 5. Teto por malha ──────────────────────────────────────────────────────
-- Corrida ABERTA bloqueia o disparo: corrida sem teto congelaria a malha para
-- sempre, sem tela para destravar (§6.6). NULL = usa o padrao global.
IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'teto_horas') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha ADD teto_horas INT NULL;
    PRINT '[OK] Coluna dbo.etl_malha.teto_horas criada';
END
ELSE
    PRINT '[--] dbo.etl_malha.teto_horas nao criada (ja existe ou tabela ausente)';
GO

-- ── 6. Configs (uma por bloco, todas idempotentes) ─────────────────────────
-- ⚠️ T-SQL NAO concatena literais adjacentes (o erro real da 025 e da 083):
-- cada descricao vai numa string SO, sem quebra de linha dentro das aspas.

-- KILL SWITCH. Nasce em 0 e o trem inteiro sobe desligado (Decisao 51): sem
-- ele o rollback da F2 seria "reverter o merge e refazer o ciclo de deploy",
-- as 3h. So vai a 1 depois da F7 e do smoke — o teto e a rede obrigatoria.
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'malha_corrida_ativa')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('malha_corrida_ativa', '0',
            'Liga a corrida de malha (0/1). Com 0 nada abre nem fecha, o card usa o fallback e a data de referencia segue a regra anterior. Ligue somente apos o smoke.');
    PRINT '[OK] etl_app_config.malha_corrida_ativa criada (DESLIGADA)';
END
ELSE
    PRINT '[--] etl_app_config.malha_corrida_ativa ja existe';
GO

-- Teto padrao da corrida, em horas. Dominio 1..168; fora disso o codigo volta
-- ao default (teto 0 expiraria tudo na abertura; teto enorme e o mesmo que
-- nao ter teto, e corrida aberta bloqueia disparo).
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'malha_teto_horas_padrao')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('malha_teto_horas_padrao', '24',
            'Teto padrao da corrida de malha em horas (1 a 168, padrao 24): passado o teto SEM nenhum membro vivo, a corrida vai a EXPIRADA e libera o disparo. Com membro vivo o teto so alarma, nunca fecha. Override por malha em etl_malha.teto_horas.');
    PRINT '[OK] etl_app_config.malha_teto_horas_padrao criada (padrao 24)';
END
ELSE
    PRINT '[--] etl_app_config.malha_teto_horas_padrao ja existe';
GO

-- Carencia de quiescencia = 3 ciclos da guardia (que roda a cada 5 min).
-- Menos que isso fecharia a corrida na janela real entre o commit do SUCESSO
-- e o disparo dos dependentes (_registrar_sucesso commita e SO ENTAO chama
-- _disparar_dependentes). Dominio 5..240.
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'malha_quiescencia_minutos')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('malha_quiescencia_minutos', '15',
            'Carencia de quiescencia em minutos (5 a 240, padrao 15 = 3 ciclos da guardia): tempo sem nenhum membro vivo antes de a corrida de uma malha SEM no Fim poder fechar. Valor baixo fecha a corrida no intervalo entre o sucesso de um membro e o disparo do dependente.');
    PRINT '[OK] etl_app_config.malha_quiescencia_minutos criada (padrao 15)';
END
ELSE
    PRINT '[--] etl_app_config.malha_quiescencia_minutos ja existe';
GO

-- Piso absoluto por aberta_em antes de declarar ABORTADA (Decisao 28): o
-- disparo manual fecha o banco ANTES de chamar o Airflow, e entre o commit e
-- o primeiro EXECUTANDO ha latencia de scheduler, pool saturado, DAG pausada
-- e nao_iniciar_antes. Sem o piso, a guardia abortaria a corrida na janela e
-- o proximo disparo seria liberado por cima da malha rodando. Dominio 1..240.
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'malha_carencia_partida_min')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('malha_carencia_partida_min', '15',
            'Carencia de partida em minutos (1 a 240, padrao 15): tempo minimo desde a abertura antes de uma corrida com ZERO linhas vinculadas poder ser declarada ABORTADA. Cobre a latencia entre o commit da abertura e o primeiro EXECUTANDO das raizes.');
    PRINT '[OK] etl_app_config.malha_carencia_partida_min criada (padrao 15)';
END
ELSE
    PRINT '[--] etl_app_config.malha_carencia_partida_min ja existe';
GO
