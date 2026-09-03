"""Tela Utilitários › Ver arquivo (F3 da spec docs/spec-utilitarios-arquivos.md) — o front.

  1. **Bancada renderizada** (`tests/js/utilitarios_tela_harness.cjs`): o
     formulário e o modal rodam no React mínimo da casa e a bancada CLICA —
     Iniciar só com pasta abaixo de uma raiz e nome válido; o campo diz
     "abaixo de /dados/bi" ou "fora dos diretórios" antes da API; o modal
     abre em "buscando", vira conteúdo com rodapé, o Copiar diz o que
     aconteceu, e o 413 oferece "últimas N linhas" sem fechar. Sem Node
     ou sem `node_modules`, SALTA.
  2. **Anti-drift** por leitura do fonte, sem Node: a tela está nos QUATRO
     lugares (NAV, App, RBAC_RECURSOS, migration), a página chama os
     endpoints da F1, e o Copiar passa por `lib/copiar.ts` — nunca por
     `navigator.clipboard` direto (a produção é HTTP).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_tela_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
NAV = RAIZ / "ui-react" / "src" / "lib" / "nav.ts"
APP = RAIZ / "ui-react" / "src" / "App.tsx"
ADMIN = RAIZ / "ui-react" / "src" / "pages" / "Admin.tsx"
PAGINA = RAIZ / "ui-react" / "src" / "pages" / "Utilitarios.tsx"
MODAL = RAIZ / "ui-react" / "src" / "components" / "utilitarios" / "ModalConteudoArquivo.tsx"
MIGRATION = RAIZ / "sql" / "migrations" / "105_utilitarios_arquivos.sql"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. funções puras ══════════════════════════════════════════════

def test_raiz_de_por_componente(cen):
    r = cen["puras"]["raizDe"]
    assert r["dentro"] == "/dados/bi" and r["igual"] == "/dados/param"
    assert r["prefixoEnganoso"] is None and r["fora"] is None
    assert r["raizBarra"] is None          # raiz `/` nunca libera


def test_aviso_da_pasta_antes_da_api(cen):
    a = cen["puras"]["avisoPasta"]
    assert a["vazio"] is None
    assert a["relativa"]["tom"] == "erro" and "absoluto" in a["relativa"]["texto"]
    assert a["fora"] == {"tom": "erro", "texto": "Fora dos diretórios liberados."}
    assert a["traversal"]["tom"] == "erro"          # o `..` é resolvido antes de conferir
    assert a["dentro"] == {"tom": "neutro", "texto": "abaixo de /dados/bi"}
    assert "Admin" in a["semRaizes"]["texto"]
    assert "1000" in a["longa"]["texto"]


def test_nome_ultimas_e_pedido_pronto(cen):
    n = cen["puras"]["avisoNome"]
    assert n["vazio"] is None and n["ok"] is None
    assert n["barra"] and n["ponto"] and "255" in n["longo"]
    u = cen["puras"]["ultimasLinhas"]
    assert u == {"vazio": None, "ok": 200, "zero": "invalido", "acima": "invalido",
                 "texto": "invalido", "decimal": "invalido"}
    p = cen["puras"]["pedidoPronto"]
    assert p == {"ok": True, "semNome": False, "fora": False, "nomeRuim": False, "ultimasRuim": False}


def test_erro_de_leitura_e_resumo(cen):
    e = cen["puras"]["erroLeitura"]
    assert e["detail"] == {"status": 403, "mensagem": "Fora dos diretórios liberados."}
    assert e["lista"]["status"] == 422 and "ultimas_linhas" in e["lista"]["mensagem"]
    assert e["semDetail413"]["status"] == 413 and "últimas N linhas" in e["semDetail413"]["mensagem"]
    # 502 SEM detail é o nginx por uma API fora do ar; COM detail é a própria API (SSH).
    assert "API do Orquestra não respondeu" in e["nginx502"]["mensagem"]
    assert "SSH" in e["apiSsh502"]["mensagem"]
    assert e["rede"] == {"status": None, "mensagem": "Não foi possível falar com a API."}
    assert e["nada"]["status"] is None
    assert cen["puras"]["formatarTamanho"] == ["512 B", "1,5 KB", "4,8 MB"]
    assert cen["puras"]["resumo"] == ["1,5 KB", "1 linha (só o fim)", "codificação latin-1",
                                      "modificado em 2026-09-03 10:00:00", "1,2 s"]


# ═══════════ 2. formulário ═════════════════════════════════════════════════

def test_iniciar_so_liga_com_pasta_dentro_da_raiz_e_nome_valido(cen):
    f = cen["form"]
    assert f["desligadoNoInicio"] is True
    assert f["placeholderPasta"] == "/dados/bi/…"
    assert f["relativa"] == {"desligado": True, "aviso": True}
    assert f["fora"] == {"desligado": True, "aviso": True}
    assert f["dentro"] == {"raizDe": ["abaixo de /dados/bi"], "desligadoSemNome": True}
    assert f["nomeRuim"] == {"desligado": True, "aviso": True}
    assert f["valido"]["desligado"] is False
    assert f["ultimasRuim"] == {"desligado": True, "aviso": True}
    assert f["ocupado"] is True


def test_iniciar_manda_o_pedido_certo(cen):
    pedidos = cen["form"]["pedidos"]
    assert pedidos == [
        {"servidor": "datastage", "diretorio": "/dados/bi/2026", "nome": "carga.txt", "ultimas_linhas": 200},
        {"servidor": "datastage", "diretorio": "/dados/bi/2026", "nome": "carga.txt"},
    ]


def test_sem_raiz_o_campo_aponta_o_admin(cen):
    s = cen["form"]["semRaiz"]
    assert s["desligado"] is True and s["aviso"] is True
    assert s["placeholder"] == "/caminho/da/pasta"


# ═══════════ 3. modal ══════════════════════════════════════════════════════

def test_modal_abre_buscando_e_fecha(cen):
    b = cen["modal"]["buscando"]
    assert b["estado"] == "buscando"
    assert b["caminho"] == "/dados/bi/consulta.sql"     # barra final do pedido colapsada
    assert b["spinner"] == 1 and b["conteudo"] == 0
    assert b["fechou"] == 1
    assert cen["modal"]["fechado"] == {"nos": 0}


def test_modal_pronto_mostra_conteudo_e_rodape(cen):
    p = cen["modal"]["pronto"]
    assert p["caminhoReal"] == "/dados/bi/consulta.sql"
    assert p["texto"] == "SELECT 1 AS x;"
    assert p["resumo"] == "15 B 1 linha codificação utf-8 modificado em 2026-09-03 00:57:23 0,2 s"
    assert p["truncadoBadge"] is False and p["spinner"] == 0
    # Arquivo vazio: badge de truncado, placeholder, e NADA a copiar (senão o
    # fallback selecionaria o próprio placeholder "(arquivo vazio)").
    assert cen["modal"]["truncadoVazio"] == {"badge": True, "vazio": True, "copiarDesligado": True}


def test_copiar_leva_o_conteudo_inteiro_e_diz_o_que_aconteceu(cen):
    ok = cen["modal"]["copiarOk"]
    # COM o `\n` final: copiar conteúdo de arquivo não pode alterar o dado
    # (o `trim` do helper é para número de chamado, não para arquivo).
    assert ok["escritos"] == ["SELECT 1 AS x;\n"]
    assert ok["aviso"] == ["copiado"] and ok["check"] == 1
    assert cen["modal"]["copiarSemApi"]["aviso"] == ["use Ctrl+C"]


def test_413_oferece_ultimas_linhas_sem_fechar(cen):
    e = cen["modal"]["erro413"]
    assert e["mensagem"] is True and e["form"] is True
    assert e["valorInicial"] == "200" and e["botaoLigado"] is True
    assert e["invalido"] is True
    assert e["retentar"] == [200]                       # o submit inválido não chamou
    assert cen["modal"]["erro403"] == {"mensagem": True, "form": 0, "atributo": 403}


# ═══════════ 4. anti-drift (sem Node) ══════════════════════════════════════

def test_tela_nos_quatro_lugares():
    nav = NAV.read_text(encoding="utf-8")
    assert re.search(r"to:\s*'/utilitarios',\s*label:\s*'Utilitários',\s*icon:\s*Wrench,\s*group:\s*'Operação',\s*perm:\s*'tela_utilitarios'", nav)
    app = APP.read_text(encoding="utf-8")
    assert "'/utilitarios': <Utilitarios />" in app and "from './pages/Utilitarios'" in app
    admin = ADMIN.read_text(encoding="utf-8")
    assert "['tela_utilitarios', 'Utilitários']" in admin
    mig = MIGRATION.read_text(encoding="utf-8")
    for perfil in ("admin", "desenvolvedor", "operador"):
        assert re.search(rf"\('{perfil}',\s*'tela_utilitarios'\)", mig), perfil


def _sem_comentarios(fonte: str) -> str:
    """O comentário que documenta a guarda CONTÉM a guarda (falso positivo que o
    repo já pagou em test_migrations_idempotentes): só o código conta."""
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in fonte.splitlines())


def test_pagina_chama_os_endpoints_e_copia_pelo_helper():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "/utilitarios/config" in pagina and "/utilitarios/arquivo/ler" in pagina
    modal = MODAL.read_text(encoding="utf-8")
    assert "from '../../lib/copiar'" in modal
    assert "navigator.clipboard" not in _sem_comentarios(modal), \
        "clipboard direto não existe em HTTP — use lib/copiar"
    # Nada de aba "em breve" desabilitada: uma aba ou existe inteira ou não aparece.
    assert "em breve" not in pagina
    # Achado da revisão adversarial: os callbacks vão POR CHAMADA (`mutate(p, {...})`)
    # e conferem o número de série — a resposta de um pedido fechado não pode
    # sobrescrever o modal do pedido atual.
    assert "leitura.mutate(p, {" in pagina and "serie.current === minha" in pagina
    modal_codigo = _sem_comentarios(modal)
    assert "{ bruto: true }" in modal_codigo, "copiar conteúdo de arquivo não pode passar por trim"
