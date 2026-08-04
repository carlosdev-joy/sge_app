-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 082 — SEGURAR o Aguarde (hold do ponto de junção)
--   O Aguarde é açúcar de compilação: ligar as pernas vira dependência normal
--   na 067, e quem segura é o predicado de liberação. Não havia como dizer
--   "pare AQUI e não solte até eu mandar" — o operador só conseguia isso
--   inativando os pipelines à frente, que mexe no cadastro de cada um.
--
--   `retido_em` marca o nó SEGURADO: enquanto estiver preenchido, nenhuma
--   dependência compilada por ele libera — em TODAS as portas, porque quem
--   consulta é o predicado canônico (push, guardiã e o painel herdam juntos).
--   `retido_por` é a matrícula de quem segurou, para o card e a auditoria.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_malha_no', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha_no', 'retido_em') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha_no ADD retido_em DATETIME NULL;
    PRINT '[OK] Coluna dbo.etl_malha_no.retido_em criada';
END
GO

IF OBJECT_ID('dbo.etl_malha_no', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha_no', 'retido_por') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha_no ADD retido_por NVARCHAR(64) NULL;
    PRINT '[OK] Coluna dbo.etl_malha_no.retido_por criada';
END
GO
