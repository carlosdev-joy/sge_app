-- sql/migrations/121_agentes_cadastro.sql
-- B1 da spec docs/spec-agentes-admin.md §4.1: agentes criados pela tela
-- (Admin › Agentes). O DataStage NÃO entra aqui — continua no CATALOGO do
-- código (services/agentes.py), com os interruptores que já tem (T3).
--
--   1. dbo.etl_agente — o cadastro. Id é um slug que nunca é reaproveitado:
--      desativar é `ativo = 0`; não existe exclusão (conversas, propostas e
--      aprendizados do agente ficam). O prompt de cada agente mora em
--      dbo.etl_agente_prompt (migration 120), versão 1 gravada na criação.
--   2. dbo.etl_agente_fato.agente — quem PROPÔS uma interpretação aprovada.
--      A `origem` continua 'interpretacao_aprovada' (VARCHAR(30), comparada
--      por igualdade exata em services/agentes_conhecimento.py).
--
-- Idempotente (roda 2×): IF OBJECT_ID / IF COL_LENGTH. Sem índice filtrado
-- (gotcha do QUOTED_IDENTIFIER). Datas em GETDATE() (BRT), como a 117.
-- Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_agente', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente (
        -- slug ^[a-z][a-z0-9_]{2,29}$ — 30 no máximo para `agente_<slug>_curador`
        -- (45) caber em etl_usuario_permissao.recurso VARCHAR(50)
        agente_id         VARCHAR(30)    NOT NULL,
        nome              NVARCHAR(100)  NOT NULL,
        descricao         NVARCHAR(500)  NOT NULL,
        acesso            VARCHAR(10)    NOT NULL,  -- 'manual' | 'perfil'
        perfis_json       NVARCHAR(200)  NOT NULL,  -- ex.: '["desenvolvedor"]'; a API exige ≥1 (vazio = ninguém usa)
        ferramentas_json  NVARCHAR(400)  NOT NULL,  -- '[]' = só conversa; senão subconjunto da allowlist
        ativo             BIT            NOT NULL CONSTRAINT DF_etl_agente_ativo DEFAULT 0,
        criado_em         DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_criado DEFAULT GETDATE(),
        criado_por        VARCHAR(20)    NOT NULL,
        atualizado_em     DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_atualizado DEFAULT GETDATE(),
        atualizado_por    VARCHAR(20)    NOT NULL,
        CONSTRAINT PK_etl_agente PRIMARY KEY (agente_id),
        CONSTRAINT CK_etl_agente_acesso CHECK (acesso IN ('manual', 'perfil'))
    );
    PRINT '[OK] Tabela etl_agente criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente ja existe';
GO

IF COL_LENGTH('dbo.etl_agente_fato', 'agente') IS NULL
BEGIN
    ALTER TABLE dbo.etl_agente_fato ADD agente VARCHAR(40) NULL;
    PRINT '[OK] Coluna etl_agente_fato.agente criada';
END
ELSE
    PRINT '[SKIP] Coluna etl_agente_fato.agente ja existe';
GO
