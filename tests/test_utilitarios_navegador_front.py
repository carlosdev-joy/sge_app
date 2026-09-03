"""Navegador de pastas (F6 da spec docs/spec-utilitarios-arquivos.md) — o front.

  1. **Bancada renderizada** (`tests/js/utilitarios_navegador_harness.cjs`): o
     componente roda no React mínimo da casa e a bancada CLICA — nível zero
     lista as raízes; pasta desce; arquivo devolve pasta + nome; link para
     fora fica inerte; Subir/Backspace seguem o `pai` e nunca sobem acima da
     raiz; "Usar esta pasta" só com pasta aberta; filtro por nome. Sem Node
     ou sem `node_modules`, SALTA.
  2. **Anti-drift** sem Node: as duas abas têm o botão Navegar…, a página chama
     `/utilitarios/pasta/listar`, e o clique num arquivo na aba de edição
     separa a extensão.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_navegador_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
PAGINA = RAIZ / "ui-react" / "src" / "pages" / "Utilitarios.tsx"
CAMPO = RAIZ / "ui-react" / "src" / "components" / "utilitarios" / "CampoPasta.tsx"


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


def _sem_comentarios(fonte: str) -> str:
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in fonte.splitlines())


# ═══════════ 1. puras ══════════════════════════════════════════════════════

def test_o_que_desce_e_o_que_e_arquivo(cen):
    p = cen["puras"]
    assert p["podeDescer"] == [True, True, True, False, False]
    assert p["ehArquivo"] == [True, True, False, False]
    assert p["caminho"] == ["/dados/bi", "/dados/bi/2026", "/dados/bi/x.txt"]


def test_migalhas_da_raiz_ate_a_pasta(cen):
    m = cen["puras"]["migalhas"]
    assert m[0] == []
    assert m[1] == [{"rotulo": "/dados/bi", "caminho": "/dados/bi"}]
    assert m[2] == [{"rotulo": "/dados/bi", "caminho": "/dados/bi"}, {"rotulo": "2026", "caminho": "/dados/bi/2026"},
                    {"rotulo": "cargas", "caminho": "/dados/bi/2026/cargas"}]
    assert m[3] == [{"rotulo": "/u01/dados/x", "caminho": "/u01/dados/x"}]   # raiz-symlink: caminho real inteiro


def test_descricao_e_erro(cen):
    assert cen["puras"]["descricao"] == ["raiz liberada", "pasta", "arquivo · 1,5 KB", "link → pasta",
                                         "link → arquivo · 15 B", "link (fora dos diretórios liberados ou quebrado)",
                                         "link (não verificado — clique para tentar)"]
    assert cen["puras"]["erro"] == ["Fora dos diretórios liberados.", "Pasta não encontrada.", "Não foi possível listar a pasta."]


def test_onde_o_navegador_abre(cen):
    # várias raízes e nada digitado → lista das raízes; uma raiz só → direto nela;
    # pasta digitada abaixo de uma raiz → nela; fora → raízes (ou a única raiz).
    assert cen["puras"]["inicio"] == [None, "/dados/bi", "/dados/bi/2026", None, "/dados/bi", None]


# ═══════════ 2. navegador ══════════════════════════════════════════════════

def test_nivel_zero_lista_as_raizes_e_nao_sobe(cen):
    z = cen["nivelZero"]
    assert z["entradas"] == ["/dados/bi", "/dados/param"]
    assert z["subirDesligado"] is True and z["usarDesligado"] is True
    assert z["migalhas"] == ["raizes"]
    assert z["navegou"] == ["/dados/bi"]
    assert z["backspaceNoZero"] == ["/dados/bi"]          # Backspace no nível zero não faz nada


def test_dentro_da_raiz_pastas_arquivos_links_e_gestos(cen):
    r = cen["raiz"]
    assert r["migalhas"] == ["raizes", "/dados/bi"]
    assert r["entradas"] == [["2026", "pasta", None], ["logs", "pasta", None], ["consulta.sql", "arquivo", None],
                             ["imagem.bin", "arquivo", None], ["link_fora", "link", None], ["atalho.param", "link", "arquivo"],
                             ["l_desconhecido", "link", "desconhecido"], ["RELATORIO.TXT", "arquivo", None], ["README", "arquivo", None]]
    assert r["linkForaInerte"] is True and r["atalhoAtivo"] is True and r["desconhecidoAtivo"] is True
    assert r["subirDesligado"] is False
    assert "1 ocultos escondidos" in r["rodape"] and "1 links não verificados" in r["rodape"]
    assert "consulta.sql" in r["textoConsulta"] and "15 B" in r["textoConsulta"]
    assert r["real"] == 0                          # caminho_real == caminho: sem nota
    assert r["todosTypeButton"] is True            # dentro do <form>: nenhum botão pode submeter
    assert r["enterNoFiltroPrevenido"] == 1
    c = r["chamadas"]
    # pasta; link não verificado (tenta); Subir na raiz → zero; Backspace → zero; migalha raízes
    assert c["navegar"] == ["/dados/bi/2026", "/dados/bi/l_desconhecido", None, None, None]
    assert c["arquivo"] == [["/dados/bi", "consulta.sql"], ["/dados/bi", "atalho.param"]]
    assert c["usar"] == ["/dados/bi"]
    assert c["ocultos"] == [True]
    assert r["filtrado"] == ["consulta.sql"] and r["filtroVazio"] == 1


def test_no_fundo_subir_segue_o_pai_e_a_migalha_volta(cen):
    f = cen["fundo"]
    assert f["migalhas"] == ["raizes", "/dados/bi", "/dados/bi/2026", "/dados/bi/2026/cargas"]   # lexical, não o real
    assert f["real"] == "→ /u01/dados/bi/2026/cargas"                                          # o real é só nota
    assert "truncada em 1" in f["rodape"]
    assert f["navegou"] == ["/dados/bi/2026", "/dados/bi"]


def test_carregando_erro_e_fechado(cen):
    assert cen["carregando"] == {"spinner": 1, "entradas": 0}
    assert cen["erro"] == {"caixa": 1, "texto": True}
    assert cen["fechado"] == 0


# ═══════════ 3. os formulários com o navegador ═════════════════════════════

def test_ver_arquivo_navega_e_preenche_pasta_e_nome(cen):
    v = cen["formVer"]
    assert v["botao"] == 1 and v["fechadoNoInicio"] == 0
    assert v["abriuNoZero"] == {"aberto": 1, "pedidos": [["datastage", None, False]], "entradas": ["/dados/bi", "/dados/param"]}
    assert v["desceu"]["entradas"] == ["2026", "logs", "consulta.sql"]
    assert v["desceu"]["migalhas"] == ["raizes", "/dados/bi"]
    assert v["escolheuArquivo"] == {"pasta": "/dados/bi", "nome": "consulta.sql", "aberto": 0}


def test_ver_arquivo_abre_na_pasta_digitada_e_usa_esta_pasta(cen):
    v = cen["formVer"]
    assert v["abriuNaDigitada"] == {"ultimoPedido": ["datastage", "/dados/bi/2026/cargas", False], "entradas": ["carga_utf8.txt"]}
    assert v["usouPasta"] == {"pasta": "/dados/bi/2026/cargas", "aberto": 0}   # lexical (o real é /u01/…)
    assert v["filtrouTudo"] == 0 and v["reabriuSemFiltro"] == {"entradas": 1, "filtro": ""}   # o filtro morre com o painel


def test_pasta_digitada_invalida_mostra_o_erro_e_cai_nas_raizes(cen):
    p = cen["formVer"]["pastaInvalida"]
    assert p["pedidos"] == [["datastage", "/dados/bi/nao_existe", False], ["datastage", None, False]]
    assert p["erro"] == 1 and p["entradas"] == ["/dados/bi", "/dados/param"] and p["carregando"] == 0


def test_ocultos_relista_a_pasta_atual(cen):
    v = cen["formVer"]
    assert v["ocultosDesligadoNoZero"] is True                        # no nível zero não há o que esconder
    assert v["ocultos"] == ["datastage", "/dados/bi", True]
    assert v["fechou"] == 0
    assert cen["formVerSemListar"] == 0 and cen["formVerSemRaiz"] is True


def test_editar_arquivo_separa_nome_e_extensao_do_arquivo_escolhido(cen):
    e = cen["formEditar"]
    assert e["botao"] == 1
    assert e["sql"] == {"pasta": "/dados/bi", "nome": "consulta", "extensao": "sql", "aberto": 0, "gravar": False, "carregar": False}
    assert e["bin"] == {"nome": "imagem", "extensao": "bin", "gravar": True, "aviso": True}
    assert e["abriuNaPastaDoCampo"] == ["datastage", "/dados/bi", False]   # o campo já tinha /dados/bi: abre nela
    assert e["maiuscula"] == {"nome": "imagem", "aviso": 1, "cita": True}   # RELATORIO.TXT: nome intacto + aviso
    assert e["semExtensao"] == {"nome": "imagem", "aviso": 1}              # README idem
    assert e["avisoSomeAoDigitar"] == 0
    assert cen["formEditarOperador"] is True


# ═══════════ 4. anti-drift (sem Node) ══════════════════════════════════════

def test_navegar_esta_nas_duas_abas_e_a_pagina_lista():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "/utilitarios/pasta/listar" in pagina
    assert pagina.count("onListar={listarPasta}") == 2, "as duas abas recebem o listar"
    campo = _sem_comentarios(CAMPO.read_text(encoding="utf-8"))
    assert "data-acao=\"navegar\"" in campo
    for f in ("FormVerArquivo.tsx", "FormEditarArquivo.tsx"):
        fonte = _sem_comentarios((RAIZ / "ui-react" / "src" / "components" / "utilitarios" / f).read_text(encoding="utf-8"))
        assert "<CampoPasta" in fonte and "<NavegadorPastas" in fonte and "useNavegadorPastas(" in fonte, f
        assert "chega na F" not in fonte
