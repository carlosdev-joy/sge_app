-- sql/migrations/126_versao_admin_reestruturado.sql
-- Registra a VERSÃO desta entrega em Admin › Versões — mesmo formato da 123/124/125
-- (a convenção: cada entrega leva a sua migration de versão).
--
--   • Entrega de FUNCIONALIDADE NOVA (docs/spec-admin-reestruturacao.md, F1–F6):
--     +1 no SEGUNDO número, zerando o terceiro (2.3.2 → 2.4.0), como a 123.
--     Ajuste pequeno sobe o terceiro (124/125).
--   • Número: a maior versão numérica já registrada (1 a 4 partes, comparadas
--     como números — a mesma regra do cabeçalho). Sem nenhuma, parte de 2.2.0.
--   • Idempotente (roda 2×): o título desta entrega é a chave — já registrada,
--     nada muda (nem o número). Editar/excluir depois continua pela aba.
--   • Sincroniza app_version/app_release_name em etl_app_config, como o
--     "Nova Versão" da aba faz (routers/infra.py, register_versao).
--
-- Um lote só (sem GO): as variáveis não atravessam lotes. Etapa 6c do deploy.sh.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Admin reorganizado: sub-menu, busca e link por aba';

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
    VALUES (@nova, @titulo, N'## Admin reorganizado

O Admin deixou de ser uma fileira de 24 abas: agora tem um **sub-menu lateral com 6 grupos por assunto** — **Acesso**, **Inteligência Artificial**, **Comunicação**, **Integrações & Dados**, **Pipelines & Ambiente** e **Sistema**. No celular, o sub-menu vira um botão seletor no topo.

- **Busca no admin:** digite o assunto (e-mail, agentes, calendário) ou o **nome de um parâmetro** (`email_remetente`, `teams_webhook_url`) e o sub-menu mostra a aba certa. A tecla **/** leva direto à busca.
- **Link por aba:** cada aba tem endereço próprio (`/admin/<grupo>/<aba>`) e botão **Copiar link**; o F5 mantém a aba. Ao abrir o Admin, você volta à **última aba visitada**. Links antigos continuam funcionando.
- **⌘K (Ctrl+K):** a busca geral ganhou o grupo **Administração** — "e-mail" leva a Comunicação › E-mail.

### Onde foram parar as coisas
- **Usuários & Perfis** virou três abas em Acesso: **Usuários**, **Perfis e Permissões** e **Roles do Airflow**.
- **Triagem de chamados** saiu de ServiceNow e foi para **Inteligência Artificial**.
- A sonda de descoberta virou a seção **Diagnóstico** em Integrações & Dados › **ServiceNow**.
- O **webhook padrão** e o "Testar Webhook" estão em Comunicação › **Teams**.
- **Servidor** e **Monitoramento** viraram uma aba só: **Bancos & Monitoramento**.
- O **Relatório SLA** agora é a seção "Aderência ao SLA", no fim de **Performance**.
- O **guia de acessos do Power BI** é a seção "Como liberar acessos", no fim da tela **Power BI**.
- O **Fluxo DS** saiu do Admin: use a aba Fluxo (XML) do **Console DataStage**.
- **Configurações** virou Sistema › **Parâmetros avançados** e mostra só as chaves **sem tela própria**; as demais são gravadas na aba do assunto (a busca leva até ela).

Detalhes: `docs/MANUAL_USUARIO.md` §4 e `docs/release-notes/admin-reestruturacao.md`.', 'deploy');

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
