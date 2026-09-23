-- ═══════════════════════════════════════════════════════════════════════════
-- 119 — Semente da base de aprendizados do agente DataStage (F6 da spec
--       docs/spec-agentes-datastage.md)
-- ═══════════════════════════════════════════════════════════════════════════
--
-- O QUE FAZ: insere 5 aprendizados iniciais em `etl_agente_aprendizado` — o
-- que já se sabe sobre o ambiente (o erro real de produção da D-12 e as
-- regras conhecidas de nome, allowlist, istool e SFTP).
--
-- ESTADO `rascunho`: pela B-12, a lista inicial é aprovada pelo CURADOR
-- antes de o agente usar. Rascunho nunca entra no contexto do modelo; o
-- curador a valida na aba Curadoria da tela Agentes.
--
-- SÓ DADOS, nenhuma estrutura: as tabelas vieram na 117.
--
-- IDEMPOTENTE: cada linha só entra se a assinatura ainda não existe para o
-- agente (`UNIQUE (agente, assinatura)` da 117). Rodar duas vezes não
-- duplica nada nem desfaz a decisão do curador. As assinaturas são
-- sha256("semente|<slug>") em hex minúsculo — o mesmo cálculo de
-- `agentes_aprendizado.assinatura("semente", slug)` (preso por teste).
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_agente_aprendizado', 'U') IS NOT NULL
BEGIN
    DECLARE @semente TABLE (
        tipo       VARCHAR(20),
        assinatura CHAR(64),
        titulo     NVARCHAR(200),
        corpo      NVARCHAR(2000),
        evidencia  NVARCHAR(MAX)
    );

    INSERT INTO @semente (tipo, assinatura, titulo, corpo, evidencia) VALUES
    ('erro', '57d04b557f57ae920bfcb78458f0cac09d6d005b93f88995b2b16e5ba02303c1',
     N'XML da definição do job inválido na extração ISX',
     N'Quando a extração ISX falha com "XML da definição do job inválido (reference to invalid character number…)", '
     + N'a definição do job tem um caractere inválido. Não tente extrair de novo: informe o usuário que o job '
     + N'precisa ser corrigido no DataStage Designer, e use dsjob (lstages/lparams) ou o DSX para responder.',
     N'Semente da spec — D-12, erro real de produção validado em 21/09/2026.'),

    ('busca', '0e2b3a4b624e58dfbbb70a9b3e067a3fde4f04c83c880ee28ce1b293b72abf1b',
     N'Nomes de job e de projeto são sensíveis a maiúsculas/minúsculas',
     N'No DataStage, JobX e jobx são jobs diferentes, e o mesmo vale para projetos. Use a grafia exata; se o '
     + N'usuário escrever com outra caixa, confirme com ele a grafia cadastrada antes de consultar o servidor.',
     N'Semente da spec — regra conhecida do DataStage (memória do projeto: nome de job case-sensitive).'),

    ('leitura', '24a887ddc63240b89a9d9fdb84a91ccfec2cb85f001e3e461f6f2dd8a6706f04',
     N'O dsjob do agente só tem ljobs, lstages, lparams, jobinfo e report',
     N'Os logs de execução (logsum/logdetail) ficam fora de propósito, porque podem conter valores de dados. '
     + N'Não peça esses comandos; para entender o fluxo use lstages, lparams e report, ou a extração ISX.',
     N'Semente da spec — allowlist em código (B-03).'),

    ('acesso', '0b826619bfe41c96959bcd2279b7c5cf74ce38071b3afbc52bcd1e1eca3fd2c7',
     N'O authfile do istool aceita caminho com ~/',
     N'Se a extração ISX reclamar do authfile do istool, o caminho configurado em DS_ISTOOL_AUTHFILE pode usar '
     + N'~/ (home do usuário do SSH). É configuração do administrador, não do usuário que pergunta.',
     N'Semente da spec — configuração conhecida da extração ISX.'),

    ('acesso', '90a683a59d684ce39253ff7e848423f390836d1faad59d8547f183e1f108dd71',
     N'As pastas SFTP do DataStage não têm ISX nem DSX úteis',
     N'As raízes /Projetos/BI_CVP/Scripts e /Projetos/BI_CVP não guardam ISX nem DSX para mapeamento. Para '
     + N'detalhar um job use a base, o DSX local, o dsjob ou a extração ISX.',
     N'Semente da spec — D-11 validada em produção em 21/09/2026 (SFTP fora do v1).');

    INSERT INTO dbo.etl_agente_aprendizado (agente, tipo, assinatura, titulo, corpo, evidencia, origem, estado)
    SELECT 'datastage', s.tipo, s.assinatura, s.titulo, s.corpo, s.evidencia, 'semente', 'rascunho'
    FROM @semente s
    WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_agente_aprendizado a
                      WHERE a.agente = 'datastage' AND a.assinatura = s.assinatura);

    PRINT '[OK] 119: ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' aprendizado(s) de semente inserido(s) como rascunho';
END
ELSE
    PRINT '[SKIP] 119: etl_agente_aprendizado nao existe (migration 117 pendente)';
GO
