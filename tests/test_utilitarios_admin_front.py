"""Admin › Utilitários (F2 da spec docs/spec-utilitarios-arquivos.md) — o front.

Duas famílias:

  1. **Bancada renderizada** (`tests/js/utilitarios_admin_harness.cjs`): os
     três componentes de apresentação rodam no React mínimo da casa e a
     bancada CLICA — Incluir desligado com caminho inválido, raiz inativa
     esmaecida com "Reativar", Testar com o id certo, exclusão de extensão só
     depois de confirmar, `sh` pedindo confirmação a mais, Salvar desligado
     sem mudança. Sem Node ou sem `node_modules`, SALTA (não finge).
  2. **Anti-drift** por leitura do fonte, sem Node: a aba está registrada e
     renderizada no Admin, o container chama os endpoints da F1, e as
     constantes espelhadas no front (`RAIZES_PROIBIDAS`, regex de extensão,
     teto, limite da raiz) batem com as do backend — o servidor é a
     autoridade, mas o campo tem de avisar a MESMA coisa.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_admin_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
ADMIN = RAIZ / "ui-react" / "src" / "pages" / "Admin.tsx"
TAB = RAIZ / "ui-react" / "src" / "components" / "admin" / "UtilitariosTab.tsx"
PURAS_TS = RAIZ / "ui-react" / "src" / "lib" / "utilitariosAdmin.ts"
SERVICO_PY = RAIZ / "api" / "services" / "ssh_arquivos.py"
ROUTER_PY = RAIZ / "api" / "routers" / "utilitarios.py"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:  # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. funções puras (espelho do servidor, no campo) ═══════════════

def test_aviso_da_raiz_diz_o_mesmo_que_o_servidor(cen):
    a = cen["puras"]["avisoRaiz"]
    assert a["vazio"] is None
    assert "absoluto" in a["relativa"]
    assert "barra" in a["barra"] and "barra" in a["duplaBarra"]
    assert "/etc" in a["sistema"] and "sistema" in a["sistema"]
    assert "/usr" in a["sistemaPorDoisPontos"]          # o `..` é resolvido ANTES de conferir
    assert "800" in a["longa"]
    assert a["ok"] is None and a["okSob"] is None


def test_normpath_lexical_colapsa_barras_e_resolve_dois_pontos(cen):
    n = cen["puras"]["normalizarCaminhoLexical"]
    assert n["duplas"] == "/dados/bi/x"
    assert n["doisPontos"] == "/etc"
    assert n["acima"] == "/etc"


def test_extensao_normaliza_como_o_servidor(cen):
    e = cen["puras"]["normalizarExtensao"]
    assert e["vazia"]["ok"] is False
    assert e["pontoMaiuscula"] == {"ok": True, "valor": "sh"}
    assert e["invalida"]["ok"] is False and e["longa"]["ok"] is False
    assert e["ok"] == {"ok": True, "valor": "properties"}
    assert cen["puras"]["pedeConfirmacao"] == {"sh": True, "txt": False}


def test_tom_do_teste(cen):
    assert cen["puras"]["tomDoTeste"] == {
        "naoExiste": "error", "arquivo": "error", "ilegivel": "warning",
        "semPermissao": "warning",   # eh_pasta=None (403 no realpath) não é "arquivo"
        "ok": "success",
    }


def test_teto_valido(cen):
    t = cen["puras"]["tetoValido"]
    assert t["ok"] == 2048 and t["max"] == 16384
    assert t["zero"] is None and t["acima"] is None and t["texto"] is None and t["decimal"] is None


def test_mensagem_de_erro_le_string_lista_e_cai_no_padrao(cen):
    m = cen["puras"]["mensagemErro"]
    assert m["string"] == "Raiz já cadastrada"
    assert "2147483647" in m["lista"]
    assert m["generico"] == "padrão"          # "500 Internal Server Error" não é mensagem para o usuário
    assert m["nada"] == "padrão"
    assert cen["puras"]["migrationPendente"] == {"sim": True, "outro503": False, "n404": False}


# ═══════════ 2. raízes ═════════════════════════════════════════════════════

def test_raizes_renderizam_com_estado_e_acoes_certas(cen):
    r = cen["raizes"]
    assert r["linhas"] == 2
    assert r["inativas"] == [2]
    assert r["estados"] == ["ativa", "inativa"]
    assert r["acoesLinha1"] == "1/1"          # a ativa tem Desativar, a inativa tem Reativar
    assert r["vazio"] == 0


def test_raizes_testar_e_ativar_chamam_o_pai_com_o_id(cen):
    c = cen["raizes"]["chamadas"]
    assert c["testar"] == [1]
    assert c["ativar"] == [[1, False], [2, True]]


def test_incluir_raiz_fica_desligado_com_caminho_invalido_e_avisa_no_campo(cen):
    r = cen["raizes"]
    assert r["botaoVazio"] is True
    assert r["relativa"] == {"desligado": True, "aviso": True}
    assert r["sistema"] == {"desligado": True, "aviso": True}
    assert r["barra"]["desligado"] is True
    assert r["valida"]["desligado"] is False
    assert r["ocupadoDesligado"] is True


def test_incluir_raiz_envia_o_caminho_como_digitado_e_limpa_o_campo(cen):
    r = cen["raizes"]["aposSubmit"]
    # O servidor normaliza; a tela manda o que o admin escreveu (só sem espaços).
    assert r["incluir"] == [["datastage", "/dados//param/"]]
    assert r["campo"] == ""


def test_servidor_recusou_a_raiz_o_campo_mantem_o_texto(cen):
    """409 "já cadastrada" não pode apagar o que o admin digitou."""
    assert cen["raizes"]["falhaMantemCampo"] == "/dados/bi"


def test_resultado_do_testar_aparece_na_linha_com_o_tom(cen):
    linhas = cen["raizesTeste"]["linhas"]
    assert [l["id"] for l in linhas] == [1, 2]
    assert [l["tom"] for l in linhas] == ["success", "error"]
    assert "é um link para /u01/dados/bi" in linhas[0]["texto"]
    assert "caminho real /u01/dados/bi" in linhas[0]["texto"]
    assert "120 ms" in linhas[0]["texto"]
    assert "não existe" in linhas[1]["texto"]


def test_raizes_vazio_avisa_e_servidor_sem_ssh_avisa(cen):
    assert cen["raizesVazio"] == ["raizes"]
    assert cen["raizesSemSsh"] is True
    assert cen["raizesTestando"] == [True, True]   # uma conexão por vez: os dois Testar desligam


# ═══════════ 3. extensões ══════════════════════════════════════════════════

def test_excluir_extensao_so_depois_de_confirmar(cen):
    e = cen["extensoes"]
    assert e["chips"] == ["txt", "sql"]
    assert e["antesDeConfirmar"] == {"excluir": [], "modal": 1}
    assert e["aposConfirmar"] == {"excluir": ["txt"], "modal": 0}


def test_incluir_extensao_normaliza_limpa_e_recusa_invalida_e_repetida(cen):
    e = cen["extensoes"]
    assert e["csv"] == {"incluir": ["csv"], "campo": ""}
    assert e["invalida"] == {"incluir": ["csv"], "aviso": True}
    assert e["repetida"] == {"incluir": ["csv"], "aviso": True}


def test_sh_pede_confirmacao_a_mais(cen):
    e = cen["extensoes"]
    assert e["shAntes"] == {"incluir": ["csv"], "modal": 1, "aviso": True}
    assert e["shDepois"] == {"incluir": ["csv", "sh"], "modal": 0, "campo": ""}
    assert cen["extensoesVazio"] == ["extensoes"]


def test_servidor_recusou_a_extensao_o_campo_mantem_o_texto(cen):
    assert cen["extensoes"]["falhaMantemCampo"] == "csv"


# ═══════════ 4. limites ════════════════════════════════════════════════════

def test_salvar_limites_so_com_mudanca_valida(cen):
    l = cen["limites"]
    assert l["semMudanca"] is True
    assert l["valorInicial"] == "2048" and l["chaveInicial"] is True
    assert l["mudou"] is False
    assert l["salvou"] == [[4096, True]]
    assert l["invalido"] == {"desligado": True, "aviso": True}
    assert l["invalidoNaoSalva"] == 1
    assert l["soChave"] is False
    assert l["salvouChave"] == [[4096, True], [2048, False]]


# ═══════════ 5. anti-drift (sem Node) ══════════════════════════════════════

def test_aba_registrada_e_renderizada_no_admin():
    fonte = ADMIN.read_text(encoding="utf-8")
    assert re.search(r"\{\s*id:\s*'utilitarios',\s*label:\s*'Utilitários'\s*\}", fonte), "aba fora de ADMIN_GROUPS"
    assert "tab === 'utilitarios' && <UtilitariosTab />" in fonte, "aba registrada mas nunca renderizada"
    assert "from '../components/admin/UtilitariosTab'" in fonte


def test_container_chama_os_endpoints_da_f1():
    fonte = TAB.read_text(encoding="utf-8")
    for rota in ("/utilitarios/config", "/utilitarios/admin/raizes", "/utilitarios/admin/extensoes",
                 "/utilitarios/admin/config", "/testar`"):
        assert rota in fonte, rota
    assert "method: 'PATCH'" in fonte and "method: 'DELETE'" in fonte and "method: 'PUT'" in fonte


def test_container_ressincroniza_em_erro_e_nao_desmonta_no_refetch():
    """Achados da revisão adversarial da F2: 404/409 = lista defasada (invalidar
    também no erro); refetch falho com dados na tela avisa sem desmontar os
    formulários (o admin pode estar no meio de um caminho digitado)."""
    fonte = TAB.read_text(encoding="utf-8")
    assert fonte.count("onSettled: invalidar") == 5, "toda mutation ressincroniza em onSettled"
    assert "data-aviso=\"refetch\"" in fonte
    assert "const semDados" in fonte and "if (semDados" in fonte
    # O ramo de erro que troca a aba inteira só existe SEM dados.
    assert "if (erro || !config.data" not in fonte


def _tupla_py(nome: str) -> list[str]:
    fonte = SERVICO_PY.read_text(encoding="utf-8")
    m = re.search(nome + r"\s*=\s*\((.*?)\)", fonte, re.S)
    assert m, nome
    return re.findall(r'"([^"]+)"', m.group(1))


def _lista_ts(nome: str) -> list[str]:
    fonte = PURAS_TS.read_text(encoding="utf-8")
    m = re.search(nome + r"\s*=\s*\[(.*?)\]", fonte, re.S)
    assert m, nome
    return re.findall(r"'([^']+)'", m.group(1))


def test_constantes_do_front_espelham_o_backend():
    assert set(_lista_ts("RAIZES_PROIBIDAS")) == set(_tupla_py("RAIZES_PROIBIDAS"))
    py = SERVICO_PY.read_text(encoding="utf-8")
    ts = PURAS_TS.read_text(encoding="utf-8")
    assert re.search(r"LIMITE_RAIZ\s*=\s*800", py) and re.search(r"LIMITE_RAIZ\s*=\s*800", ts)
    assert re.search(r"TETO_MAX_KB\s*=\s*16384", py) and re.search(r"TETO_MAX_KB\s*=\s*16384", ts)
    rt = ROUTER_PY.read_text(encoding="utf-8")
    assert 'r"^[a-z0-9]{1,15}$"' in rt and "/^[a-z0-9]{1,15}$/" in ts
