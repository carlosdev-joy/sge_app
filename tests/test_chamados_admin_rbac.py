"""As rotas /admin/servicenow/* exigem `acao_admin` — e continuam exigindo.

Em produção elas pedem apenas AUTENTICAÇÃO: hoje, lá, qualquer usuário logado
lê e **grava** a configuração da integração, edita os grupos monitorados, salva
os perfis de acesso do módulo e dispara o delta. A F3 do porte fecha isso.

O que este arquivo prende, e por que cada parte existe:

  1. **Cada rota, uma a uma, recusa quem não tem `acao_admin`.** Um teste que
     verificasse só "existe `get_admin_user` no arquivo" ficaria verde com uma
     rota nova nascendo sem a dependência — que é exatamente como a proteção
     cai: ninguém remove, alguém esquece.
  2. **O varredor descobre as rotas sozinho.** Lista escrita à mão envelhece: a
     décima rota entraria protegida hoje e desprotegida no dia em que alguém
     acrescentasse a décima primeira sem lembrar deste arquivo.
  3. **Um piso** — varredor que deixa de achar rota passa verde para sempre.

⚠️ 403 e não 401: quem chega aqui ESTÁ autenticado; o que falta é permissão.
Responder 401 mandaria o operador tentar logar de novo para resolver algo que
o login não resolve.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "api" / "routers" / "chamados.py"


def _rotas_admin() -> list[tuple[str, str]]:
    """(método, caminho) de cada rota /admin/servicenow/* do módulo.

    Descoberto por AST em vez de lista fixa: rota nova entra no teste sozinha.
    """
    achados = []
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef):
            continue
        for dec in no.decorator_list:
            if not (isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"):
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            caminho = dec.args[0].value
            if caminho.startswith("/admin/servicenow"):
                achados.append((dec.func.attr.upper(), caminho))
    return achados


def _url(caminho: str) -> str:
    """Troca os parâmetros de rota por valores quaisquer.

    O valor não importa: a dependência de permissão roda ANTES do handler, e é
    ela que este arquivo interroga.
    """
    import re
    return re.sub(r"\{[^}]+\}", "1", caminho)


@pytest.fixture
def sem_permissao():
    """Usuário autenticado, com a tela de chamados, SEM `acao_admin`."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador",
        "permissoes": ["tela_chamados"], "email": "fulano@caixa.gov.br"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("metodo,caminho", _rotas_admin())
def test_rota_admin_recusa_quem_nao_e_admin(sem_permissao, metodo, caminho):
    """A exposição que a F3 fecha: em produção, isto responde 200."""
    chamada = getattr(sem_permissao, metodo.lower())
    # GET e DELETE desta versão do TestClient não aceitam `json=`
    resposta = (chamada(_url(caminho), json={})
                if metodo in ("POST", "PUT") else chamada(_url(caminho)))
    assert resposta.status_code == 403, (
        f"{metodo} {caminho} respondeu {resposta.status_code} para usuário sem "
        f"acao_admin — em produção esta rota grava configuração de integração, "
        f"edita grupos e dispara sincronização")


def test_o_varredor_acha_as_rotas_admin():
    """Piso: varredor que deixa de achar passa verde para sempre."""
    rotas = _rotas_admin()
    assert len(rotas) >= 9, (
        f"o varredor achou {len(rotas)} rotas /admin/servicenow — se o módulo "
        f"foi reorganizado, este teste precisa ser revisto, não ignorado")


def test_nenhuma_rota_admin_do_modulo_usa_so_autenticacao():
    """A leitura estática que complementa a dinâmica.

    A dinâmica prova o 403 das rotas que EXISTEM; esta pega a rota que nasceu
    com `get_current_user` mas ainda não foi exercitada — por exemplo, uma que
    o TestClient não alcance por falta de rota registrada.
    """
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    faltando = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef):
            continue
        caminhos = [d.args[0].value for d in no.decorator_list
                    if isinstance(d, ast.Call) and d.args
                    and isinstance(d.args[0], ast.Constant)
                    and isinstance(d.args[0].value, str)
                    and d.args[0].value.startswith("/admin/servicenow")]
        if not caminhos:
            continue
        fonte_fn = ast.unparse(no)
        if "get_admin_user" not in fonte_fn:
            faltando.append(caminhos[0])
    assert not faltando, (
        "rotas /admin/servicenow sem get_admin_user: " + ", ".join(faltando))


# ═══════════ Nenhuma rota do módulo fica sem autenticação ═══════════════════
#
# Acrescentado na revisão adversarial de fecho da spec (F6). O risco #2 da spec
# era "rotas admin sem permissão — exposição viva hoje", fechado pela F3. Este
# teste impede a REGRESSÃO: uma rota nova sem `Depends` não quebra nada, não
# aparece em teste nenhum, e fica aberta.
#
# ⚠️ A verificação é por AST, não por regex. Uma primeira tentativa usou regex
# sobre a linha do `def` e acusou as 19 rotas — porque assinatura de várias
# linhas põe o `Depends(...)` na linha seguinte. Alarme falso é pior que
# nenhum: ele treina quem lê a suíte a ignorar a saída.

def _rotas_do_modulo():
    """(método, caminho, tem_depends) para cada rota do arquivo."""
    import ast
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    saida = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decs = [d for d in no.decorator_list
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name)
                and d.func.value.id == "router"]
        if not decs:
            continue
        # `Depends` em QUALQUER default da assinatura, inclusive kwonly.
        defaults = list(no.args.defaults) + [d for d in no.args.kw_defaults if d]
        tem = any(isinstance(d, ast.Call)
                  and getattr(d.func, "id", "") == "Depends"
                  for d in defaults)
        caminho = decs[0].args[0].value if decs[0].args else "?"
        saida.append((decs[0].func.attr.upper(), caminho, tem))
    return saida


def test_ha_rotas_para_analisar() -> None:
    """Piso: um parser que deixa de achar rotas passa verde para sempre."""
    assert len(_rotas_do_modulo()) >= 15


def test_toda_rota_exige_autenticacao() -> None:
    """Rota sem `Depends` responde a qualquer um. Não quebra, não aparece em
    teste nenhum, e fica aberta."""
    abertas = [f"{m} {c}" for m, c, tem in _rotas_do_modulo() if not tem]
    assert not abertas, "rotas sem autenticação:\n  " + "\n  ".join(abertas)


def test_toda_rota_admin_exige_acao_admin() -> None:
    """`get_current_user` autentica mas não autoriza: um operador logado
    passaria. As rotas `/admin/` precisam do `get_admin_user`."""
    import ast
    fonte = FONTE.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    fracas = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decs = [d for d in no.decorator_list
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name)
                and d.func.value.id == "router"]
        if not decs or not decs[0].args:
            continue
        caminho = decs[0].args[0].value
        if not str(caminho).startswith("/admin"):
            continue
        defaults = list(no.args.defaults) + [d for d in no.args.kw_defaults if d]
        usa_admin = any(
            isinstance(d, ast.Call) and getattr(d.func, "id", "") == "Depends"
            and any(getattr(a, "id", "") == "get_admin_user" for a in d.args)
            for d in defaults)
        if not usa_admin:
            fracas.append(f"{decs[0].func.attr.upper()} {caminho}")
    assert not fracas, ("rotas /admin sem `get_admin_user`:\n  "
                        + "\n  ".join(fracas))
