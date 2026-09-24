-- sql/migrations/123_versao_agentes_banco.sql
-- Registra a VERSÃO desta entrega em Admin › Versões (dbo.etl_versao_ferramenta) —
-- o número do cabeçalho do Orquestra é a MAIOR versão registrada ali
-- (ui-react/src/lib/version.ts), e até aqui só entrava à mão, pela aba.
--
--   • Número: a maior versão numérica já registrada (1 a 4 partes, comparadas
--     como números — a mesma regra do cabeçalho), com +1 no segundo número
--     (2.4.1 → 2.5.0; 2.9 < 2.10 → 2.11.0; 3 → 3.1.0). Sem nenhuma registrada,
--     parte de 2.2.0 (a última release note numerada, docs/release-notes/v2.2.0.md)
--     → 2.3.0.
--   • Idempotente (roda 2×): o título desta entrega é a chave — já registrada,
--     nada muda (nem o número). Editar/excluir depois continua pela aba.
--   • Sincroniza app_version/app_release_name em etl_app_config, como o
--     "Nova Versão" da aba faz (routers/infra.py, register_versao).
--
-- Um lote só (sem GO): as variáveis não atravessam lotes. Etapa 6c do deploy.sh.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Agentes pela tela e consulta a banco';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    DECLARE @maior INT, @menor INT, @nova NVARCHAR(20);

    -- Só versões numéricas de 1 a 4 partes ("3", "2.2", "2.4.1", "2.4.1.7"),
    -- completadas para 4 partes; o resto é ignorado.
    ;WITH v AS (
        SELECT versao + REPLICATE('.0', 3 - (LEN(versao) - LEN(REPLACE(versao, '.', '')))) AS v4
          FROM dbo.etl_versao_ferramenta
         WHERE versao NOT LIKE '%[^0-9.]%' AND versao NOT LIKE '%..%'
           AND versao NOT LIKE '.%' AND versao NOT LIKE '%.' AND versao <> ''
           AND LEN(versao) - LEN(REPLACE(versao, '.', '')) BETWEEN 0 AND 3
    ), n AS (
        SELECT TRY_CONVERT(INT, PARSENAME(v4, 4)) AS a, TRY_CONVERT(INT, PARSENAME(v4, 3)) AS b,
               TRY_CONVERT(INT, PARSENAME(v4, 2)) AS c, TRY_CONVERT(INT, PARSENAME(v4, 1)) AS d
          FROM v
    )
    SELECT TOP 1 @maior = a, @menor = b
      FROM n
     WHERE a IS NOT NULL AND b IS NOT NULL AND c IS NOT NULL AND d IS NOT NULL
     ORDER BY a DESC, b DESC, c DESC, d DESC;

    -- Versão fora do padrão (sufixo "-hotfix", 5+ partes, espaço) é ignorada aqui,
    -- mas o cabeçalho a compara com parseInt: avisa no log do deploy, para o admin
    -- conferir o número em Admin › Versões.
    IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta
                WHERE versao LIKE '%[^0-9.]%' OR versao LIKE '%..%' OR versao LIKE '.%' OR versao LIKE '%.'
                   OR LEN(versao) - LEN(REPLACE(versao, '.', '')) > 3)
        PRINT '[ATENÇÃO] há versões fora do padrão em etl_versao_ferramenta (ignoradas no cálculo) — confira o número em Admin › Versões';

    IF @maior IS NULL
        SELECT @maior = 2, @menor = 2;
    SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Agentes pela tela

- **Prompt editável:** em Admin › Agentes, o administrador edita as instruções do domínio de cada agente, com versões, motivo, histórico e restauração. Vale na pergunta seguinte, sem deploy.
- **Criar agentes:** só de conversa, com parte das ferramentas do DataStage ou com a consulta a banco; acesso manual ou por perfil; nascem desligados.
- **Vigência das versões do prompt:** de quando a quando valeu, quanto tempo, quantas respostas e o tempo médio.

## Consulta a banco

- Os agentes criados pela tela consultam os **bancos liberados** pelo administrador, entre as conexões SQL Server já cadastradas — vários servidores e vários bancos.
- **Só SELECT**, mesmo que o login da conexão possa gravar: análise da consulta, conferência pelo plano do próprio SQL Server e transação sempre desfeita.
- Até **100 linhas** e **30 s** por consulta; dados pessoais mascarados por padrão.
- No chat, cada SQL aparece num bloco **Consulta SQL**, com realce e **Copiar**, e em **Consultas executadas** (banco, linhas e tempo).

Detalhes: `docs/release-notes/agentes-admin.md` e `docs/release-notes/agentes-banco.md`.', 'deploy');

    -- O mesmo que o "Nova Versão" da aba faz.
    IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
    BEGIN
        UPDATE dbo.etl_app_config SET config_value = @nova WHERE config_key = 'app_version';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_version', @nova);
        UPDATE dbo.etl_app_config SET config_value = @titulo WHERE config_key = 'app_release_name';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_release_name', @titulo);
    END

    PRINT CONCAT('[OK] versão ', @nova, ' registrada: ', @titulo);
END
