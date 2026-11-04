-- sql/migrations/197_agente_terminal.sql
-- F2 da spec docs/spec-agente-terminal.md: auditoria do agente "Terminal".
-- Uma linha por comando que o Claude PROPÕE ou executa no servidor — leitura,
-- escrita (com confirmação) e bloqueado — com quem pediu, o que rodou e o que
-- aconteceu. O texto do comando e o resumo da saída entram JÁ REDIGIDOS
-- (services/agentes_ferramentas.redigir): nunca segredo em claro aqui.
--
-- Idempotente (roda 2×): IF OBJECT_ID/IF NOT EXISTS em cada bloco. SEM índice
-- filtrado (WHERE) — gotcha do QUOTED_IDENTIFIER (migration 117).
-- Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_agente_terminal_cmd', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_terminal_cmd (
        cmd_id        UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_etl_agente_terminal_cmd_id DEFAULT NEWID(),
        conversa_id   VARCHAR(36)    NULL,       -- dbo.etl_agente_conversa.conversa_id (sem FK: a auditoria sobrevive à purga da conversa)
        matricula     VARCHAR(20)    NOT NULL,   -- quem PEDIU (largura de dbo.etl_usuario.matricula)
        servidor      VARCHAR(60)    NOT NULL,   -- id de services/ssh_arquivos.SERVIDORES
        comando       NVARCHAR(2000) NOT NULL,   -- já redigido; cortar por UTF-16 (cortar_utf16)
        hash          CHAR(64)       NOT NULL,   -- SHA-256 do comando que o usuário VIU (a confirmação confere este hash)
        classe        VARCHAR(10)    NOT NULL,   -- leitura | escrita | proibido (decidido pelo backend, nunca pela IA)
        estado        VARCHAR(12)    NOT NULL,   -- proposto | executando | executado | falhou | recusado | expirado | bloqueado
        motivo        NVARCHAR(500)  NULL,       -- por que o Claude quer rodar / por que foi bloqueado
        codigo_saida  INT            NULL,
        duracao_ms    INT            NULL,
        saida_resumo  NVARCHAR(4000) NULL,       -- só um resumo, já redigido
        ip            VARCHAR(45)    NULL,
        redigido      BIT            NOT NULL CONSTRAINT DF_etl_agente_terminal_cmd_redigido DEFAULT 0,  -- o texto mostrado difere do pedido (havia segredo)
        criado_em     DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_terminal_cmd_criado DEFAULT GETDATE(),
        expira_em     DATETIME2(0)   NULL,       -- só em `proposto`
        decidido_por  VARCHAR(20)    NULL,       -- quem confirmou/recusou (a mesma pessoa que pediu)
        decidido_em   DATETIME2(0)   NULL,
        executado_em  DATETIME2(0)   NULL,
        CONSTRAINT PK_etl_agente_terminal_cmd PRIMARY KEY (cmd_id),
        CONSTRAINT CK_etl_agente_terminal_cmd_classe CHECK (classe IN ('leitura', 'escrita', 'proibido')),
        CONSTRAINT CK_etl_agente_terminal_cmd_estado CHECK (estado IN
            ('proposto', 'executando', 'executado', 'falhou', 'recusado', 'expirado', 'bloqueado')),
        -- Coerência classe × estado (a máquina de estados está em services/agentes_terminal.py):
        -- proibido <=> bloqueado; proposto/recusado/expirado só existem para escrita; comando com
        -- segredo redigido só pode ser proibido (nunca é executado nem "confirmado").
        CONSTRAINT CK_etl_agente_terminal_cmd_bloqueio CHECK
            ((classe = 'proibido' AND estado = 'bloqueado') OR (classe <> 'proibido' AND estado <> 'bloqueado')),
        CONSTRAINT CK_etl_agente_terminal_cmd_escrita CHECK (estado NOT IN ('proposto', 'recusado', 'expirado') OR classe = 'escrita'),
        CONSTRAINT CK_etl_agente_terminal_cmd_segredo CHECK (redigido = 0 OR classe = 'proibido')
    );
    PRINT '[OK] Tabela etl_agente_terminal_cmd criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_terminal_cmd ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_terminal_cmd_usuario' AND object_id = OBJECT_ID('dbo.etl_agente_terminal_cmd'))
BEGIN
    CREATE INDEX IX_etl_agente_terminal_cmd_usuario
        ON dbo.etl_agente_terminal_cmd (matricula, criado_em DESC);
    PRINT '[OK] Indice IX_etl_agente_terminal_cmd_usuario criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_terminal_cmd_usuario ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_terminal_cmd_conversa' AND object_id = OBJECT_ID('dbo.etl_agente_terminal_cmd'))
BEGIN
    CREATE INDEX IX_etl_agente_terminal_cmd_conversa
        ON dbo.etl_agente_terminal_cmd (conversa_id);
    PRINT '[OK] Indice IX_etl_agente_terminal_cmd_conversa criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_terminal_cmd_conversa ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_terminal_cmd_estado' AND object_id = OBJECT_ID('dbo.etl_agente_terminal_cmd'))
BEGIN
    CREATE INDEX IX_etl_agente_terminal_cmd_estado
        ON dbo.etl_agente_terminal_cmd (estado, criado_em DESC);
    PRINT '[OK] Indice IX_etl_agente_terminal_cmd_estado criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_terminal_cmd_estado ja existe';
GO
