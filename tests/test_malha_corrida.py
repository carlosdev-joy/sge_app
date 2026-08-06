"""
dags/utils/malha_corrida.py — o registro da CORRIDA de malha (F1 da spec
docs/spec-malha-execucao.md §5 e §6).

O ciclo da malha deixa de ser inferido por quatro réguas incompatíveis e passa a
ser UM registro. Estes testes cobrem o canônico de `dags/` (o port de `api/` tem
paridade provada em tests/test_malha_corrida_paridade.py).

POR QUE UM DUBLÊ QUE **INTERPRETA**, e não um mock que devolve resposta pronta:
o que a F1 entrega é *comportamento contra invariante de banco*. Um mock que
responde "já existe corrida" ao segundo `abrir_corrida` provaria apenas que o
mock foi programado; o que precisa ser provado é que o módulo reage certo a uma
violação de `ux_malha_exec_aberta` que ele NÃO pediu — que é como o SQL Server
responde quando outra ponta abriu primeiro. Por isso `Banco` abaixo é um SQL
Server em miniatura: guarda linhas, avalia `WHERE`, aplica os dois índices
únicos (o FILTRADO por `fechada_em IS NULL` e o de `(malha, data, sequencia)`),
o `CK_mexec_coerente`, a FK do snapshot e devolve `rowcount` de verdade. O
relógio dele é o do BANCO, deslocado de propósito do relógio do Python
(Decisão 10) — assim, qualquer aritmética de tempo feita em Python apareceria
como resultado errado, não como teste verde.

O dublê também é CONTRATO: SQL que ele não reconhece levanta `AssertionError`.
Mudar o SQL do módulo sem passar por aqui quebra a suíte, que é o ponto.

Cobertura: abertura idempotente (violação de índice → devolve a existente),
sequência do dia, leituras, fechamento com `rowcount` de árbitro, reabertura,
snapshot congelado, vínculo write-once, o interruptor com cache, as configs, o
ODATE canônico, e a degradação em duas metades — leitura larga, escrita
ESTREITA — sem a 085 e com o banco fora do ar.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_FONTE_DAGS = _ROOT / "dags/utils/malha_corrida.py"

# `odate_da_abertura` importa `utils.data_referencia` PREGUIÇOSAMENTE — em
# produção quem põe a pasta de DAGs no `sys.path` é o próprio Airflow. Aqui o
# teste reproduz esse ambiente (mesmo gesto de test_ds_estrutura.py), em vez de
# dublar o `calcular`: é justamente a concordância entre a corrida e o cálculo
# de ODATE que a Decisão 18 exige, e um dublê a esconderia.
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))


def _load(name, rel):
    """Carrega o módulo de `dags/` por caminho (técnica de test_malha_ciclo)."""
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mc():
    return _load("utils_malha_corrida_test", "dags/utils/malha_corrida.py")


@pytest.fixture(autouse=True)
def _sem_cache(mc):
    """O interruptor é cacheado por PROCESSO no canônico; sem isto o primeiro
    teste que o lê decidiria a resposta de todos os outros."""
    mc.limpar_cache()
    yield
    mc.limpar_cache()


# ═══════════════════════════════ o dublê ════════════════════════════════════

# A projeção da corrida, escrita aqui por extenso de propósito: é o CONTRATO da
# ordem das colunas entre o SQL e `_como_dict`. O teste
# `test_projecao_e_a_do_contrato` confronta esta tupla com a do módulo — se
# alguém acrescentar coluna só de um lado, a suíte diz onde.
CAMPOS = (
    "id", "malha_name", "data_referencia", "sequencia", "status", "aberta_em",
    "fechada_em", "fechada_por", "origem", "aberta_por", "ancora_pipeline",
    "ancora_execution_id", "no_inicio", "no_fim", "modo_fechamento", "teto_em",
    "teto_creditado_min", "falha_vista_em", "atraso_visto_em", "tentativas",
    "reaberta_em", "reaberta_por", "motivo")

# O relógio do BANCO. Fica 3h à frente do "agora" do worker de propósito: é o
# desvio MEDIDO no dev (Decisão 10), e é o que transforma aritmética de tempo em
# Python de bug silencioso em teste vermelho.
AGORA_BANCO = datetime(2026, 8, 5, 1, 30, 0)
AGORA_WORKER = datetime(2026, 8, 4, 22, 30, 0)

ODATE = date(2026, 8, 4)
ODATE_ONTEM = date(2026, 8, 3)


class ErroDriver(Exception):
    """Exceção com a FORMA do driver, porque é da forma que `_sem_085` depende.

    pymssql entrega `args[0]` inteiro (`(208, b'Invalid object name ...')`); o
    pyodbc entrega `('42S02', '[42S02] ... (208) (SQLExecDirectW)')` e põe o
    código nativo entre parênteses no texto. As duas formas são geradas aqui
    para que o mesmo módulo seja provado contra as duas árvores de deploy."""


def erro(numero: int, mensagem: str, driver: str = "pymssql") -> ErroDriver:
    if driver == "pymssql":
        return ErroDriver(numero, mensagem.encode("utf-8"))
    return ErroDriver(
        "42S02",
        "[42S02] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
        f"{mensagem} ({numero}) (SQLExecDirectW)")


def erro_objeto_ausente(objeto: str, driver="pymssql") -> ErroDriver:
    """O 208 do SQL Server quando a 085 não foi aplicada."""
    return erro(208, f"Invalid object name '{objeto}'.", driver)


def erro_coluna_ausente(coluna: str, driver="pymssql") -> ErroDriver:
    return erro(207, f"Invalid column name '{coluna}'.", driver)


def erro_duplicata(indice: str, driver="pymssql") -> ErroDriver:
    """O 2601 real: ele NOMEIA o índice, e é o nome que distingue as duas
    invariantes opostas da corrida (Decisão 7)."""
    return erro(2601,
                "Cannot insert duplicate key row in object "
                f"'dbo.etl_malha_execucao' with unique index '{indice}'. "
                "The duplicate key value is (M1).", driver)


def erro_fk_membro(driver="pymssql") -> ErroDriver:
    """O 547 da FK do snapshot. Ele TAMBÉM cita `etl_malha_execucao` no texto —
    é o falso positivo que a degradação estreita existe para não cometer."""
    return erro(547,
                'The INSERT statement conflicted with the FOREIGN KEY '
                'constraint "FK_mexec_membro_corrida". The conflict occurred in '
                'database "orquestra_dev", table "dbo.etl_malha_execucao", '
                "column 'id'.", driver)


class Banco:
    """SQL Server em miniatura para a 085.

    Guarda linhas e AVALIA o SQL: os dois índices únicos, o CHECK de coerência,
    a FK do snapshot, o `rowcount` e a acumulação de `motivo` são executados de
    verdade. O relógio é `agora` (o do banco), nunca o do Python.

    Botões que existem para produzir o que só a concorrência produz:
      • `forcar_seq`    — N violações de `ux_malha_exec_seq` antes de deixar
                          inserir (outra ponta levou a sequência entre o MAX e
                          o INSERT);
      • `forcar_aberta` — N violações de `ux_malha_exec_aberta` SEM que haja
                          corrida aberta (a corrida fechou entre a violação e a
                          releitura de adesão);
      • `com_085=False` — a migration não está no banco: 207/208 com a forma do
                          driver;
      • `explodir=True` — banco fora do ar: erro que NÃO é da 085.
    """

    def __init__(self, *, malhas=None, malha_pipeline=None, pipelines=None,
                 dependencias=None, config=None, execucoes=None, eventos=None,
                 com_085=True, explodir=False, driver="pymssql",
                 agora=AGORA_BANCO, forcar_seq=0, forcar_aberta=0):
        self.malhas = dict(malhas or {})                  # nome → {teto_horas, hora_virada}
        self.malha_pipeline = dict(malha_pipeline or {})  # malha → [pipelines]
        self.pipelines = dict(pipelines or {})            # pipeline → active(bool)
        self.dependencias = list(dependencias or [])      # (pipeline, depende_de, tipo)
        self.config = dict(config or {})
        self.execucoes = list(execucoes or [])            # dicts de etl_pipeline_execucao
        self.corridas: list[dict] = []
        self.membros: list[dict] = []
        # F8: a fila de alerta. O dublê a guarda porque a reabertura passou a
        # MEXER nela — e um dublê que não conhecesse o DELETE deixaria o
        # descarte cair no `except` do módulo, verde, com o card da segunda
        # conclusão perdido em produção. (Foi o que aconteceu na 1ª rodada.)
        self.eventos: list[dict] = list(eventos or [])
        self.com_085 = com_085
        self.explodir = explodir
        self.driver = driver
        self.agora = agora
        self.forcar_seq = forcar_seq
        self.forcar_aberta = forcar_aberta
        self.sqls: list[tuple] = []
        self._proximo_id = 1
        # O contrato "nenhuma função abre conexão, commita ou faz rollback" só é
        # verificável se houver o que contar.
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    # ── superfície de conexão ────────────────────────────────────────────────
    def cursor(self):
        return Cur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1

    # ── helpers de cenário ───────────────────────────────────────────────────
    def abertas(self, malha):
        return [c for c in self.corridas
                if c["malha_name"] == malha and c["fechada_em"] is None]

    def por_id(self, corrida_id):
        for c in self.corridas:
            if c["id"] == int(corrida_id):
                return c
        return None

    def membros_de(self, corrida_id):
        return [m for m in self.membros if m["malha_execucao_id"] == int(corrida_id)]


def _acumula_motivo(atual, novo):
    """`motivo = CASE WHEN ? IS NULL THEN motivo ELSE LEFT(ISNULL(motivo + ' | ',
    ''), 500) ... END` — em T-SQL `NULL + ' | '` é NULL, e o ISNULL o troca por
    string vazia. Reproduzido aqui para que o teste do acúmulo seja do SQL, não
    do dublê."""
    if novo is None:
        return atual
    prefixo = (atual + " | ") if atual is not None else ""
    return (prefixo + novo)[:500]


def _texto_da_reabertura(s, c, motivo):
    """O `motivo` que o `SQL_REABRIR` compõe em T-SQL (F8): o desfecho anulado,
    a hora dele e — opcionalmente — o texto de quem reabriu. Reproduzido aqui
    para que a prova seja do statement, não da bondade do dublê; se o módulo
    parar de compor, o `in s` abaixo não casa e o dublê volta ao texto cru."""
    if "'reaberta apos '" not in s:
        return motivo
    quando = c["fechada_em"]
    quando = (quando.strftime("%Y-%m-%d %H:%M:%S") if quando is not None
              else "data desconhecida")
    texto = f"reaberta apos {c['status']} de {quando}"
    return texto + (f": {motivo}" if motivo is not None else "")


# ── o CONTRATO textual das três consultas do §7 (F5) ────────────────────────
#
# REGRA DA HONESTIDADE DO DUBLÊ, e por que ela precisou virar isto aqui: as
# guardas dos degraus 0, 1 e 3 moram TODAS no `WHERE` (`fechada_em IS NULL`, o
# `mp.pipeline_name` do JOIN, o filtro por `execution_id`, o `ORDER BY id`), e
# este dublê não tem avaliador de `WHERE` — ele despachava por prefixo e
# aplicava as guardas por conta própria. Provado por mutação em 2026-08-05:
# apagar `me.fechada_em IS NULL` do degrau 1, ou o `ORDER BY id` do degrau 0,
# deixava a suíte INTEIRA verde; só a paridade acusava — e paridade prova que
# as duas árvores dizem a MESMA coisa, não que a coisa está certa (o repo manda
# mudar as duas no mesmo commit, então uma regressão coordenada passaria).
#
# A saída honesta é a que o próprio contrato do dublê já declara — "SQL que ele
# não reconhece levanta AssertionError": as três consultas são servidas SÓ na
# forma canônica. Enfraquecer um predicado no módulo deixa de ser uma resposta
# filtrada pela bondade do dublê e passa a ser divergência de contrato.
_WHERE_CANONICO = {
    "degrau_0": ("WHERE pipeline_name = ? AND execution_id = ? ORDER BY id"),
    "degrau_1": ("WHERE me.id = ? AND mp.pipeline_name = ? "
                 "AND me.fechada_em IS NULL"),
    "degrau_3": ("WHERE mp.pipeline_name = ? AND me.fechada_em IS NULL "
                 "ORDER BY me.malha_name"),
}


def _contrato(s: str, chave: str):
    esperado = _WHERE_CANONICO[chave]
    assert s.endswith(esperado), (
        f"{chave}: o WHERE mudou, e o dublê nao pode adivinhar a intencao.\n"
        f"  esperado terminar em: {esperado}\n  veio: {s}")


class Cur:
    def __init__(self, db: Banco):
        self.db = db
        self._rows: list[tuple] = []
        self.rowcount = -1

    # ── despacho ────────────────────────────────────────────────────────────
    def execute(self, sql, params=()):  # noqa: C901 — é um despachante de dublê
        db = self.db
        s = " ".join(str(sql).split()).replace("%s", "?")
        p = tuple(params)
        db.sqls.append((s, p))
        self._rows = []
        self.rowcount = -1

        # A sonda vem ANTES de tudo: `OBJECT_ID` de tabela inexistente devolve
        # NULL, não levanta — é justamente por isso que ela serve de sonda.
        if "OBJECT_ID('dbo.etl_malha_execucao','U')" in s:
            if db.explodir:
                raise RuntimeError("banco fora do ar (teste)")
            self._rows = [(1, 1, 1)] if db.com_085 else [(None, None, None)]
            return

        if db.explodir:
            raise RuntimeError("banco fora do ar (teste)")

        if not db.com_085:
            if "etl_malha_execucao_membro" in s:
                raise erro_objeto_ausente("dbo.etl_malha_execucao_membro", db.driver)
            if "etl_malha_execucao" in s:
                raise erro_objeto_ausente("dbo.etl_malha_execucao", db.driver)
            if "malha_execucao_id" in s:
                raise erro_coluna_ausente("malha_execucao_id", db.driver)
            if "m.teto_horas" in s:
                raise erro_coluna_ausente("teto_horas", db.driver)

        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            chave = p[0] if p else "dependencia_hora_virada"
            if chave in db.config:
                self._rows = [(db.config[chave],)]
            return

        if s.startswith("SELECT m.teto_horas, c.config_value"):
            m = db.malhas.get(p[0])
            if m is not None:
                self._rows = [(m.get("teto_horas"),
                               db.config.get("malha_teto_horas_padrao"))]
            return

        if s.startswith("SELECT m.hora_virada, c.config_value"):
            m = db.malhas.get(p[0])
            if m is not None:
                self._rows = [(m.get("hora_virada"),
                               db.config.get("dependencia_hora_virada"))]
            return

        if s.startswith("SELECT id, malha_name"):
            if "WHERE malha_name = ? AND fechada_em IS NULL" in s:
                self._rows = [self._proj(c) for c in db.abertas(p[0])]
            elif "WHERE fechada_em IS NULL ORDER BY malha_name" in s:
                self._rows = [self._proj(c) for c in
                              sorted((c for c in db.corridas
                                      if c["fechada_em"] is None),
                                     key=lambda c: c["malha_name"])]
            elif "WHERE id IN (SELECT DISTINCT e.malha_execucao_id" in s:
                # F8 — as corridas DONAS das linhas de um lote de pipelines.
                # As guardas do módulo são reproduzidas do SQL EMITIDO, e não
                # inventadas: sem `malha_execucao_id IS NOT NULL` o dublê
                # devolveria a corrida de quem não tem vínculo nenhum.
                assert "e.data_referencia = ?" in s and \
                       "e.malha_execucao_id IS NOT NULL" in s, s
                data_ref, alvos = p[0], set(p[1:])
                ids = {l.get("malha_execucao_id") for l in db.execucoes
                       if l["pipeline_name"] in alvos
                       and l["data_referencia"] == data_ref
                       and l.get("malha_execucao_id") is not None}
                if "1 = 0" in s:
                    ids = set()
                achadas = [c for c in db.corridas if c["id"] in ids]
                self._rows = [self._proj(c)
                              for c in sorted(achadas, key=lambda c: c["id"])]
            elif "WHERE id = ?" in s:
                achada = db.por_id(p[0])
                self._rows = [self._proj(achada)] if achada else []
            else:  # pragma: no cover — só se alguém inventar um terceiro WHERE
                raise AssertionError(f"SELECT da corrida fora do contrato: {s}")
            return

        if s.startswith("SELECT me.id, me.malha_name"):
            # Duas consultas começam igual e são OPOSTAS em intenção: as
            # corridas abertas DO PIPELINE (degrau 3) e a corrida DO CONF
            # (degrau 1, que também exige `me.id`). Despachar pelo prefixo
            # devolveria a lista inteira para quem pediu uma corrida só.
            if "WHERE me.id = ?" in s:
                _contrato(s, "degrau_1")
                corrida_id, pipe = int(p[0]), p[1]
                c = db.por_id(corrida_id)
                malhas = [m for m, ps in db.malha_pipeline.items() if pipe in ps]
                achou = (c is not None and c["fechada_em"] is None
                         and c["malha_name"] in malhas)
                self._rows = [self._proj(c)] if achou else []
                return
            _contrato(s, "degrau_3")
            malhas = [m for m, ps in db.malha_pipeline.items() if p[0] in ps]
            achadas = [c for c in db.corridas
                       if c["malha_name"] in malhas and c["fechada_em"] is None]
            self._rows = [self._proj(c) for c in
                          sorted(achadas, key=lambda c: c["malha_name"])]
            return

        # Degrau 0 do §7: o ODATE que a linha deste run já carimbou. `ORDER BY
        # id` é do SQL e é reproduzido aqui — se um dia houver duas linhas do
        # mesmo run (a doença), a resposta tem de ser SEMPRE a mesma.
        if s.startswith("SELECT TOP 1 data_referencia, malha_execucao_id"):
            _contrato(s, "degrau_0")
            achadas = [l for l in db.execucoes
                       if l["pipeline_name"] == p[0]
                       and str(l["execution_id"]) == str(p[1])]
            achadas.sort(key=lambda l: l.get("id", 0))
            self._rows = [(l["data_referencia"], l.get("malha_execucao_id"))
                          for l in achadas[:1]]
            return

        if s.startswith("SELECT pipeline_name, conta_para_fim"):
            self._rows = [(m["pipeline_name"], m["conta_para_fim"],
                           m["ativo_na_abertura"], m["eh_raiz"])
                          for m in sorted(db.membros_de(p[0]),
                                          key=lambda m: m["pipeline_name"])]
            return

        # O membro vem ANTES da corrida: `etl_malha_execucao` é prefixo de
        # `etl_malha_execucao_membro`.
        if s.startswith("INSERT INTO dbo.etl_malha_execucao_membro"):
            self._snapshot(s, p)
            return

        if s.startswith("INSERT INTO dbo.etl_malha_execucao"):
            self._abrir(s, p)
            return

        if s.startswith("UPDATE dbo.etl_pipeline_execucao"):
            self._vincular(s, p)
            return

        if s.startswith("UPDATE dbo.etl_malha_execucao SET status = ?"):
            self._fechar(s, p)
            return

        if s.startswith("UPDATE me SET me.status = 'ABERTA'"):
            self._reabrir(s, p)
            return

        if s.startswith("UPDATE dbo.etl_malha_execucao SET falha_vista_em"):
            self._visto(s, "falha_vista_em", p)
            return

        if s.startswith("UPDATE dbo.etl_malha_execucao SET atraso_visto_em"):
            self._visto(s, "atraso_visto_em", p)
            return

        if s.startswith("DELETE FROM dbo.etl_dependencia_evento"):
            self._descartar_desfecho(s, p)
            return

        raise AssertionError(f"SQL fora do contrato do dublê: {s}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    # ── implementações ──────────────────────────────────────────────────────
    #
    # REGRA DO DUBLÊ (a lição do `filtra_substituida` de
    # tests/test_dependencias_f5_paridade.py): guarda que mora no `WHERE` do
    # módulo só é aplicada aqui se o SQL EMITIDO a contiver. Um dublê que
    # aplicasse o write-once por conta própria passaria verde com o módulo
    # reescrevendo o passado — ele estaria provando a si mesmo. As únicas
    # regras incondicionais são as do MODELO (os dois índices únicos, os CHECKs
    # e a FK), porque essas o SQL Server aplica quer o statement peça, quer não.
    def _proj(self, c):
        return tuple(c[campo] for campo in CAMPOS)

    def _abrir(self, s, p):
        db = self.db
        assert len(p) == 14, f"abertura com {len(p)} parametros: {p}"
        # A (malha, data) aparece DUAS vezes: uma na projeção, outra na
        # subconsulta da sequência sob (UPDLOCK, HOLDLOCK).
        assert p[0] == p[2] and p[1] == p[3], f"malha/odate fora de par: {p}"
        assert "WITH (UPDLOCK, HOLDLOCK)" in s, "sequência sem trava de faixa"
        malha, odate = p[0], p[1]
        origem, modo, teto = p[4], p[10], p[11]
        if origem not in ("inicio", "manual", "implicita"):
            raise erro(547, 'conflicted with the CHECK constraint '
                            '"CK_mexec_origem"', db.driver)
        if modo not in ("fim", "quiescencia"):
            raise erro(547, 'conflicted with the CHECK constraint '
                            '"CK_mexec_modo"', db.driver)
        if db.forcar_aberta > 0:
            db.forcar_aberta -= 1
            raise erro_duplicata("ux_malha_exec_aberta", db.driver)
        if db.abertas(malha):
            raise erro_duplicata("ux_malha_exec_aberta", db.driver)
        seq = max([c["sequencia"] for c in db.corridas
                   if c["malha_name"] == malha and c["data_referencia"] == odate],
                  default=0) + 1
        if db.forcar_seq > 0:
            db.forcar_seq -= 1
            raise erro_duplicata("ux_malha_exec_seq", db.driver)
        # `aberta_em` = COALESCE(param, SYSDATETIME()); `teto_em` sai da MESMA
        # avaliação (a tabela derivada `v.ab`), nunca de um segundo relógio.
        ab = p[13] if p[13] is not None else db.agora
        linha = {
            "id": db._proximo_id, "malha_name": malha, "data_referencia": odate,
            "sequencia": seq, "status": "ABERTA", "aberta_em": ab,
            "fechada_em": None, "fechada_por": None, "origem": origem,
            "aberta_por": p[5], "ancora_pipeline": p[6],
            "ancora_execution_id": p[7], "no_inicio": p[8], "no_fim": p[9],
            "modo_fechamento": modo, "teto_em": ab + timedelta(hours=int(teto)),
            "teto_creditado_min": 0, "falha_vista_em": None,
            "atraso_visto_em": None, "tentativas": 1, "reaberta_em": None,
            "reaberta_por": None, "motivo": p[12],
        }
        db._proximo_id += 1
        db.corridas.append(linha)
        self._rows = [self._proj(linha)]   # o OUTPUT inserted.*
        self.rowcount = 1

    def _snapshot(self, s, p):
        db = self.db
        corrida_id = int(p[0])
        malha = p[-2]
        quantos = len(p) - 3
        if db.por_id(corrida_id) is None:
            raise erro_fk_membro(db.driver)
        if "CASE WHEN 1 = 1 THEN" in s:
            def conta(_):
                return 1
        elif "CASE WHEN 1 = 0 THEN" in s:
            def conta(_):
                return 0
        else:
            assert "mp.pipeline_name IN (" in s, f"snapshot sem IN: {s}"
            assert quantos > 0, "IN sem parâmetros"
            alvo = set(p[1:1 + quantos])

            def conta(pipe):
                return 1 if pipe in alvo else 0
        # A idempotência é do statement, não do dublê: sem o NOT EXISTS a PK
        # composta estoura, que é justamente o 2627 que rolaria de volta a
        # transação do chamador (inclusive o INSERT da corrida).
        idempotente = "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao_membro m" in s
        ja = {m["pipeline_name"] for m in db.membros_de(corrida_id)}
        irmaos = set(db.malha_pipeline.get(malha, []))
        inseridos = 0
        for pipe in db.malha_pipeline.get(malha, []):
            if pipe in ja:
                if idempotente:
                    continue
                raise erro(2627, "Violation of PRIMARY KEY constraint "
                                 "'PK_etl_malha_exec_membro'. Cannot insert "
                                 "duplicate key in object "
                                 "'dbo.etl_malha_execucao_membro'.", db.driver)
            tem_pai_na_malha = any(
                d[0] == pipe and d[2] == "PIPELINE" and d[1] in irmaos
                for d in db.dependencias)
            db.membros.append({
                "malha_execucao_id": corrida_id, "pipeline_name": pipe,
                "conta_para_fim": conta(pipe),
                # LEFT JOIN + ISNULL(p.active, 0): membro fora do cadastro entra
                # como inativo, não derruba o snapshot.
                "ativo_na_abertura": 1 if db.pipelines.get(pipe) else 0,
                "eh_raiz": 0 if tem_pai_na_malha else 1,
            })
            inseridos += 1
        self.rowcount = inseridos

    def _vincular(self, s, p):
        db = self.db
        corrida_id, pipe, dref, exec_id = int(p[0]), p[1], p[2], p[3]
        write_once = "AND malha_execucao_id IS NULL" in s
        n = 0
        for linha in db.execucoes:
            if (linha["pipeline_name"] == pipe
                    and linha["data_referencia"] == dref
                    and linha["execution_id"] == exec_id
                    and not (write_once
                             and linha.get("malha_execucao_id") is not None)):
                linha["malha_execucao_id"] = corrida_id
                n += 1
        self.rowcount = n

    def _fechar(self, s, p):
        db = self.db
        desfecho, fechada_por, motivo, motivo2, corrida_id = p
        assert motivo == motivo2, "o motivo entra duas vezes no mesmo CASE"
        if desfecho == "ABERTA" or desfecho not in (
                "CONCLUIDA", "FALHA", "SEM_TRABALHO", "EXPIRADA", "ABORTADA",
                "CANCELADA"):
            raise erro(547, 'conflicted with the CHECK constraint '
                            '"CK_mexec_status"', db.driver)
        c = db.por_id(corrida_id)
        if c is None:
            self.rowcount = 0
            return
        if "AND fechada_em IS NULL" in s and c["fechada_em"] is not None:
            self.rowcount = 0
            return
        c.update({"status": desfecho, "fechada_em": db.agora,
                  "fechada_por": fechada_por,
                  "motivo": _acumula_motivo(c["motivo"], motivo)})
        self.rowcount = 1

    def _reabrir(self, s, p):
        db = self.db
        reaberta_por, motivo, motivo2, corrida_id = p[0], p[1], p[2], int(p[3])
        assert motivo == motivo2, "o motivo entra duas vezes no mesmo CASE"
        permitidos = set(p[4:])
        c = db.por_id(corrida_id)
        if c is None:
            self.rowcount = 0
            return
        if "me.status IN (" in s and c["status"] not in permitidos:
            self.rowcount = 0
            return
        # O NOT EXISTS correlacionado: nenhuma OUTRA corrida aberta da malha.
        if "NOT EXISTS" in s and db.abertas(c["malha_name"]):
            self.rowcount = 0
            return
        if [o for o in db.abertas(c["malha_name"]) if o["id"] != c["id"]]:
            # O modelo tem a última palavra: sem a guarda no WHERE, a reabertura
            # deixaria DUAS linhas abertas da mesma malha, e é o índice filtrado
            # que recusa — dentro da transação do rerun, que rolaria inteira.
            raise erro_duplicata("ux_malha_exec_aberta", db.driver)
        novo = {"status": "ABERTA", "fechada_em": None, "fechada_por": None,
                "tentativas": c["tentativas"] + 1, "reaberta_em": db.agora,
                "reaberta_por": reaberta_por,
                # F8: o desfecho anulado e a HORA dele viram texto no `motivo`
                # — é o que preserva a história do ciclo depois que os eventos
                # da tentativa 1 forem descartados. Composto a partir dos
                # valores ANTERIORES ao UPDATE, como o SQL Server faz.
                "motivo": _acumula_motivo(
                    c["motivo"], _texto_da_reabertura(s, c, motivo))}
        # Regra do dublê: guarda que mora no statement só vale se o statement a
        # contiver. Zerar a memória de efeito colateral por conta própria faria
        # o teste passar com o módulo esquecendo de zerá-la.
        if "me.falha_vista_em = NULL" in s:
            novo["falha_vista_em"] = None
        if "me.atraso_visto_em = NULL" in s:
            novo["atraso_visto_em"] = None
        c.update(novo)
        self.rowcount = 1

    def _descartar_desfecho(self, s, p):
        """O DELETE da F8: por corrida, por tipo, e SÓ em linha de marcador."""
        db = self.db
        corrida_id, tipos = int(p[0]), set(p[1:])
        assert "malha_execucao_id = ?" in s and "tipo IN (" in s, s
        # Os dois `LEFT(...)` são o que impede o DELETE de alcançar o evento de
        # um MEMBRO. Se o módulo os perder, o dublê deixa de filtrar — e o
        # teste que guarda o evento de `CARGA_A` fica vermelho.
        so_marcador = ("LEFT(pipeline_name, 9) = '#corrida:'" in s
                       and "LEFT(pipeline_name, 4) = '#no:'" in s)

        def alvo(ev):
            if ev.get("malha_execucao_id") != corrida_id or ev["tipo"] not in tipos:
                return False
            nome = str(ev.get("pipeline_name") or "")
            if so_marcador and not (nome.startswith("#corrida:")
                                    or nome.startswith("#no:")):
                return False
            return True

        antes = len(db.eventos)
        db.eventos = [ev for ev in db.eventos if not alvo(ev)]
        self.rowcount = antes - len(db.eventos)

    def _visto(self, s, coluna, p):
        db = self.db
        c = db.por_id(p[0])
        if c is None:
            self.rowcount = 0
            return
        if "AND fechada_em IS NULL" in s and c["fechada_em"] is not None:
            self.rowcount = 0
            return
        if f"AND {coluna} IS NULL" in s and c[coluna] is not None:
            self.rowcount = 0
            return
        c[coluna] = db.agora
        self.rowcount = 1


# ── cenário padrão ──────────────────────────────────────────────────────────
# M1: A → B → C (A é a única raiz). M2 compartilha o pipeline B — é o membro de
# N malhas que a Decisão 1 existe para não escolher em silêncio.

def banco(**kw) -> Banco:
    base = dict(
        malhas={"M1": {"teto_horas": None, "hora_virada": None},
                "M2": {"teto_horas": None, "hora_virada": None}},
        malha_pipeline={"M1": ["PIPE_A", "PIPE_B", "PIPE_C"],
                        "M2": ["PIPE_B", "PIPE_D"]},
        pipelines={"PIPE_A": True, "PIPE_B": True, "PIPE_C": True,
                   "PIPE_D": True},
        dependencias=[("PIPE_B", "PIPE_A", "PIPELINE"),
                      ("PIPE_C", "PIPE_B", "PIPELINE"),
                      ("PIPE_D", "PIPE_B", "PIPELINE")],
        config={"malha_corrida_ativa": "1"},
    )
    base.update(kw)
    return Banco(**base)


def abre(mc, db, malha="M1", odate=ODATE, origem="manual", **kw):
    return mc.abrir_corrida(db, malha, odate, origem, **kw)


# ═══════════════════ contrato de forma (projeção e domínio) ═════════════════

def test_projecao_e_a_do_contrato(mc):
    """A ordem das colunas do SELECT É o contrato de `_como_dict`; o dublê
    projeta por esta tupla, então uma coluna acrescentada só no SQL apareceria
    aqui como divergência, e não como dict com valores trocados de casa."""
    assert mc._CAMPOS == CAMPOS
    assert mc._COLS.replace(" ", "").split(",") == list(CAMPOS)


def test_dominio_espelha_os_checks_da_085(mc):
    assert mc.STATUS_ABERTA == "ABERTA"
    assert set(mc.DESFECHOS) == {"CONCLUIDA", "FALHA", "SEM_TRABALHO",
                                 "EXPIRADA", "ABORTADA", "CANCELADA"}
    assert "ABERTA" not in mc.DESFECHOS   # fechar com ABERTA viola o CK de coerência
    assert set(mc.ORIGENS) == {"inicio", "manual", "implicita"}
    assert set(mc.MODOS_FECHAMENTO) == {"fim", "quiescencia"}
    # Fim de linha não volta: reabrir EXPIRADA/ABORTADA/CANCELADA/SEM_TRABALHO
    # seria ressuscitar um ciclo que alguém (ou o teto) encerrou de propósito.
    assert set(mc.REABREM) == {"CONCLUIDA", "FALHA"}


def test_como_dict_coage_os_inteiros(mc):
    """pymssql e pyodbc discordam no tipo de BIGINT/INT, e o `id` viaja daqui
    para dentro de outro SQL — um `Decimal` ou uma string ali dentro vira
    conversão implícita e scan."""
    linha = tuple("7" if c == "id" else ("3" if c in mc._INTEIROS else None)
                  for c in CAMPOS)
    d = mc._como_dict(linha)
    assert d["id"] == 7 and isinstance(d["id"], int)
    for campo in mc._INTEIROS:
        assert isinstance(d[campo], int)


# ══════════════════════════════ o interruptor ═══════════════════════════════

@pytest.mark.parametrize("valor,esperado", [
    ("1", True), ("true", True), ("True", True), (" 1 ", True),
    ("0", False), ("", False), ("nao", False), (None, False),
])
def test_interruptor_le_a_config(mc, valor, esperado):
    db = banco(config={"malha_corrida_ativa": valor})
    assert mc.corrida_ativa(db) is esperado


def test_interruptor_ausente_e_desligado(mc):
    """Sem a 085 a chave não existe — e "ausente" e "desligado" TÊM de ser o
    mesmo caminho, senão cada chamador inventa o seu."""
    assert mc.corrida_ativa(banco(config={})) is False


def test_interruptor_com_banco_fora_do_ar_nao_liga_sozinho(mc, capsys):
    assert mc.corrida_ativa(banco(explodir=True)) is False
    assert "DESLIGADA" in capsys.readouterr().out


def test_interruptor_e_uma_consulta_por_processo(mc):
    """Cacheado por processo (precedente `modo_sequencia`): a guardiã avalia N
    malhas por ciclo e perguntar por malha seriam N idas ao banco para uma
    resposta que não muda no meio do ciclo."""
    db = banco(config={"malha_corrida_ativa": "1"})
    for _ in range(5):
        assert mc.corrida_ativa(db) is True
    perguntas = [p for _, p in db.sqls if mc.CHAVE_ATIVA in p]
    assert len(perguntas) == 1


def test_limpar_cache_faz_a_chave_valer_de_novo(mc):
    """Trocar a chave vale no ciclo seguinte — o teste é justamente que ela
    NÃO vale antes, senão o cache seria decorativo."""
    db = banco(config={"malha_corrida_ativa": "1"})
    assert mc.corrida_ativa(db) is True
    db.config["malha_corrida_ativa"] = "0"
    assert mc.corrida_ativa(db) is True          # ainda o valor do ciclo
    mc.limpar_cache()
    assert mc.corrida_ativa(db) is False


def test_sonda_da_085(mc):
    assert mc.tabela_085_presente(banco()) is True
    assert mc.tabela_085_presente(banco(com_085=False)) is False
    assert mc.tabela_085_presente(banco(explodir=True)) is False


# ═════════════════════════════ configs numéricas ════════════════════════════

def test_teto_da_malha_vence_o_global(mc):
    db = banco(malhas={"M1": {"teto_horas": 6}},
               config={"malha_teto_horas_padrao": "48"})
    assert mc.teto_horas_da_malha(db, "M1") == 6


def test_teto_cai_no_global_quando_a_malha_nao_define(mc):
    db = banco(malhas={"M1": {"teto_horas": None}},
               config={"malha_teto_horas_padrao": "48"})
    assert mc.teto_horas_da_malha(db, "M1") == 48


def test_teto_e_uma_consulta_so(mc):
    """`etl_malha.teto_horas ?? config ?? 24` resolvido num SELECT — a forma de
    `virada_efetiva`, e não duas idas ao banco por corrida."""
    db = banco(malhas={"M1": {"teto_horas": None}},
               config={"malha_teto_horas_padrao": "48"})
    mc.teto_horas_da_malha(db, "M1")
    assert len(db.sqls) == 1


@pytest.mark.parametrize("valor", [0, -1, 169, 100000, "abc", "", None])
def test_teto_fora_do_dominio_volta_ao_padrao(mc, valor):
    """Teto 0 congelaria a malha para SEMPRE (corrida aberta bloqueia disparo) e
    teto de mil horas transforma a rede de segurança em decoração."""
    db = banco(malhas={"M1": {"teto_horas": valor}}, config={})
    assert mc.teto_horas_da_malha(db, "M1") == mc.TETO_HORAS_PADRAO == 24


@pytest.mark.parametrize("invalido", [0, -1, 169, "abc", ""])
def test_teto_passado_PELO_CHAMADOR_tambem_passa_pelo_dominio(mc, invalido):
    """O override de `abrir_corrida(teto_horas=...)` é a mesma trava, não uma
    porta dos fundos: `teto_horas=0` faria `teto_em = aberta_em` e a corrida
    nasceria EXPIRADA — o inverso exato do buraco que `teto_horas_da_malha` já
    fecha, e no mesmo lugar (o teto é a única rede que impede corrida aberta de
    congelar o disparo, §6.6). Fora do domínio resolve pela malha."""
    db = banco(malhas={"M1": {"teto_horas": 6}})
    c = abre(mc, db, teto_horas=invalido)
    assert c["teto_em"] - c["aberta_em"] == timedelta(hours=6)   # o da malha


def test_teto_valido_do_chamador_e_respeitado(mc):
    """A trava não pode virar "ignora o chamador": dentro do domínio, o valor
    passado vence o da malha (é assim que a porta 1 do disparo o define)."""
    db = banco(malhas={"M1": {"teto_horas": 6}})
    c = abre(mc, db, teto_horas=48)
    assert c["teto_em"] - c["aberta_em"] == timedelta(hours=48)
    assert len(db.sqls) == 1        # teto válido não vai ao banco perguntar


def test_teto_nunca_e_zero_nem_com_banco_fora(mc):
    assert mc.teto_horas_da_malha(banco(explodir=True), "M1") == 24
    assert mc.teto_horas_da_malha(banco(malhas={}), "INEXISTENTE") == 24


def test_malha_ausente_do_cadastro_ignora_ate_o_teto_GLOBAL(mc):
    """Pino de comportamento, não elogio: sem linha em `etl_malha` o `WHERE` não
    devolve NADA, então nem o `LEFT JOIN` da config global chega — a resposta é
    o padrão de 24h, e não o global de 48.

    Não é defeito no caminho da F1 (só se abre corrida de malha que existe), mas
    é reachable por construção: a Decisão 5 tirou a FK justamente para a corrida
    sobreviver ao cadastro (§6.9/#8 — corrida aberta segue até fechar mesmo que
    inativem a malha no meio do voo). Quem, na F7, recalcular o teto de uma
    corrida viva precisa saber que o global não cobre esse caso."""
    db = banco(malhas={}, config={"malha_teto_horas_padrao": "48"})
    assert mc.teto_horas_da_malha(db, "APAGADA") == 24    # não 48


@pytest.mark.parametrize("chave,funcao,padrao,dentro,fora", [
    ("malha_quiescencia_minutos", "quiescencia_minutos", 15, "30", "1"),
    ("malha_carencia_partida_min", "carencia_partida_min", 15, "45", "999"),
])
def test_configs_de_carencia(mc, chave, funcao, padrao, dentro, fora):
    f = getattr(mc, funcao)
    assert f(banco(config={chave: dentro})) == int(dentro)
    assert f(banco(config={chave: fora})) == padrao      # fora do domínio
    assert f(banco(config={})) == padrao                 # ausente
    assert f(banco(explodir=True)) == padrao             # banco fora


# ════════════════════════════ o ODATE canônico ══════════════════════════════

def test_odate_usa_a_virada_da_malha(mc):
    """Uma função, três portas (Decisão 18): a virada da MALHA vence a global,
    senão disparar às 02:00 pela tela e pelo cron no mesmo minuto produziria
    ciclos com DIAS diferentes conforme quem chegasse primeiro."""
    db = banco(malhas={"M1": {"hora_virada": time(20, 0)}},
               config={"dependencia_hora_virada": "00:00"})
    assert mc.odate_da_abertura(db, "M1", datetime(2026, 8, 4, 23, 30)) \
        == date(2026, 8, 5)


def test_odate_cai_na_virada_global_quando_a_malha_nao_tem(mc):
    db = banco(malhas={"M1": {"hora_virada": None}},
               config={"dependencia_hora_virada": "20:00"})
    assert mc.odate_da_abertura(db, "M1", datetime(2026, 8, 4, 23, 30)) \
        == date(2026, 8, 5)


def test_odate_sem_a_081_ainda_usa_a_global(mc, capsys):
    """Banco sem a coluna `hora_virada`: a leitura da malha estoura, e a
    degradação é a virada GLOBAL — o comportamento ANTERIOR a esta spec, não um
    terceiro comportamento inventado."""
    db = banco(malhas={"M1": {"hora_virada": None}},
               config={"dependencia_hora_virada": "20:00"})
    original = Cur.execute

    def sem_081(self, sql, params=()):
        if "m.hora_virada" in str(sql):
            raise erro_coluna_ausente("hora_virada")
        return original(self, sql, params)

    Cur.execute = sem_081
    try:
        assert mc.odate_da_abertura(db, "M1", datetime(2026, 8, 4, 23, 30)) \
            == date(2026, 8, 5)
    finally:
        Cur.execute = original
    assert "tentando a global" in capsys.readouterr().out


def test_odate_sem_nada_e_a_data_do_calendario(mc):
    db = banco(malhas={"M1": {}}, config={})
    assert mc.odate_da_abertura(db, "M1", datetime(2026, 8, 4, 23, 30)) \
        == date(2026, 8, 4)
    assert mc.odate_da_abertura(banco(explodir=True), "M1",
                                datetime(2026, 8, 4, 23, 30)) == date(2026, 8, 4)


# ═════════════════════════════════ abertura ═════════════════════════════════

def test_abre_a_corrida_com_o_registro_completo(mc):
    db = banco()
    c = abre(mc, db, origem="inicio", aberta_por="inicio:#12",
             ancora_pipeline="PIPE_A", ancora_execution_id="run_1",
             no_inicio=12, no_fim=13, modo_fechamento="fim", motivo="porta 1")
    assert c["nova"] is True and c["odate_confere"] is True
    assert c["id"] == 1 and c["status"] == "ABERTA" and c["fechada_em"] is None
    assert c["malha_name"] == "M1" and c["data_referencia"] == ODATE
    assert c["sequencia"] == 1 and c["tentativas"] == 1
    assert c["origem"] == "inicio" and c["modo_fechamento"] == "fim"
    assert c["ancora_pipeline"] == "PIPE_A" and c["no_inicio"] == 12
    assert c["motivo"] == "porta 1"


def test_aberta_em_e_teto_saem_do_relogio_do_BANCO(mc):
    """Decisão 10: o teto é `aberta_em + teto` avaliado UMA vez, no relógio do
    banco. O dublê está 3h à frente do Python de propósito — se alguma linha
    usasse `datetime.now()`, `aberta_em` viria com o horário do worker."""
    db = banco(config={"malha_teto_horas_padrao": "24"})
    c = abre(mc, db)
    assert c["aberta_em"] == AGORA_BANCO
    assert c["aberta_em"] != AGORA_WORKER
    assert c["teto_em"] - c["aberta_em"] == timedelta(hours=24)


def test_teto_sai_da_mesma_avaliacao_de_aberta_em(mc):
    """`aberta_em` recuado (portas 2 e 3, guardiã): o teto acompanha o recuo,
    porque os dois saem da MESMA tabela derivada — dois `SYSDATETIME()` no mesmo
    INSERT deixariam o teto fora do que a tela mostra como início."""
    db = banco()
    recuo = AGORA_BANCO - timedelta(minutes=7)
    c = abre(mc, db, aberta_em=recuo, teto_horas=6)
    assert c["aberta_em"] == recuo
    assert c["teto_em"] == recuo + timedelta(hours=6)


def test_sequencia_e_o_rotulo_da_n_esima_corrida_do_dia(mc):
    db = banco()
    primeira = abre(mc, db)
    assert primeira["sequencia"] == 1
    mc.fechar_corrida(db, primeira["id"], "CONCLUIDA", "guardia")
    segunda = abre(mc, db)
    assert segunda["nova"] is True and segunda["sequencia"] == 2
    mc.fechar_corrida(db, segunda["id"], "CONCLUIDA", "guardia")
    outro_dia = abre(mc, db, odate=date(2026, 8, 5))
    assert outro_dia["sequencia"] == 1


def test_abertura_e_IDEMPOTENTE_por_violacao_do_indice(mc, capsys):
    """A invariante é do MODELO: a segunda abertura NÃO consulta antes — ela
    tenta inserir e leva o 2601 de `ux_malha_exec_aberta`, que significa "outra
    ponta abriu primeiro". O retorno é a corrida EXISTENTE, com `nova=False` e
    a `origem` de quem chegou primeiro."""
    db = banco()
    primeira = abre(mc, db, origem="inicio", aberta_por="inicio:#12")
    segunda = abre(mc, db, origem="manual", aberta_por="manual:C123456")
    assert segunda["nova"] is False
    assert segunda["id"] == primeira["id"]
    assert segunda["origem"] == "inicio"            # não sobrescreve o vencedor
    assert segunda["aberta_por"] == "inicio:#12"
    assert len(db.corridas) == 1                    # uma linha, não duas


def test_adesao_com_ODATE_DIFERENTE_avisa_em_vez_de_carimbar(mc):
    """Decisão 15 — o `Carga_Vida` por dentro do mecanismo criado para matá-lo:
    corrida de terça travada, quarta 01:00 o cron parte e aderiria carimbando
    TERÇA em toda a carga de quarta. `odate_confere=False` é o que faz o
    chamador PULAR com motivo nominal em vez de aderir em silêncio."""
    db = banco()
    abre(mc, db, odate=ODATE_ONTEM)
    hoje = abre(mc, db, odate=ODATE)
    assert hoje["nova"] is False
    assert hoje["odate_confere"] is False
    assert hoje["data_referencia"] == ODATE_ONTEM


def test_a_vaga_do_indice_filtrado_vaga_quando_a_corrida_fecha(mc):
    """O índice é FILTRADO por `fechada_em IS NULL`: fechada a primeira, a
    segunda corrida do MESMO dia entra — é o redisparo, e ele é legítimo."""
    db = banco()
    primeira = abre(mc, db)
    assert abre(mc, db)["nova"] is False
    assert mc.fechar_corrida(db, primeira["id"], "CONCLUIDA", "guardia") is True
    terceira = abre(mc, db)
    assert terceira["nova"] is True and terceira["id"] != primeira["id"]


def test_colisao_de_SEQUENCIA_recalcula_em_vez_de_aderir(mc, capsys):
    """Decisão 7 — os dois índices únicos pedem reações OPOSTAS. `ux_malha_exec_seq`
    não é adesão: é "outra ponta levou a sequência", e a resposta é tentar de
    novo. Um handler genérico de 2601 aderiria à corrida errada."""
    db = banco(forcar_seq=1)
    c = abre(mc, db)
    assert c is not None and c["nova"] is True and c["sequencia"] == 1
    assert "recalculando" in capsys.readouterr().out


def test_colisao_de_sequencia_teimosa_desiste_sem_corrida(mc, capsys):
    db = banco(forcar_seq=mc._TENTATIVAS_ABERTURA)
    assert abre(mc, db) is None
    assert "desistiu" in capsys.readouterr().out
    assert db.corridas == []


def test_corrida_que_fecha_entre_a_violacao_e_a_releitura(mc, capsys):
    """A borda que o `continue` cobre: o 2601 de abertura chega, mas quando o
    módulo relê `fechada_em IS NULL` a corrida JÁ fechou — a vaga do índice
    filtrado vagou, e tentar de novo é a resposta certa (aderir a nada seria
    devolver None com corrida disponível)."""
    db = banco(forcar_aberta=1)
    c = abre(mc, db)
    assert c is not None and c["nova"] is True
    assert "fechou durante a abertura" in capsys.readouterr().out


def test_abertura_impossivel_devolve_None_sem_inventar_corrida(mc):
    db = banco(forcar_aberta=mc._TENTATIVAS_ABERTURA)
    assert abre(mc, db) is None
    assert db.corridas == []


@pytest.mark.parametrize("origem,modo", [("cron", "quiescencia"),
                                         ("agenda", "quiescencia"),
                                         ("manual", "teto"),
                                         ("manual", "fim_de_fila")])
def test_dominio_invalido_e_erro_de_PROGRAMA(mc, origem, modo):
    """Domínio inventado é bug, não estado do mundo: recusar na borda evita o
    `CK_mexec_origem`/`CK_mexec_modo` estourar no MEIO da transação do chamador,
    que rolaria de volta o que ele já tinha escrito."""
    db = banco()
    with pytest.raises(ValueError):
        mc.abrir_corrida(db, "M1", ODATE, origem, modo_fechamento=modo)
    assert db.sqls == []            # recusou ANTES de tocar o banco


# ══════════════════════════════════ leituras ════════════════════════════════

def test_corrida_aberta_e_por_id(mc):
    db = banco()
    c = abre(mc, db)
    assert mc.corrida_aberta(db, "M1")["id"] == c["id"]
    assert mc.corrida_aberta(db, "M2") is None
    assert mc.corrida(db, c["id"])["malha_name"] == "M1"
    assert mc.corrida(db, 999) is None


def test_corrida_aberta_nao_procura_por_malha_e_data(mc):
    """A releitura é SEMPRE `(malha, fechada_em IS NULL)`: `(malha, data)` é o
    beco de que esta spec inteira sai — duas corridas no mesmo ODATE são
    legítimas. E não se filtra por `status`, que seria uma segunda régua para o
    mesmo fato (o `CK_mexec_coerente` já garante que não discordam)."""
    db = banco()
    mc.corrida_aberta(db, "M1")
    sql = db.sqls[0][0]
    assert "WHERE malha_name = ? AND fechada_em IS NULL" in sql
    assert "data_referencia = ?" not in sql
    assert "status =" not in sql


def test_corrida_fechada_some_da_leitura_de_aberta(mc):
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    assert mc.corrida_aberta(db, "M1") is None
    assert mc.corrida(db, c["id"])["status"] == "FALHA"   # o registro fica


def test_corridas_abertas_e_uma_consulta_para_o_ciclo_inteiro(mc):
    db = banco()
    abre(mc, db, malha="M1")
    abre(mc, db, malha="M2")
    db.sqls.clear()
    todas = mc.corridas_abertas(db)
    assert [c["malha_name"] for c in todas] == ["M1", "M2"]
    assert len(db.sqls) == 1


def test_pipeline_membro_de_duas_malhas_com_o_mesmo_odate(mc):
    """Duas corridas com o MESMO ODATE não são ambiguidade nenhuma — a resposta
    é a mesma data."""
    db = banco()
    abre(mc, db, malha="M1", odate=ODATE)
    abre(mc, db, malha="M2", odate=ODATE)
    r = mc.corrida_aberta_do_pipeline(db, "PIPE_B")
    assert len(r["corridas"]) == 2
    assert r["odate"] == ODATE and r["ambiguo"] is False


def test_odate_ambiguo_nunca_e_resolvido_por_escolha(mc, capsys):
    """Decisão 34: escolher uma das duas datas seria reintroduzir a doença com
    rótulo novo. `odate=None` + `ambiguo=True`, e o chamador pula com motivo."""
    db = banco()
    abre(mc, db, malha="M1", odate=ODATE)
    abre(mc, db, malha="M2", odate=ODATE_ONTEM)
    r = mc.corrida_aberta_do_pipeline(db, "PIPE_B")
    assert r["odate"] is None and r["ambiguo"] is True
    assert len(r["corridas"]) == 2
    assert "ambiguo" in capsys.readouterr().out


def test_pipeline_sem_corrida_aberta_nao_e_ambiguo(mc):
    r = mc.corrida_aberta_do_pipeline(banco(), "PIPE_B")
    assert r == {"corridas": [], "odate": None, "ambiguo": False}


def test_pipeline_fora_da_malha_da_corrida_nao_pega_carona(mc):
    db = banco()
    abre(mc, db, malha="M1")
    assert mc.corrida_aberta_do_pipeline(db, "PIPE_D")["corridas"] == []


# ═════════════════════════════════ snapshot ═════════════════════════════════

def test_snapshot_congela_o_denominador(mc):
    """Sem nó Fim (`conta_para_fim=None`) TODOS contam, e `eh_raiz` sai de
    `etl_pipeline_dependencia ∩ etl_malha_pipeline` — só PIPE_A não tem
    predecessor DENTRO da malha."""
    db = banco()
    c = abre(mc, db)
    assert mc.congelar_snapshot(db, c["id"], "M1") == 3
    ms = {m["pipeline"]: m for m in mc.membros(db, c["id"])}
    assert set(ms) == {"PIPE_A", "PIPE_B", "PIPE_C"}
    assert all(m["conta_para_fim"] for m in ms.values())
    assert all(m["ativo_na_abertura"] for m in ms.values())
    assert ms["PIPE_A"]["eh_raiz"] is True
    assert ms["PIPE_B"]["eh_raiz"] is False and ms["PIPE_C"]["eh_raiz"] is False


def test_raiz_e_por_predecessor_DENTRO_da_malha(mc):
    """"Raiz" é relativo à MALHA, não ao grafo inteiro: em M2, PIPE_B é raiz
    porque seu único predecessor (PIPE_A) não é membro de M2 — embora em M1 ele
    seja um nó do meio. Sem esse recorte, a porta implícita abriria a corrida a
    partir do MEIO da cadeia, com `aberta_em` depois de metade dos membros já
    ter concluído: essas linhas virariam "pendentes" e a corrida iria a FALHA
    numa malha que rodou perfeitamente."""
    db = banco()
    c = abre(mc, db, malha="M2")
    mc.congelar_snapshot(db, c["id"], "M2")
    ms = {m["pipeline"]: m for m in mc.membros(db, c["id"])}
    assert ms["PIPE_B"]["eh_raiz"] is True      # PIPE_A não é membro de M2
    assert ms["PIPE_D"]["eh_raiz"] is False     # depende de PIPE_B, que é membro


def test_snapshot_com_no_fim_marca_so_o_upstream(mc):
    db = banco()
    c = abre(mc, db, modo_fechamento="fim")
    mc.congelar_snapshot(db, c["id"], "M1", conta_para_fim=["PIPE_A", "PIPE_B"])
    ms = {m["pipeline"]: m for m in mc.membros(db, c["id"])}
    assert ms["PIPE_A"]["conta_para_fim"] and ms["PIPE_B"]["conta_para_fim"]
    assert ms["PIPE_C"]["conta_para_fim"] is False


def test_fim_que_nao_alcanca_ninguem_nao_e_erro(mc):
    """Conjunto VAZIO é diferente de `None`: há um Fim e ele não alcança
    ninguém. Os membros entram com `conta_para_fim=0` e o painel os lista
    nominalmente, em vez de a corrida fechar com membros vivos."""
    db = banco()
    c = abre(mc, db, modo_fechamento="fim")
    assert mc.congelar_snapshot(db, c["id"], "M1", conta_para_fim=[]) == 3
    assert not any(m["conta_para_fim"] for m in mc.membros(db, c["id"]))


def test_membro_inativo_sai_do_denominador_mas_nao_some(mc):
    db = banco(pipelines={"PIPE_A": True, "PIPE_B": False, "PIPE_C": True})
    c = abre(mc, db)
    mc.congelar_snapshot(db, c["id"], "M1")
    ms = {m["pipeline"]: m for m in mc.membros(db, c["id"])}
    assert len(ms) == 3
    assert ms["PIPE_B"]["ativo_na_abertura"] is False


def test_membro_fora_do_cadastro_entra_inativo(mc):
    """O LEFT JOIN é deliberado: pipeline apagado do cadastro mas ainda em
    `etl_malha_pipeline` entra como inativo — não derruba o snapshot inteiro."""
    db = banco(pipelines={"PIPE_A": True, "PIPE_C": True})
    c = abre(mc, db)
    assert mc.congelar_snapshot(db, c["id"], "M1") == 3
    ms = {m["pipeline"]: m for m in mc.membros(db, c["id"])}
    assert ms["PIPE_B"]["ativo_na_abertura"] is False


def test_snapshot_e_idempotente(mc):
    """A abertura pode ter ADERIDO a uma corrida que já congelou; uma violação
    de PK aqui rolaria de volta a transação do chamador — inclusive o INSERT da
    corrida."""
    db = banco()
    c = abre(mc, db)
    assert mc.congelar_snapshot(db, c["id"], "M1") == 3
    assert mc.congelar_snapshot(db, c["id"], "M1") == 0
    assert len(mc.membros(db, c["id"])) == 3


def test_snapshot_de_malha_sem_membros_grava_zero(mc):
    """Zero não é erro aqui — é o denominador zero que a §6.5 leva a ABORTADA
    depois da carência, e quem decide isso é a guardiã, não este módulo."""
    db = banco(malha_pipeline={"M1": []})
    c = abre(mc, db)
    assert mc.congelar_snapshot(db, c["id"], "M1") == 0


def test_membros_de_corrida_sem_snapshot_e_lista_vazia(mc):
    assert mc.membros(banco(), 42) == []


# ════════════════════════════════ vínculo ═══════════════════════════════════

def _execucao(pipe="PIPE_A", dref=ODATE, exec_id="run_1", corrida=None):
    return {"pipeline_name": pipe, "data_referencia": dref,
            "execution_id": exec_id, "malha_execucao_id": corrida}


def test_vinculo_carimba_a_proveniencia(mc):
    db = banco(execucoes=[_execucao()])
    c = abre(mc, db)
    assert mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", c["id"]) is True
    assert db.execucoes[0]["malha_execucao_id"] == c["id"]


def test_vinculo_e_WRITE_ONCE(mc):
    """Decisão 9 — o `UPDATE` de `_registrar_execucao` roda a cada estado e o
    Clear do rerun REUSA o mesmo `run_id`. Sem a guarda, uma linha da corrida
    #12 reexecutada no dia seguinte passaria a pertencer à #13: o passado
    reescrito."""
    db = banco(execucoes=[_execucao()])
    primeira = abre(mc, db)
    mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", primeira["id"])
    mc.fechar_corrida(db, primeira["id"], "CONCLUIDA", "guardia")
    segunda = abre(mc, db)
    assert mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", segunda["id"]) is False
    assert db.execucoes[0]["malha_execucao_id"] == primeira["id"]


def test_vinculo_da_write_once_pelo_WHERE_para_o_rowcount_dizer_a_verdade(mc):
    db = banco(execucoes=[_execucao()])
    mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", 7)
    sql = db.sqls[-1][0]
    assert sql.endswith("AND malha_execucao_id IS NULL")
    assert "COALESCE" not in sql        # aqui o WHERE responde "carimbei"/"já tinha dono"


def test_vinculo_de_linha_inexistente_nao_e_erro(mc):
    db = banco(execucoes=[])
    assert mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", 1) is False


def test_vinculo_nao_alcanca_outra_data_nem_outro_run(mc):
    db = banco(execucoes=[_execucao()])
    assert mc.vincular_execucao(db, "PIPE_A", ODATE_ONTEM, "run_1", 1) is False
    assert mc.vincular_execucao(db, "PIPE_A", ODATE, "run_2", 1) is False
    assert db.execucoes[0]["malha_execucao_id"] is None


# ════════════════════════════ fechamento e reabertura ═══════════════════════

@pytest.mark.parametrize("desfecho", ["CONCLUIDA", "FALHA", "SEM_TRABALHO",
                                      "EXPIRADA", "ABORTADA", "CANCELADA"])
def test_fecha_com_cada_desfecho(mc, desfecho):
    db = banco()
    c = abre(mc, db)
    assert mc.fechar_corrida(db, c["id"], desfecho, "guardia") is True
    fechada = mc.corrida(db, c["id"])
    assert fechada["status"] == desfecho
    assert fechada["fechada_em"] == AGORA_BANCO      # relógio do banco
    assert fechada["fechada_por"] == "guardia"


def test_o_rowcount_e_o_arbitro_do_fechamento(mc):
    """Decisão 8 — duas pontas não fecham a mesma corrida com desfechos
    diferentes. O segundo fechamento devolve False (não é erro: é "outra ponta
    chegou primeiro") e NÃO reescreve o desfecho."""
    db = banco()
    c = abre(mc, db)
    assert mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia") is True
    assert mc.fechar_corrida(db, c["id"], "FALHA", "manual:C123456") is False
    assert mc.corrida(db, c["id"])["status"] == "CONCLUIDA"


def test_fechar_corrida_inexistente_e_False_sem_estouro(mc):
    assert mc.fechar_corrida(banco(), 999, "CONCLUIDA", "guardia") is False


def test_motivo_ACUMULA_em_vez_de_sobrescrever(mc):
    """Sobrescrever apagaria justamente o `DATA_DIVERGENTE` gravado na
    abertura."""
    db = banco()
    c = abre(mc, db, motivo="DATA_DIVERGENTE")
    mc.fechar_corrida(db, c["id"], "EXPIRADA", "guardia", motivo="teto de 24h")
    assert mc.corrida(db, c["id"])["motivo"] == "DATA_DIVERGENTE | teto de 24h"


def test_fechar_sem_motivo_preserva_o_que_havia(mc):
    db = banco()
    c = abre(mc, db, motivo="DATA_DIVERGENTE")
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    assert mc.corrida(db, c["id"])["motivo"] == "DATA_DIVERGENTE"


@pytest.mark.parametrize("invalido", ["ABERTA", "TERMINADA", "concluida", ""])
def test_desfecho_invalido_e_erro_de_programa(mc, invalido):
    """`ABERTA` aqui seria o `CK_mexec_coerente` (status aberto com `fechada_em`
    preenchida) estourando dentro da transação do chamador."""
    db = banco()
    c = abre(mc, db)
    db.sqls.clear()
    with pytest.raises(ValueError):
        mc.fechar_corrida(db, c["id"], invalido, "guardia")
    assert db.sqls == []


@pytest.mark.parametrize("desfecho", ["CONCLUIDA", "FALHA"])
def test_reabre_o_que_pode_voltar(mc, desfecho):
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], desfecho, "guardia")
    assert mc.reabrir_corrida(db, c["id"], "manual:C123456", "rerun") is True
    reaberta = mc.corrida(db, c["id"])
    assert reaberta["status"] == "ABERTA" and reaberta["fechada_em"] is None
    assert reaberta["fechada_por"] is None
    assert reaberta["tentativas"] == 2
    assert reaberta["reaberta_em"] == AGORA_BANCO
    assert reaberta["reaberta_por"] == "manual:C123456"
    # F8: o `motivo` guarda o desfecho ANULADO e a hora dele — é onde a história
    # do ciclo passa a morar depois que os eventos da tentativa 1 são
    # descartados. Sem esta linha, "concluiu 05:12 e foi reprocessada" viraria
    # um fato sem registro em lugar nenhum.
    assert reaberta["motivo"] == (
        f"reaberta apos {desfecho} de 2026-08-05 01:30:00: rerun")


@pytest.mark.parametrize("desfecho", ["SEM_TRABALHO", "EXPIRADA", "ABORTADA",
                                      "CANCELADA"])
def test_fim_de_linha_nao_reabre(mc, desfecho):
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], desfecho, "guardia")
    assert mc.reabrir_corrida(db, c["id"], "manual:C123456") is False
    assert mc.corrida(db, c["id"])["status"] == desfecho


def test_nao_reabre_com_outra_corrida_ABERTA_da_malha(mc):
    """§6.9/#3 — a guarda mora DENTRO do UPDATE: a reabertura roda na transação
    do rerun, e um 2601 ali dentro rolaria o rerun inteiro de volta. Com a
    condição no WHERE, o pior caso é `rowcount = 0`, que é resposta."""
    db = banco()
    velha = abre(mc, db)
    mc.fechar_corrida(db, velha["id"], "CONCLUIDA", "guardia")
    nova = abre(mc, db)
    assert mc.reabrir_corrida(db, velha["id"], "manual:C123456") is False
    assert mc.corrida(db, velha["id"])["status"] == "CONCLUIDA"
    assert mc.corrida_aberta(db, "M1")["id"] == nova["id"]
    assert len(db.abertas("M1")) == 1      # a invariante do modelo, preservada


def test_reabrir_nunca_produz_duas_abertas(mc):
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    assert mc.reabrir_corrida(db, c["id"], "op") is True
    assert mc.reabrir_corrida(db, c["id"], "op") is False   # já está aberta
    assert len(db.abertas("M1")) == 1
    assert mc.corrida(db, c["id"])["tentativas"] == 2


# ══════════════ F8 — o que a reabertura precisa desfazer ════════════════════

def _evento(tipo, corrida, pipeline=None, data=ODATE):
    return {"pipeline_name": pipeline or f"#corrida:{corrida}",
            "data_referencia": data, "tipo": tipo,
            "malha_execucao_id": corrida}


def test_reabertura_zera_a_memoria_para_a_tentativa_2_poder_alertar(mc):
    """Sem isto, a corrida reabre, falha de novo e fica MUDA: `falha_vista_em`
    é a memória que impede o mesmo card 200 vezes no dia (Decisão 12) — e essa
    memória é da TENTATIVA, não da linha. É o mesmo raciocínio que já fez
    `creditar_hold` zerar `atraso_visto_em` ao empurrar o teto."""
    db = banco()
    c = abre(mc, db)
    assert mc.marcar_visto(db, c["id"], "falha") is True
    assert mc.marcar_visto(db, c["id"], "atraso") is True
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    assert mc.reabrir_corrida(db, c["id"], "manual:C1", "rerun") is True

    reaberta = mc.corrida(db, c["id"])
    assert reaberta["falha_vista_em"] is None
    assert reaberta["atraso_visto_em"] is None
    # e a prova de que zerar SERVE para alguma coisa: a tentativa 2 alerta.
    assert mc.marcar_visto(db, c["id"], "falha") is True


def test_reabertura_descarta_o_desfecho_para_a_2a_CONCLUIDA_poder_existir(mc):
    """O ganho da fase, e o que hoje some em silêncio (§10/F8).

    A corrida reaberta guarda o MESMO `id`, então a chave de
    `ux_dep_evento_corrida` (marcador, data, tipo, corrida) da tentativa 2 é
    byte a byte a da tentativa 1: o `INSERT ... WHERE NOT EXISTS` de
    `gravar_evento` engoliria a segunda `MALHA_CONCLUIDA` do dia. O operador
    que mandou reprocessar não receberia card nenhum e o painel continuaria
    marcando a hora do ciclo que ele acabou de anular."""
    db = banco(eventos=[_evento("MALHA_CONCLUIDA", 1),
                        _evento("MALHA_FALHOU", 1),
                        _evento("MALHA_ATRASADA", 1)])
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    assert mc.reabrir_corrida(db, c["id"], "manual:C1") is True
    assert db.eventos == []
    # A história não se perde: ela migra para a casa certa, que é a corrida.
    assert "reaberta apos CONCLUIDA de" in mc.corrida(db, c["id"])["motivo"]


def test_o_descarte_nao_alcanca_evento_de_MEMBRO_nem_de_outra_corrida(mc):
    """O DELETE é por corrida, por tipo e só em linha de MARCADOR. O evento de
    um pipeline (`EXECUCAO_ORFA` de CARGA_A) fala do pipeline, não do ciclo —
    apagá-lo seria perder histórico de verdade, e é o que o `LEFT(...)` do
    statement impede."""
    db = banco(eventos=[
        _evento("MALHA_CONCLUIDA", 1),                       # sai
        _evento("MALHA_CONCLUIDA", 1, pipeline="#no:38"),    # sai (nó Fim)
        _evento("MALHA_CONCLUIDA", 2),                       # outra corrida
        _evento("MALHA_CANCELADA", 1),                       # não é desfecho anulável
        _evento("EXECUCAO_ORFA", 1, pipeline="CARGA_A"),     # é do MEMBRO
    ])
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    mc.reabrir_corrida(db, c["id"], "op")
    restaram = sorted((e["pipeline_name"], e["tipo"]) for e in db.eventos)
    assert restaram == [("#corrida:1", "MALHA_CANCELADA"),
                        ("#corrida:2", "MALHA_CONCLUIDA"),
                        ("CARGA_A", "EXECUCAO_ORFA")]


def test_reabertura_que_NAO_acontece_nao_descarta_evento_nenhum(mc):
    """Fim de linha não volta — e não pode limpar a fila de alerta de um ciclo
    que ninguém reabriu. O descarte é consequência da reabertura, nunca gesto
    independente."""
    db = banco(eventos=[_evento("MALHA_CONCLUIDA", 1)])
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "EXPIRADA", "guardia")
    assert mc.reabrir_corrida(db, c["id"], "op") is False
    assert len(db.eventos) == 1


def test_descarte_indisponivel_nao_derruba_a_reabertura(mc):
    """Banco sem a coluna da 085 no evento: não havia chave estendida para
    liberar. Derrubar aqui trocaria um card perdido por um REPROCESSO perdido —
    e o reprocesso é o gesto que o operador mandou fazer."""
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")

    class _CurQueQuebraNoDelete(type(db.cursor())):
        def execute(self, sql, params=()):
            if str(sql).lstrip().startswith("DELETE"):
                raise RuntimeError("Invalid column name 'malha_execucao_id'.")
            return super().execute(sql, params)

    db.cursor = lambda: _CurQueQuebraNoDelete(db)   # noqa: E731
    assert mc.reabrir_corrida(db, c["id"], "op") is True
    assert mc.corrida(db, c["id"])["status"] == "ABERTA"


# ═══════════ F8 — de que ciclo era a linha que o rerun aposentou ════════════

def test_corridas_das_linhas_responde_pelo_VINCULO_da_linha(mc):
    """A pergunta do rerun. A resposta sai do `malha_execucao_id` da linha, e
    não de `corrida_da_data(malha, data)`: com duas corridas da mesma malha no
    mesmo dia (§6.9/#7), a segunda devolveria a MAIS RECENTE, e o rerun de um
    membro da primeira reabriria a errada."""
    db = banco(execucoes=[_execucao("PIPE_A", ODATE, "run_1", corrida=1),
                          _execucao("PIPE_B", ODATE, "run_2", corrida=2),
                          _execucao("PIPE_C", ODATE, "run_3", corrida=None)])
    primeira = abre(mc, db)
    mc.fechar_corrida(db, primeira["id"], "CONCLUIDA", "guardia")
    segunda = abre(mc, db)

    achadas = mc.corridas_das_linhas(db, ["PIPE_A"], ODATE)
    assert [c["id"] for c in achadas] == [primeira["id"]]
    achadas2 = mc.corridas_das_linhas(db, ["PIPE_A", "PIPE_B"], ODATE)
    assert [c["id"] for c in achadas2] == [primeira["id"], segunda["id"]]
    # Linha sem vínculo (pipeline fora de malha) não inventa corrida nenhuma —
    # e isso NÃO é erro: é o caso comum do rerun de pipeline avulso.
    assert mc.corridas_das_linhas(db, ["PIPE_C"], ODATE) == []
    assert mc.corridas_das_linhas(db, [], ODATE) == []


def test_corridas_das_linhas_nao_atravessa_o_ODATE(mc):
    """O reprocesso do dia 03 não pode reabrir o ciclo do dia 04 — é a mesma
    exigência de ODATE da Decisão 23, na porta do rerun."""
    db = banco(execucoes=[_execucao("PIPE_A", ODATE, "run_1", corrida=1)])
    abre(mc, db)
    assert mc.corridas_das_linhas(db, ["PIPE_A"], ODATE_ONTEM) == []


def test_corridas_das_linhas_degrada_larga(mc):
    """Leitura indisponível devolve `[]` e o rerun segue sem tocar em corrida
    nenhuma. O reprocesso do operador nunca cai porque a malha não pôde ser
    consultada."""
    assert mc.corridas_das_linhas(banco(explodir=True), ["PIPE_A"], ODATE) == []


# ═════════════════════ memória de efeito colateral ══════════════════════════

@pytest.mark.parametrize("o_que,coluna", [("falha", "falha_vista_em"),
                                          ("atraso", "atraso_visto_em")])
def test_marcar_visto_e_verdadeiro_uma_vez_so(mc, o_que, coluna):
    """O `rowcount` é o árbitro do "primeira vez", em UMA operação:
    ler-e-decidir deixaria a janela que dois workers da guardiã encontram — e o
    resultado seria o mesmo card 200 vezes num dia."""
    db = banco()
    c = abre(mc, db)
    assert mc.marcar_visto(db, c["id"], o_que) is True
    assert mc.marcar_visto(db, c["id"], o_que) is False
    assert mc.corrida(db, c["id"])[coluna] == AGORA_BANCO


def test_marcador_nao_carimba_corrida_fechada(mc):
    db = banco()
    c = abre(mc, db)
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    assert mc.marcar_visto(db, c["id"], "falha") is False


def test_marcador_invalido_e_erro_de_programa(mc):
    with pytest.raises(ValueError):
        mc.marcar_visto(banco(), 1, "cancelamento")


# ═════════════ degradação: sem a 085, NADA estoura (invariante §16/10) ══════

@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_sem_a_085_nenhuma_leitura_estoura(mc, driver, capsys):
    """Leitura degrada LARGA: a tela volta ao comportamento de hoje e o motor
    não muda de comportamento em ponto nenhum."""
    db = banco(com_085=False, driver=driver, config={})
    assert mc.tabela_085_presente(db) is False
    assert mc.corrida_ativa(db) is False
    assert mc.corrida_aberta(db, "M1") is None
    assert mc.corridas_abertas(db) == []
    assert mc.corrida(db, 1) is None
    assert mc.membros(db, 1) == []
    assert mc.corrida_aberta_do_pipeline(db, "PIPE_B") == {
        "corridas": [], "odate": None, "ambiguo": False}
    assert mc.teto_horas_da_malha(db, "M1") == 24
    assert mc.quiescencia_minutos(db) == 15
    assert mc.carencia_partida_min(db) == 15
    assert capsys.readouterr().out.count(mc.LOG) >= 4


@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_sem_a_085_nenhuma_escrita_estoura(mc, driver, capsys):
    """Escrita degrada ESTREITA — mas 207/208 nomeando objeto da 085 é
    exatamente o caso que degrada: deploy parcial (a célula MAIS provável da
    matriz do §11.1, porque `api/` é automático e `dags/` é padrão-NÃO)."""
    db = banco(com_085=False, driver=driver, config={})
    assert mc.abrir_corrida(db, "M1", ODATE, "manual") is None
    assert mc.congelar_snapshot(db, 1, "M1") is None
    assert mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", 1) is False
    assert mc.fechar_corrida(db, 1, "CONCLUIDA", "guardia") is False
    assert mc.reabrir_corrida(db, 1, "op") is False
    assert mc.marcar_visto(db, 1, "falha") is False
    assert "085 ausente" in capsys.readouterr().out


@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_sem_085_reconhece_as_duas_formas_de_erro_do_driver(mc, driver):
    """pymssql entrega `args[0]` inteiro, pyodbc põe `(208)` no texto — e nada
    disso depende do IDIOMA do SQL Server, porque o que se lê é o NÚMERO."""
    assert mc._sem_085(erro_objeto_ausente("dbo.etl_malha_execucao", driver))
    assert mc._sem_085(erro_coluna_ausente("malha_execucao_id", driver))


@pytest.mark.parametrize("driver", ["pymssql", "pyodbc"])
def test_erro_que_NAO_e_ausencia_da_085_nao_e_confundido(mc, driver):
    """O atalho "a mensagem cita a tabela" daria falso positivo caro: a violação
    de FK, o 2601 e o truncamento TAMBÉM citam `etl_malha_execucao`, e os três
    são bug do chamador que precisa SUBIR."""
    assert mc._sem_085(erro_fk_membro(driver)) is False
    assert mc._sem_085(erro_duplicata("ux_malha_exec_aberta", driver)) is False
    assert mc._sem_085(erro(2628, "String or binary data would be truncated in "
                                  "table 'dbo.etl_malha_execucao', column "
                                  "'motivo'.", driver)) is False
    assert mc._sem_085(erro(207, "Invalid column name 'outra_coisa'.",
                            driver)) is False     # 207 sem marca da 085
    assert mc._sem_085(RuntimeError("timeout")) is False


def test_escrita_NAO_engole_erro_de_verdade(mc):
    """A outra metade da política: engolir deadlock/timeout/FK devolvendo "não
    abriu" faria o chamador seguir achando que não há corrida — a classe de
    defeito que o `ERRO_CONSULTA` de utils/dependencias.py existe para evitar."""
    db = banco()
    c = abre(mc, db)
    with pytest.raises(ErroDriver):                     # FK: corrida inexistente
        mc.congelar_snapshot(db, c["id"] + 99, "M1")
    for chamada in (
            lambda: mc.abrir_corrida(banco(explodir=True), "M1", ODATE, "manual"),
            lambda: mc.congelar_snapshot(banco(explodir=True), 1, "M1"),
            lambda: mc.vincular_execucao(banco(explodir=True), "P", ODATE, "r", 1),
            lambda: mc.fechar_corrida(banco(explodir=True), 1, "CONCLUIDA", "g"),
            lambda: mc.reabrir_corrida(banco(explodir=True), 1, "op"),
            lambda: mc.marcar_visto(banco(explodir=True), 1, "falha")):
        with pytest.raises(RuntimeError):
            chamada()


def test_leitura_com_banco_fora_do_ar_nao_estoura(mc):
    db = banco(explodir=True)
    assert mc.corrida_aberta(db, "M1") is None
    assert mc.corridas_abertas(db) == []
    assert mc.corrida(db, 1) is None
    assert mc.membros(db, 1) == []
    assert mc.corrida_aberta_do_pipeline(db, "PIPE_B")["corridas"] == []


# ═══════════════════ invariantes estruturais (testes de AUSÊNCIA) ═══════════

def test_nenhuma_funcao_commita_ou_faz_rollback(mc):
    """Regra do módulo `dags/utils/dependencias.py`: o CHAMADOR é dono da
    transação. Abrir a corrida e congelar o snapshot são UM commit só, e fechar
    commita junto com o evento — nada disso funciona se o módulo commitar por
    conta."""
    db = banco(execucoes=[_execucao()])
    c = abre(mc, db)
    mc.congelar_snapshot(db, c["id"], "M1")
    mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", c["id"])
    mc.marcar_visto(db, c["id"], "falha")
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    mc.reabrir_corrida(db, c["id"], "op")
    assert (db.commits, db.rollbacks, db.closes) == (0, 0, 0)


def test_o_modulo_nao_sabe_fazer_conta_de_tempo():
    """Decisão 10, provada por AUSÊNCIA: sem `datetime` importado, o módulo é
    incapaz de somar teto em Python. No dev o banco está 3h à frente — teto de
    24h viraria 27h, e `teto_em += (agora − retido_desde)` nasceria negativo, de
    modo que soltar um hold de 1h EXPIRARIA a corrida na hora."""
    fonte = _FONTE_DAGS.read_text(encoding="utf-8")
    assert "import datetime" not in fonte
    assert "from datetime import" not in fonte


def test_todo_carimbo_de_tempo_sai_do_banco(mc):
    """O outro lado da mesma decisão: os relógios que o módulo escreve são
    `SYSDATETIME()`/`DATEADD`, nunca parâmetro calculado."""
    db = banco(execucoes=[_execucao()])
    c = abre(mc, db)
    mc.marcar_visto(db, c["id"], "falha")
    mc.marcar_visto(db, c["id"], "atraso")
    mc.fechar_corrida(db, c["id"], "FALHA", "guardia")
    mc.reabrir_corrida(db, c["id"], "op")
    escritas = [s for s, _ in db.sqls
                if s.startswith(("INSERT INTO dbo.etl_malha_execucao ",
                                 "UPDATE dbo.etl_malha_execucao",
                                 "UPDATE me SET"))]
    assert escritas
    for sql in escritas:
        assert "SYSDATETIME()" in sql, sql


def test_toda_transicao_tem_estado_esperado_no_WHERE(mc):
    """Decisão 8 — `rowcount` só pode ser árbitro se o `WHERE` disser qual
    estado se esperava encontrar."""
    assert "WHERE id = %s AND fechada_em IS NULL" in mc.SQL_FECHAR
    assert "me.status IN (" in mc.SQL_REABRIR and "NOT EXISTS" in mc.SQL_REABRIR
    assert mc.SQL_VINCULAR.endswith("AND malha_execucao_id IS NULL")
    for sql in mc._SQL_VISTO.values():
        assert "AND fechada_em IS NULL AND" in sql


def test_o_modulo_NAO_inventa_verde(mc):
    """Invariante §16/4, em forma de ausência: nada aqui emite evento. "Não
    inventar verde" é do chamador, e a corrida fecha junto com o evento no mesmo
    commit (Decisão 20) — se este módulo escrevesse o evento sozinho, a ordem
    voltaria a ser a que perdia o card para sempre."""
    db = banco(execucoes=[_execucao()])
    c = abre(mc, db)
    mc.congelar_snapshot(db, c["id"], "M1")
    mc.vincular_execucao(db, "PIPE_A", ODATE, "run_1", c["id"])
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    tudo = " ".join(s for s, _ in db.sqls)
    assert "etl_dependencia_evento" not in tudo
    assert "MALHA_CONCLUIDA" not in tudo
    fonte = _FONTE_DAGS.read_text(encoding="utf-8")
    assert "INSERT INTO dbo.etl_dependencia_evento" not in fonte


def test_os_consumidores_em_dags_sao_a_guardia_e_o_fonte_gerado():
    """A F2 trouxe o primeiro consumidor (a guardiã); a F5 trouxe o segundo, e
    ele é o FONTE GERADO — a fase que custa `force_all` num deploy inteiro.

    A diferença é sutil e é o ponto: `etl_dag_factory.py` **emite** o import
    dentro do texto da DAG; o processo da factory continua sem importar a
    corrida. Por isso ele sai da lista do AST (a DAG gerada é que importa) e
    ganha as duas asserções de EMISSÃO abaixo — inclusive a da marca sintática
    que a sonda do §12.2 procura no fonte publicado.

    A lista de fora continua valendo, e por motivos diferentes em cada linha:

      • `utils/dependencias.py` é o módulo que TODA porta do motor carrega:
        acoplá-lo à corrida faria um erro de import na corrida derrubar o push
        de dependências do banco inteiro;
      • `utils/malha_ciclo.py` e `utils/malha_nos.py` são as autoridades que a
        corrida CONSOME (virada e expansão do desenho). O sentido da seta é
        parte do desenho: invertê-la cria o ciclo de import.
    """
    guardia = (_ROOT / "dags/etl_dependencia_guardia.py").read_text(encoding="utf-8")
    assert "from utils import malha_corrida as mc" in guardia
    assert "_abrir_corridas_malha" in guardia and "_fechar_corridas_malha" in guardia
    factory = (_ROOT / "dags/etl_dag_factory.py").read_text(encoding="utf-8")
    assert '"    from utils import malha_corrida as _corrida",' in factory
    assert "_corrida.odate(" in factory     # a marca sintática do §12.2
    fora = [
        "dags/utils/dependencias.py",
        "dags/utils/malha_ciclo.py", "dags/utils/malha_nos.py",
    ]   # o lado da API é varrido inteiro em test_malha_corrida_paridade.py
    # Por AST e não por substring: `dependencias.py` CITA o módulo num
    # comentário que explica justamente por que não o importa, e um `in` cru
    # transformaria a explicação correta em falha de teste. O que a invariante
    # proíbe é a DEPENDÊNCIA, não a menção.
    for rel in fora:
        caminho = _ROOT / rel
        if not caminho.exists():
            continue
        for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                assert all("malha_corrida" not in a.name for a in no.names), rel
            elif isinstance(no, ast.ImportFrom):
                alvo = (no.module or "") + "." + ".".join(a.name for a in no.names)
                assert "malha_corrida" not in alvo, rel


# ═════════════ o ODATE do §7 — a precedência dos degraus (F5) ═══════════════
#
# O que estes testes guardam não é "a data saiu certa": é QUAL degrau respondeu.
# A data pode sair certa pelo motivo errado (foi o cálculo, e não a corrida) e o
# incidente `Carga_Vida` voltaria no primeiro dia em que os dois discordassem.

def _linha(pipe="PIPE_A", dref=ODATE, exec_id="run_1", corrida=None, ident=1):
    return {"pipeline_name": pipe, "data_referencia": dref,
            "execution_id": exec_id, "malha_execucao_id": corrida, "id": ident}


def test_degrau_0_o_carimbo_do_run_manda_em_todos_os_outros(mc):
    """O run tem UM ODATE, e quem o decidiu foi a primeira chamada.

    É a Decisão 36 atravessando TASKS: o `check_agenda` gravou a linha às 01:10
    e o `_registrar_sucesso` das 04:52 é outro processo. Aqui a corrida está
    aberta em `ODATE` e a linha carimbou `ODATE_ONTEM` — se o degrau 3 vencesse,
    o UPDATE de fechamento erraria a chave e nasceria uma SEGUNDA linha do mesmo
    run em outro dia."""
    db = banco(execucoes=[_linha(dref=ODATE_ONTEM, corrida=7)])
    abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", run_id="run_1")
    assert r["data"] == ODATE_ONTEM
    assert r["corrida_id"] == 7
    assert r["degrau"] == mc.DEGRAU_CARIMBO


def test_degrau_0_ignora_run_de_outro_pipeline(mc):
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE_ONTEM)])
    c = abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", run_id="run_1")
    assert r["degrau"] == mc.DEGRAU_CORRIDA and r["data"] == ODATE
    assert r["corrida_id"] == c["id"]


def test_degrau_1_conf_com_corrida_aberta_da_malha_do_pipeline(mc):
    db = banco()
    c = abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", conf_id=c["id"])
    assert r["data"] == ODATE and r["corrida_id"] == c["id"]
    assert r["degrau"] == mc.DEGRAU_CONF_CORRIDA


def test_degrau_1_conf_de_corrida_FECHADA_e_tratado_como_ausente(mc, capsys):
    """Decisão 37 — o conf é otimização, nunca identidade. Um rerun tardio
    carrega o conf do ciclo de ontem; obedecê-lo carimbaria a linha de hoje com
    o ODATE de um ciclo encerrado."""
    db = banco()
    c = abre(mc, db, odate=ODATE_ONTEM)
    mc.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    r = mc.odate(db, "PIPE_A", conf_id=c["id"])
    assert r["degrau"] is None and r["data"] is None
    assert "tratado como AUSENTE" in capsys.readouterr().out


def test_degrau_1_conf_de_malha_que_nao_contem_o_pipeline_e_ausente(mc):
    """`POST /airflow/dags/{id}/dagRuns` repassa o conf CRU: sem o JOIN por
    `etl_malha_pipeline`, qualquer id arbitrário ditaria o ODATE por HTTP."""
    db = banco()
    c = abre(mc, db, malha="M2", odate=ODATE_ONTEM)     # M2 não tem PIPE_A
    r = mc.odate(db, "PIPE_A", conf_id=c["id"])
    assert r["degrau"] is None and r["corrida_id"] is None


def test_degrau_1_conf_invalido_nao_levanta(mc):
    db = banco()
    abre(mc, db)
    assert mc.odate(db, "PIPE_A", conf_id="nao-e-numero")["degrau"] == mc.DEGRAU_CORRIDA


def test_degrau_2_a_heranca_vence_a_corrida_aberta(mc, capsys):
    """Quem recebeu data explícita já teve o ODATE decidido por quem disparou
    (rerun, disparo manual com data, push de fora da malha). Re-decidir aqui
    reabriria a porta que a herança fechou — e a divergência vira LOG, não
    recusa."""
    db = banco()
    abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", herdada=ODATE_ONTEM)
    assert r["data"] == ODATE_ONTEM and r["degrau"] == mc.DEGRAU_CONF_DATA
    assert r["corrida_id"] is None            # linha sem proveniência, de propósito
    assert "difere do ODATE" in capsys.readouterr().out


def test_degrau_2_com_a_mesma_data_carimba_a_proveniencia(mc):
    db = banco()
    c = abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", herdada=ODATE)
    assert r["degrau"] == mc.DEGRAU_CONF_DATA and r["corrida_id"] == c["id"]


def test_degrau_3_o_Carga_Vida_invertido(mc):
    """O membro com cron próprio ADERE ao ciclo em voo em vez de calcular a
    própria data (Decisão 33) — e não precisou ser republicado para isso, porque
    quem consulta é a DAG que JÁ foi."""
    db = banco()
    c = abre(mc, db, odate=ODATE_ONTEM)
    r = mc.odate(db, "PIPE_A")
    assert r["data"] == ODATE_ONTEM and r["corrida_id"] == c["id"]
    assert r["degrau"] == mc.DEGRAU_CORRIDA


def test_degrau_3_duas_corridas_com_ODATES_DIFERENTES_e_RECUSA(mc):
    """Decisão 34: nunca escolha. PIPE_B é membro de M1 e M2 — o caso do membro
    compartilhado, que é quase sempre um DEPENDENTE."""
    db = banco()
    abre(mc, db, malha="M1", odate=ODATE)
    abre(mc, db, malha="M2", odate=ODATE_ONTEM)
    r = mc.odate(db, "PIPE_B")
    assert r["ambiguo"] is True
    assert r["data"] is None and r["corrida_id"] is None
    assert mc.MOTIVO_ODATE_AMBIGUO in r["detalhe"]
    # o detalhe NOMEIA as duas corridas: é o que o operador precisa para saber
    # qual encerrar, e é o corpo do card que chega às 3h
    assert str(ODATE) in r["detalhe"] and str(ODATE_ONTEM) in r["detalhe"]


def test_degrau_3_duas_corridas_no_MESMO_odate_nao_sao_ambiguidade(mc, capsys):
    """A resposta é a mesma data — não há o que escolher. O que fica sem dono é
    a PROVENIÊNCIA, e inventá-la seria escolher onde não há motivo (Decisão 2:
    a prova de que o membro concluiu é da LINHA no intervalo)."""
    db = banco()
    abre(mc, db, malha="M1", odate=ODATE)
    abre(mc, db, malha="M2", odate=ODATE)
    r = mc.odate(db, "PIPE_B")
    assert r["ambiguo"] is False and r["data"] == ODATE
    assert r["corrida_id"] is None
    assert "proveniencia sem dono" in capsys.readouterr().out


def test_sem_corrida_aberta_o_modulo_nao_responde_e_o_chamador_calcula(mc):
    db = banco()
    r = mc.odate(db, "PIPE_A")
    assert r == {"data": None, "corrida_id": None, "ambiguo": False,
                 "degrau": None, "detalhe": None}


def test_interruptor_desligado_nao_toca_o_banco(mc):
    """"Sem a 085" e "desligado" são o MESMO caminho (§11.2) — e ele é mudo:
    nenhuma consulta, nenhum degrau, nada para a DAG velha notar."""
    db = banco(config={"malha_corrida_ativa": "0"})
    abre(mc, db, odate=ODATE)
    db.sqls.clear()
    r = mc.odate(db, "PIPE_A", run_id="run_1", conf_id=1, herdada=ODATE_ONTEM)
    assert r["data"] is None and r["degrau"] is None
    assert [s for s, _ in db.sqls if "etl_app_config" not in s] == []


def test_sem_a_085_o_odate_e_mudo(mc):
    db = banco(com_085=False, config={})
    assert mc.odate(db, "PIPE_A", run_id="run_1")["data"] is None


def test_banco_fora_do_ar_nao_levanta(mc):
    """Leitura degrada LARGA: o ODATE volta para o degrau 4 e a carga anda."""
    db = banco(explodir=True)
    assert mc.odate(db, "PIPE_A", run_id="run_1")["data"] is None


def test_degrau_0_sem_dono_ainda_procura_a_proveniencia(mc):
    """⛔ Defeito MEDIDO no dev em 2026-08-05, e corrigido aqui.

    A linha do DEPENDENTE nasce no claim do pai (`reservar_corrida`) já com
    data e run_id, e SEM `malha_execucao_id`. Com o degrau 0 respondendo
    sozinho, o filho herdava a data certa e ficava para sempre sem vínculo —
    mesmo tendo recebido a corrida do pai no conf. Resultado medido: DEV_F10_D
    concluiu em 2026-08-02 com `malha_execucao_id` NULL, isto é, TODA a cascata
    (a maior parte de uma malha) fora do ciclo a que pertence, e o "4 de 7" do
    card contando errado.

    O degrau 0 decide a DATA. A proveniência é procurada enquanto a linha não
    tem dono."""
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE, exec_id="dep_1")])
    c = abre(mc, db, malha="M1", odate=ODATE)
    r = mc.odate(db, "PIPE_B", run_id="dep_1", conf_id=c["id"])
    assert r["degrau"] == mc.DEGRAU_CARIMBO and r["data"] == ODATE
    assert r["corrida_id"] == c["id"]


def test_degrau_0_acha_a_dona_ate_sem_o_conf(mc):
    """O filho de uma DAG antiga (que não repassa a corrida no conf) também
    entra no ciclo: basta haver UMA corrida aberta do MESMO ODATE."""
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE, exec_id="dep_1")])
    c = abre(mc, db, malha="M1", odate=ODATE)
    assert mc.odate(db, "PIPE_B", run_id="dep_1")["corrida_id"] == c["id"]


def test_degrau_0_NAO_carimba_corrida_de_outro_odate(mc):
    """Proveniência é "de onde veio ESTA data". Carimbar a corrida de terça na
    linha de quarta seria a doença desta spec com outro rótulo — e é o que
    aconteceria se a busca ignorasse a data."""
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE, exec_id="dep_1")])
    c = abre(mc, db, malha="M1", odate=ODATE_ONTEM)
    r = mc.odate(db, "PIPE_B", run_id="dep_1", conf_id=c["id"])
    assert r["data"] == ODATE and r["corrida_id"] is None


def test_degrau_0_com_dono_NAO_e_reescrito(mc):
    """WRITE-ONCE também na leitura: linha que já tem dono devolve o dono dela,
    e nenhuma corrida nova a reivindica."""
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE, exec_id="dep_1",
                                 corrida=555)])
    c = abre(mc, db, malha="M1", odate=ODATE)
    assert c["id"] != 555
    assert mc.odate(db, "PIPE_B", run_id="dep_1")["corrida_id"] == 555


def test_degrau_0_com_duas_corridas_do_mesmo_odate_nao_escolhe_dona(mc):
    """PIPE_B é membro de M1 e M2. Duas corridas do MESMO dia não tornam a data
    ambígua, mas a proveniência não tem por que ser inventada."""
    db = banco(execucoes=[_linha(pipe="PIPE_B", dref=ODATE, exec_id="dep_1")])
    abre(mc, db, malha="M1", odate=ODATE)
    abre(mc, db, malha="M2", odate=ODATE)
    r = mc.odate(db, "PIPE_B", run_id="dep_1")
    assert r["data"] == ODATE and r["corrida_id"] is None


def test_degrau_0_com_DUAS_linhas_do_mesmo_run_responde_sempre_a_MAIS_ANTIGA(mc):
    """LOTE, e não "um caso": o degrau 0 é `TOP 1 ... ORDER BY id`, e a ordem
    não é decoração.

    Se a doença já aconteceu — o run existe em dois ODATEs, que é exatamente o
    estrago que a Decisão 36 evita —, a resposta tem de ser SEMPRE a mesma, e
    tem de ser a linha que NASCEU primeiro: é ela a identidade do run. Uma
    resposta que alternasse faria o `UPDATE ... WHERE data_referencia=%s` mudar
    de alvo entre uma task e outra, transformando duas linhas em três."""
    db = banco(execucoes=[
        _linha(pipe="PIPE_A", dref=ODATE_ONTEM, exec_id="run_1", corrida=7,
               ident=10),
        _linha(pipe="PIPE_A", dref=ODATE, exec_id="run_1", corrida=8,
               ident=11)])
    for _ in range(3):
        r = mc.odate(db, "PIPE_A", run_id="run_1")
        assert (r["data"], r["corrida_id"]) == (ODATE_ONTEM, 7)
    # e a mais nova primeiro na lista não muda a resposta: quem ordena é o SQL
    db.execucoes.reverse()
    assert mc.odate(db, "PIPE_A", run_id="run_1")["data"] == ODATE_ONTEM


def test_conf_de_corrida_FECHADA_cai_no_degrau_3_e_o_ciclo_em_voo_resolve(mc):
    """Decisão 37 diz "tratado como AUSENTE" — e ausente significa *o degrau
    seguinte responde*, não *ninguém responde*.

    O caso é o rerun tardio: ele carrega o conf do ciclo de ontem enquanto o de
    hoje está em voo. Obedecer ao conf carimbaria a data de um ciclo encerrado;
    parar aqui devolveria o pipeline ao cálculo próprio, que é o incidente. A
    resposta certa é a corrida ABERTA."""
    db = banco()
    velha = abre(mc, db, odate=ODATE_ONTEM)
    mc.fechar_corrida(db, velha["id"], "CONCLUIDA", "guardia")
    hoje = abre(mc, db, odate=ODATE)
    r = mc.odate(db, "PIPE_A", conf_id=velha["id"])
    assert r["degrau"] == mc.DEGRAU_CORRIDA
    assert r["data"] == ODATE and r["corrida_id"] == hoje["id"]


def test_conf_de_MALHA_QUE_NAO_CONTEM_o_pipeline_cai_no_degrau_3(mc):
    """A outra metade da validação do §7/degrau 1, com o degrau seguinte
    respondendo: `POST /airflow/dags/{id}/dagRuns` repassa o conf CRU, então um
    id de corrida de outra malha não pode ditar o ODATE — nem paralisar o
    pipeline."""
    db = banco()
    outra = abre(mc, db, malha="M2", odate=ODATE_ONTEM)   # M2 não tem PIPE_A
    minha = abre(mc, db, malha="M1", odate=ODATE)
    r = mc.odate(db, "PIPE_A", conf_id=outra["id"])
    assert r["degrau"] == mc.DEGRAU_CORRIDA
    assert r["data"] == ODATE and r["corrida_id"] == minha["id"]


def test_085_ausente_com_o_interruptor_LIGADO_degrada_sem_levantar(mc, capsys):
    """A célula que ninguém planeja e que acontece: a chave de configuração
    existe (restore de outro ambiente, rollback parcial, alguém que inseriu a
    linha na mão) e as TABELAS não.

    Com o interruptor lendo `1`, a função passa da primeira linha e vai ao
    banco de verdade — e é aí que "leitura degrada larga" precisa valer, ou
    todo pipeline do produto cai junto com a 085 que não está lá."""
    db = banco(com_085=False)               # config ainda traz o interruptor em 1
    assert mc.corrida_ativa(db) is True
    r = mc.odate(db, "PIPE_A", run_id="run_1", conf_id=1, herdada=None)
    assert r == {"data": None, "corrida_id": None, "ambiguo": False,
                 "degrau": None, "detalhe": None}
    assert "indisponivel" in capsys.readouterr().out
