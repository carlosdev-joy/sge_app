-- 177: contrato de alertas principais F7; versão idempotente, sem transporte.
DECLARE @titulo NVARCHAR(200) = N'Contrato de alertas do pipeline e prévia sem envio';

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
    SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Contrato de alertas do pipeline e prévia sem envio

- Política de alertas integra o rascunho e a versão imutável, sem editor separado.
- Prévia autorizada mostra E-mail, Teams pessoal e canal adicional, sem resolver identidade nem enviar mensagem.
- Contrato de evento separa resultado, geração de ciclo e identidade de entrega; leitura conserva política original da corrida.
- Novos pipelines começam com canais desabilitados; configurações e tarefas legadas permanecem preservadas.
- Fonte agregada de Warning e geração de reprocesso ainda não certificadas; emissões ficam indisponíveis até os adapters das próximas fases.
', 'deploy');

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

GO

-- Gate concreto identificado no adapter; não marcar emissões disponíveis na F7.
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — gate de alertas não registrado';
ELSE IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Alertas principais: certificar resultado agregado e geração de reprocesso')
    INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
    VALUES (N'Alertas principais: certificar resultado agregado e geração de reprocesso',
            N'Gate EOC-F9: factory registra SUCESSO/FALHA por run e Clear reutiliza a linha; falta Warning agregado confirmado e geração operacional confiável. Não emitir evento principal por contagem UI nem erro de transporte. Antes do dispatcher, fornecer autoridade/timestamp/geração reais e preservar policyRevision do vínculo original, mesmo após publicação posterior. Contrato e limites: docs/eoc-f7-contrato-alertas.md. F7 oferece apenas preview sem envio.',
            N'spike', N'backend', N'P1', N'refinado', N'EOC-F7,EOC-F9,alertas', N'eoc-f7');
GO
