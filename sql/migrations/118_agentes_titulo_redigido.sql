-- ═══════════════════════════════════════════════════════════════════════════
-- 118 — Limpa os títulos de conversa gravados ANTES da redação (F4 da spec
--       docs/spec-agentes-datastage.md)
-- ═══════════════════════════════════════════════════════════════════════════
--
-- O QUE ACONTECEU: até a F4, `POST /agentes/datastage/conversar` gravava o
-- título da conversa a partir da mensagem CRUA (`mensagem[:200]`), enquanto
-- `af.redigir` só rodava depois, para o corpo. Um segredo digitado na
-- PRIMEIRA pergunta ia em claro para `etl_agente_conversa.titulo`.
--
-- POR QUE PASSOU DESPERCEBIDO: até a F4 o título não era lido por ninguém —
-- não havia tela de histórico. A F4 o transforma no rótulo da conversa na
-- lista E no campo que a busca varre (`AND titulo LIKE ? ESCAPE '\'`).
--
-- POR QUE UMA MIGRATION: a correção no código só vale para o que vier
-- depois. As linhas gravadas entre o deploy da F1/F2/F3 (22/09/2026) e este
-- deploy continuam com o texto cru em repouso — no banco, nos backups e nos
-- planos de execução. É exatamente o que o critério 5 da F4 existe para
-- evitar, e não há como redigir em T-SQL: a lógica de `redigir()` é Python.
--
-- O QUE FAZ: zera o título (NULL) de toda conversa existente no momento em
-- que esta migration roda. A tela mostra "Conversa sem título" para elas; a
-- conversa em si, as mensagens (que SEMPRE foram gravadas redigidas) e o
-- projeto resolvido continuam intactos e retomáveis. O custo é cosmético e
-- recai sobre poucas conversas — a feature entrou em produção no mesmo dia.
--
-- IDEMPOTENTE: roda duas vezes sem efeito diferente. A 2ª execução não acha
-- título não-nulo criado ANTES desta migration, porque a marca de corte é a
-- própria existência da coluna de controle (ver abaixo) — e, se ela já
-- existe, nada mais é zerado.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_agente_conversa', 'U') IS NULL
BEGIN
    PRINT '[SKIP] 118: etl_agente_conversa nao existe (migration 117 pendente)';
END
ELSE
BEGIN
    -- Marca de corte: uma vez gravada, esta migration não zera mais nada.
    -- Sem ela, reaplicar a migration apagaria títulos LEGÍTIMOS (já
    -- redigidos) criados depois — e toda migration deste repo roda 2x.
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'agentes_titulo_redigido_em')
    BEGIN
        DECLARE @afetadas INT;
        UPDATE dbo.etl_agente_conversa SET titulo = NULL WHERE titulo IS NOT NULL;
        SET @afetadas = @@ROWCOUNT;

        INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
        VALUES ('agentes_titulo_redigido_em', CONVERT(VARCHAR(19), GETDATE(), 120),
                'F4: marca de corte da limpeza de titulos gravados antes da redacao',
                'migration_118', GETDATE());

        PRINT '[OK] 118: titulos anteriores a redacao zerados: ' + CAST(@afetadas AS VARCHAR(10));
    END
    ELSE
        PRINT '[SKIP] 118: titulos ja haviam sido zerados (agentes_titulo_redigido_em presente)';
END
GO
