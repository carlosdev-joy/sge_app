-- 185: Teams pessoal F11; Idempotente — seguro para rodar mais de uma vez.
DECLARE @titulo NVARCHAR(200) = N'Teams pessoal — provider e administração';

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
    VALUES (@nova, @titulo, N'## Teams pessoal corporativo

- Resolução corporativa exata, instalação pessoal e provider autenticado.
- Aceitação pelo transporte não confirma recebimento; erro não muda execução.
- Configuração e referência Connector cifradas, administração e lookup sem envio.
- Dispatcher permanece fixture-only e desligado; sem cutover dos legados.
- Envio real depende de destino de teste autorizado; autoridade e cutover são gates.
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

IF OBJECT_ID('dbo.etl_backlog','U') IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo=N'Teams pessoal: homologar tenant e concluir integração operacional')
    INSERT dbo.etl_backlog (titulo,descricao,tipo,area,prioridade,status,tags,criado_por)
    VALUES (N'Teams pessoal: homologar tenant e concluir integração operacional',
    N'EOC-F11 technical_delivered_activation_pending. Provider OAuth single-tenant/Connector REST e configuração/referência Fernet via API admin. Externos: tenant/app/catalog/consentimento/instalação/referência confiável e destinatário real de teste autorizado; não houve envio ou recibo real. Internos antes de ativar e atéF13: integração do snapshot/dispatcher/tentativa durável/fence/cutover F9/F10 e formulário administrativo no padrão existente. Readiness administrativo não habilita delivery. Sem Graph app-only para chat nem permissão de migração; Unknown sem retry cego, Accepted não é Received.',
    N'spike',N'backend',N'P1',N'refinado',N'EOC-F11,teams,activation-gate',N'eoc-f11');
GO
