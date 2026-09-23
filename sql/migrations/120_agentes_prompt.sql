-- sql/migrations/120_agentes_prompt.sql
-- A1 da spec docs/spec-agentes-admin.md §3.2: versões do bloco de DOMÍNIO do
-- prompt de cada agente, editadas pelo admin na tela (Admin › Agentes).
--
-- Só ACRESCENTA (append-only): gravar cria a versão seguinte; restaurar grava
-- o texto antigo como versão NOVA (`origem_versao` aponta de onde veio).
-- Nenhuma linha é atualizada nem apagada — é o histórico de auditoria de um
-- texto que carrega regras de comportamento do agente. A versão ATIVA é a de
-- MAIOR número; sem linha nenhuma, vale o padrão do código
-- (`services/agentes.PROMPT_DOMINIO_PADRAO`, a "versão 0") — não se grava
-- semente: o padrão acompanha as PRs.
--
-- O UNIQUE (agente_id, versao) barra duas gravações simultâneas com o mesmo
-- número: quem perde recebe 409 `prompt_mudou` (services/agentes_prompt.py).
--
-- Idempotente (roda 2×): IF OBJECT_ID(...) IS NULL. Sem índice filtrado
-- (gotcha do QUOTED_IDENTIFIER). Datas em GETDATE() (BRT), como a 117.
-- Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_agente_prompt', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_prompt (
        id              INT IDENTITY(1,1) NOT NULL,
        agente_id       VARCHAR(40)    NOT NULL,  -- id do catálogo (largura de etl_agente_conversa.agente)
        versao          INT            NOT NULL,  -- 1, 2, 3… por agente; a ativa é a MAIOR
        texto           NVARCHAR(MAX)  NOT NULL,  -- só o bloco de domínio (os fixos são do código)
        motivo          NVARCHAR(200)  NOT NULL,  -- obrigatório: por que mudou
        origem_versao   INT            NULL,      -- preenchido quando a versão é uma restauração
        criado_em       DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_prompt_criado DEFAULT GETDATE(),
        criado_por      VARCHAR(20)    NOT NULL,  -- matrícula do admin
        CONSTRAINT PK_etl_agente_prompt PRIMARY KEY (id),
        CONSTRAINT UQ_etl_agente_prompt_versao UNIQUE (agente_id, versao)
    );
    PRINT '[OK] Tabela etl_agente_prompt criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_prompt ja existe';
GO
