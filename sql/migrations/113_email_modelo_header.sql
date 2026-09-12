-- ============================================================================
-- 113_email_modelo_header.sql — cabecalho do modelo institucional no Outlook
--
-- Spec: docs/spec-email-tabela-sql-e-ajustes.md (F3)
--
-- O modelo semeado pela 112 chegava QUEBRADO no Outlook desktop: o cabecalho
-- aparecia cortado ao meio e com uma faixa de outra cor a direita. Tres causas
-- somadas, todas do mesmo bloco:
--
--   1. o <v:textbox> do retangulo VML nao tinha `mso-fit-shape-to-text:true` e
--      o <v:rect> nao tinha altura -> o motor do Word da a forma uma altura
--      fixa e CLIPA o que nao cabe (o texto cortado);
--   2. o corpo era enviado SEM <head>, entao sem
--      <o:PixelsPerInch>96</o:PixelsPerInch> o Word dimensiona o VML com o DPI
--      do Windows: em tela a 125% a forma sai menor que a celula (a faixa
--      sobrando). Isso foi corrigido no envio (documento_html), aqui some a
--      dependencia do VML;
--   3. no modo escuro o Outlook inverte `bgcolor` mas NAO inverte preenchimento
--      VML -> dois azuis diferentes no mesmo cabecalho.
--
-- O cabecalho novo nao usa VML nem gradiente (cor solida) e monta a escadinha
-- do logo com CELULAS: o Word ignora width/height em <div>, que era como os
-- quatro quadradinhos estavam desenhados.
--
-- ⚠️ GUARDA: so atualiza o corpo que ainda esta IDENTICO ao semeado pela 112
-- (SHA2_256 conferido no banco). Modelo editado pela tela fica INTACTO — quem
-- editou aplica o cabecalho novo a mao, e o roteiro esta em
-- docs/release-notes/email-header.md.
--
-- Idempotente: depois do UPDATE o hash deixa de bater e a segunda execucao cai
-- no ramo que preserva.
-- ============================================================================

SET NOCOUNT ON;
GO

IF OBJECT_ID('dbo.etl_email_modelo', 'U') IS NULL
BEGIN
    PRINT '[--] dbo.etl_email_modelo nao existe — migration 112 pendente, nada a fazer';
END
ELSE
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.etl_email_modelo
                WHERE nome = N'Aviso de fim de carga'
                  AND HASHBYTES('SHA2_256', corpo) = 0xEBCC13E7CA65EDC90B88342DD0B1E8705751E9F70412F573AF2B7F725687CB32)
    BEGIN
        UPDATE dbo.etl_email_modelo
           SET corpo = N'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8FAFC;padding:24px 0;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background-color:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;">

  <tr>
    <!-- Cabecalho: cor SOLIDA, sem VML e sem gradiente. O retangulo VML
         com textbox (sem mso-fit-shape-to-text) fazia o Outlook desktop
         CLIPAR o conteudo, cortando o nome do produto ao meio; e o modo
         escuro inverte bgcolor mas NAO inverte preenchimento VML,
         deixando dois azuis no mesmo cabecalho.
         Comentarios aqui nao podem citar tags: o texto simples do e-mail
         e gerado tirando tudo entre "menor que" e o primeiro "maior que",
         e o resto do comentario vazaria para quem le em texto puro. -->
    <td bgcolor="#0F4C88" style="background-color:#0F4C88;padding:22px 28px;border-radius:10px 10px 0 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="middle" style="padding-right:14px;">
          <!-- Escadinha do logo em CELULAS: o motor do Word ignora largura
               e altura em caixa flutuante, e os quadrados sumiam. -->
          <table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">
                <tr><td style="padding-left:21px;font-size:0;line-height:0;"><table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;"><tr><td width="8" height="8" bgcolor="#7FE3F5" style="width:8px;height:8px;font-size:0;line-height:0;">&#160;</td></tr></table></td></tr>
                <tr><td style="padding-left:14px;padding-top:3px;font-size:0;line-height:0;"><table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;"><tr><td width="8" height="8" bgcolor="#7FE3F5" style="width:8px;height:8px;font-size:0;line-height:0;">&#160;</td></tr></table></td></tr>
                <tr><td style="padding-left:7px;padding-top:3px;font-size:0;line-height:0;"><table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;"><tr><td width="8" height="8" bgcolor="#C5DCF2" style="width:8px;height:8px;font-size:0;line-height:0;">&#160;</td></tr></table></td></tr>
                <tr><td style="padding-top:3px;font-size:0;line-height:0;"><table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;"><tr><td width="8" height="8" bgcolor="#8FB3D9" style="width:8px;height:8px;font-size:0;line-height:0;">&#160;</td></tr></table></td></tr>
          </table>
        </td>
        <td valign="middle">
          <div style="color:#FFFFFF;font-size:13px;font-weight:bold;letter-spacing:3px;">ORQUESTRA</div>
          <div style="color:#C5DCF2;font-size:11px;letter-spacing:1px;padding-top:2px;">Gestão de Pipelines</div>
        </td>
      </tr></table>
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
               atualizado_em = GETDATE()
         WHERE nome = N'Aviso de fim de carga'
           AND HASHBYTES('SHA2_256', corpo) = 0xEBCC13E7CA65EDC90B88342DD0B1E8705751E9F70412F573AF2B7F725687CB32;
        PRINT '[OK] cabecalho do modelo institucional corrigido (sem VML, logo em celulas)';
    END
    ELSE IF EXISTS (SELECT 1 FROM dbo.etl_email_modelo WHERE nome = N'Aviso de fim de carga')
        PRINT '[--] modelo EDITADO (ou ja corrigido) — corpo preservado, nada alterado';
    ELSE
        PRINT '[--] modelo institucional ausente — nada a fazer';
END
GO

PRINT '[FIM] 113_email_modelo_header.sql';
