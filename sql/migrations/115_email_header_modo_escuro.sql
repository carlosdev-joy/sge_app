-- 115_email_header_modo_escuro.sql — preserva cores do header no Outlook escuro.
-- Idempotente — seguro para rodar mais de uma vez.
-- Atualiza somente o corpo ORIGINAL da 114; preserva modelos personalizados.
-- Requer API/worker com suporte ao CID reservado e asset local antes de enviar.
SET NOCOUNT ON;
GO
IF OBJECT_ID('dbo.etl_email_modelo', 'U') IS NULL
BEGIN
    PRINT '[--] catalogo ausente: migration 112 pendente';
END
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_email_modelo
               WHERE nome = N'Aviso de fim de carga'
                 AND HASHBYTES('SHA2_256', corpo) = 0x9E5D3DB5D8FC847879B1D10A7AA6DF4CD0559975108DFF9419CC702D0FEE5739)
BEGIN
    UPDATE dbo.etl_email_modelo
       SET corpo = N'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8FAFC;padding:24px 0;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background-color:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;">

  <tr>
    <td bgcolor="#04143C" style="background-color:#04143C;padding:0;font-size:0;line-height:0;">
      <img src="cid:orq-header@orquestra" width="600" height="208" alt="ORQ — Plataforma de Orquestração de Dados, Processos e Inteligência" style="display:block;width:100%;max-width:600px;height:auto;border:0;color:#FFFFFF;font-size:18px;line-height:24px;">
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
      <div style="color:#64748B;font-size:11px;">
        ORQ · Engenharia de Dados — mensagem enviada automaticamente, não responda.
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
',
               atualizado_em = GETDATE()
     WHERE nome = N'Aviso de fim de carga'
       AND HASHBYTES('SHA2_256', corpo) = 0x9E5D3DB5D8FC847879B1D10A7AA6DF4CD0559975108DFF9419CC702D0FEE5739;
    PRINT '[OK] header ORQ incorporado para preservar cores no modo escuro';
END
ELSE
    PRINT '[--] corpo personalizado, ausente ou ja atualizado: preservado';
GO
