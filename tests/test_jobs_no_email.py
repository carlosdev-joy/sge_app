"""
Testes da régua do nó `email` na API (spec docs/spec-notificacao-email.md, F2):
`_validate_email` / `_normalize_email` em api/routers/jobs.py.

A config do nó vive na MESMA coluna do nó de notificação Teams (`notify_json`)
— o tipo do job é quem diz qual das duas é. Estes testes prendem o contrato
que o front e o operador do worker leem dos dois lados.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
for _p in (str(_ROOT / "api"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="module")
def J():
    from routers import jobs
    return jobs


RAIZES = ["/dados/saida", "/opt/IBM/dados"]
VALIDO = {
    "assunto": "Carga {pipeline} concluída - {data}",
    "corpo": "Foram {linhas} linhas.",
    "html": False,
    "destinatarios": ["ana@cvp.com.br", "Ana@CVP.com.br"],
    "incluir_pipeline": True,
    "anexo": {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"},
}


# ── tipo ────────────────────────────────────────────────────────────────────

def test_email_e_tipo_de_job_valido(J):
    assert "email" in J.VALID_JOB_TYPES


def test_tipos_anteriores_preservados(J):
    """Não-regressão: a F2 só ADICIONA um tipo."""
    assert {"datastage", "shell", "python", "storedproc", "http",
            "decisao", "notificacao", "sql", "aguarde"} <= J.VALID_JOB_TYPES


# ── validação ───────────────────────────────────────────────────────────────

def test_config_valida_passa(J):
    assert J._validate_email(VALIDO, RAIZES, []) == []


def test_config_ausente_ou_de_outro_tipo_e_erro(J):
    assert J._validate_email(None, RAIZES, [])
    assert J._validate_email("texto", RAIZES, [])
    assert J._validate_email([], RAIZES, [])


def test_assunto_e_corpo_sao_obrigatorios(J):
    erros = J._validate_email({**VALIDO, "assunto": "", "corpo": "  "}, RAIZES, [])
    assert any("assunto obrigatório" in e for e in erros)
    assert any("corpo obrigatório" in e for e in erros)


def test_assunto_com_quebra_de_linha_e_recusado(J):
    """Quebra no assunto viraria cabeçalho novo na mensagem MIME."""
    erros = J._validate_email({**VALIDO, "assunto": "Fim\nBcc: outro@x.com"}, RAIZES, [])
    assert any("quebra de linha" in e for e in erros)


def test_destinatario_invalido_e_recusado(J):
    erros = J._validate_email({**VALIDO, "destinatarios": ["sem-arroba"]}, RAIZES, [])
    assert any("endereço inválido" in e for e in erros)


def test_dominio_fora_da_allowlist_e_recusado_no_cadastro(J):
    """A régua do cadastro é a MESMA do envio: barrar só na corrida faria o
    erro aparecer longe de quem cadastrou."""
    erros = J._validate_email(VALIDO, RAIZES, ["parceiro.com.br"])
    assert any("domínio não permitido" in e for e in erros)
    assert J._validate_email(VALIDO, RAIZES, ["cvp.com.br"]) == []


def test_sem_lista_propria_e_sem_herdar_do_fluxo_e_erro(J):
    cfg = {**VALIDO, "destinatarios": [], "incluir_pipeline": False}
    erros = J._validate_email(cfg, RAIZES, [])
    assert any("ao menos um destinatário" in e for e in erros)
    # herdando a lista do fluxo, lista própria vazia é legítima
    assert J._validate_email({**cfg, "incluir_pipeline": True}, RAIZES, []) == []


def test_anexo_fora_das_raizes_permitidas_e_recusado(J):
    erros = J._validate_email({**VALIDO, "anexo": {"raiz": "/etc", "nome": "passwd"}}, RAIZES, [])
    assert any("não está entre as permitidas" in e for e in erros)


def test_anexo_com_barra_ou_ponto_ponto_no_nome_e_recusado(J):
    for nome in ("../../etc/passwd", "sub/dir.csv", "..", "rel\natorio.csv"):
        erros = J._validate_email({**VALIDO, "anexo": {"raiz": "/dados/saida", "nome": nome}},
                                  RAIZES, [])
        assert erros, f"nome de anexo perigoso aceito: {nome!r}"


def test_nome_do_anexo_e_livre_e_pode_nao_existir_ainda(J):
    """Decisão do usuário: o arquivo costuma ser gerado pela própria corrida."""
    for nome in ("relatorio_{odate}.xlsx", "base final.csv", "saída-2026.TXT", "sem_extensao"):
        assert J._validate_email({**VALIDO, "anexo": {"raiz": "/dados/saida", "nome": nome}},
                                 RAIZES, []) == [], nome


def test_sem_anexo_e_valido(J):
    for vazio in (None, {}, ""):
        assert J._validate_email({**VALIDO, "anexo": vazio}, RAIZES, []) == []


def test_sem_raiz_liberada_no_admin_o_anexo_e_recusado(J):
    """Sem a migration 111 (ou sem raízes no Admin) não há pasta liberada."""
    erros = J._validate_email(VALIDO, [], [])
    assert any("não está entre as permitidas" in e for e in erros)


def test_marcadores_booleanos_recusam_texto(J):
    assert J._validate_email({**VALIDO, "html": "sim"}, RAIZES, [])
    assert J._validate_email({**VALIDO, "incluir_pipeline": "sim"}, RAIZES, [])


# ── normalização ────────────────────────────────────────────────────────────

def test_normaliza_para_o_formato_gravado(J):
    out = J._normalize_email(VALIDO, RAIZES)
    assert out == {
        "assunto": "Carga {pipeline} concluída - {data}",
        "corpo": "Foram {linhas} linhas.",
        "html": False,
        "destinatarios": ["ana@cvp.com.br"],          # duplicata por caixa some
        "incluir_pipeline": True,
        "anexo": {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"},
    }


def test_incluir_pipeline_ausente_vira_ligado(J):
    """Quem cadastra a lista no fluxo espera que os nós a usem."""
    cfg = dict(VALIDO); cfg.pop("incluir_pipeline")
    assert J._normalize_email(cfg, RAIZES)["incluir_pipeline"] is True


def test_normalizacao_e_ponto_fixo(J):
    """Normalizar o já normalizado não muda nada — o round-trip do GET /fluxo
    devolve ao painel exatamente o que o operador vai ler."""
    uma = J._normalize_email(VALIDO, RAIZES)
    assert J._normalize_email(uma, RAIZES) == uma
    assert J._validate_email(uma, RAIZES, []) == []
