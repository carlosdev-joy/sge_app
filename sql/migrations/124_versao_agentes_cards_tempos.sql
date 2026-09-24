-- sql/migrations/124_versao_agentes_cards_tempos.sql
-- Registra a VERSÃO desta entrega em Admin › Versões — mesmo formato da 123
-- (a convenção: cada entrega leva a sua migration de versão).
--
--   • Entrega PEQUENA (ajustes): +1 no TERCEIRO número (2.3.0 → 2.3.1). Entrega
--     de funcionalidade nova sobe o segundo (como a 123).
--   • Número: a maior versão numérica já registrada (1 a 4 partes, comparadas
--     como números — a mesma regra do cabeçalho). Sem nenhuma, parte de 2.2.0.
--   • Idempotente (roda 2×): o título desta entrega é a chave — já registrada,
--     nada muda (nem o número). Editar/excluir depois continua pela aba.
--   • Sincroniza app_version/app_release_name em etl_app_config, como o
--     "Nova Versão" da aba faz (routers/infra.py, register_versao).
--
-- Um lote só (sem GO): as variáveis não atravessam lotes. Etapa 6c do deploy.sh.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Agentes: escolha em cards e tempos da consulta a banco';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    DECLARE @maior INT, @menor INT, @patch INT, @nova NVARCHAR(20);

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
    SELECT TOP 1 @maior = a, @menor = b, @patch = c
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
        SELECT @maior = 2, @menor = 2, @patch = 0;
    SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Escolha do agente em cards

- Ao abrir **Agentes**, cada agente liberado aparece num card com o nome, a descrição e o que ele consulta (DataStage, banco ou só conversa).
- O card marca o agente **usado por último** e a **conversa em andamento**; com 6 agentes ou mais aparece a **busca** (nome, descrição ou tipo).
- No chat, **Trocar agente** volta aos cards (o "voltar" do navegador também).

## Tempos da consulta a banco

- Em Admin › Agentes › Gateway e limites: **Tempo para conectar ao banco** (5 a 60 s, padrão 10) e **Tempo máximo de cada consulta** (5 a 120 s, padrão 30).
- Quando o servidor não responde no tempo, a mensagem diz quanto o Orquestra esperou.

Detalhes: `docs/release-notes/agentes-banco.md`.', 'deploy');

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
