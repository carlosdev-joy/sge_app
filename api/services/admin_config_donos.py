"""Dono de cada chave de dbo.etl_app_config — trava de escrita do editor genérico.

F5 de docs/spec-admin-reestruturacao.md. Uma chave "tem dono" quando uma aba do
Admin a grava pela rota PRÓPRIA (com a validação dela: E-mail por
POST /email/admin/config, IA por ia_set, ServiceNow/Triagem por servicenow_set,
Teams por teams_webhook_set…). As actions genéricas `config_upsert` e
`config_delete` (Parâmetros avançados) recusam essas chaves com 422 — senão o
editor genérico seria um desvio de toda validação 422 das abas.

ESPELHO de `chavesConfig` do registro do front (ui-react/src/lib/adminNav.ts):
cada item é (prefixo, rótulo), e o rótulo é exatamente o de `rotuloAdmin(grupo,
aba)` — é ele que aparece no `detail` e na tela. tests/test_admin_config_donos.py
roda o registro real (bancada tests/js/admin_nav_harness.cjs) e prende as duas
listas: aba nova com chave própria, ou aba renomeada, muda nos dois lugares.

A regra de casamento é a mesma do front (`donoDaChave`): a chave começa com o
prefixo, sem diferença de caixa e sem espaço nas pontas — o SQL Server compara
config_key sem caixa (EMAIL_REMETENTE atualizaria a linha email_remetente).
"""
from __future__ import annotations

DONOS: tuple[tuple[str, str], ...] = (
    # Inteligência Artificial › Provedor (caixa_ia_* = espelho legado do ia_set)
    ("ia_", "Admin › Inteligência Artificial › Provedor"),
    ("caixa_ia_", "Admin › Inteligência Artificial › Provedor"),
    # Inteligência Artificial › Maestro
    ("maestro_", "Admin › Inteligência Artificial › Maestro"),
    # Inteligência Artificial › Agentes (chaves inteiras: agentes_titulo_redigido_em é marca de migration)
    ("agentes_enabled", "Admin › Inteligência Artificial › Agentes"),
    ("agente_datastage_enabled", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_gateway_campo_usuario", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_cadastro_texto", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_ssh_max", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_fato_validade_dias", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_banco_conexao_s", "Admin › Inteligência Artificial › Agentes"),
    ("agentes_banco_consulta_s", "Admin › Inteligência Artificial › Agentes"),
    # Inteligência Artificial › Triagem de chamados
    ("chamados_triagem_", "Admin › Inteligência Artificial › Triagem de chamados"),
    # Comunicação
    ("teams_webhook_url", "Admin › Comunicação › Teams"),
    ("email_", "Admin › Comunicação › E-mail"),
    # Integrações & Dados › ServiceNow (servicenow_admin_perfis é da tela /chamados: sem dono aqui)
    ("servicenow_url", "Admin › Integrações & Dados › ServiceNow"),
    ("servicenow_usuario", "Admin › Integrações & Dados › ServiceNow"),
    ("servicenow_senha_enc", "Admin › Integrações & Dados › ServiceNow"),
    ("servicenow_grupos", "Admin › Integrações & Dados › ServiceNow"),
    ("servicenow_habilitado", "Admin › Integrações & Dados › ServiceNow"),
    ("servicenow_proxy", "Admin › Integrações & Dados › ServiceNow"),
    # Integrações & Dados › Servidor DataStage (SFTP)
    ("utilitarios_", "Admin › Integrações & Dados › Servidor DataStage (SFTP)"),
)


def dono_da_chave(chave: str | None) -> str | None:
    """Rótulo da migalha (rotuloAdmin do front) da aba dona da chave, ou None (chave órfã)."""
    k = (chave or "").strip().lower()
    if not k:
        return None
    for prefixo, rotulo in DONOS:
        if k.startswith(prefixo):
            return rotulo
    return None


def mensagem_chave_com_dono(chave: str, rotulo: str) -> str:
    """O `detail` do 422 — o front mostra como veio."""
    return f"A chave {chave} é gerida em {rotulo}."
