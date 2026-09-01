"""GET /pio/contagens e /pio/propostas — a fonte real dos cards do Workflow.

O que estes testes prendem:

  1. **"Não consegui ler" ≠ "não há carga".** As duas chegam como card zerado
     na tela, e só `disponivel` separa uma da outra. Sem essa distinção, o dia
     em que a carga das 07:30 falhar tem exatamente a mesma aparência de um dia
     sem propostas pendentes — e ninguém investiga um zero.
  2. **Tabela ausente NÃO derruba o endpoint.** No intervalo normal do deploy
     (API nova, migration 101 ainda não aplicada) a tela precisa abrir.
  3. **Categoria desconhecida não vira consulta.** O valor entra
     parametrizado, mas recusar cedo evita varrer 8.700 linhas por um filtro
     que não existe.
  4. **O mapeamento de campos**, que é onde a lista mente sem dar erro:
     celular preferido ao residencial, prêmio numérico, dias pendentes
     inteiros.
  5. **Busca de CPF ignora máscara** — o banco guarda de um jeito e a tela
     mostra de outro; comparar literal devolve "nada encontrado" para um CPF
     que existe.
  6. **Placeholder `?`, nunca `%s`** — esta é a árvore `api/` (pyodbc). O
     dialeto errado dá "Incorrect syntax near" com o endpoint de pé.

Nada toca banco: cursor dublê e `get_db_conn` substituído.
"""
from __future__ import annotations

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

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "pio.py"


def _det(proposta="80316460327404", nome="Maria Silva", cpf="397.750.878-48",
         agencia="0316", matricula="106562", venda="2026-08-02", dias=30,
         produto="Vida Conforto", area="Vida", premio=129.90, imp=50000.0,
         cidade="Curitiba", uf="PR", ddd_cel="41", cel="998765432",
         ddd_res="41", res="33221100", email="maria@example.com", idade=45,
         situacao="AT", pago="N", referencia="2026-09-01"):
    """Uma linha do SELECT de `_DET`, na ordem exata do router."""
    return (proposta, nome, cpf, agencia, matricula, venda, dias,
            produto, area, premio, imp, cidade, uf,
            ddd_cel, cel, ddd_res, res, email, idade, situacao, pago,
            referencia)


class CursorFalso:
    """Responde ao COUNT e ao SELECT da página, e registra o SQL executado."""

    def __init__(self, linhas=None, total=None, estoura=False):
        self.linhas = linhas if linhas is not None else []
        self.total = total if total is not None else len(self.linhas)
        self.estoura = estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ultimo_count = False

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.PIO_PROPOSTA_PENDENTE_DET'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ultimo_count = "COUNT(*)" in sql
        return self

    def fetchone(self):
        return (self.total,) if self._ultimo_count else None

    def fetchall(self):
        return [] if self._ultimo_count else self.linhas

    def close(self):
        pass


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador",
        "permissoes": ["tela_caixa_seguro"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def sem_permissao():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U2", "perfil": "visitante", "permissoes": []}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": CursorFalso()}

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.pio.get_db_conn", _fabrica)
    return estado


# ═══════════ 1 e 2. as duas caras do card zerado ════════════════════════════

def test_contagem_lida_marca_disponivel(cliente, banco):
    banco["cur"] = CursorFalso([("PE", "Pendentes de Assinatura", 8706,
                                 "2026-09-01", "2026-09-01 07:30:11")])
    d = cliente.get("/pio/contagens").json()
    assert d["disponivel"] is True
    assert d["referencia"] == "2026-09-01"
    assert d["categorias"][0] == {
        "categoria": "PE", "descricao": "Pendentes de Assinatura",
        "quantidade": 8706, "carga": "2026-09-01 07:30:11"}


def test_carga_que_nao_rodou_e_lista_vazia_com_disponivel(cliente, banco):
    """Li a tabela, e não há linha. É notícia sobre o DADO."""
    banco["cur"] = CursorFalso([])
    d = cliente.get("/pio/contagens").json()
    assert d["disponivel"] is True
    assert d["categorias"] == []


def test_tabela_ausente_nao_derruba_e_avisa(cliente, banco):
    """Não li a tabela. É notícia sobre o AMBIENTE — e a tela precisa saber
    que a diferença existe, senão trata falha de carga como fila vazia."""
    banco["cur"] = CursorFalso(estoura=True)
    r = cliente.get("/pio/contagens")
    assert r.status_code == 200
    assert r.json()["disponivel"] is False


def test_propostas_com_tabela_ausente_tambem_degrada(cliente, banco):
    banco["cur"] = CursorFalso(estoura=True)
    d = cliente.get("/pio/propostas?categoria=PE").json()
    assert d["disponivel"] is False
    assert d["itens"] == [] and d["total"] == 0


def test_descricao_cai_no_dicionario_quando_a_carga_nao_trouxe(cliente, banco):
    """`DES_CATEGORIA` vazia não pode virar card sem nome na tela."""
    banco["cur"] = CursorFalso([("PE", "", 10, "2026-09-01", "2026-09-01 07:30:00")])
    d = cliente.get("/pio/contagens").json()
    assert d["categorias"][0]["descricao"] == "Pendentes de Assinatura"


# ═══════════ 3. categoria fora do catálogo ══════════════════════════════════

def test_categoria_desconhecida_nao_consulta_o_banco(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    d = cliente.get("/pio/propostas?categoria=XX").json()
    assert d["itens"] == [] and d["total"] == 0
    assert banco["cur"].sqls == [], "consultou o banco por uma categoria que não existe"


@pytest.mark.parametrize("codigo", ["PE", "PP", "AP", "AN", "EM", "RE"])
def test_as_seis_categorias_da_carga_sao_aceitas(cliente, banco, codigo):
    banco["cur"] = CursorFalso([_det()])
    d = cliente.get(f"/pio/propostas?categoria={codigo}").json()
    assert d["disponivel"] is True
    assert d["categoria"] == codigo


def test_limite_acima_do_teto_e_recusado(cliente, banco):
    """Sem teto, uma chamada pede as 8.706 de uma vez."""
    assert cliente.get("/pio/propostas?categoria=PE&limite=5000").status_code == 422


# ═══════════ 4. o mapeamento de campos ══════════════════════════════════════

def test_campos_da_proposta(cliente, banco):
    banco["cur"] = CursorFalso([_det()], total=8706)
    d = cliente.get("/pio/propostas?categoria=PE").json()
    item = d["itens"][0]
    assert d["total"] == 8706, "o total é da CONSULTA inteira, não da página"
    assert item["proposta"] == "80316460327404"
    assert item["nome"] == "Maria Silva"
    assert item["premio"] == 129.90 and isinstance(item["premio"], float)
    assert item["dias_pendente"] == 30 and isinstance(item["dias_pendente"], int)
    assert item["uf"] == "PR" and item["idade"] == 45
    assert d["referencia"] == "2026-09-01"


def test_telefone_prefere_o_celular(cliente, banco):
    """Quem opera liga para o celular: com os dois preenchidos, o residencial
    não pode ser o que aparece."""
    banco["cur"] = CursorFalso([_det(ddd_cel="41", cel="998765432")])
    item = cliente.get("/pio/propostas?categoria=PE").json()["itens"][0]
    assert item["telefone"] == "(41) 998765432"


def test_telefone_cai_no_residencial_sem_celular(cliente, banco):
    banco["cur"] = CursorFalso([_det(ddd_cel="", cel="", ddd_res="41", res="33221100")])
    item = cliente.get("/pio/propostas?categoria=PE").json()["itens"][0]
    assert item["telefone"] == "(41) 33221100"


def test_sem_telefone_nenhum_o_campo_vem_vazio(cliente, banco):
    """String vazia, não "( ) " — rótulo de telefone com parênteses vazios na
    tela parece dado, e não é."""
    banco["cur"] = CursorFalso([_det(ddd_cel="", cel="", ddd_res="", res="")])
    item = cliente.get("/pio/propostas?categoria=PE").json()["itens"][0]
    assert item["telefone"] == ""


def test_valores_nulos_nao_viram_zero(cliente, banco):
    """`None` em prêmio é "não sei", e zero é "de graça". A tela precisa poder
    mostrar coisas diferentes."""
    banco["cur"] = CursorFalso([_det(premio=None, imp=None, idade=None)])
    item = cliente.get("/pio/propostas?categoria=PE").json()["itens"][0]
    assert item["premio"] is None and item["imp_segurada"] is None
    assert item["idade"] is None


# ═══════════ 5. busca ═══════════════════════════════════════════════════════

def test_busca_por_cpf_compara_so_digitos(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?categoria=PE&busca=397.750.878-48")
    params = banco["cur"].params[0]
    assert "%39775087848%" in params, (
        "a máscara do CPF foi para a consulta — o banco guarda sem ela")


def test_busca_por_nome_vai_inteira(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?categoria=PE&busca=Maria")
    assert "%Maria%" in banco["cur"].params[0]


def test_sem_busca_nao_ha_filtro_de_texto(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?categoria=PE")
    assert "LIKE" not in banco["cur"].sqls[0]


# ═══════════ 6. dialeto e permissão ═════════════════════════════════════════

def _strings_sql() -> list[str]:
    """Só os literais que são SQL — lidos da árvore sintática, não do texto.

    Ler o arquivo linha a linha reprovava o próprio comentário que EXPLICA a
    regra (ele cita `%s` para dizer que não se usa aqui) e o `%s` do log.
    """
    import ast
    arvore = ast.parse(ROUTER.read_text(encoding="utf-8"))
    return [no.value for no in ast.walk(arvore)
            if isinstance(no, ast.Constant) and isinstance(no.value, str)
            and ("SELECT" in no.value or "WHERE" in no.value)]


def test_o_router_usa_placeholder_de_pyodbc():
    """`api/` é pyodbc (`?`); `dags/` é pymssql (`%s`). Trocar dá "Incorrect
    syntax near" — e o erro chega como se fosse a tabela, não o dialeto."""
    culpados = [s for s in _strings_sql() if "%s" in s]
    assert not culpados, f"placeholder de pymssql na árvore api/: {culpados}"


def test_ha_sql_para_conferir():
    """Guarda do teste acima: se a regex/AST parar de achar SQL nenhum, ele
    passaria por vazio — o falso verde clássico de teste que lê fonte."""
    assert _strings_sql(), "nenhum SQL encontrado no router — o leitor quebrou"


def test_a_pagina_tem_order_by(cliente, banco):
    """OFFSET/FETCH sem ORDER BY é erro de sintaxe no SQL Server — e, se
    passasse, a página 2 poderia repetir linha da página 1."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?categoria=PE&offset=50")
    pagina = banco["cur"].sqls[1]
    assert "ORDER BY" in pagina and "OFFSET" in pagina


def test_mais_antigas_primeiro(cliente, banco):
    """A fila do card existe para mostrar o atraso: a proposta parada há mais
    tempo é a que precisa aparecer antes."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?categoria=PE")
    assert "ORDER BY d.DTH_VENDA ASC" in banco["cur"].sqls[1]


@pytest.mark.parametrize("rota", ["/pio/contagens", "/pio/propostas?categoria=PE"])
def test_exige_a_permissao_da_secao(sem_permissao, rota):
    r = sem_permissao.get(rota)
    assert r.status_code == 403
    assert "tela_caixa_seguro" in r.json()["detail"]


# ═══════════ 7. o front e o back falando do mesmo card ══════════════════════
# `ORIGEM_PIO` (TypeScript) diz qual card lê qual categoria; `CATEGORIAS`
# (Python) diz quais categorias existem. Os dois são listas escritas à mão em
# linguagens diferentes, e nada além destes testes impede que divirjam — uma
# categoria com um caractere trocado no front devolve lista vazia com HTTP 200,
# e o card mostra ZERO. Não há erro em lugar nenhum para investigar.

CAIXA = Path(__file__).resolve().parents[1] / "ui-react" / "src" / "caixa"
PIO_TS = CAIXA / "lib" / "pio.ts"
WORKFLOW_TS = CAIXA / "lib" / "workflow.ts"
COMPONENTES = [CAIXA / "components" / "InlineWorkflow.tsx",
               CAIXA / "components" / "ProposalWorkflowSheet.tsx"]


def _origem_pio() -> dict[str, str]:
    """{status do card: categoria} lido de ORIGEM_PIO, ignorando o comentário
    que lista as categorias ainda não ligadas."""
    import re as _re
    bloco = _re.search(r"export const ORIGEM_PIO:.*?\n\};",
                       PIO_TS.read_text(encoding="utf-8"), _re.S)
    assert bloco, "ORIGEM_PIO não encontrado em lib/pio.ts"
    ativos = [l for l in bloco.group(0).splitlines() if not l.strip().startswith("//")]
    return dict(_re.findall(r'(\w+):\s*"(\w+)"', "\n".join(ativos)))


def test_ha_pelo_menos_um_card_ligado():
    """Guarda dos dois testes abaixo: com ORIGEM_PIO vazio eles passariam sem
    verificar nada."""
    assert _origem_pio(), "nenhum card lendo do PIO — o leitor quebrou?"


def test_toda_categoria_do_front_existe_no_router():
    from routers.pio import CATEGORIAS
    desconhecidas = set(_origem_pio().values()) - set(CATEGORIAS)
    assert not desconhecidas, (
        f"o front pede categoria que o router recusa: {sorted(desconhecidas)} — "
        f"o card mostraria zero, sem erro nenhum")


def test_todo_card_ligado_existe_na_sequencia():
    import re as _re
    fonte = WORKFLOW_TS.read_text(encoding="utf-8")
    bloco = _re.search(r"export const SEQUENCIA_WORKFLOW.*?\n\];", fonte, _re.S)
    da_sequencia = set(_re.findall(r'value:\s*"(\w+)"', bloco.group(0)))
    fora = set(_origem_pio()) - da_sequencia
    assert not fora, f"ORIGEM_PIO liga status que não tem card: {sorted(fora)}"


@pytest.mark.parametrize("arquivo", COMPONENTES, ids=lambda p: p.stem)
def test_o_exemplo_sai_de_cena_onde_ha_dado_real(arquivo):
    """Mock e carga descrevendo o mesmo card é como um número de teste vira
    produção aos olhos de quem lê a tela."""
    fonte = arquivo.read_text(encoding="utf-8")
    assert "propostasWorkflow.filter((p) => !ORIGEM_PIO[p.status])" in fonte, (
        f"{arquivo.name} pode listar proposta de exemplo num card que já lê a carga")


def test_nenhum_card_ligado_depende_de_sub_filtro():
    """Armadilha para a PRÓXIMA ligação, não para esta.

    A lista de um card que lê a carga vem paginada do servidor, e o sub-filtro
    da tela roda sobre o array local — ou seja, ele não se aplica ali. Hoje
    isso é inofensivo: o único card ligado (`pending_signature`) não tem
    sub-status. Ligar `awaiting_payment` ou `in_analysis` sem antes levar o
    sub-filtro para a consulta faria o Select aparecer na tela e não filtrar
    nada — mudar a opção, a lista continuar igual, e ninguém entender por quê.
    """
    import re as _re
    inline = COMPONENTES[0].read_text(encoding="utf-8")
    bloco = _re.search(r"const SUB_FILTRO:.*?\n\};", inline, _re.S)
    com_sub_filtro = set(_re.findall(r"(\w+):\s*\{\s*campo:", bloco.group(0)))
    conflito = set(_origem_pio()) & com_sub_filtro
    assert not conflito, (
        f"{sorted(conflito)} lê do PIO E tem sub-filtro local: o Select apareceria "
        f"sem filtrar. Leve o sub-status para /pio/propostas antes de ligar o card.")


@pytest.mark.parametrize("arquivo", COMPONENTES, ids=lambda p: p.stem)
def test_card_com_origem_real_nao_mostra_zero_sem_saber(arquivo):
    """Zero é uma resposta, e nem "ainda estou lendo" nem "não consegui ler"
    são respostas. Os dois estados precisam ter símbolo próprio."""
    fonte = arquivo.read_text(encoding="utf-8")
    assert "contagens.isPending" in fonte, f"{arquivo.name}: sem estado de leitura"
    assert "contagens.data?.disponivel" in fonte, (
        f"{arquivo.name}: não distingue carga ilegível de carga vazia")
