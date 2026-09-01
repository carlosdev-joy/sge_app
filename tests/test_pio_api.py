"""GET /pio/contagens e /pio/propostas — a fonte real dos cards do Workflow.

O que estes testes prendem:

  1. **"Não consegui ler" ≠ "não há carga".** As duas chegam como card zerado
     na tela, e só `disponivel` separa uma da outra. Sem essa distinção, o dia
     em que a carga das 07:30 falhar tem exatamente a mesma aparência de um dia
     sem propostas pendentes — e ninguém investiga um zero.
  2. **Tabela ausente NÃO derruba o endpoint.** No intervalo normal do deploy
     (API nova, migration 101 ainda não aplicada) a tela precisa abrir.
  3. **Card desconhecido não vira consulta, e o `card` nunca vira SQL.** O
     COD_CARD escolhe a TABELA de detalhe, e nome de objeto não aceita
     parâmetro em T-SQL: a lista branca `CARDS` é a única fronteira entre a
     querystring e o FROM.
  3b. **Cada card lê a SUA tabela, e a DET não é refiltrada por status.** As
     duas DET têm estrutura idêntica — trocar uma pela outra devolve propostas
     erradas com cara de certas; e refiltrar o que a carga já filtrou é como um
     card zera sozinho quando o critério da carga mudar.
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
         situacao="AT", pago="N", referencia="2026-09-01", renda=4800.0):
    """Uma linha do SELECT de `_DET`, na ordem exata do router."""
    return (proposta, nome, cpf, agencia, matricula, venda, dias,
            produto, area, premio, imp, cidade, uf,
            ddd_cel, cel, ddd_res, res, email, idade, situacao, pago,
            referencia, renda)


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
    banco["cur"] = CursorFalso([("PEND_ASSIN", "Pendentes de Assinatura", 8706,
                                 "2026-09-01", "2026-09-01 07:30:11")])
    d = cliente.get("/pio/contagens").json()
    assert d["disponivel"] is True
    assert d["referencia"] == "2026-09-01"
    assert d["cards"][0] == {
        "card": "PEND_ASSIN", "descricao": "Pendentes de Assinatura",
        "quantidade": 8706, "carga": "2026-09-01 07:30:11"}


def test_todos_os_cards_vem_na_mesma_contagem(cliente, banco):
    """Uma leitura só alimenta todos os cards — se um sumisse da resposta, o
    front o trataria como "zero de verdade"."""
    banco["cur"] = CursorFalso([
        ("ASSINA_PAGA", "Assinadas e Pagas", 5120, "2026-09-01", "2026-09-01 07:32:40"),
        ("PEND_ASSIN", "Pendentes de Assinatura", 8706, "2026-09-01", "2026-09-01 07:30:11"),
        ("PEND_PGTO", "Pendentes de Pagamento", 22500, "2026-09-01", "2026-09-01 07:31:02"),
    ])
    d = cliente.get("/pio/contagens").json()
    assert [c["card"] for c in d["cards"]] == ["ASSINA_PAGA", "PEND_ASSIN", "PEND_PGTO"]
    assert [c["quantidade"] for c in d["cards"]] == [5120, 8706, 22500]


def test_carga_que_nao_rodou_e_lista_vazia_com_disponivel(cliente, banco):
    """Li a tabela, e não há linha. É notícia sobre o DADO."""
    banco["cur"] = CursorFalso([])
    d = cliente.get("/pio/contagens").json()
    assert d["disponivel"] is True
    assert d["cards"] == []


def test_tabela_ausente_nao_derruba_e_avisa(cliente, banco):
    """Não li a tabela. É notícia sobre o AMBIENTE — e a tela precisa saber
    que a diferença existe, senão trata falha de carga como fila vazia."""
    banco["cur"] = CursorFalso(estoura=True)
    r = cliente.get("/pio/contagens")
    assert r.status_code == 200
    assert r.json()["disponivel"] is False


def test_propostas_com_tabela_ausente_tambem_degrada(cliente, banco):
    banco["cur"] = CursorFalso(estoura=True)
    d = cliente.get("/pio/propostas?card=PEND_ASSIN").json()
    assert d["disponivel"] is False
    assert d["itens"] == [] and d["total"] == 0


def test_descricao_cai_no_dicionario_quando_a_carga_nao_trouxe(cliente, banco):
    """`DES_CARD` vazia não pode virar card sem nome na tela."""
    banco["cur"] = CursorFalso([("PEND_ASSIN", "", 10, "2026-09-01", "2026-09-01 07:30:00")])
    d = cliente.get("/pio/contagens").json()
    assert d["cards"][0]["descricao"] == "Pendentes de Assinatura"


# ═══════════ 3. card fora do catálogo, e a TABELA que ele escolhe ═══════════
# O `card` da querystring decide de qual tabela a lista sai. Nome de objeto não
# aceita parâmetro em T-SQL, então ele é interpolado no SQL — e a única coisa
# que separa isso de uma injeção é a lista branca `CARDS`. Estes testes prendem
# essa fronteira.

def test_card_desconhecido_nao_consulta_o_banco(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    d = cliente.get("/pio/propostas?card=XX").json()
    assert d["itens"] == [] and d["total"] == 0
    assert banco["cur"].sqls == [], "consultou o banco por um card que não existe"


@pytest.mark.parametrize("injecao", [
    "PEND_ASSIN; DROP TABLE dbo.PIO_AGG--",
    "dbo.OUTRA_TABELA",
    "PEND_ASSIN' OR '1'='1",
])
def test_card_malicioso_nunca_chega_ao_sql(cliente, banco, injecao):
    """O nome da tabela sai do dicionário, nunca da requisição."""
    banco["cur"] = CursorFalso([_det()])
    r = cliente.get("/pio/propostas", params={"card": injecao})
    assert r.status_code == 200
    assert banco["cur"].sqls == [], f"a requisição virou SQL: {banco['cur'].sqls}"


@pytest.mark.parametrize("codigo,tabela", [
    ("PEND_ASSIN", "dbo.PIO_PROPOSTA_PENDENTE_DET"),
    ("PEND_PGTO", "dbo.PIO_PROPOSTA_PEND_PGTO_DET"),
    ("ASSINA_PAGA", "dbo.PIO_PROPOSTA_ASSINA_PAGA_DET"),
])
def test_cada_card_le_a_sua_tabela(cliente, banco, codigo, tabela):
    """As três DET têm estrutura idêntica: trocar uma pela outra devolve uma
    lista plausível de propostas ERRADAS, sem erro nenhum. Vale em dobro para
    PEND_PGTO × ASSINA_PAGA, que saem do mesmo STA_ASSINATURA='CO' e só se
    distinguem pelo STA_PAGO."""
    banco["cur"] = CursorFalso([_det()])
    d = cliente.get(f"/pio/propostas?card={codigo}").json()
    assert d["disponivel"] is True
    assert d["card"] == codigo
    for sql in banco["cur"].sqls:
        assert tabela in sql, f"{codigo} consultou fora da sua tabela: {sql}"


def test_a_det_nao_e_refiltrada_por_status(cliente, banco):
    """A carga já entregou cada DET com o filtro do seu card. Refiltrar por
    `STA_ASSINATURA` aqui é como um card zera sozinho no dia em que a carga
    mudar de critério — a tela mostraria 0 com a tabela cheia."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=PEND_PGTO")
    for sql in banco["cur"].sqls:
        assert "STA_ASSINATURA" not in sql, (
            f"o router refiltra o que a carga já filtrou: {sql}")


def test_limite_acima_do_teto_e_recusado(cliente, banco):
    """Sem teto, uma chamada pede as 22.500 de PEND_PGTO de uma vez."""
    assert cliente.get("/pio/propostas?card=PEND_ASSIN&limite=5000").status_code == 422


# ═══════════ 4. o mapeamento de campos ══════════════════════════════════════

def test_campos_da_proposta(cliente, banco):
    banco["cur"] = CursorFalso([_det()], total=8706)
    d = cliente.get("/pio/propostas?card=PEND_ASSIN").json()
    item = d["itens"][0]
    assert d["total"] == 8706, "o total é da CONSULTA inteira, não da página"
    assert item["proposta"] == "80316460327404"
    assert item["nome"] == "Maria Silva"
    assert item["premio"] == 129.90 and isinstance(item["premio"], float)
    assert item["dias_pendente"] == 30 and isinstance(item["dias_pendente"], int)
    assert item["uf"] == "PR" and item["idade"] == 45
    assert d["referencia"] == "2026-09-01"


def test_renda_e_premio_sao_campos_DIFERENTES(cliente, banco):
    """O modal exibia o PRÊMIO sob o rótulo "Renda Individual" até 2026-09-01 —
    rótulo de um dado com o número de outro, e a diferença que ninguém
    explicava olhando a tela. Se os dois voltarem a sair da mesma coluna, este
    teste cai."""
    banco["cur"] = CursorFalso([_det(premio=129.90, renda=4800.0)])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["premio"] == 129.90, "prêmio veio de VLR_PREMIO"
    assert item["renda"] == 4800.0, "renda veio de VLR_RENDA_FORMAL"
    assert item["renda"] != item["premio"]


def test_renda_ausente_nao_vira_zero(cliente, banco):
    """Renda `None` é "a carga não trouxe"; R$ 0,00 seria "não ganha nada"."""
    banco["cur"] = CursorFalso([_det(renda=None)])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["renda"] is None


def test_telefone_prefere_o_celular(cliente, banco):
    """Quem opera liga para o celular: com os dois preenchidos, o residencial
    não pode ser o que aparece."""
    banco["cur"] = CursorFalso([_det(ddd_cel="41", cel="998765432")])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["telefone"] == "(41) 998765432"


def test_telefone_cai_no_residencial_sem_celular(cliente, banco):
    banco["cur"] = CursorFalso([_det(ddd_cel="", cel="", ddd_res="41", res="33221100")])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["telefone"] == "(41) 33221100"


def test_sem_telefone_nenhum_o_campo_vem_vazio(cliente, banco):
    """String vazia, não "( ) " — rótulo de telefone com parênteses vazios na
    tela parece dado, e não é."""
    banco["cur"] = CursorFalso([_det(ddd_cel="", cel="", ddd_res="", res="")])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["telefone"] == ""


def test_valores_nulos_nao_viram_zero(cliente, banco):
    """`None` em prêmio é "não sei", e zero é "de graça". A tela precisa poder
    mostrar coisas diferentes."""
    banco["cur"] = CursorFalso([_det(premio=None, imp=None, idade=None)])
    item = cliente.get("/pio/propostas?card=PEND_ASSIN").json()["itens"][0]
    assert item["premio"] is None and item["imp_segurada"] is None
    assert item["idade"] is None


# ═══════════ 5. busca ═══════════════════════════════════════════════════════

def test_busca_por_cpf_compara_so_digitos(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=PEND_ASSIN&busca=397.750.878-48")
    params = banco["cur"].params[0]
    assert "%39775087848%" in params, (
        "a máscara do CPF foi para a consulta — o banco guarda sem ela")


def test_busca_por_nome_vai_inteira(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=PEND_ASSIN&busca=Maria")
    assert "%Maria%" in banco["cur"].params[0]


def test_sem_busca_nao_ha_filtro_de_texto(cliente, banco):
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=PEND_ASSIN")
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
    cliente.get("/pio/propostas?card=PEND_ASSIN&offset=50")
    pagina = banco["cur"].sqls[1]
    assert "ORDER BY" in pagina and "OFFSET" in pagina


def test_mais_antigas_primeiro(cliente, banco):
    """A fila do card existe para mostrar o atraso: a proposta parada há mais
    tempo é a que precisa aparecer antes."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=PEND_ASSIN")
    assert "ORDER BY t.DTA_VENDA ASC" in banco["cur"].sqls[1]


# ═══════════ 8. a busca da Consulta de Propostas ════════════════════════════
# A tela de busca procura pelo NÚMERO sem saber em que estado a proposta está —
# por isso `card=TODOS`, que une as três DET. E cada modo da tela compara um
# campo diferente: buscar CPF no campo da proposta não acha nada e parece que a
# proposta não existe.

def test_card_todos_varre_todas_as_tabelas(cliente, banco):
    """Uma proposta pode estar em qualquer um dos oito cards. Tabela que ficar
    de fora do UNION é proposta que a busca nunca acha, sem erro nenhum."""
    banco["cur"] = CursorFalso([_det()])
    d = cliente.get("/pio/propostas?card=TODOS&busca=8031").json()
    assert d["disponivel"] is True
    for _cod, ficha in _cards_do_router().items():
        assert all(ficha.tabela in sql for sql in banco["cur"].sqls), (
            f"{ficha.tabela} ficou de fora da busca — proposta nesse card não seria achada")


def test_card_todos_diz_de_onde_cada_linha_veio(cliente, banco):
    """Sem o card de origem a tela acha a proposta e não sabe o status dela."""
    banco["cur"] = CursorFalso([_det() + ("PEND_PGTO",)])
    item = cliente.get("/pio/propostas?card=TODOS").json()["itens"][0]
    assert item["card"] == "PEND_PGTO"


def _cards_do_router():
    from routers.pio import CARDS
    return CARDS


@pytest.mark.parametrize("modo,campo", [
    ("proposta", "COD_PROPOSTA"),
    ("cpf", "COD_CPF"),
    ("agencia", "NUM_AGENCIA"),
    ("matricula", "NUM_MATRICULA"),
])
def test_cada_modo_compara_o_seu_campo(cliente, banco, modo, campo):
    banco["cur"] = CursorFalso([_det()])
    cliente.get(f"/pio/propostas?card=TODOS&modo={modo}&busca=12345")
    sql = banco["cur"].sqls[0]
    assert campo in sql, f"modo {modo} não compara {campo}"


def test_agencia_e_igualdade_e_nao_contem(cliente, banco):
    """Agência 316 não pode trazer a 3160: o modo compara por igualdade, não
    por "contém". O zero à esquerda é resolvido no SQL, com padding dos dois
    lados — "0316" e "316" são a mesma agência escrita de dois jeitos."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=TODOS&modo=agencia&busca=0316")
    sql = banco["cur"].sqls[0]
    assert "REPLACE(d.NUM_AGENCIA" in sql, "o modo agência não compara a agência"
    assert "d.NUM_AGENCIA, ' ', '') LIKE" not in sql, "agência virou busca por 'contém'"
    assert "REPLICATE('0'" in sql, "sem padding, 316 ≠ 0316"
    from routers.pio import CARDS
    assert banco["cur"].params[0] == ["0316"] * len(CARDS), (
        "o termo entra uma vez por tabela, por parâmetro")


@pytest.mark.parametrize("modo,termo,esperado", [
    ("proposta", "8047413032422-7", "%80474130324227%"),
    ("cpf", "397.750.878-48", "%39775087848%"),
    ("matricula", "0000122795-B", "%0000122795%"),
])
def test_a_mascara_digitada_nao_impede_a_busca(cliente, banco, modo, termo, esperado):
    """O usuário digita como a tela mostra. Exigir igualdade literal é o que
    fazia a busca "não funcionar" com o número certo na mão — e no caso da
    matrícula o dígito verificador é LETRA, que só os dígitos ignoram."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas", params={"card": "TODOS", "modo": modo, "busca": termo})
    assert esperado in banco["cur"].params[0]


@pytest.mark.parametrize("rota", ["/pio/contagens", "/pio/propostas?card=PEND_ASSIN"])
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


def test_todo_card_do_front_existe_no_router():
    from routers.pio import CARDS
    desconhecidos = set(_origem_pio().values()) - set(CARDS)
    assert not desconhecidos, (
        f"o front pede card que o router recusa: {sorted(desconhecidos)} — "
        f"o card mostraria zero, sem erro nenhum")


def test_cada_card_do_router_tem_tabela_propria():
    """Duas entradas apontando para a mesma DET faria um card mostrar a lista
    do outro — plausível, e errado."""
    from routers.pio import CARDS
    tabelas = [c.tabela for c in CARDS.values()]
    assert len(tabelas) == len(set(tabelas)), f"tabela repetida entre cards: {tabelas}"


# ═══════════ 10. as duas famílias de coluna ═════════════════════════════════
# Cards 1–3 vêm do TDDB48 (COD_PROPOSTA, COD_CPF, NUM_MATRICULA); cards 4–8 vêm
# do DMDB05 (NUM_PROPOSTA, COD_CPF_CNPJ, NUM_MATRI_VENDEDOR). Ler uma família
# com o vocabulário da outra dá "Invalid column name" — e no UNION ALL, um
# apelido faltando em um dos ramos derruba a consulta inteira.

def test_os_dois_esquemas_tem_os_mesmos_apelidos():
    from routers.pio import ESQUEMA_TDDB48, ESQUEMA_DMDB05, ORDEM_COLUNAS
    assert set(ESQUEMA_TDDB48) == set(ESQUEMA_DMDB05), (
        "apelido presente em um esquema e ausente no outro: "
        f"{set(ESQUEMA_TDDB48) ^ set(ESQUEMA_DMDB05)}")
    assert set(ORDEM_COLUNAS) == set(ESQUEMA_TDDB48), (
        "a ordem de leitura não cobre os mesmos apelidos do SELECT")


def test_todo_card_aponta_para_um_esquema_conhecido():
    from routers.pio import CARDS, ESQUEMA_TDDB48, ESQUEMA_DMDB05
    for cod, ficha in CARDS.items():
        assert ficha.colunas in (ESQUEMA_TDDB48, ESQUEMA_DMDB05), (
            f"{cod} usa um esquema de colunas próprio")


def test_o_card_do_dmdb05_nao_le_coluna_do_tddb48(cliente, banco):
    """`COD_PROPOSTA` não existe nas DET dos cards 4–8. Se o esquema errado
    vazar para lá, o endpoint degrada e o card fica em branco — sem erro na
    tela, porque a degradação engole a exceção."""
    banco["cur"] = CursorFalso([_det()])
    cliente.get("/pio/propostas?card=CRITICA&modo=proposta&busca=1")
    sql = banco["cur"].sqls[0]
    assert "d.NUM_PROPOSTA" in sql, "o card do DMDB05 não usou NUM_PROPOSTA"
    assert "d.COD_PROPOSTA" not in sql, "vazou coluna do TDDB48 para o DMDB05"
    assert "d.COD_CPF_CNPJ" in sql or "COD_CPF" not in sql.split("FROM")[0]


def test_o_que_a_fonte_nao_tem_vira_null_tipado():
    """Num UNION ALL o tipo vem do primeiro ramo; `NULL` puro deixa o SQL
    Server escolher, e texto longo é truncado sem aviso."""
    from routers.pio import ESQUEMA_DMDB05
    faltantes = [a for a, expr in ESQUEMA_DMDB05.items() if "NULL" in expr.upper()]
    assert faltantes, "nenhuma coluna ausente — o leitor quebrou?"
    for alias in faltantes:
        assert "CAST(NULL AS" in ESQUEMA_DMDB05[alias], (
            f"{alias} usa NULL sem tipo no ramo do DMDB05")


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


def test_card_que_le_a_carga_nao_mostra_sub_filtro():
    """A armadilha que disparou quando `awaiting_payment` foi ligado (2026-09-01).

    A lista de um card que lê a carga vem paginada do servidor, e o sub-filtro
    da tela roda sobre o array local de exemplo — ele não se aplica ali.
    `awaiting_payment` tem sub-status de pagamento E agora lê o PIO: sem
    esconder o Select, o usuário escolheria "Cartão de crédito", a lista
    continuaria idêntica, e nada na tela explicaria por quê.

    A proteção é anular `subFiltroAtivo` quando o card vem da carga. Quando o
    sub-status for para dentro de `/pio/propostas`, este teste muda junto.
    """
    import re as _re
    inline = COMPONENTES[0].read_text(encoding="utf-8")

    bloco = _re.search(r"const SUB_FILTRO:.*?\n\};", inline, _re.S)
    com_sub_filtro = set(_re.findall(r"(\w+):\s*\{\s*campo:", bloco.group(0)))
    conflito = set(_origem_pio()) & com_sub_filtro
    if not conflito:
        pytest.skip("nenhum card ligado tem sub-filtro — nada a esconder")

    atribuicao = _re.search(
        r"const subFiltroAtivo\s*=\s*(.*?);", inline, _re.S)
    assert atribuicao, "subFiltroAtivo não encontrado no InlineWorkflow"
    expressao = " ".join(atribuicao.group(1).split())
    assert expressao.startswith("cardSelecionado ? undefined"), (
        f"{sorted(conflito)} lê do PIO E tem sub-filtro local, mas o Select não é "
        f"escondido: `subFiltroAtivo = {expressao}`. Ele apareceria sem filtrar nada.")


@pytest.mark.parametrize("arquivo", COMPONENTES, ids=lambda p: p.stem)
def test_card_com_origem_real_nao_mostra_zero_sem_saber(arquivo):
    """Zero é uma resposta, e nem "ainda estou lendo" nem "não consegui ler"
    são respostas. Os dois estados precisam ter símbolo próprio."""
    fonte = arquivo.read_text(encoding="utf-8")
    assert "contagens.isPending" in fonte, f"{arquivo.name}: sem estado de leitura"
    assert "contagens.data?.disponivel" in fonte, (
        f"{arquivo.name}: não distingue carga ilegível de carga vazia")


# ═══════════ 9. a busca da tela × os modos da API ═══════════════════════════
# `searchOptions` (a lista de botões da tela) e `MODO_BUSCA_PIO` (o de-para para
# a API) são duas listas escritas à mão. Modo novo na tela sem entrada no mapa
# cai em "livre" — a busca por agência viraria busca por nome, achando outra
# coisa ou nada, sem erro nenhum.

BUSCA_TSX = CAIXA / "components" / "SearchProposals.tsx"


def _modos_da_tela() -> set[str]:
    import re as _re
    bloco = _re.search(r"const searchOptions.*?\n\];",
                       BUSCA_TSX.read_text(encoding="utf-8"), _re.S)
    assert bloco, "searchOptions não encontrado em SearchProposals.tsx"
    return set(_re.findall(r'value: "(\w+)"', bloco.group(0)))


def _modos_mapeados() -> dict[str, str]:
    import re as _re
    bloco = _re.search(r"export const MODO_BUSCA_PIO.*?\n\};",
                       PIO_TS.read_text(encoding="utf-8"), _re.S)
    assert bloco, "MODO_BUSCA_PIO não encontrado em lib/pio.ts"
    ativos = [l for l in bloco.group(0).splitlines() if not l.strip().startswith("//")]
    return dict(_re.findall(r'(\w+):\s*"(\w+)"', "\n".join(ativos)))


def test_todo_modo_da_tela_tem_campo_na_api():
    faltando = _modos_da_tela() - set(_modos_mapeados())
    assert not faltando, (
        f"modo(s) da tela sem campo na API: {sorted(faltando)} — a busca cairia "
        f"no modo livre e procuraria no campo errado, sem erro nenhum")


def test_todo_campo_mapeado_existe_no_router():
    from routers.pio import _filtro_da_busca
    for modo, campo in _modos_mapeados().items():
        sql, params = _filtro_da_busca(campo, "12345")
        assert sql and params, f"o campo `{campo}` (modo {modo}) não filtra nada"


def test_a_busca_da_tela_nao_le_mais_o_mock():
    """A lógica do `buscarPropostas` estava certa — comparava dígitos e ignorava
    máscara. O problema era a FONTE: 20 propostas em memória, onde nenhum número
    real existia. Voltar a ela é voltar a "a busca não funciona"."""
    fonte = BUSCA_TSX.read_text(encoding="utf-8")
    assert "buscarPropostas" not in fonte, "a busca voltou a filtrar o mock"
    assert "useBuscaPio" in fonte, "a busca deixou de consultar a carga"
