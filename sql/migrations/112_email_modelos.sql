-- ============================================================================
-- 112_email_modelos.sql — catálogo de modelos de e-mail
-- Spec: docs/spec-email-modelos-e-navegacao.md (F2)
--
-- O corpo do nó de e-mail deixa de ser campo livre e passa a ser ESCOLHIDO
-- numa lista: os modelos ativos daqui, mais a opção "Corpo livre" (decisão do
-- usuário, 2026-09-11: "exigido com escape").
--
-- O nó guarda `modelo_id` em notify_json e o corpo é lido NO ENVIO — trocar o
-- layout aqui vale para todos os nós, sem republicar DAG e sem reeditar nó.
--
-- ⚠️ IDEMPOTENTE: roda 2x sem quebrar (regra do repo, tests/test_migrations_*).
-- Aplicada na etapa 6c do deploy.sh.
-- ============================================================================

SET NOCOUNT ON;

-- (A) Catálogo -----------------------------------------------------------
IF OBJECT_ID('dbo.etl_email_modelo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_email_modelo (
        id            INT IDENTITY(1,1) PRIMARY KEY,
        nome          NVARCHAR(120)  NOT NULL,
        descricao     NVARCHAR(400)  NULL,
        assunto       NVARCHAR(500)  NULL,
        corpo         NVARCHAR(MAX)  NOT NULL,
        html          BIT            NOT NULL CONSTRAINT DF_etl_email_modelo_html    DEFAULT (1),
        ativo         BIT            NOT NULL CONSTRAINT DF_etl_email_modelo_ativo   DEFAULT (1),
        padrao        BIT            NOT NULL CONSTRAINT DF_etl_email_modelo_padrao  DEFAULT (0),
        criado_por    NVARCHAR(100)  NULL,
        criado_em     DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_email_modelo_criado  DEFAULT (GETDATE()),
        atualizado_em DATETIME2(0)   NULL
    );
    PRINT '[OK] dbo.etl_email_modelo criada';
END
ELSE
    PRINT '[--] dbo.etl_email_modelo ja existe';
GO

-- Nome unico: o catalogo do Teams (etl_msg_template) nao tem, e nome repetido
-- confunde justamente na lista de escolha do no.
IF OBJECT_ID('dbo.etl_email_modelo', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_etl_email_modelo_nome'
                     AND object_id = OBJECT_ID('dbo.etl_email_modelo'))
BEGIN
    CREATE UNIQUE INDEX ux_etl_email_modelo_nome ON dbo.etl_email_modelo (nome);
    PRINT '[OK] indice ux_etl_email_modelo_nome criado';
END
ELSE
    PRINT '[--] indice ux_etl_email_modelo_nome ja existe';
GO

-- (B) Interruptor de padronizacao ---------------------------------------
-- Ligado, remove a opcao "Corpo livre" da lista (o nivel "travado").
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_exigir_modelo')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_exigir_modelo', '0',
            'E-mail: exigir modelo do catalogo no no (remove a opcao Corpo livre)',
            'migration 112', GETDATE());
    PRINT '[OK] chave email_exigir_modelo semeada';
END
ELSE
    PRINT '[--] chave email_exigir_modelo ja existe';
GO

-- (C) Modelo institucional ----------------------------------------------
-- Layout validado com o usuario em 2026-09-11: cabecalho com o gradiente da
-- tela de entrada, a tarja laranja do topo do sistema e a tabela de dados da
-- corrida. Nasce como PADRAO: o caminho de menor esforco passa a ser usa-lo.
-- Guarda pelo CATALOGO VAZIO, nao pelo nome: renomeado (ou apagado depois de o
-- admin criar os proprios), o nome nao casaria e a semente voltaria com
-- padrao = 1, deixando DOIS padroes e quebrando a invariante de um so.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_email_modelo)
BEGIN
    INSERT INTO dbo.etl_email_modelo (nome, descricao, assunto, corpo, html, ativo, padrao, criado_por)
    VALUES (N'Aviso de fim de carga',
            N'Layout institucional do Orquestra. Use para avisar o fim de uma carga: traz situacao, linhas, inicio, duracao e data de referencia.',
            N'[Orquestra] {pipeline} - {status}',
            N'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8FAFC;padding:24px 0;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background-color:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;">

  <tr>
    <td bgcolor="#0F4C88" style="background-color:#0F4C88;background-image:linear-gradient(135deg,#1A5FA8 0%,#0F4C88 55%,#0D3D6B 100%);border-radius:10px 10px 0 0;">
      <!--[if mso]>
      <v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:600px;">
      <v:fill type="gradient" color="#1A5FA8" color2="#0D3D6B" angle="135" />
      <v:textbox inset="0,0,0,0"><![endif]-->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="padding:22px 28px;">
          <table cellpadding="0" cellspacing="0" border="0"><tr>
            <td valign="middle" style="padding-right:14px;">
              <table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">
                <tr><td style="padding-left:21px;"><div style="width:8px;height:8px;background-color:#7FE3F5;font-size:0;line-height:0;">&#160;</div></td></tr>
                <tr><td style="padding-left:14px;padding-top:3px;"><div style="width:8px;height:8px;background-color:#7FE3F5;font-size:0;line-height:0;">&#160;</div></td></tr>
                <tr><td style="padding-left:7px;padding-top:3px;"><div style="width:8px;height:8px;background-color:#C5DCF2;font-size:0;line-height:0;">&#160;</div></td></tr>
                <tr><td style="padding-top:3px;"><div style="width:8px;height:8px;background-color:#8FB3D9;font-size:0;line-height:0;">&#160;</div></td></tr>
              </table>
            </td>
            <td valign="middle">
              <div style="color:#FFFFFF;font-size:13px;font-weight:bold;letter-spacing:3px;">ORQUESTRA</div>
              <div style="color:#C5DCF2;font-size:11px;letter-spacing:1px;padding-top:2px;">Gestão de Pipelines</div>
            </td>
          </tr></table>
        </td>
      </tr></table>
      <!--[if mso]></v:textbox></v:rect><![endif]-->
    </td>
  </tr>

  <tr>
    <td bgcolor="#F26B00" style="background-color:#F26B00;font-size:0;line-height:0;" height="4">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td width="33%" height="4" bgcolor="#F26B00" style="background-color:#F26B00;font-size:0;line-height:0;">&#160;</td>
        <td width="34%" height="4" bgcolor="#FF9D4D" style="background-color:#FF9D4D;font-size:0;line-height:0;">&#160;</td>
        <td width="33%" height="4" bgcolor="#F26B00" style="background-color:#F26B00;font-size:0;line-height:0;">&#160;</td>
      </tr></table>
    </td>
  </tr>

  <tr>
    <td style="padding:28px 28px 8px 28px;">
      <div style="color:#1E293B;font-size:19px;font-weight:600;line-height:1.35;">
        O fluxo {pipeline} terminou em {data}.
      </div>
    </td>
  </tr>

  <tr>
    <td style="padding:12px 28px 4px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;">
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px;width:150px;">Situação</td>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#1E293B;font-size:13px;font-weight:600;">{status}</td>
        </tr>
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px;">Linhas processadas</td>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#1E293B;font-size:13px;">{linhas}</td>
        </tr>
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px;">Início · duração</td>
          <td style="padding:12px 16px;border-bottom:1px solid #E2E8F0;color:#1E293B;font-size:13px;">{inicio} · {duracao}</td>
        </tr>
        <tr>
          <td style="padding:12px 16px;color:#64748B;font-size:12px;">Data de referência</td>
          <td style="padding:12px 16px;color:#1E293B;font-size:13px;">{odate}</td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding:16px 28px 24px 28px;">
      <div style="color:#64748B;font-size:12px;line-height:1.6;">
        Aviso automático da etapa {job}. Execução {execution_id}.
      </div>
    </td>
  </tr>

  <tr>
    <td style="background-color:#F8FAFC;border-top:1px solid #E2E8F0;padding:14px 28px;border-radius:0 0 10px 10px;">
      <div style="color:#94A3B8;font-size:11px;">
        ORQUESTRA · Gestão de Pipelines — mensagem enviada automaticamente, não responda.
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
',
            1, 1, 1, N'migration 112');
    PRINT '[OK] modelo institucional semeado';
END
ELSE
    PRINT '[--] modelo institucional ja existe';
GO

PRINT '[FIM] 112_email_modelos.sql';
