"""
Paridade da corrida de malha — `dags/utils/malha_corrida.py` (canônico, `%s`,
pymssql) × `api/services/malha_corrida.py` (port, `?`, pyodbc), F1 da spec
docs/spec-malha-execucao.md (invariante §16/12).

Molde de tests/test_dependencias_f5_paridade.py, com um nível a mais:

  1. **TEXTO** — todo SQL do port é textualmente idêntico ao do canônico depois
     de normalizar whitespace e placeholder. As duas árvores de deploy são
     separadas (o container da API não embarca `dags/`), então a cópia é
     inevitável; o que não pode existir é a cópia DIVERGENTE, que é como o
     painel e o motor passam a responder coisas diferentes sobre o mesmo fato.

  2. **EMISSÃO** — não basta a constante bater: o que vai ao banco é
     `(sql, params)`, e é o *params* que troca de ordem quando alguém edita um
     dos dois lados. Cada função é chamada nas duas árvores com um cursor de
     captura e comparada estatuto por estatuto.

  3. **SEMÂNTICA** — o roteiro completo (abrir → snapshot → vincular → aderir →
     marcar → fechar → reabrir) roda contra o MESMO dublê interpretador de
     tests/test_malha_corrida.py, nas duas árvores, e tem de produzir: os mesmos
     retornos, a mesma SEQUÊNCIA de statements e **as mesmas linhas gravadas**.

  4. **DEGRADAÇÃO CRUZADA** — o canônico recebe o erro com a forma do *pymssql*
     e o port com a forma do *pyodbc* (que é como cada um os recebe em
     produção), e os dois têm de chegar ao MESMO veredito. Sem isto a paridade
     seria só de texto: o `_sem_085` lê o número do erro, e os dois drivers o
     entregam em lugares diferentes.

DIVERGÊNCIAS DELIBERADAS, e o teste que as mantém contidas: (i) o port recebe
`cur` e o canônico recebe `conn` — a API já carrega o cursor pela request
inteira; (ii) o cache do interruptor é por PROCESSO no canônico (a task do
Airflow é curta e morre levando o cache) e por TTL no port (o processo da API é
longo, e cachear para sempre obrigaria a reiniciar o container para virar a
chave no Admin). É o mesmo par de formas de `dependencias.py`, e o teste abaixo
exige que as duas respondam IGUAL para a mesma configuração.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from services import malha_corrida as mca

# O dublê interpretador e o cenário são os MESMOS do teste do canônico
# (precedente: test_malhas_f9 estende o FakeDb de test_malhas_f8). Se a paridade
# usasse um dublê próprio, ela provaria a paridade entre dois dublês.
from tests.test_malha_corrida import (
    AGORA_BANCO, CAMPOS, ODATE, ODATE_ONTEM, Banco, banco, erro,
    erro_coluna_ausente, erro_duplicata, erro_fk_membro, erro_objeto_ausente)

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def mcd():
    """O canônico de `dags/`, carregado por caminho."""
    spec = importlib.util.spec_from_file_location(
        "malha_corrida_dags_paridade", _ROOT / "dags/utils/malha_corrida.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _sem_cache(mcd):
    """As duas formas de cache do interruptor zeradas — é a única divergência
    de estado entre as árvores, e nenhum teste daqui pode herdá-la do anterior."""
    mcd.limpar_cache()
    mca.limpar_cache()
    yield
    mcd.limpar_cache()
    mca.limpar_cache()


def _norm(sql: str) -> str:
    return " ".join(str(sql).split()).replace("%s", "?")


# ═══════════════════════ nível 1 — o texto do SQL ═══════════════════════════

_CONSTANTES_SQL = ("SQL_TETO_DA_MALHA", "SQL_VIRADA_DA_MALHA",
                   "SQL_VIRADA_GLOBAL", "SQL_CORRIDA_ABERTA",
                   "SQL_CORRIDAS_ABERTAS", "SQL_CORRIDA_POR_ID",
                   "SQL_ABERTAS_DO_PIPELINE", "SQL_MEMBROS", "SQL_ABRIR",
                   "SQL_VINCULAR", "SQL_FECHAR", "SQL_REABRIR",
                   # F2 — as portas, o predicado `estado` e os relógios. Entram
                   # nesta tupla no MESMO commit em que nascem: um SQL que
                   # exista só de um lado é a próxima divergência silenciosa
                   # entre o que o motor fecha e o que o painel mostra.
                   "SQL_RAIZES_DA_MALHA", "SQL_ESTADO", "SQL_FORA_DO_ODATE",
                   "SQL_AGUARDANDO_DO_SNAPSHOT", "SQL_RELOGIOS",
                   "SQL_NO_RETIDO", "SQL_CARIMBAR_MOTIVO",
                   "SQL_HEARTBEAT_GRAVAR", "SQL_HEARTBEAT_CRIAR",
                   "SQL_HEARTBEAT_LER", "SQL_CORRIDA_DA_DATA")


@pytest.mark.parametrize("nome", _CONSTANTES_SQL)
def test_paridade_das_constantes_de_sql(mcd, nome):
    assert _norm(getattr(mcd, nome)) == _norm(getattr(mca, nome)), nome


def test_paridade_do_sql_dos_marcadores(mcd):
    assert set(mcd._SQL_VISTO) == set(mca._SQL_VISTO) == {"falha", "atraso"}
    for chave in mcd._SQL_VISTO:
        assert _norm(mcd._SQL_VISTO[chave]) == _norm(mca._SQL_VISTO[chave])


@pytest.mark.parametrize("quantos", [0, 1, 2, 5])
def test_paridade_das_partidas_que_variam_com_a_lista(mcd, quantos):
    """Mesma razão do snapshot: sem `IN ()` em T-SQL, o texto muda com o
    tamanho da lista, e lista vazia vira `1 = 0` (nunca a ausência da cláusula,
    que varreria a maior tabela do schema)."""
    assert _norm(mcd.sql_partidas(quantos)) == _norm(mca.sql_partidas(quantos))
    assert "?" not in mcd.sql_partidas(quantos)
    assert "%s" not in mca.sql_partidas(quantos)


@pytest.mark.parametrize("quantos", [None, 0, 1, 2, 5])
def test_paridade_do_snapshot_que_varia_com_a_lista(mcd, quantos):
    """O SQL do snapshot é o único que muda de forma com o dado: não há `IN ()`
    em T-SQL, então lista vazia vira `1 = 0` e `None` (malha sem nó Fim) vira
    `1 = 1`. É por isso que `sql_snapshot` é público — para a paridade poder
    comparar as três formas."""
    assert _norm(mcd.sql_snapshot(quantos)) == _norm(mca.sql_snapshot(quantos))


def test_cada_arvore_usa_o_SEU_placeholder(mcd):
    """O GOTCHA do projeto: `dags/` é pymssql (`%s`) e `api/` é pyodbc (`?`).
    Trocar dá "Incorrect syntax near '?'" — e no caminho errado dá task VERDE
    com zero gravação, porque o try/except esconde."""
    for nome in _CONSTANTES_SQL:
        do_dags, do_api = getattr(mcd, nome), getattr(mca, nome)
        assert "?" not in do_dags, nome
        assert "%s" not in do_api, nome
    assert "%s" in mcd.SQL_ABRIR and "?" in mca.SQL_ABRIR
    assert "?" not in mcd.sql_snapshot(2) and "%s" not in mca.sql_snapshot(2)


def test_paridade_do_dominio_e_das_constantes(mcd):
    """O domínio espelha os CHECKs da 085; espelhá-lo diferente em cada árvore
    faria uma delas recusar na borda o que a outra deixa estourar no banco."""
    for nome in ("STATUS_ABERTA", "DESFECHOS", "ORIGENS", "MODOS_FECHAMENTO",
                 "REABREM", "TETO_HORAS_PADRAO", "TETO_HORAS_MIN",
                 "TETO_HORAS_MAX", "QUIESCENCIA_MIN_PADRAO",
                 "QUIESCENCIA_MIN_MIN", "QUIESCENCIA_MIN_MAX",
                 "CARENCIA_PARTIDA_PADRAO", "CARENCIA_PARTIDA_MIN",
                 "CARENCIA_PARTIDA_MAX", "CHAVE_ATIVA", "CHAVE_TETO",
                 "CHAVE_QUIESCENCIA", "CHAVE_CARENCIA", "LOG", "IX_ABERTA",
                 "IX_SEQUENCIA", "_TENTATIVAS_ABERTURA", "_ERROS_AUSENCIA",
                 "_MARCAS_085", "_COLS", "_CAMPOS", "_INTEIROS",
                 # F2 — o vocabulário da classificação e dos carimbos. Não é
                 # domínio do banco como os de cima, e por isso é MAIS fácil de
                 # divergir: nenhum CHECK reclamaria se o painel da F4 lesse
                 # `orfa` de um lado e `orfã` do outro, ou se o fechador
                 # considerasse PULADO uma partida e a API não. O que se
                 # perderia é a concordância entre quem FECHA a corrida e quem
                 # a MOSTRA — que é o defeito desta spec, com outra roupa.
                 "STATUS_PARTIU", "CLASSES_PENDENTES", "_ORDEM_CLASSE",
                 "EVENTO_ORFA", "ERRO_LEITURA", "MOTIVO_FORA_DA_CORRIDA",
                 "MOTIVO_OUTRO_ODATE", "CHAVE_HEARTBEAT",
                 "DESCRICAO_HEARTBEAT", "_MARCAS_HOLD"):
        assert getattr(mcd, nome) == getattr(mca, nome), nome
    assert mcd._CAMPOS == CAMPOS       # e os dois batem com o contrato do dublê


def test_a_superficie_publica_e_a_mesma(mcd):
    """Uma função que exista só de um lado é a próxima divergência: o consumidor
    da F2 a chama no canônico e o router da F4 não a encontra."""
    def publicas(m):
        return {n for n in dir(m)
                if not n.startswith("_") and callable(getattr(m, n))
                and getattr(getattr(m, n), "__module__", None) == m.__name__}
    assert publicas(mcd) == publicas(mca)


def test_o_canonico_esta_declarado_como_canonico():
    """A regra que impede a cópia de virar fork: quem muda a regra muda em
    `dags/` primeiro e espelha em `api/` no MESMO commit."""
    fonte_api = (_ROOT / "api/services/malha_corrida.py").read_text(encoding="utf-8")
    assert "dags/utils/malha_corrida.py" in fonte_api
    assert "canônico" in fonte_api.lower() or "canonico" in fonte_api.lower()


# ═════════════════ nível 2 — o (sql, params) de fato EMITIDO ════════════════

class Captura:
    """Captura `(sql, params)` cru, sem responder nada — o que importa aqui é o
    que sai, não o que volta."""

    def __init__(self):
        self.chamadas: list[tuple] = []
        # As escritas leem `rowcount` logo depois do `execute` (Decisão 8) —
        # 0 aqui significa "não achei nada para mudar", que é resposta válida e
        # não interfere na comparação, que é do que SAIU.
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.chamadas.append((str(sql), tuple(params)))

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def cursor(self):          # o canônico recebe `conn` e abre o cursor
        return self


def _emitido(mcd, chamada):
    """Roda a MESMA chamada nas duas árvores e devolve as duas listas de
    statements. `chamada` recebe (modulo, alvo)."""
    cap_dags, cap_api = Captura(), Captura()
    chamada(mcd, cap_dags)
    chamada(mca, cap_api)
    return cap_dags.chamadas, cap_api.chamadas


_CHAMADAS = {
    "corrida_ativa": lambda m, a: m.corrida_ativa(a),
    "tabela_085_presente": lambda m, a: m.tabela_085_presente(a),
    "teto_horas_da_malha": lambda m, a: m.teto_horas_da_malha(a, "M1"),
    "quiescencia_minutos": lambda m, a: m.quiescencia_minutos(a),
    "carencia_partida_min": lambda m, a: m.carencia_partida_min(a),
    "corrida_aberta": lambda m, a: m.corrida_aberta(a, "M1"),
    "corridas_abertas": lambda m, a: m.corridas_abertas(a),
    "corrida": lambda m, a: m.corrida(a, 7),
    "corrida_aberta_do_pipeline": lambda m, a: m.corrida_aberta_do_pipeline(a, "PIPE_B"),
    "membros": lambda m, a: m.membros(a, 7),
    "abrir_corrida": lambda m, a: m.abrir_corrida(
        a, "M1", ODATE, "manual", aberta_por="manual:C123456",
        ancora_pipeline="PIPE_A", ancora_execution_id="run_1", no_inicio=12,
        no_fim=13, modo_fechamento="fim", teto_horas=6, motivo="porta 1"),
    # Teto fora do domínio: as duas árvores têm de fazer a MESMA ida a mais ao
    # banco (resolver pela malha) em vez de uma aceitar o 0 do chamador e abrir
    # a corrida já expirada.
    "abrir_corrida_teto_invalido": lambda m, a: m.abrir_corrida(
        a, "M1", ODATE, "manual", teto_horas=0),
    "congelar_snapshot_sem_fim": lambda m, a: m.congelar_snapshot(a, 7, "M1"),
    "congelar_snapshot_com_fim": lambda m, a: m.congelar_snapshot(
        a, 7, "M1", conta_para_fim=["PIPE_B", "PIPE_A", "PIPE_A"]),
    "congelar_snapshot_fim_vazio": lambda m, a: m.congelar_snapshot(
        a, 7, "M1", conta_para_fim=[]),
    "vincular_execucao": lambda m, a: m.vincular_execucao(
        a, "PIPE_A", ODATE, "run_1", 7),
    "fechar_corrida": lambda m, a: m.fechar_corrida(a, 7, "EXPIRADA", "guardia",
                                                    motivo="teto de 24h"),
    "reabrir_corrida": lambda m, a: m.reabrir_corrida(a, 7, "manual:C123456",
                                                      motivo="rerun"),
    "marcar_visto_falha": lambda m, a: m.marcar_visto(a, 7, "falha"),
    "marcar_visto_atraso": lambda m, a: m.marcar_visto(a, 7, "atraso"),
    "odate_da_abertura": lambda m, a: m.odate_da_abertura(
        a, "M1", datetime(2026, 8, 4, 23, 30)),
    # ── F2 ──────────────────────────────────────────────────────────────────
    "raizes_da_malha": lambda m, a: m.raizes_da_malha(a, "M1"),
    "partidas_a_cobrir": lambda m, a: m.partidas_a_cobrir(
        a, "M1", ["PIPE_B", "PIPE_A", "PIPE_A"], (ODATE_ONTEM, ODATE), 24),
    "estado": lambda m, a: m.estado(a, _CORRIDA_F2),
    "aguardando_do_snapshot": lambda m, a: m.aguardando_do_snapshot(
        a, _CORRIDA_F2),
    "relogios": lambda m, a: m.relogios(a, _CORRIDA_F2, 15, 20),
    "ha_no_retido": lambda m, a: m.ha_no_retido(a, "M1"),
    "carimbar_motivo": lambda m, a: m.carimbar_motivo(
        a, "PIPE_A", ODATE, "run_1", m.MOTIVO_FORA_DA_CORRIDA, "texto"),
    "marcar_heartbeat": lambda m, a: m.marcar_heartbeat(a),
    "heartbeat_guardia": lambda m, a: m.heartbeat_guardia(a, 15),
    "corrida_da_data": lambda m, a: m.corrida_da_data(a, "M1", ODATE),
}

# A corrida que a F2 passa para `estado`/`relogios`/`aguardando_do_snapshot`:
# as três leem os MESMOS três campos, e trocá-los de ordem entre as árvores não
# muda o texto do SQL — só os parâmetros, que é o que o nível 2 compara.
_CORRIDA_F2 = {"id": 7, "malha_name": "M1", "data_referencia": ODATE,
               "aberta_em": datetime(2026, 8, 4, 23, 30)}


@pytest.mark.parametrize("nome", sorted(_CHAMADAS))
def test_paridade_do_que_vai_ao_banco(mcd, nome):
    """Mesma sequência de statements, mesmo texto (a menos do placeholder) e —
    o ponto — MESMOS parâmetros, na mesma ordem. A ordem dos parâmetros do
    `SQL_ABRIR` é o lugar mais fácil de divergir sem que o texto mude."""
    dags, api = _emitido(mcd, _CHAMADAS[nome])
    assert len(dags) == len(api) >= 1, nome
    for (sql_d, par_d), (sql_a, par_a) in zip(dags, api):
        assert _norm(sql_d) == _norm(sql_a), nome
        assert par_d == par_a, (nome, par_d, par_a)


def test_a_ordem_dos_parametros_da_abertura_e_a_mesma(mcd):
    """Explicitado à parte porque é o statement com 14 parâmetros e uma tabela
    derivada: `(malha, odate)` aparece duas vezes (projeção + subconsulta da
    sequência) e `aberta_em` é o ÚLTIMO, dentro do `COALESCE` do `FROM`."""
    dags, api = _emitido(mcd, _CHAMADAS["abrir_corrida"])
    par = dags[0][1]
    assert par == api[0][1]
    assert len(par) == 14
    assert par[0] == par[2] == "M1" and par[1] == par[3] == ODATE
    assert par[4] == "manual" and par[10] == "fim" and par[11] == 6
    assert par[12] == "porta 1" and par[13] is None      # aberta_em = SYSDATETIME()


def test_o_snapshot_ordena_e_deduplica_a_lista_nas_duas_arvores(mcd):
    """`sorted(set(...))`: sem isso o mesmo conjunto de pipelines produziria
    parâmetros em ordens diferentes conforme a ordem de iteração de quem chamou
    — e o cache de plano do SQL Server veria dois statements."""
    dags, api = _emitido(mcd, _CHAMADAS["congelar_snapshot_com_fim"])
    assert dags[0][1] == api[0][1] == (7, "PIPE_A", "PIPE_B", "M1", 7)


# ═══════════════ nível 3 — a matriz semântica, no mesmo dublê ═══════════════

def _roteiro(m, alvo, db):
    """O ciclo inteiro da corrida, em uma árvore. Devolve o rastro de retornos.

    É deliberadamente a MESMA sequência de chamadas que a F2 e a F3 farão:
    abrir, congelar, vincular, tentar abrir de novo (adesão via 2601), marcar,
    fechar, reabrir e fechar. Um `if` a mais em uma das árvores apareceria aqui
    como rastro diferente, e não como bug em produção."""
    passos = [("ativa", m.corrida_ativa(alvo)),
              ("085", m.tabela_085_presente(alvo)),
              ("teto", m.teto_horas_da_malha(alvo, "M1")),
              ("quiescencia", m.quiescencia_minutos(alvo)),
              ("carencia", m.carencia_partida_min(alvo)),
              ("odate", m.odate_da_abertura(alvo, "M1",
                                            datetime(2026, 8, 4, 23, 30)))]

    # `no_inicio`/`no_fim` entram com valores DIFERENTES de propósito: são dois
    # inteiros vizinhos na tupla de 14 parâmetros, e trocá-los de lugar não muda
    # o texto do SQL — é a divergência que só a linha gravada denuncia.
    c = m.abrir_corrida(alvo, "M1", ODATE, "inicio", aberta_por="inicio:#12",
                        ancora_pipeline="PIPE_A", ancora_execution_id="run_1",
                        no_inicio=12, no_fim=13,
                        modo_fechamento="quiescencia", motivo="porta 2")
    passos.append(("abrir", c))
    passos.append(("snapshot", m.congelar_snapshot(alvo, c["id"], "M1",
                                                   conta_para_fim=["PIPE_A", "PIPE_B"])))
    passos.append(("membros", m.membros(alvo, c["id"])))
    passos.append(("vinculo1", m.vincular_execucao(alvo, "PIPE_A", ODATE,
                                                   "run_1", c["id"])))
    passos.append(("vinculo2", m.vincular_execucao(alvo, "PIPE_A", ODATE,
                                                   "run_1", c["id"] + 1)))
    # adesão: o 2601 de `ux_malha_exec_aberta` vindo do dublê, com ODATE de
    # ontem — tem de voltar a corrida existente com `odate_confere=False`.
    passos.append(("aderir", m.abrir_corrida(alvo, "M1", ODATE_ONTEM, "manual",
                                             aberta_por="manual:C123456")))
    passos.append(("aberta", m.corrida_aberta(alvo, "M1")))
    passos.append(("abertas", m.corridas_abertas(alvo)))
    passos.append(("do_pipeline", m.corrida_aberta_do_pipeline(alvo, "PIPE_B")))
    passos.append(("visto1", m.marcar_visto(alvo, c["id"], "falha")))
    passos.append(("visto2", m.marcar_visto(alvo, c["id"], "falha")))
    passos.append(("fechar1", m.fechar_corrida(alvo, c["id"], "FALHA",
                                               "guardia", motivo="1 falhou")))
    passos.append(("fechar2", m.fechar_corrida(alvo, c["id"], "CONCLUIDA",
                                               "guardia")))
    passos.append(("reabrir1", m.reabrir_corrida(alvo, c["id"], "manual:C1",
                                                 motivo="rerun")))
    passos.append(("reabrir2", m.reabrir_corrida(alvo, c["id"], "manual:C1")))
    passos.append(("final", m.corrida(alvo, c["id"])))
    return passos


def _estado(db: Banco):
    return (db.corridas, db.membros, db.execucoes)


def _nas_duas_arvores(mcd, **kw):
    """Roda o roteiro nas duas árvores, contra bancos idênticos, e devolve
    (rastro_dags, rastro_api, db_dags, db_api)."""
    db_d = banco(execucoes=[{"pipeline_name": "PIPE_A",
                             "data_referencia": ODATE,
                             "execution_id": "run_1",
                             "malha_execucao_id": None}], **kw)
    db_a = banco(execucoes=[{"pipeline_name": "PIPE_A",
                             "data_referencia": ODATE,
                             "execution_id": "run_1",
                             "malha_execucao_id": None}], **kw)
    return _roteiro(mcd, db_d, db_d), _roteiro(mca, db_a.cursor(), db_a), db_d, db_a


def test_o_roteiro_completo_da_o_mesmo_resultado_nas_duas_arvores(mcd):
    r_dags, r_api, db_d, db_a = _nas_duas_arvores(mcd)
    for (nome_d, valor_d), (nome_a, valor_a) in zip(r_dags, r_api):
        assert nome_d == nome_a
        assert valor_d == valor_a, nome_d


def test_as_duas_arvores_gravam_as_MESMAS_linhas(mcd):
    """O rastro de retornos poderia coincidir com gravações diferentes (um
    `UPDATE` a mais, um campo não escrito). O estado final do banco é o que o
    próximo ciclo vai ler."""
    _, _, db_d, db_a = _nas_duas_arvores(mcd)
    assert _estado(db_d) == _estado(db_a)


def test_as_duas_arvores_emitem_a_MESMA_sequencia_de_statements(mcd):
    """Mais forte que comparar constante: pega a consulta a mais, a que falta e
    a que trocou de lugar."""
    _, _, db_d, db_a = _nas_duas_arvores(mcd)
    assert db_d.sqls == db_a.sqls


def test_o_roteiro_prova_o_que_a_F2_vai_precisar(mcd):
    """Guarda contra roteiro que passa por ser trivialmente igual dos dois
    lados: os pontos que a F2/F3 dependem TÊM de ter acontecido de verdade."""
    r_dags, _, db_d, _ = _nas_duas_arvores(mcd)
    passos = dict(r_dags)
    assert passos["abrir"]["nova"] is True and passos["abrir"]["sequencia"] == 1
    assert passos["abrir"]["no_inicio"] == 12 and passos["abrir"]["no_fim"] == 13
    assert passos["snapshot"] == 3
    assert [m["pipeline"] for m in passos["membros"]] == ["PIPE_A", "PIPE_B",
                                                          "PIPE_C"]
    assert passos["vinculo1"] is True and passos["vinculo2"] is False
    assert passos["aderir"]["nova"] is False           # o 2601 virou adesão
    assert passos["aderir"]["odate_confere"] is False  # e o ODATE não confere
    assert passos["visto1"] is True and passos["visto2"] is False
    assert passos["fechar1"] is True and passos["fechar2"] is False
    assert passos["reabrir1"] is True and passos["reabrir2"] is False
    assert passos["final"]["status"] == "ABERTA"
    assert passos["final"]["tentativas"] == 2
    assert passos["final"]["motivo"] == "porta 2 | 1 falhou | rerun"
    assert passos["final"]["aberta_em"] == AGORA_BANCO   # o relógio do BANCO
    assert len(db_d.corridas) == 1                       # a adesão não criou linha


def test_o_erro_de_dominio_e_o_mesmo_nas_duas_arvores(mcd):
    """Domínio inventado é ValueError nas duas — e ANTES de tocar o banco, para
    não estourar o CHECK no meio da transação do chamador."""
    casos = [
        lambda m, a: m.abrir_corrida(a, "M1", ODATE, "cron"),
        lambda m, a: m.abrir_corrida(a, "M1", ODATE, "manual",
                                     modo_fechamento="teto"),
        lambda m, a: m.fechar_corrida(a, 1, "ABERTA", "guardia"),
        lambda m, a: m.fechar_corrida(a, 1, "TERMINADA", "guardia"),
        lambda m, a: m.marcar_visto(a, 1, "cancelamento"),
    ]
    for caso in casos:
        db_d, db_a = banco(), banco()
        with pytest.raises(ValueError):
            caso(mcd, db_d)
        with pytest.raises(ValueError):
            caso(mca, db_a.cursor())
        assert db_d.sqls == db_a.sqls == []


def test_o_interruptor_responde_igual_apesar_do_cache_diferente(mcd):
    """A divergência de cache (processo × TTL) é deliberada e documentada; o que
    ela NÃO pode fazer é mudar a RESPOSTA para a mesma configuração."""
    for valor, esperado in [("1", True), ("true", True), ("0", False),
                            ("", False), ("sim", False), (None, False)]:
        mcd.limpar_cache()
        mca.limpar_cache()
        db_d, db_a = (banco(config={"malha_corrida_ativa": valor}),
                      banco(config={"malha_corrida_ativa": valor}))
        assert mcd.corrida_ativa(db_d) is esperado
        assert mca.corrida_ativa(db_a.cursor()) is esperado
    mcd.limpar_cache()
    mca.limpar_cache()
    vazio_d, vazio_a = banco(config={}), banco(config={})
    assert mcd.corrida_ativa(vazio_d) is False
    assert mca.corrida_ativa(vazio_a.cursor()) is False


def test_o_TTL_do_port_expira_sem_reiniciar_o_container(monkeypatch):
    """A razão de ser da divergência de cache: o processo da API é LONGO. Um
    cache sem expiração faria o operador virar `malha_corrida_ativa` no Admin e
    ter de reiniciar o container para a chave valer — e o kill switch do §11.2
    existe justamente para o caso em que reiniciar não é opção, às 3h.

    O relógio é injetado (o módulo lê `_t.time()`), em vez de dormir 30s."""

    class Relogio:
        agora = 1000.0

        def time(self):
            return self.agora

    relogio = Relogio()
    monkeypatch.setattr(mca, "_t", relogio)
    db = banco(config={"malha_corrida_ativa": "1"})
    cur = db.cursor()
    mca.limpar_cache()
    assert mca.corrida_ativa(cur) is True
    db.config["malha_corrida_ativa"] = "0"
    relogio.agora += mca._TTL_ATIVA_S - 1
    assert mca.corrida_ativa(cur) is True        # dentro da janela, o cache manda
    relogio.agora += 2
    assert mca.corrida_ativa(cur) is False       # expirou: a chave nova vale
    assert mca._TTL_ATIVA_S <= 60, "TTL longo demais para um kill switch"


def test_limpar_cache_existe_e_funciona_nos_dois(mcd):
    db_d, db_a = (banco(config={"malha_corrida_ativa": "1"}),
                  banco(config={"malha_corrida_ativa": "1"}))
    cur_a = db_a.cursor()
    assert mcd.corrida_ativa(db_d) is True and mca.corrida_ativa(cur_a) is True
    db_d.config["malha_corrida_ativa"] = "0"
    db_a.config["malha_corrida_ativa"] = "0"
    assert mcd.corrida_ativa(db_d) is True and mca.corrida_ativa(cur_a) is True
    mcd.limpar_cache()
    mca.limpar_cache()
    assert mcd.corrida_ativa(db_d) is False and mca.corrida_ativa(cur_a) is False


# ═══════════ nível 4 — degradação CRUZADA (cada árvore, seu driver) ═════════

def test_sem_a_085_as_duas_arvores_degradam_igual(mcd):
    """Cada árvore recebe o erro com a forma do SEU driver — pymssql entrega o
    número em `args[0]`, pyodbc o põe entre parênteses no texto — e as duas têm
    de chegar ao mesmo veredito. É a célula MAIS provável da matriz do §11.1:
    `api/` é deploy automático e a migration é padrão-NÃO na 6c."""
    db_d = banco(com_085=False, driver="pymssql", config={})
    db_a = banco(com_085=False, driver="pyodbc", config={})
    cur_a = db_a.cursor()
    pares = [
        (mcd.tabela_085_presente(db_d), mca.tabela_085_presente(cur_a), False),
        (mcd.corrida_ativa(db_d), mca.corrida_ativa(cur_a), False),
        (mcd.corrida_aberta(db_d, "M1"), mca.corrida_aberta(cur_a, "M1"), None),
        (mcd.corridas_abertas(db_d), mca.corridas_abertas(cur_a), []),
        (mcd.corrida(db_d, 1), mca.corrida(cur_a, 1), None),
        (mcd.membros(db_d, 1), mca.membros(cur_a, 1), []),
        (mcd.teto_horas_da_malha(db_d, "M1"),
         mca.teto_horas_da_malha(cur_a, "M1"), 24),
        (mcd.quiescencia_minutos(db_d), mca.quiescencia_minutos(cur_a), 15),
        (mcd.carencia_partida_min(db_d), mca.carencia_partida_min(cur_a), 15),
        (mcd.abrir_corrida(db_d, "M1", ODATE, "manual"),
         mca.abrir_corrida(cur_a, "M1", ODATE, "manual"), None),
        (mcd.congelar_snapshot(db_d, 1, "M1"),
         mca.congelar_snapshot(cur_a, 1, "M1"), None),
        (mcd.vincular_execucao(db_d, "PIPE_A", ODATE, "run_1", 1),
         mca.vincular_execucao(cur_a, "PIPE_A", ODATE, "run_1", 1), False),
        (mcd.fechar_corrida(db_d, 1, "CONCLUIDA", "guardia"),
         mca.fechar_corrida(cur_a, 1, "CONCLUIDA", "guardia"), False),
        (mcd.reabrir_corrida(db_d, 1, "op"),
         mca.reabrir_corrida(cur_a, 1, "op"), False),
        (mcd.marcar_visto(db_d, 1, "falha"),
         mca.marcar_visto(cur_a, 1, "falha"), False),
    ]
    for do_dags, do_api, esperado in pares:
        assert do_dags == do_api == esperado
    assert mcd.corrida_aberta_do_pipeline(db_d, "PIPE_B") \
        == mca.corrida_aberta_do_pipeline(cur_a, "PIPE_B") \
        == {"corridas": [], "odate": None, "ambiguo": False}


@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_as_duas_arvores_classificam_o_erro_do_MESMO_jeito(mcd, driver):
    """`_sem_085` é o que separa "deploy parcial, degrade" de "bug do chamador,
    suba". Uma árvore mais permissiva que a outra engoliria em produção o erro
    que a outra reporta."""
    casos = [
        (erro_objeto_ausente("dbo.etl_malha_execucao", driver), True),
        (erro_objeto_ausente("dbo.etl_malha_execucao_membro", driver), True),
        (erro_coluna_ausente("malha_execucao_id", driver), True),
        (erro_coluna_ausente("outra_coluna_qualquer", driver), False),
        (erro_fk_membro(driver), False),
        (erro_duplicata("ux_malha_exec_aberta", driver), False),
        (erro_duplicata("ux_malha_exec_seq", driver), False),
        (erro(2628, "String or binary data would be truncated in table "
                    "'dbo.etl_malha_execucao', column 'motivo'.", driver), False),
        (erro(1205, "Transaction was deadlocked on lock resources.", driver), False),
        (RuntimeError("timeout"), False),
    ]
    for excecao, esperado in casos:
        assert mcd._sem_085(excecao) is esperado, str(excecao)
        assert mca._sem_085(excecao) is esperado, str(excecao)


@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_as_duas_arvores_distinguem_os_dois_indices_pelo_nome(mcd, driver):
    """Decisão 7 — `ux_malha_exec_aberta` significa "adira" e `ux_malha_exec_seq`
    significa "recalcule". Um handler genérico de 2601 aderiria à corrida
    errada, ou pior: a uma corrida FECHADA."""
    aberta = erro_duplicata("ux_malha_exec_aberta", driver)
    seq = erro_duplicata("ux_malha_exec_seq", driver)
    for m in (mcd, mca):
        assert m._violou(aberta, m.IX_ABERTA) is True
        assert m._violou(aberta, m.IX_SEQUENCIA) is False
        assert m._violou(seq, m.IX_SEQUENCIA) is True
        # `ux_malha_exec_aberta` NÃO pode casar por prefixo com outro nome
        assert m._violou(seq, m.IX_ABERTA) is False


def test_a_adesao_e_a_colisao_de_sequencia_se_comportam_igual(mcd):
    """As duas bordas de concorrência, lado a lado nas duas árvores: o 2601 de
    abertura vira adesão (mesma corrida, `nova=False`), e o de sequência vira
    nova tentativa (corrida nova, `sequencia` recalculada)."""
    db_d, db_a = banco(forcar_seq=1), banco(forcar_seq=1)
    c_d = mcd.abrir_corrida(db_d, "M1", ODATE, "manual")
    c_a = mca.abrir_corrida(db_a.cursor(), "M1", ODATE, "manual")
    assert c_d == c_a
    assert c_d["nova"] is True and c_d["sequencia"] == 1

    db_d, db_a = banco(forcar_seq=3), banco(forcar_seq=3)
    assert mcd.abrir_corrida(db_d, "M1", ODATE, "manual") is None
    assert mca.abrir_corrida(db_a.cursor(), "M1", ODATE, "manual") is None

    db_d, db_a = banco(forcar_aberta=1), banco(forcar_aberta=1)
    assert mcd.abrir_corrida(db_d, "M1", ODATE, "manual")["nova"] is True
    assert mca.abrir_corrida(db_a.cursor(), "M1", ODATE, "manual")["nova"] is True

    db_d, db_a = banco(forcar_aberta=3), banco(forcar_aberta=3)
    assert mcd.abrir_corrida(db_d, "M1", ODATE, "manual") is None
    assert mca.abrir_corrida(db_a.cursor(), "M1", ODATE, "manual") is None


def test_o_erro_que_nao_e_da_085_sobe_nas_DUAS_arvores(mcd):
    """A metade estreita da degradação, com paridade: uma árvore que engolisse
    o deadlock devolveria "não abriu" e o chamador seguiria achando que não há
    corrida."""
    for chamada in (
            lambda m, a: m.abrir_corrida(a, "M1", ODATE, "manual"),
            lambda m, a: m.congelar_snapshot(a, 1, "M1"),
            lambda m, a: m.vincular_execucao(a, "P", ODATE, "r", 1),
            lambda m, a: m.fechar_corrida(a, 1, "CONCLUIDA", "g"),
            lambda m, a: m.reabrir_corrida(a, 1, "op"),
            lambda m, a: m.marcar_visto(a, 1, "falha")):
        with pytest.raises(RuntimeError):
            chamada(mcd, banco(explodir=True))
        with pytest.raises(RuntimeError):
            chamada(mca, banco(explodir=True).cursor())


# ═══════════════════════ ausência estrutural (F1) ═══════════════════════════

def test_so_o_router_de_malhas_consome_o_port():
    """A F1 provava a AUSÊNCIA total de consumidor ("nenhum leitor, nenhum
    escritor no motor" — a fase era inerte de propósito). A F3 é a fase que
    rompe isso, e a invariante que a substitui é mais forte que a original:
    **um consumidor só, e ele fala com o registro pelo MÓDULO**.

    A segunda metade é a que importa de verdade. Um router que montasse SQL de
    `etl_malha_execucao` por conta própria teria escapado do teste de paridade —
    e é exatamente assim que a API e o motor passam a discordar sobre o que é
    uma corrida, que é a doença que esta spec inteira existe para curar. As duas
    exceções nomeadas em `malhas.py` (a listagem da tela e o carimbo do rename)
    são de TELA e de CADASTRO, existem só nesta árvore e estão comentadas lá.
    """
    routers = _ROOT / "api/routers"
    for arquivo in sorted(routers.glob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        if arquivo.name == "malhas.py":
            assert "from services import malha_corrida as mc" in fonte
            continue
        assert "malha_corrida" not in fonte, arquivo.name
        assert "etl_malha_execucao" not in fonte, arquivo.name


def test_nenhuma_das_arvores_commita_por_conta(mcd):
    """As duas metades do mesmo contrato: abrir a corrida e congelar o snapshot
    são UM commit só, e fechar commita junto com o evento (Decisão 20). Uma
    árvore que commitasse sozinha quebraria a atomicidade da outra ponta."""
    _, _, db_d, db_a = _nas_duas_arvores(mcd)
    assert (db_d.commits, db_d.rollbacks, db_d.closes) == (0, 0, 0)
    assert (db_a.commits, db_a.rollbacks, db_a.closes) == (0, 0, 0)


def test_nenhuma_das_arvores_sabe_fazer_conta_de_tempo():
    """Decisão 10 provada por AUSÊNCIA nas DUAS árvores — o teste do canônico
    (`test_o_modulo_nao_sabe_fazer_conta_de_tempo`) só lê `dags/`, e o port é
    justamente o lado onde o desvio de 3h entre a API e o SQL Server aparece.
    `time` fica de fora da proibição de propósito: ele mede o TTL do cache do
    interruptor, que é relógio do PROCESSO, não da corrida.

    A prova é pela ÁRVORE SINTÁTICA, e não por `"datetime" not in fonte`: as duas
    docstrings citam `datetime.now()` e `timedelta` justamente para explicar por
    que não os usam, e um teste de substring proibiria o comentário em vez do
    código."""
    import ast

    def importados(rel):
        arvore = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        nomes = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes.update(a.name.split(".")[0] for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes.add(no.module.split(".")[0])
        return nomes

    assert importados("api/services/malha_corrida.py") == {
        "__future__", "logging", "time", "services"}
    assert importados("dags/utils/malha_corrida.py") == {"__future__", "utils"}


def test_nenhuma_das_arvores_importa_a_outra():
    """Import cruzado quebraria no primeiro deploy parcial — o container da API
    não embarca `dags/`."""
    fonte_api = (_ROOT / "api/services/malha_corrida.py").read_text(encoding="utf-8")
    fonte_dags = (_ROOT / "dags/utils/malha_corrida.py").read_text(encoding="utf-8")
    assert "from utils" not in fonte_api and "import utils" not in fonte_api
    assert "from services" not in fonte_dags and "import services" not in fonte_dags
