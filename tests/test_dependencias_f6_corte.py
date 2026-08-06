"""
F6 — o corte em três degraus e a CASCATA de degradação, sem banco
(`docs/spec-malha-execucao.md` §8, Decisões 38 e 39; aceite da §10 "### F6").

O arquivo irmão `test_dependencias_f6_vivo.py` pergunta ao SQL Server de
verdade — e pula onde não há banco, que é justamente o CI e a máquina de quem
vai fazer o deploy. Este aqui roda **sempre**, e carrega duas coisas que o vivo
não tem como carregar:

  1. **a catástrofe da §11.1** — um banco SEM a migration 085. Não se derruba
     uma tabela no dev para medir isso; o dublê simula o banco parcial e a
     cascata é exercitada de ponta a ponta;
  2. **a paridade de SEMÂNTICA sob degradação** — as duas árvores (`dags/`
     pymssql `%s` e `api/` pyodbc `?`) respondendo o MESMO para os MESMOS
     fatos, inclusive quando o banco está pela metade.

⚠️ **A regra do dublê honesto** (ela já custou dois defeitos ALTOS na F2 e um
na F4): *guarda que mora no `WHERE` só pode ser aplicada pelo dublê se o SQL
emitido a contiver*. O `Banco` daqui **lê o SQL que recebeu** e aplica só o que
está escrito nele — inclusive a ORDEM dos degraus do `COALESCE`. Um dublê que
filtrasse `substituida_em` por conta própria ficaria verde depois de alguém
apagar a guarda do SQL, e a produção liberaria filho com sucesso substituído.
Pelo mesmo motivo nenhum cenário aqui tem um caso só: o predicado devolve
LOTE (uma linha por dependência que falta), e dublê que responde sempre um caso
não exercita lote nenhum.

Os instantes usam os números da própria spec (corrida aberta às 01:10, pai que
concluiu às 22:00 do dia anterior, janela de 12h) porque aqui o relógio é do
dublê — no arquivo vivo, quem manda no relógio é o banco, e lá o que se fixa é
a geometria.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.datasets", "airflow.utils", "airflow.utils.trigger_rule",
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402  (ordem de import — ver test_copias.py)

from services import dependencias as deps_api  # noqa: E402

_ROOT = Path(__file__).parent.parent

# O relógio do cenário é o da narrativa do aceite: o filho é avaliado à 01:10,
# a corrida da malha abriu à 01:10 e o pai concluiu às 22:00 do dia anterior —
# DENTRO das 12h da janela (o corte da janela cai às 13:10 do dia 04).
AGORA = datetime(2026, 8, 5, 1, 10)
ABERTURA = datetime(2026, 8, 5, 1, 10)
PAI_ONTEM_22H = datetime(2026, 8, 4, 22, 0)
PAI_DESTA_RODADA = datetime(2026, 8, 5, 1, 30)
JANELA_PADRAO = timedelta(hours=12)
DATA_REF = date(2026, 8, 5)
OUTRA_DATA = date(2026, 8, 4)

_PLACEHOLDER = re.compile(r"%s|\?")


# ═══════════════════════════ o dublê honesto ════════════════════════════════

def _degraus_do_corte(sql: str):
    """Os degraus do `COALESCE`, **na ordem em que o texto os escreve**.

    Ler a ordem do SQL — em vez de assumi-la — é o que faz este dublê reprovar
    a troca do 1º degrau pelo 2º, que é o defeito que a Decisão 39 nomeia: o
    corte deixaria de ser "a corrida desta linha" e passaria a ser "a corrida
    aberta no instante da avaliação".

    Devolve [(nome, trecho do SQL daquele degrau)], onde o trecho é o que
    permite conferir as guardas do próprio degrau (`fechada_em`, `ORDER BY`)
    sem inventar nenhuma."""
    regiao = sql[sql.index("COALESCE("):]
    marcas = []
    i = regiao.find("me.id =")
    if i >= 0:
        marcas.append((i, "corrida_da_linha"))
    j = regiao.find("(SELECT TOP 1 me2")
    if j >= 0:
        marcas.append((j, "corrida_da_malha"))
    for m in _PLACEHOLDER.finditer(regiao):
        if regiao[max(0, m.start() - 5):m.start()] == "CAST(":
            continue                      # esse é o parâmetro do 1º degrau
        marcas.append((m.start(), "janela"))
        break
    marcas.sort()
    trechos = []
    for pos, (inicio, nome) in enumerate(marcas):
        fim = marcas[pos + 1][0] if pos + 1 < len(marcas) else len(regiao)
        trechos.append((nome, regiao[inicio:fim]))
    return trechos


class Banco:
    """Um SQL Server de brinquedo que só entende as consultas do predicado.

    O que ele NÃO faz, de propósito: aplicar guarda que o SQL não pediu,
    responder consulta que não reconhece (levanta), e "consertar" parâmetro
    fora de ordem. O que ele faz de propósito: falhar por MARCA de migration
    olhando o TEXTO da consulta — é assim que um banco parcial se comporta, e é
    o que garante que a cascata seja exercitada em qualquer ordem que ela tente
    os degraus, não só na ordem que o teste imaginou.

    `migrations` = as que ESTE banco tem. Tirar a 85 é a célula 2 da matriz
    §11.1: `dags/` novo com a migration ainda não aplicada."""

    def __init__(self, *, migrations=(78, 82, 85), janela_h=12, modo=True,
                 agora=AGORA, linhas=(), execucoes=(), nos=None, corridas=None,
                 erro_fixo=None):
        self.migrations = set(migrations)
        self.janela_h = janela_h
        self.modo = modo
        self.agora = agora
        self.linhas = list(linhas)          # (pipeline, depende_de, origem_no)
        self.execucoes = list(execucoes)    # dicts
        self.nos = dict(nos or {})          # id → {"malha", "retido"}
        self.corridas = dict(corridas or {})  # id → {"malha","aberta_em","fechada_em"}
        self.erro_fixo = erro_fixo
        self.execs: list[tuple] = []
        self._rows: list = []

    # ── protocolo de driver ──────────────────────────────────────────────
    def cursor(self):
        return self

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        p = tuple(params or ())
        self.execs.append((s, p))
        self._rows = self._responder(s, p)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    # ── o banco ──────────────────────────────────────────────────────────
    def _responder(self, s, p):
        if "etl_app_config" in s:
            if "dependencia_modo_sequencia" in s:
                return [("1" if self.modo else "0",)]
            if "dependencia_janela_sequencia_horas" in s:
                return [(str(self.janela_h),)]
            return []
        if "GETDATE()" in s or "SYSDATETIME()" in s:
            return [(self.agora,)]
        if "etl_pipeline_dependencia" not in s:
            raise AssertionError(f"consulta inesperada no dublê: {s[:120]}")
        self._checar_migrations(s)
        if self.erro_fixo:
            raise Exception(self.erro_fixo)
        return self._predicado(s, p)

    def _checar_migrations(self, s):
        """O banco reclama do OBJETO que falta — e reclama sempre que o texto o
        cita, em qualquer degrau. É a mensagem literal do SQL Server porque é
        ela que a cascata reconhece por marca."""
        if 85 not in self.migrations and (
                "etl_malha_execucao" in s or "malha_execucao_id" in s):
            raise Exception("Invalid object name 'dbo.etl_malha_execucao'.")
        if 82 not in self.migrations and (
                "etl_malha_no" in s or "retido_em" in s):
            raise Exception("Invalid column name 'retido_em'.")
        if 78 not in self.migrations and "substituida_em" in s:
            raise Exception("Invalid column name 'substituida_em'.")

    def _corte_da_linha(self, s, p, origem_no):
        """O corte QUE O SQL PEDE, degrau a degrau, para ESTA linha.

        Devolve (corte, tem_corte). `tem_corte=False` = o SQL não compara
        instante nenhum (é o predicado por data). Corte `None` com
        `tem_corte=True` = `>= NULL`, que em SQL é UNKNOWN e faz o `EXISTS`
        não achar nada — a semântica que um `COALESCE` sem último degrau teria
        de verdade."""
        if "ISNULL(e.fim, e.inicio) >=" not in s:
            return None, False
        if "COALESCE(" not in s:
            return p[1], True                       # SEQ_084: o corte é a janela
        for nome, trecho in _degraus_do_corte(s):
            if nome == "corrida_da_linha":
                c = self.corridas.get(p[1])
                if c and ("fechada_em" not in trecho or c["fechada_em"] is None):
                    return c["aberta_em"], True
            elif nome == "corrida_da_malha":
                if "dd.origem_no" not in trecho or origem_no is None:
                    continue
                malha = self.nos.get(origem_no, {}).get("malha")
                cands = [c for c in self.corridas.values() if c["malha"] == malha]
                if "fechada_em IS NULL" in trecho:
                    cands = [c for c in cands if c["fechada_em"] is None]
                if "ORDER BY" in trecho and "aberta_em DESC" in trecho:
                    cands.sort(key=lambda c: c["aberta_em"], reverse=True)
                if cands:
                    return cands[0]["aberta_em"], True
            elif nome == "janela":
                return p[2], True
        return None, True

    def _conta(self, s, p, ex, corte, tem_corte):
        """Esta execução conta como sucesso — pelas guardas que o SQL escreveu."""
        if "e.status = 'SUCESSO'" in s and ex.get("status", "SUCESSO") != "SUCESSO":
            return False
        if "e.substituida_em IS NULL" in s and ex.get("substituida"):
            return False
        if "e.data_referencia =" in s and ex.get("data_ref", DATA_REF) != p[1]:
            return False
        if tem_corte:
            if corte is None:
                return False                        # `>= NULL` → UNKNOWN
            if ex["fim"] < corte:
                return False
        return True

    def _predicado(self, s, p):
        pipeline = p[0]
        linhas = [l for l in self.linhas if l[0] == pipeline]
        tem_coluna_retencao = "aguarde_retido" in s
        olha_retencao = "n2.retido_em IS NOT NULL" in s
        rows = []
        for _filho, pai, origem_no in linhas:
            corte, tem_corte = self._corte_da_linha(s, p, origem_no)
            achou = any(self._conta(s, p, ex, corte, tem_corte)
                        for ex in self.execucoes if ex["pipeline"] == pai)
            retido = bool(olha_retencao and origem_no is not None
                          and self.nos.get(origem_no, {}).get("retido"))
            if achou and not retido:
                continue
            if tem_coluna_retencao:
                rows.append((pai, origem_no if retido else None))
            else:
                rows.append((pai,))
        return rows


# ═══════════════════ as duas árvores, pela mesma porta ══════════════════════

class Arvore:
    """Adaptador: `dags/` recebe CONEXÃO, `api/` recebe CURSOR. A pergunta e a
    resposta são as mesmas — é isso que a paridade afirma."""

    def __init__(self, nome, mod, passa_conn):
        self.nome = nome
        self.mod = mod
        self.passa_conn = passa_conn

    def liberado(self, banco, pipeline, corrida=None, data_ref=DATA_REF):
        self.mod.limpar_cache_modo()
        alvo = banco if self.passa_conn else banco.cursor()
        try:
            return self.mod.liberado(alvo, pipeline, data_ref, corrida)
        finally:
            self.mod.limpar_cache_modo()


@pytest.fixture(scope="module")
def deps_dags():
    spec = importlib.util.spec_from_file_location(
        "dependencias_dags_f6", _ROOT / "dags/utils/dependencias.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(params=["dags", "api"])
def arvore(request, deps_dags):
    """Todo teste desta suíte roda nas DUAS árvores. Paridade que só compara
    texto deixa passar a divergência de COMPORTAMENTO — e é o comportamento que
    o operador vê quando o painel diz uma coisa e o motor faz outra."""
    if request.param == "dags":
        return Arvore("dags", deps_dags, passa_conn=True)
    return Arvore("api", deps_api, passa_conn=False)


# ── o mundo dos cenários (um só, com naturezas diferentes de linha) ──────────

MALHA_A, MALHA_B, MALHA_C = "MALHA_A", "MALHA_B", "MALHA_C"
NO_A, NO_B, NO_RETIDO, NO_C = 11, 12, 13, 14
CORRIDA_A, CORRIDA_C = 501, 503


def _mundo(**over):
    """O cenário do aceite, em LOTE: seis filhos de naturezas diferentes
    avaliados contra o MESMO banco. Um dublê que devolvesse sempre um caso não
    diria nada sobre o `SELECT` que devolve N linhas."""
    base = dict(
        nos={NO_A: {"malha": MALHA_A, "retido": False},
             NO_B: {"malha": MALHA_B, "retido": False},
             NO_RETIDO: {"malha": MALHA_A, "retido": True},
             NO_C: {"malha": MALHA_C, "retido": False}},
        corridas={CORRIDA_A: {"malha": MALHA_A, "aberta_em": ABERTURA,
                              "fechada_em": None}},
        linhas=[
            ("FILHO_MALHA", "PAI_ONTEM", NO_A),        # assinada, pai da rodada passada
            ("FILHO_AVULSO", "PAI_ONTEM", None),       # avulsa: só a janela responde
            ("FILHO_MISTO", "PAI_ONTEM", NO_A),        # as duas naturezas na MESMA
            ("FILHO_MISTO", "PAI_AVULSO", None),       # consulta
            ("FILHO_OK", "PAI_HOJE", NO_A),            # pai DESTA rodada
            ("FILHO_RETIDO", "PAI_HOJE", NO_RETIDO),   # Aguarde segurado
            ("FILHO_SUBST", "PAI_SUBST", NO_A),        # sucesso substituído
            ("FILHO_SEM_CORRIDA", "PAI_ONTEM", NO_B),  # malha sem corrida aberta
        ],
        execucoes=[
            {"pipeline": "PAI_ONTEM", "fim": PAI_ONTEM_22H},
            {"pipeline": "PAI_AVULSO", "fim": PAI_ONTEM_22H},
            {"pipeline": "PAI_HOJE", "fim": PAI_DESTA_RODADA},
            {"pipeline": "PAI_SUBST", "fim": PAI_DESTA_RODADA, "substituida": True},
        ],
    )
    base.update(over)
    return Banco(**base)


# ═════════ 1. o corte é `aberta_em`, e não a janela (aceite, bullet 1) ══════

def test_pai_dentro_da_janela_mas_antes_da_abertura_NAO_libera(arvore):
    """**Bullet 1.** Corrida aberta às 01:10, pai que concluiu às 22:00 do dia
    anterior — dentro das 12h (o corte da janela é 13:10 do dia 04). O corte é
    `aberta_em`, então o sucesso é da rodada passada e não conta."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A) == (False, ["PAI_ONTEM"])


def test_a_janela_sozinha_teria_soltado_o_mesmo_pai(arvore):
    """O contraste que dá sentido ao teste de cima — e o defeito que a Decisão
    38 evita: **a mesma linha, o mesmo pai**, avaliada sem corrida nenhuma em
    degrau algum, é liberada pela janela de 12h."""
    banco = _mundo(corridas={})
    assert arvore.liberado(banco, "FILHO_MALHA", None) == (True, [])


def test_pai_concluido_DEPOIS_da_abertura_libera(arvore):
    """O controle positivo: o corte novo não é "segura sempre"."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_OK", CORRIDA_A) == (True, [])


def test_pai_que_terminou_NO_INSTANTE_da_abertura_conta(arvore):
    """A borda do `>=`, e ela não é teórica: o membro que a corrida dispara na
    abertura pode carimbar `fim` no mesmo instante do `aberta_em` (os dois saem
    do relógio do banco, e `datetime2` tem resolução de sobra para empatar
    dentro da mesma transação de abertura). Com `>` esse sucesso sumiria e o
    filho esperaria por um pai que já terminou — o travamento mais difícil de
    diagnosticar que este corte pode produzir."""
    banco = _mundo(execucoes=[{"pipeline": "PAI_NA_BORDA", "fim": ABERTURA}],
                   linhas=[("FILHO_BORDA", "PAI_NA_BORDA", NO_A)])
    assert arvore.liberado(banco, "FILHO_BORDA", CORRIDA_A) == (True, [])


# ═══════ 2. a janela continua inteira para quem não tem corrida ════════════

def test_dependencia_avulsa_continua_na_janela_de_12h(arvore):
    """**Bullet 2.** `origem_no IS NULL` não tem corrida em degrau nenhum: os
    dois primeiros devolvem NULL e responde a janela — INALTERADA. Removê-la
    quebraria toda dependência criada pelo `POST /dependencias`."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_AVULSO", None) == (True, [])


def test_dependencia_avulsa_com_pai_FORA_da_janela_continua_segurando(arvore):
    """A régua da janela é medida, não presumida: com a janela em 2h, o mesmo
    pai das 22:00 fica fora e a linha segura. Sem este teste, o de cima também
    passaria se a janela tivesse virado "libera sempre"."""
    banco = _mundo(janela_h=2)
    assert arvore.liberado(banco, "FILHO_AVULSO", None) == (False, ["PAI_ONTEM"])


def test_linha_AVULSA_de_um_membro_da_corrida_TAMBEM_e_cortada_pela_corrida(arvore):
    """A consequência que precisa estar escrita em algum lugar: o 1º degrau é
    do **dependente**, não da linha. Quando quem está sendo avaliado é membro
    de uma corrida (o push manda `_od_filho['corrida_id']`), TODAS as linhas
    dele — inclusive as avulsas — passam a ser cortadas pelo `aberta_em`.

    É o que a §8 escreve, e é defensável: o membro está rodando DENTRO do
    ciclo, então o insumo dele tem de ser deste ciclo. Mas é uma mudança de
    comportamento para dependência avulsa de membro de malha, e sem um teste
    com nome ela seria "descoberta" numa madrugada. O bullet do aceite (janela
    inalterada) vale para quem NÃO tem corrida em degrau nenhum — o teste
    acima."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_AVULSO", CORRIDA_A) == (False, ["PAI_ONTEM"])


def test_corte_resolvido_POR_LINHA_na_mesma_consulta(arvore):
    """**O coração da Decisão 38.** Um filho, duas linhas de naturezas
    diferentes, uma consulta: a assinada é cortada pelo `aberta_em` (não conta)
    e a avulsa pela janela (conta). Corte único — qualquer um — daria as duas
    faltando ou nenhuma."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_MISTO", None) == (False, ["PAI_ONTEM"])


# ═════════════ 3. a corrida atravessa a virada do dia (bullet 3) ════════════

def test_corrida_que_atravessa_a_virada_o_filho_da_01h_ve_o_pai_das_23h30(arvore):
    """**Bullet 3.** Malha que abre 23h e termina 01h: o filho avaliado à 01:10
    tem de ENXERGAR o pai das 23h30 do dia anterior. A janela está em 1h de
    propósito — assim o corte da janela cai às 00:10 e quem deixa o pai passar
    só pode ser o `aberta_em` das 23h. Um corte na VIRADA do dia devolveria a
    mesma coisa que a janela curta: travaria em silêncio."""
    banco = _mundo(
        janela_h=1,
        corridas={CORRIDA_C: {"malha": MALHA_C,
                              "aberta_em": datetime(2026, 8, 4, 23, 0),
                              "fechada_em": None}},
        linhas=[("FILHO_VIRADA", "PAI_2330", NO_C)],
        execucoes=[{"pipeline": "PAI_2330", "fim": datetime(2026, 8, 4, 23, 30)}])
    assert arvore.liberado(banco, "FILHO_VIRADA", CORRIDA_C) == (True, [])
    # e a prova de que foi a corrida, não a janela: sem corrida em mãos e sem
    # corrida aberta na malha, a mesma linha trava.
    assert arvore.liberado(_mundo(
        janela_h=1, corridas={},
        linhas=[("FILHO_VIRADA", "PAI_2330", NO_C)],
        execucoes=[{"pipeline": "PAI_2330",
                    "fim": datetime(2026, 8, 4, 23, 30)}]),
        "FILHO_VIRADA", None) == (False, ["PAI_2330"])


# ═════ 4. o corte não muda de significado no meio do ciclo (Decisão 39) ═════

def test_corrida_que_FECHA_entre_duas_avaliacoes_nao_muda_o_corte(arvore):
    """**Bullet 4.** A corrida é PARÂMETRO, não subconsulta viva: o 1º degrau
    não filtra `fechada_em`. Fechada entre duas avaliações, a resposta é a
    mesma — e a segunda asserção mostra o que a subconsulta viva teria feito:
    cair na janela **em silêncio** e soltar o filho com o dado da rodada
    passada."""
    banco = _mundo()
    antes = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    banco.corridas[CORRIDA_A]["fechada_em"] = datetime(2026, 8, 5, 1, 15)
    depois = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    assert antes == depois == (False, ["PAI_ONTEM"])

    assert arvore.liberado(banco, "FILHO_MALHA", None) == (True, []), (
        "cenario invalido: sem a corrida da LINHA a janela tem de soltar")


def test_a_corrida_da_LINHA_ganha_da_corrida_aberta_AGORA(arvore):
    """A ordem dos degraus, no cenário em que ela decide: a corrida #1 fechou,
    a #2 já abriu e o pai concluiu ENTRE as duas. Pela corrida da linha (#1) o
    pai é desta rodada e LIBERA; pela "corrida aberta agora" (#2) ele seria da
    rodada passada. Trocar o 1º degrau pelo 2º inverte esta resposta."""
    banco = _mundo(
        corridas={
            CORRIDA_A: {"malha": MALHA_A, "aberta_em": datetime(2026, 8, 4, 22, 0),
                        "fechada_em": datetime(2026, 8, 5, 0, 30)},
            CORRIDA_A + 1: {"malha": MALHA_A, "aberta_em": datetime(2026, 8, 5, 1, 0),
                            "fechada_em": None}},
        linhas=[("FILHO_RERUN", "PAI_ENTRE", NO_A)],
        execucoes=[{"pipeline": "PAI_ENTRE", "fim": datetime(2026, 8, 5, 0, 45)}])
    assert arvore.liberado(banco, "FILHO_RERUN", CORRIDA_A) == (True, [])
    assert arvore.liberado(banco, "FILHO_RERUN", CORRIDA_A + 1) == (False, ["PAI_ENTRE"])
    assert arvore.liberado(banco, "FILHO_RERUN", None) == (False, ["PAI_ENTRE"])


# ══════════ 5. o 2º degrau: a malha que ASSINOU, e só ela ═══════════════════

def test_degrau_2_usa_a_malha_que_ASSINOU_a_linha(arvore):
    """A malha vem do NÓ (`dd.origem_no`, migration 075), então é DETERMINADA
    por linha. A linha assinada pela malha A (com corrida aberta) segura; a
    assinada pela malha B (sem corrida) é julgada pela janela e passa — um
    degrau 2 que pegasse "qualquer corrida aberta" seguraria as duas."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_MALHA", None) == (False, ["PAI_ONTEM"])
    assert arvore.liberado(banco, "FILHO_SEM_CORRIDA", None) == (True, [])


def test_degrau_2_ignora_corrida_ja_FECHADA(arvore):
    """`me2.fechada_em IS NULL`: corrida encerrada não corta mais nada — senão
    a última corrida da malha seguiria segurando os filhos de um ciclo que
    acabou."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_MALHA", None) == (False, ["PAI_ONTEM"])
    banco.corridas[CORRIDA_A]["fechada_em"] = datetime(2026, 8, 5, 1, 15)
    assert arvore.liberado(banco, "FILHO_MALHA", None) == (True, [])


# ═══════════ 6. o que o SQL reescrito tinha de continuar respeitando ════════

def test_aguarde_RETIDO_continua_segurando_no_corte_novo(arvore):
    """O `OR EXISTS (… retido_em IS NOT NULL)` sobreviveu à reescrita do
    `WHERE`: nó segurado segura o filho mesmo com o pai concluído DENTRO da
    corrida — e o faltante é a TRAVA, com o id do nó."""
    banco = _mundo()
    lib, falt = arvore.liberado(banco, "FILHO_RETIDO", CORRIDA_A)
    assert lib is False
    assert falt == [arvore.mod.MSG_AGUARDE_RETIDO.format(NO_RETIDO)]


def test_sucesso_SUBSTITUIDO_nao_conta_no_corte_novo(arvore):
    """`e.substituida_em IS NULL` também sobreviveu: sucesso de corrida
    substituída não é sucesso desta rodada, mesmo carimbado depois da
    abertura."""
    banco = _mundo()
    assert arvore.liberado(banco, "FILHO_SUBST", CORRIDA_A) == (False, ["PAI_SUBST"])


def test_com_o_modo_DESLIGADO_a_corrida_nao_muda_nada(arvore):
    """Interruptor em 0 (o valor de hoje no dev e em produção): a pergunta
    volta a ser "SUCESSO NESTA data de referência" e a corrida é ignorada. É o
    teste que afirma que a fase é INERTE até alguém virar a chave."""
    banco = _mundo(modo=False, execucoes=[
        {"pipeline": "PAI_ONTEM", "fim": PAI_ONTEM_22H, "data_ref": DATA_REF},
        {"pipeline": "PAI_HOJE", "fim": PAI_DESTA_RODADA, "data_ref": OUTRA_DATA}])
    assert arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A) == (True, []), (
        "no modo DATA o sucesso NA DATA libera, mesmo anterior a abertura"
    )
    assert arvore.liberado(banco, "FILHO_OK", CORRIDA_A) == (False, ["PAI_HOJE"]), (
        "no modo DATA o sucesso de OUTRA data nao libera, mesmo dentro da corrida"
    )
    assert all("etl_malha_execucao" not in sql for sql, _ in banco.execs)


# ══════════════════ 7. A CATÁSTROFE: banco sem a migration 085 ══════════════
#
# É o teste mais importante da fase, e o que ele mede não é uma tela: é a
# diferença entre "a trava nova segura um Aguarde" e "a trava nova para a
# produção". Célula 2 da matriz §11.1 — `dags/` novo com a 085 ainda não
# aplicada — e ela é a combinação MAIS PROVÁVEL do deploy, porque a etapa de
# migrations do `deploy.sh` é padrão-NÃO.

_TODOS = ["FILHO_MALHA", "FILHO_AVULSO", "FILHO_MISTO", "FILHO_OK",
          "FILHO_RETIDO", "FILHO_SUBST", "FILHO_SEM_CORRIDA"]


def test_sem_a_085_liberado_NAO_vira_nao_liberado_para_o_banco_inteiro(arvore):
    """⚠️ **A catástrofe evitada.** Sem a migration, todo SQL que cite
    `dbo.etl_malha_execucao` levanta "Invalid object name". Sem a cascata o
    erro sobe, `liberado()` devolve NÃO-LIBERADO com o sentinel para **cada
    dependente do banco** e a produção para inteira.

    O teste pergunta pelo LOTE de sete filhos de naturezas diferentes e exige
    três coisas — nenhuma delas satisfeita por um degrau que só "não explode":

      1. **nenhum** faltante é o sentinel de erro (ninguém ficou sem resposta);
      2. as respostas **discriminam** (umas liberam, outras não) — uma cascata
         que devolvesse tudo liberado seria a catástrofe simétrica: soltaria a
         casa inteira;
      3. o que sobrou é exatamente o comportamento do degrau SEQ_084: o corte
         volta a ser a janela de 12h, e é por isso que `FILHO_MALHA` — segurado
         pelo `aberta_em` quando havia 085 — passa a ser liberado aqui."""
    banco = _mundo(migrations=(78, 82))          # a 085 não passou
    respostas = {f: arvore.liberado(banco, f, CORRIDA_A) for f in _TODOS}

    sentinel = arvore.mod.ERRO_CONSULTA
    presos = {f: r for f, r in respostas.items()
              if any(str(x).startswith(sentinel) for x in r[1])}
    assert not presos, f"a trava nova parou a producao: {presos}"

    liberados = {f for f, (lib, _) in respostas.items() if lib}
    assert liberados == {"FILHO_MALHA", "FILHO_AVULSO", "FILHO_MISTO",
                         "FILHO_OK", "FILHO_SEM_CORRIDA"}, respostas
    assert respostas["FILHO_RETIDO"][0] is False   # a retenção não depende da 085
    assert respostas["FILHO_SUBST"][0] is False    # nem o descarte da substituída


def test_sem_a_085_o_modo_SEQUENCIA_sobrevive(arvore):
    """A degradação certa é um degrau, não um tombo: cai-se no SEQ_084 (modo
    SEQUÊNCIA com o corte na janela), e **não** na volta silenciosa para a data
    de referência — que mudaria a REGRA, não só a precisão do corte."""
    banco = _mundo(migrations=(78, 82))
    arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    tentativas = [sql for sql, _ in banco.execs if "etl_pipeline_dependencia" in sql]
    assert len(tentativas) == 2, tentativas
    assert "etl_malha_execucao" in tentativas[0]
    assert "etl_malha_execucao" not in tentativas[1]
    assert "data_referencia" not in tentativas[1], (
        "cair para a data de referencia troca a REGRA de liberacao")
    _sql, params = [c for c in banco.execs if "etl_pipeline_dependencia" in c[0]][1]
    assert params == ("FILHO_MALHA", AGORA - JANELA_PADRAO), params


def test_sem_a_085_a_marca_pode_ser_a_COLUNA_ou_a_TABELA(arvore):
    """O banco reclama da COLUNA quando só ela falta e da TABELA quando a
    migration inteira não passou. Reagir a uma marca só deixaria metade dos
    deploys parciais levantando exceção — e "metade" aqui é metade da
    produção."""
    for msg in ("Invalid object name 'dbo.etl_malha_execucao'.",
                "Invalid column name 'malha_execucao_id'."):
        banco = _mundo()
        banco.erro_fixo = msg
        # o erro fixo cai em TODA consulta do predicado; o que se afirma aqui é
        # que a marca é RECONHECIDA (a cascata anda) e não que ela responde.
        lib, falt = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
        tentativas = [s for s, _ in banco.execs if "etl_pipeline_dependencia" in s]
        assert len(tentativas) >= 2, (msg, tentativas)
        assert lib is False and falt and falt[0].startswith(arvore.mod.ERRO_CONSULTA)


def test_sem_a_082_a_liberacao_volta_para_a_data_em_vez_de_travar(arvore):
    """Degrau seguinte: sem `etl_malha_no` nenhum SQL do modo roda. Voltar a
    olhar a data de referência muda a regra — mas travar o banco inteiro seria
    pior, e é por isso que a cascata continua descendo."""
    banco = _mundo(migrations=(78,))
    lib, falt = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    assert not any(str(x).startswith(arvore.mod.ERRO_CONSULTA) for x in falt)
    ultima = [s for s, _ in banco.execs if "etl_pipeline_dependencia" in s][-1]
    assert "data_referencia" in ultima and "retido_em" not in ultima


def test_sem_a_078_a_cascata_chega_ao_legado(arvore):
    """O fundo do poço: banco sem `substituida_em`. Os DOIS SQLs do modo citam
    a coluna, o por-data também — e mesmo assim a resposta sai, pelo legado."""
    banco = _mundo(migrations=())
    lib, falt = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    assert not any(str(x).startswith(arvore.mod.ERRO_CONSULTA) for x in falt)
    ultima = [s for s, _ in banco.execs if "etl_pipeline_dependencia" in s][-1]
    assert "substituida_em" not in ultima and "data_referencia" in ultima


def test_erro_desconhecido_NAO_degrada(arvore):
    """Deadlock, timeout e permissão não são deploy parcial: eles PROPAGAM até
    a tradução D21 (não liberado com o sentinel). Uma cascata que engolisse
    erro de banco viraria a doença que ela veio curar — e o operador leria
    "aguardando o pai" onde o certo é "não consegui perguntar"."""
    banco = _mundo()
    banco.erro_fixo = "deadlock victim"
    lib, falt = arvore.liberado(banco, "FILHO_MALHA", CORRIDA_A)
    assert lib is False
    assert falt[0].startswith(arvore.mod.ERRO_CONSULTA)
    tentativas = [s for s, _ in banco.execs if "etl_pipeline_dependencia" in s]
    assert len(tentativas) == 1, "erro desconhecido nao pode virar degradacao"


# ════════════ 8. paridade de SEMÂNTICA — inclusive degradada ════════════════

def _todas_as_respostas(arv, migrations):
    banco = _mundo(migrations=migrations)
    return ({f: arv.liberado(banco, f, CORRIDA_A) for f in _TODOS},
            [(s, p) for s, p in banco.execs if "etl_pipeline_dependencia" in s])


@pytest.mark.parametrize("migrations", [(78, 82, 85), (78, 82), (78,), ()])
def test_as_duas_arvores_respondem_igual_em_todo_degrau_da_cascata(
        deps_dags, migrations):
    """A paridade textual (`test_dependencias_f5_paridade.py`) garante que o
    SQL é o mesmo; esta garante que o COMPORTAMENTO é — inclusive no deploy
    parcial, que é o momento em que uma divergência painel×motor é mais cara de
    diagnosticar, porque tudo já está estranho.

    Compara as respostas do lote inteiro E a sequência de SQLs tentados,
    normalizando só o placeholder (`?` ↔ `%s`), que é a ÚNICA diferença
    permitida entre as árvores."""
    r_dags, sql_dags = _todas_as_respostas(
        Arvore("dags", deps_dags, passa_conn=True), migrations)
    r_api, sql_api = _todas_as_respostas(
        Arvore("api", deps_api, passa_conn=False), migrations)
    assert r_dags == r_api
    assert [s.replace("%s", "?") for s, _ in sql_dags] == [s for s, _ in sql_api]
    assert [p for _, p in sql_dags] == [p for _, p in sql_api]
