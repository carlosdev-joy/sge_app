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
        "modelo_id": None,                            # Corpo livre
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


# ── modelo do catálogo (F2 da spec de modelos e navegação) ──────────────────

def test_com_modelo_o_corpo_do_no_deixa_de_ser_exigido(J):
    """O corpo vem do catálogo no envio. Exigir o do nó obrigaria a duplicar o
    HTML em cada fluxo — o oposto do ponto do catálogo."""
    cfg = {**VALIDO, "corpo": "", "modelo_id": 3}
    assert J._validate_email(cfg, RAIZES, [], [1, 3, 7]) == []


def test_sem_modelo_o_corpo_volta_a_ser_exigido(J):
    """A opção *Corpo livre* precisa de corpo — senão o e-mail sai vazio."""
    erros = J._validate_email({**VALIDO, "corpo": "  ", "modelo_id": None}, RAIZES, [], [1, 3])
    assert any("corpo obrigatório" in e for e in erros)


def test_modelo_fora_do_catalogo_e_recusado_na_tela(J):
    """Modelo APAGADO tem de falhar ao SALVAR, não na corrida."""
    erros = J._validate_email({**VALIDO, "modelo_id": 99}, RAIZES, [], [1, 3])
    assert any("não existe mais no catálogo" in e for e in erros)


def test_modelo_desativado_continua_salvavel(J):
    """A lista de válidos inclui os INATIVOS de propósito.

    Desativar é o gesto que a própria API recomenda no lugar de excluir ("quem
    já usa continua enviando") e o operador de fato continua enviando. Se a
    régua do salvar recusasse inativo, desativar tornaria INSALVÁVEL todo fluxo
    que usa o modelo: mexer em qualquer outro nó passaria a devolver 422."""
    assert J._validate_email({**VALIDO, "modelo_id": 8}, RAIZES, [], [1, 3, 8]) == []


def test_sem_catalogo_a_checagem_do_modelo_e_pulada(J):
    """`None` = catálogo indisponível (sem a 112). Diferente de `[]`, que é
    'catálogo vazio' e recusaria todo nó que já aponta para um."""
    assert J._validate_email({**VALIDO, "modelo_id": 99}, RAIZES, [], None) == []
    erros = J._validate_email({**VALIDO, "modelo_id": 99}, RAIZES, [], [])
    assert any("não existe mais no catálogo" in e for e in erros)


# ── padronização: exigir modelo do catálogo ─────────────────────────────────

def test_com_padronizacao_ligada_no_novo_nao_nasce_em_corpo_livre(J):
    cfg = {**VALIDO, "modelo_id": None}
    erros = J._validate_email(cfg, RAIZES, [], [1, 3], exigir_modelo=True, no_novo=True)
    assert any("Corpo livre" in e for e in erros)
    # com modelo escolhido, passa
    assert J._validate_email({**cfg, "modelo_id": 3}, RAIZES, [], [1, 3],
                             exigir_modelo=True, no_novo=True) == []


def test_ligar_a_padronizacao_nao_quebra_no_que_ja_existe(J):
    """O nó que já roda em Corpo livre continua salvável: ligar o interruptor
    não pode transformar em 422 a edição de um fluxo que está no ar."""
    cfg = {**VALIDO, "modelo_id": None}
    assert J._validate_email(cfg, RAIZES, [], [1, 3], exigir_modelo=True, no_novo=False) == []
    # e sem a padronização o nó novo segue livre
    assert J._validate_email(cfg, RAIZES, [], [1, 3], exigir_modelo=False, no_novo=True) == []


def test_corpo_continua_exigido_no_corpo_livre_mesmo_com_a_padronizacao(J):
    """Os dois erros aparecem juntos — o segundo não some por causa do primeiro."""
    erros = J._validate_email({**VALIDO, "corpo": " ", "modelo_id": None}, RAIZES, [], [1],
                              exigir_modelo=True, no_novo=True)
    assert any("Corpo livre" in e for e in erros)
    assert any("corpo obrigatório" in e for e in erros)


# ── a régua que o salvar carrega do Admin ───────────────────────────────────

class _CurAdmin:
    """Cursor de mentira: catálogo com um modelo ATIVO e um INATIVO."""

    def __init__(self, com_112=True, exigir="1"):
        self.com_112, self.exigir = com_112, exigir
        self._rows: list = []
        self.listagens: list[str] = []

    def execute(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "information_schema.tables" in s:
            self._rows = [(1 if self.com_112 else 0,)]
        elif "from dbo.etl_email_modelo" in s:
            if not self.com_112:
                raise Exception("Invalid object name 'dbo.etl_email_modelo'")
            self.listagens.append(s)
            self._rows = [
                (4, "Ativo", None, None, "corpo", 1, 1, 1, "ADM", "2026-09-11 10:00:00", None),
                (9, "Inativo", None, None, "corpo", 1, 0, 0, "ADM", "2026-09-11 10:00:00", None),
            ]
        elif "from dbo.etl_app_config" in s and params and params[0] == "email_exigir_modelo":
            # A chave é gravada por MERGE e NÃO depende da tabela do catálogo:
            # ela pode muito bem estar ligada num ambiente sem a 112.
            self._rows = [(self.exigir,)]
        elif "from dbo.etl_app_config" in s:
            self._rows = [("email_habilitado", "1"),
                          ("email_remetente", "orquestra@cvp.com.br"),
                          ("email_anexo_raizes", '["/dados/saida"]')]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_config_do_admin_traz_inativos_e_o_interruptor(J):
    cur = _CurAdmin()
    raizes, dominios, modelos, exigir = J._config_email_do_admin(cur)
    assert raizes == ["/dados/saida"] and dominios == []
    # 9 está INATIVO e mesmo assim entra: é o que mantém salvável quem já usa
    assert modelos == [4, 9] and exigir is True
    # e o SQL da listagem não pode filtrar por ativo
    assert cur.listagens and all("ativo = 1" not in s for s in cur.listagens)


def test_ancora_sem_catalogo_a_padronizacao_nao_vale_nem_com_a_chave_ligada(J):
    """⛔ Âncora. A chave `email_exigir_modelo` é gravada por MERGE e NÃO
    depende da tabela do catálogo — o interruptor do Admin aparece sem a 112 e
    pode ser ligado. Se a régua do salvar obedecesse a ela sem catálogo, o nó
    de e-mail NOVO ficaria insalvável **sem gesto possível na tela**: o painel
    não renderiza a lista de modelos quando o catálogo está indisponível, então
    não haveria como escolher o modelo que a régua cobra. É a mesma conta que
    `GET /email/modelos` faz ao devolver `exigir_modelo: False` sem a 112."""
    _r, _d, modelos, exigir = J._config_email_do_admin(_CurAdmin(com_112=False, exigir="1"))
    assert modelos is None and exigir is False
    # e com catálogo a chave volta a valer
    _r, _d, _m, exigir = J._config_email_do_admin(_CurAdmin(exigir="0"))
    assert exigir is False
    _r, _d, _m, exigir = J._config_email_do_admin(_CurAdmin(exigir="1"))
    assert exigir is True


def test_modelo_invalido_e_recusado(J):
    for ruim in ("abc", -1.5, {}, [3]):
        assert J._validate_email({**VALIDO, "modelo_id": ruim}, RAIZES, [], [3]), ruim
    # booleano NÃO é id (True viraria 1 num int() ingênuo)
    assert J._validate_email({**VALIDO, "modelo_id": True}, RAIZES, [], [1])


def test_corpo_do_no_e_preservado_ao_escolher_um_modelo(J):
    """Voltar de um modelo para o Corpo livre não pode perder o texto que a
    pessoa já tinha escrito."""
    out = J._normalize_email({**VALIDO, "modelo_id": 3}, RAIZES)
    assert out["modelo_id"] == 3
    assert out["corpo"] == "Foram {linhas} linhas."


def test_modelo_como_texto_de_digito_vira_inteiro(J):
    assert J._normalize_email({**VALIDO, "modelo_id": "7"}, RAIZES)["modelo_id"] == 7
    assert J._normalize_email({**VALIDO, "modelo_id": None}, RAIZES)["modelo_id"] is None
    assert J._normalize_email({**VALIDO, "modelo_id": True}, RAIZES)["modelo_id"] is None
