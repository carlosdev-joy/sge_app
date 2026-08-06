"""
Testes da F11 — compilador do Aguarde (grupos 4 e 5 do §13 do desenho
docs/malha-componentes-desenho.md).

Grupo 4 (compilador): transação única com rollback TOTAL (falha no meio →
nada de 067 sem CSV); assinatura origem_no; linha manual coincidente não
adotada nem removida (Decisão 5); remoção SÓ do que a expansão perdeu;
transferência de assinatura entre malhas E dentro da própria malha (§7.3);
carimbo de republicação só com dag_criada=1; dry_run devolve o efeito §7.2
sem gravar (rowcount zero); ciclo PÓS-expansão com a mensagem canônica da F1
(Decisão 15) — inclusive o par que SÓ existe expandido.

Grupo 5 (proteções, Decisão 4): DELETE /dependencias de linha assinada → 422
nomeando malha e nó; replace-all do register (_gravar_dependencias) cuja
remoção atinge assinada → 422 idem (e manter o chip PRESERVA a assinatura);
GET /pipelines/dependencias/estado marca o predecessor compilado com o campo
ADITIVO compilada_por; remover membro ligado a nó → 422.

Dublês: o FakeDb da F10 é ESTENDIDO (subclasse) com rollback REAL por
snapshot — a transação única do gesto é verificável de verdade, não só por
contagem de commits — e com a FK FK_dep_origem_no simulada como o banco a
garante (DELETE de nó com linha assinada pendurada FALHA — prova que o
compilador descompila/transfere ANTES, na ordem do §1.4). Para o register e
o estado (routers.pipelines), o FakePipeDb da F5 é estendido com a coluna
origem_no e o mapa de nós.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user
from tests.test_malhas_f10 import (FakeCur as FakeCurF10, FakeDb as FakeDbF10,
                                   _aresta, _cria_no, _monta_malha)
from tests.test_dependencias_f5 import (FakePipeCur, FakePipeDb, malha_unica,
                                        _body_registro, _linha_pipeline,
                                        _patch_airflow)


# ── dublê da malha: F10 + rollback por snapshot + FK da assinatura ───────────

class FakeDb(FakeDbF10):
    """FakeDb da F10 com com_073=True por default (o carimbo é objeto de teste
    aqui), rollback REAL (snapshot no cursor(), restauração no rollback()) e
    injeção de falha no espelho CSV (falhar_espelho_csv) para provar o
    rollback total da transação do gesto."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 com_073=True, com_075=True):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, com_073=com_073, com_075=com_075)
        self.falhar_espelho_csv = False
        self.mutacao_pos_diff = None    # callable(db) — corre 1x após o SELECT do diff
        self._snapshot = None

    def _estado(self):
        return (self.nos, self.arestas_no, self.dependencias, self.pipelines,
                self.malhas, self.membros, self._prox_no, self._prox_aresta)

    def cursor(self):
        # a "transação" do request: o snapshot vive até commit/rollback
        self._snapshot = copy.deepcopy(self._estado())
        return FakeCur(self)

    def commit(self):
        super().commit()
        self._snapshot = None

    def rollback(self):
        if self._snapshot is not None:
            (self.nos, self.arestas_no, self.dependencias, self.pipelines,
             self.malhas, self.membros, self._prox_no,
             self._prox_aresta) = self._snapshot
            self._snapshot = None


class FakeCur(FakeCurF10):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        if db.falhar_espelho_csv and s.startswith(
                "UPDATE dbo.etl_pipeline SET depends_on"):
            raise RuntimeError("deadlock simulado no espelho CSV (teste)")
        if s.startswith("DELETE FROM dbo.etl_malha_no WHERE id"):
            # FK_dep_origem_no (NO ACTION, §1.4): nó com linha ASSINADA
            # pendurada não pode ser excluído — como o banco garante.
            nid = params[0]
            if any(d.get("origem_no") == nid for d in db.dependencias):
                raise RuntimeError(
                    'The DELETE statement conflicted with the REFERENCE '
                    'constraint "FK_dep_origem_no"')
        super().execute(sql, params)
        # Simulação de CONCORRÊNCIA (defeito 2 da revisão): a mutação roda
        # DEPOIS do SELECT que alimenta o diff — o diff enxerga o estado
        # antigo (as linhas já foram materializadas em _rows) e o apply
        # encontra o estado NOVO, como um gesto paralelo commitado no vão.
        if (getattr(db, "mutacao_pos_diff", None) is not None
                and s.startswith("SELECT pipeline_name, depende_de, origem_no "
                                 "FROM dbo.etl_pipeline_dependencia")):
            mutacao, db.mutacao_pos_diff = db.mutacao_pos_diff, None
            mutacao(db)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha", "tela_pipelines"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _patch_pipes_db(db):
    return patch("routers.pipelines.get_db_conn", return_value=db)


def _pipes():
    """Cinco pipelines: A/B/C entradas, D/E saídas — D com DAG publicada
    (dag_criada=1, alvo do carimbo), E sem (dag_criada=0)."""
    return {
        "PIPE_A": {"active": 1, "criticidade": "Alta", "schedule_type": "daily",
                   "depends_on": None, "dag_criada": 0},
        "PIPE_B": {"active": 1, "criticidade": "Media", "schedule_type": "daily",
                   "depends_on": None, "dag_criada": 0},
        "PIPE_C": {"active": 1, "criticidade": "Baixa", "schedule_type": "daily",
                   "depends_on": None, "dag_criada": 0},
        "PIPE_D": {"active": 1, "criticidade": "Baixa", "schedule_type": "on_demand",
                   "depends_on": None, "dag_criada": 1},
        "PIPE_E": {"active": 1, "criticidade": "Baixa", "schedule_type": "on_demand",
                   "depends_on": None, "dag_criada": 0},
    }


def _linhas_067(db):
    """Fotografia (dependente, predecessor, origem_no) ordenada da 067."""
    return sorted((d["pipeline"], d["depende_de"], d.get("origem_no"))
                  for d in db.dependencias)


def _delete_dep(client, json):
    return client.request("DELETE", "/dependencias", json=json)


# ═══════════════ grupo 4 — o compilador ══════════════════════════════════════

def test_3x2_compila_6_linhas_assinadas_com_csv_e_carimbo(client, auth_editor):
    """Aceite central da F11 (§10): 3 entradas × 2 saídas no desenho = 6 linhas
    REAIS na 067, todas assinadas com o nó, com o espelho CSV dos DOIS
    dependentes e o carimbo de republicação de quem tem DAG publicada — cada
    gesto numa transação única."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C",
                                    "PIPE_D", "PIPE_E"])
        w = _cria_no(client, "M1", "aguarde")
        for p in ("PIPE_A", "PIPE_B", "PIPE_C"):
            assert _aresta(client, "M1", {"pipeline": p}, {"no": w}).status_code == 200
        r_d = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        commits_antes = db.commits
        r_e = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_E"})
    assert r_d.status_code == 200 and r_e.status_code == 200
    # a aresta de saída compila as 3 linhas do dependente, ordenadas
    assert r_d.json()["efeito"]["dependencias_criar"] == [
        {"dependente": "PIPE_D", "predecessor": "PIPE_A"},
        {"dependente": "PIPE_D", "predecessor": "PIPE_B"},
        {"dependente": "PIPE_D", "predecessor": "PIPE_C"}]
    # 6 linhas assinadas com o MESMO nó (proveniência — Decisão 1)
    assert _linhas_067(db) == [
        ("PIPE_D", "PIPE_A", w), ("PIPE_D", "PIPE_B", w), ("PIPE_D", "PIPE_C", w),
        ("PIPE_E", "PIPE_A", w), ("PIPE_E", "PIPE_B", w), ("PIPE_E", "PIPE_C", w)]
    # espelho CSV dos dependentes na MESMA transação (regra F6)
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A,PIPE_B,PIPE_C"
    assert db.pipelines["PIPE_E"]["depends_on"] == "PIPE_A,PIPE_B,PIPE_C"
    # entradas não ganham CSV (o espelho é só do dependente)
    assert db.pipelines["PIPE_A"]["depends_on"] is None
    # carimbo: D tem dag_criada=1 → republicar + flag; E não tem DAG publicada
    assert r_d.json()["efeito"]["republicar"] == ["PIPE_D"]
    assert r_e.json()["efeito"]["republicar"] == []
    assert db.pipelines["PIPE_D"].get("dag_config_pendente") == 1
    assert db.pipelines["PIPE_E"].get("dag_config_pendente") != 1
    # o gesto inteiro (linhas + CSV + carimbo) = UMA transação
    assert db.commits == commits_antes + 1


def test_dry_run_devolve_o_efeito_sem_gravar_nada(client, auth_editor):
    """§7.2: dry_run devolve o efeito com o schema literal e NÃO grava —
    rowcount zero de verdade (o snapshot do dublê prova por igualdade), nem
    commit. Confirmar re-envia sem dry_run e aí sim grava."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        antes = copy.deepcopy(db._estado())
        commits = db.commits
        r = client.post("/malhas/M1/arestas", json={
            "origem": {"pipeline": "PIPE_B"}, "destino": {"no": w},
            "dry_run": True})
        assert r.status_code == 200
        body = r.json()
        # nada mudou: banco byte a byte igual, zero commit
        assert db._estado() == antes
        assert db.commits == commits
        # o schema literal do §7.2
        assert set(body["efeito"].keys()) == {
            "dependencias_criar", "dependencias_remover",
            "dependencias_transferir", "ja_existentes_manuais",
            "agendamentos", "republicar"}
        assert body["efeito"]["dependencias_criar"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_B"}]
        assert body["efeito"]["republicar"] == ["PIPE_D"]
        assert body["erros"] == []
        # confirmar = re-enviar sem dry_run
        r2 = client.post("/malhas/M1/arestas", json={
            "origem": {"pipeline": "PIPE_B"}, "destino": {"no": w}})
    assert r2.status_code == 200
    assert ("PIPE_D", "PIPE_B", w) in _linhas_067(db)


def test_remover_perna_remove_so_o_que_a_expansao_perdeu(client, auth_editor):
    """E2 do §14: A,B→W→D,E; remover a perna B→W — o dry_run mostra as 2
    remoções, o confirm remove SÓ (D,B) e (E,B); (D,A) e (E,A) ficam; CSV e
    carimbo acompanham na mesma transação."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D", "PIPE_E"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        aid_b = _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w}).json()["id"]
        _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_E"})
        db.pipelines["PIPE_D"]["dag_config_pendente"] = 0   # zera p/ ver o gesto
        antes = copy.deepcopy(db._estado())
        r_dry = client.delete(f"/malhas/M1/arestas/{aid_b}?dry_run=true")
        assert r_dry.status_code == 200
        assert r_dry.json()["efeito"]["dependencias_remover"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_B"},
            {"dependente": "PIPE_E", "predecessor": "PIPE_B"}]
        assert db._estado() == antes               # dry_run não gravou
        r = client.delete(f"/malhas/M1/arestas/{aid_b}")
    assert r.status_code == 200
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w), ("PIPE_E", "PIPE_A", w)]
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A"
    assert db.pipelines["PIPE_E"]["depends_on"] == "PIPE_A"
    assert db.pipelines["PIPE_D"]["dag_config_pendente"] == 1   # dag_criada=1


def test_linha_manual_coincidente_nao_e_adotada_nem_removida(client, auth_editor):
    """Decisão 5: a linha que o operador criou à mão continua DELE — o
    compilador reporta ja_existentes_manuais (não assina) e a exclusão do nó
    não a leva."""
    db = FakeDb(pipelines=_pipes())
    db.pipelines["PIPE_D"]["depends_on"] = "PIPE_A"
    db.dependencias.append({"pipeline": "PIPE_D", "depende_de": "PIPE_A"})
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        r = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        assert r.json()["efeito"]["ja_existentes_manuais"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_A"}]
        assert r.json()["efeito"]["dependencias_criar"] == []
        # segue MANUAL (origem_no NULL) — não foi adotada
        assert _linhas_067(db) == [("PIPE_D", "PIPE_A", None)]
        # excluir o nó não leva a linha manual junto
        r_del = client.delete(f"/malhas/M1/nos/{w}")
    assert r_del.status_code == 200
    assert r_del.json()["efeito"]["dependencias_remover"] == []
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", None)]
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A"


def test_transferencia_entre_malhas_na_exclusao_do_no(client, auth_editor):
    """E4 do §14 (§7.3): M2 tem W2 que produz o MESMO par (D,A) já compilado
    por W1 de M1 — o desenho de M2 reporta o aviso (não re-assina, Decisão 4);
    excluir W1 em M1 TRANSFERE a assinatura para W2 (o diff nomeia), nunca
    remove em silêncio. Transferência não muda o grafo do motor: sem carimbo,
    sem mexer no CSV."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        _monta_malha(client, "M2", ["PIPE_A", "PIPE_D"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_D"})
        assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w1)]
        w2 = _cria_no(client, "M2", "aguarde")
        _aresta(client, "M2", {"pipeline": "PIPE_A"}, {"no": w2})
        r_m2 = _aresta(client, "M2", {"no": w2}, {"pipeline": "PIPE_D"})
        # M2 produz o par, mas a linha é de M1: AVISO no gesto (formato §2.2,
        # no=None — não pertence a nó do desenho), sem re-assinatura
        assert r_m2.json()["efeito"]["dependencias_criar"] == []
        aviso_compilada = [a for a in r_m2.json()["avisos"]
                           if a["no"] is None and "já compilada" in a["mensagem"]]
        assert len(aviso_compilada) == 1
        assert f"Aguarde #{w1}" in aviso_compilada[0]["mensagem"]
        assert "'M1'" in aviso_compilada[0]["mensagem"]
        assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w1)]
        db.pipelines["PIPE_D"]["dag_config_pendente"] = 0
        # excluir W1: dry_run nomeia a transferência; o write re-assina p/ W2
        r_dry = client.delete(f"/malhas/M1/nos/{w1}?dry_run=true")
        assert r_dry.json()["efeito"]["dependencias_transferir"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_A",
             "para_malha": "M2", "para_no": w2}]
        assert r_dry.json()["efeito"]["dependencias_remover"] == []
        r_del = client.delete(f"/malhas/M1/nos/{w1}")
    assert r_del.status_code == 200
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w2)]
    # transferência é só proveniência: CSV e carimbo intocados
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A"
    assert db.pipelines["PIPE_D"]["dag_config_pendente"] == 0
    assert r_del.json()["efeito"]["republicar"] == []


def test_transferencia_dentro_da_propria_malha(client, auth_editor):
    """Dois Aguardes da MESMA malha produzindo o mesmo par: excluir o dono
    re-assina para o outro (sem isso a FK FK_dep_origem_no — simulada no dublê
    — derrubaria o DELETE do nó e a proveniência mentiria)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_D"})
        w2 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w2})
        r2 = _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_D"})
        # par já compilado por W1 (desta malha): nada a criar
        assert r2.json()["efeito"]["dependencias_criar"] == []
        assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w1)]
        r_del = client.delete(f"/malhas/M1/nos/{w1}")
    assert r_del.status_code == 200
    assert r_del.json()["efeito"]["dependencias_transferir"] == [
        {"dependente": "PIPE_D", "predecessor": "PIPE_A",
         "para_malha": "M1", "para_no": w2}]
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w2)]


def test_delete_no_por_sql_direto_com_linha_assinada_estoura_a_fk(client, auth_editor):
    """§1.4 no MODELO (simulado como o banco garante): DELETE de nó por SQL
    direto com linha assinada pendurada falha ALTO — a descompilação explícita
    da API é a única ordem possível."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
    cur = db.cursor()
    cur.execute("DELETE FROM dbo.etl_malha_aresta "
                "WHERE origem_no = ? OR destino_no = ?", (w, w))
    with pytest.raises(RuntimeError, match="FK_dep_origem_no"):
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (w,))
    assert w in db.nos


def test_falha_no_meio_da_transacao_rollback_total(client, auth_editor):
    """Grupo 4 do §13: o gesto é UMA transação — uma falha no espelho CSV
    (injetada) desfaz TUDO: nem linha na 067 sem CSV, nem a própria aresta do
    desenho, nem commit. O invariante 'o desenho É o compilado' não admite
    metade."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        antes = copy.deepcopy(db._estado())
        commits = db.commits
        db.falhar_espelho_csv = True
        r = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        db.falhar_espelho_csv = False
    assert r.status_code == 500
    assert db._estado() == antes           # rollback TOTAL, byte a byte
    assert db.commits == commits


def test_ciclo_pos_expansao_422_com_o_texto_canonico(client, auth_editor):
    """E5/Decisão 15: A→W1→B→W2→C; propor C→W1 criaria (B depende de C) contra
    a linha compilada (C depende de B) — o par que SÓ existe expandido. O 422
    traz a MENSAGEM CANÔNICA do BFS da F1 (mesmo texto do cadastro), e nada é
    gravado."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_B"})
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w2})
        _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_C"})
        antes = copy.deepcopy(db._estado())
        r = _aresta(client, "M1", {"pipeline": "PIPE_C"}, {"no": w1})
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Dependência circular: 'PIPE_B' → 'PIPE_C' fecha um ciclo "
        "(o caminho volta para 'PIPE_B')")
    assert db._estado() == antes


def test_ciclo_no_dry_run_vai_para_erros_com_http_200(client, auth_editor):
    """§7.2: no dry_run o ciclo não é exceção — é informação. A lista `erros`
    traz o MESMO texto canônico (o modal da F12 exibe), HTTP 200, nada
    gravado; o write do mesmo gesto é 422."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_B"})
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w2})
        _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_C"})
        antes = copy.deepcopy(db._estado())
        r = client.post("/malhas/M1/arestas", json={
            "origem": {"pipeline": "PIPE_C"}, "destino": {"no": w1},
            "dry_run": True})
    assert r.status_code == 200
    assert r.json()["erros"] == [
        "Dependência circular: 'PIPE_B' → 'PIPE_C' fecha um ciclo "
        "(o caminho volta para 'PIPE_B')"]
    assert db._estado() == antes


def test_dry_run_devolve_o_preview_expandido(client, auth_editor):
    """§3.3: o dry_run devolve o conjunto PÓS-gesto (preview_expandido) — é
    sobre ele que o espelho client-side do ciclo (criaCiclo, F12) vai rodar;
    o front nunca reimplementa a expansão."""
    db = FakeDb(pipelines=_pipes())
    db.dependencias.append({"pipeline": "PIPE_E", "depende_de": "PIPE_C"})
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        r = client.post("/malhas/M1/arestas", json={
            "origem": {"no": w}, "destino": {"pipeline": "PIPE_D"},
            "dry_run": True})
    assert r.status_code == 200
    # o pós-gesto: a linha manual global preexistente + a que o gesto criaria
    assert r.json()["preview_expandido"] == [
        {"pipeline_name": "PIPE_D", "depende_de": "PIPE_A"},
        {"pipeline_name": "PIPE_E", "depende_de": "PIPE_C"}]


def test_aresta_sem_aguarde_nao_compila_nada(client, auth_editor):
    """Só o Aguarde compila (§3.1): aresta de Início/Notificação/Fim devolve o
    efeito VAZIO (chaves presentes, listas vazias) e não toca a 067."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        ini = _cria_no(client, "M1", "inicio")
        fim = _cria_no(client, "M1", "fim")
        r1 = _aresta(client, "M1", {"no": ini}, {"pipeline": "PIPE_A"})
        r2 = _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": fim})
    for r in (r1, r2):
        assert r.status_code == 200
        assert r.json()["efeito"]["dependencias_criar"] == []
        assert r.json()["efeito"]["republicar"] == []
    assert db.dependencias == []


def test_write_recomputa_sobre_o_estado_corrente(client, auth_editor):
    """§7.2: a autoridade é o estado corrente, não o preview — se entre o
    dry_run e o confirm alguém criou a linha MANUAL pelo F8, o write reporta
    ja_existentes_manuais e NÃO assina (a janela preview→confirm não é
    serializada; o write é atômico e honesto)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        r_dry = client.post("/malhas/M1/arestas", json={
            "origem": {"no": w}, "destino": {"pipeline": "PIPE_D"},
            "dry_run": True})
        assert r_dry.json()["efeito"]["dependencias_criar"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_A"}]
        # edição concorrente: a linha nasce MANUAL pela porta F8
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_D", "depende_de": "PIPE_A"}).status_code == 200
        r = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
    assert r.status_code == 200
    assert r.json()["efeito"]["dependencias_criar"] == []
    assert r.json()["efeito"]["ja_existentes_manuais"] == [
        {"dependente": "PIPE_D", "predecessor": "PIPE_A"}]
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", None)]


def test_sem_067_gesto_que_compila_da_503_e_descompilacao_segue(client, auth_editor):
    """Deploy parcial: sem a 067 não existe compilar honesto — aresta de
    Aguarde dá 503 instrutivo; já REMOVER aresta/nó de Aguarde segue como na
    F10 (não há linha compilada para descompilar) — a limpeza do desenho não
    fica refém da migration."""
    db = FakeDb(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w = _cria_no(client, "M1", "aguarde")
        r_post = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        assert r_post.status_code == 503
        assert "migration 067" in r_post.json()["detail"]
        # sem 067 nada foi desenhado acima; desenha de novo? não — o gesto de
        # remoção é testado sobre o nó (sem arestas) e um nó com aresta criada
        # direto no dublê (estado legado imaginável)
        db.arestas_no.append({"id": 99, "malha": "M1", "origem_no": None,
                              "origem_pipeline": "PIPE_A", "destino_no": w,
                              "destino_pipeline": None})
        r_del_ar = client.delete("/malhas/M1/arestas/99")
        assert r_del_ar.status_code == 200
        assert r_del_ar.json()["efeito"]["dependencias_remover"] == []
        r_del_no = client.delete(f"/malhas/M1/nos/{w}")
    assert r_del_no.status_code == 200
    assert db.nos == {}


def test_remocao_cuja_recompilacao_fecha_ciclo_422_e_dry_run_com_erros(client, auth_editor):
    """Reprodução do defeito GRAVE da revisão adversarial: gesto de REMOÇÃO
    cujo diff recompõe uma CRIAÇÃO (067 divergiu do desenho: a linha manual
    coincidente foi apagada e a inversa criada no vão) tem de passar pelo
    MESMO ciclo canônico do add — sem isso a recompilação recriava (D,A)
    contra (A,D) com HTTP 200 = deadlock real em runtime."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D"])
        # (1) linha MANUAL D←A pela porta F8
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_D", "depende_de": "PIPE_A"}).status_code == 200
        # (2) desenhar A,B→W→D: (D,A) fica manual (não adotada), (D,B) compila
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        aid_b = _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w}).json()["id"]
        r_w = _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        assert r_w.json()["efeito"]["ja_existentes_manuais"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_A"}]
        # (3) apagar a manual (permitido — é do operador) → desenho ≠ 067
        assert _delete_dep(client, {"pipeline_name": "PIPE_D",
                                    "depende_de": "PIPE_A"}).status_code == 200
        # (4) criar a INVERSA A←D: o BFS passa, (D,A) não está mais no banco
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_A", "depende_de": "PIPE_D"}).status_code == 200
        antes = copy.deepcopy(db._estado())
        # (5) remover a perna B→W: a recompilação RECRIARIA (D,A) → ciclo
        r_dry = client.delete(f"/malhas/M1/arestas/{aid_b}?dry_run=true")
        assert r_dry.status_code == 200
        assert r_dry.json()["erros"] == [
            "Dependência circular: 'PIPE_D' → 'PIPE_A' fecha um ciclo "
            "(o caminho volta para 'PIPE_D')"]
        assert db._estado() == antes           # dry_run não gravou nada
        r = client.delete(f"/malhas/M1/arestas/{aid_b}")
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Dependência circular: 'PIPE_D' → 'PIPE_A' fecha um ciclo "
        "(o caminho volta para 'PIPE_D')")
    assert db._estado() == antes               # write recusado: nada gravado


def test_exclusao_de_no_cuja_recompilacao_fecha_ciclo_422(client, auth_editor):
    """O mesmo defeito pela OUTRA porta de remoção (DELETE do nó): excluir W2
    quando W1 ainda produz o par recriável que fecharia ciclo → dry_run com
    erros[] e write 422, nada gravado."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D"])
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_D", "depende_de": "PIPE_A"}).status_code == 200
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_D"})   # manual não adotada
        w2 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w2})
        _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_D"})   # (D,B) assinada W2
        assert _delete_dep(client, {"pipeline_name": "PIPE_D",
                                    "depende_de": "PIPE_A"}).status_code == 200
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_A", "depende_de": "PIPE_D"}).status_code == 200
        antes = copy.deepcopy(db._estado())
        r_dry = client.delete(f"/malhas/M1/nos/{w2}?dry_run=true")
        assert r_dry.status_code == 200
        assert r_dry.json()["erros"] == [
            "Dependência circular: 'PIPE_D' → 'PIPE_A' fecha um ciclo "
            "(o caminho volta para 'PIPE_D')"]
        r = client.delete(f"/malhas/M1/nos/{w2}")
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Dependência circular: 'PIPE_D' → 'PIPE_A' fecha um ciclo "
        "(o caminho volta para 'PIPE_D')")
    assert db._estado() == antes               # nó, arestas e 067 intactos


def test_remocao_ja_transferida_por_gesto_concorrente_nao_mexe_no_csv(client, auth_editor):
    """Defeito MENOR da revisão: o DELETE por assinatura pode afetar 0 linhas
    (gesto concorrente transferiu a assinatura entre o diff e o apply) — o
    espelho CSV e o carimbo SÓ acompanham remoção EFETIVADA (rowcount > 0);
    sem a guarda, o CSV perdia o predecessor com a linha da 067 viva."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        _monta_malha(client, "M2", ["PIPE_A", "PIPE_D"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        aid = _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_D"}).json()["id"]
        assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w1)]
        w2 = _cria_no(client, "M2", "aguarde")      # o "outro gesto" assina p/ cá
        db.pipelines["PIPE_D"]["dag_config_pendente"] = 0

        def _transfere_no_vao(db_):
            # commit concorrente entre o SELECT do diff e o apply
            for d in db_.dependencias:
                if d["pipeline"] == "PIPE_D" and d["depende_de"] == "PIPE_A":
                    d["origem_no"] = w2
        db.mutacao_pos_diff = _transfere_no_vao
        r = client.delete(f"/malhas/M1/arestas/{aid}")
    assert r.status_code == 200
    # a linha segue VIVA, com a assinatura do gesto concorrente…
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w2)]
    # …e o CSV não perdeu o predecessor, nem houve carimbo (remoção não efetivada)
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A"
    assert db.pipelines["PIPE_D"]["dag_config_pendente"] == 0


# ═══════════════ grupo 5 — proteções da linha assinada (Decisão 4) ═══════════

def test_delete_dependencias_de_linha_assinada_422_nomeando(client, auth_editor):
    """Porta 1 (DELETE /dependencias): linha compilada é recusada nomeando o
    Aguarde e a malha donos — e nada é apagado, nem do CSV."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_D"])
        w = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
        _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
        r = _delete_dep(client, {"pipeline_name": "PIPE_D",
                                 "depende_de": "PIPE_A"})
    assert r.status_code == 422
    assert f"Aguarde #{w}" in r.json()["detail"]
    assert "'M1'" in r.json()["detail"]
    assert _linhas_067(db) == [("PIPE_D", "PIPE_A", w)]
    assert db.pipelines["PIPE_D"]["depends_on"] == "PIPE_A"


def test_delete_dependencias_manual_continua_funcionando(client, auth_editor):
    """Regressão F8: linha manual segue apagável pela porta de sempre."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_D", "depende_de": "PIPE_A"}).status_code == 200
        r = _delete_dep(client, {"pipeline_name": "PIPE_D",
                                 "depende_de": "PIPE_A"})
    assert r.status_code == 200
    assert db.dependencias == []


def test_remover_membro_ligado_a_no_422(client, auth_editor):
    """§7.3: membro ligado a componente não sai da malha — 422 com a instrução
    'desligue-o dos componentes primeiro'; desligada a aresta, o gesto passa."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        w = _cria_no(client, "M1", "aguarde")
        aid = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w}).json()["id"]
        r = client.delete("/malhas/M1/pipelines/PIPE_A")
        assert r.status_code == 422
        assert "desligue-o dos componentes primeiro" in r.json()["detail"]
        assert any(m["pipeline"] == "PIPE_A" for m in db.membros)
        # membro NÃO ligado sai normalmente (regressão F7)
        assert client.delete("/malhas/M1/pipelines/PIPE_B").status_code == 200
        # desligou a aresta → agora pode
        assert client.delete(f"/malhas/M1/arestas/{aid}").status_code == 200
        r2 = client.delete("/malhas/M1/pipelines/PIPE_A")
    assert r2.status_code == 200


# ── porta 2: replace-all do register (_gravar_dependencias) ──────────────────

class FakePipeDb11(FakePipeDb):
    """FakePipeDb da F5 + coluna origem_no (075) e o mapa de nós de malha —
    o suficiente para o register e o estado enxergarem linha assinada."""

    def __init__(self, pipelines=None, com_067=True, com_073=True,
                 com_075=True, config=None, nos=None):
        super().__init__(pipelines=pipelines, com_067=com_067,
                         com_073=com_073, config=config)
        self.com_075 = com_075
        self.nos = nos or {}   # id -> {"malha": str}

    def cursor(self):
        return FakePipeCur11(self)


class FakePipeCur11(FakePipeCur):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)
        if "COL_LENGTH('dbo.etl_pipeline_dependencia'" in s:
            self._rows = [(4,)] if db.com_075 else [(None,)]
            self.rowcount = -1
            return
        if s.startswith("SELECT d.depende_de, d.origem_no, n.malha_name"):
            # linhas_assinadas do dependente (services.dependencias)
            dep_cf = (params[0] or "").casefold()
            out = []
            for d in db.dependencias:
                if d["pipeline"].casefold() == dep_cf \
                        and d.get("origem_no") is not None:
                    n = db.nos.get(d["origem_no"]) or {}
                    out.append((d["depende_de"], d["origem_no"], n.get("malha")))
            self._rows = sorted(out)
            self.rowcount = -1
            return
        if s.startswith("DELETE FROM dbo.etl_pipeline_dependencia") \
                and "origem_no IS NULL" in s:
            antes = len(db.dependencias)
            db.dependencias = [
                d for d in db.dependencias
                if not (d["pipeline"].casefold() == (params[0] or "").casefold()
                        and d.get("origem_no") is None)]
            self.rowcount = antes - len(db.dependencias)
            self._rows = []
            return
        if s.startswith("SELECT d.pipeline_name, d.depende_de, CONVERT") \
                and "mn.malha_name" in s:
            # grafo do estado COM assinatura (F11): mesmas linhas do pai + a
            # proveniência (origem_no + malha do nó)
            out = []
            for d in db.dependencias:
                k = db._key(d["pipeline"])
                if k is None or int(db.pipelines[k].get("active") or 0) != 1:
                    continue
                p = db.pipelines[k]
                ono = d.get("origem_no")
                n = db.nos.get(ono) if ono is not None else None
                out.append((
                    k, d["depende_de"],
                    (str(p["hora_virada"])[:5] if p.get("hora_virada") else None),
                    (str(p["nao_iniciar_antes"])[:5] if p.get("nao_iniciar_antes") else None),
                    (str(p["hora_limite_dependencia"])[:5] if p.get("hora_limite_dependencia") else None),
                    ono, (n or {}).get("malha"))
                    # F11 — a malha ÚNICA do dependente entra como última
                    # coluna, e só quando a consulta a pede (banco sem a 070
                    # nasce com o literal `NULL` e a coluna não existe no SQL).
                    + (((malha_unica(db, k, s)
                         if "etl_malha_pipeline" in s else None),)
                       if "malha_unica" in s else ()))
            self._rows = sorted(out, key=lambda r: (r[0], r[1]))
            self.rowcount = -1
            return
        super().execute(sql, params)


def test_register_remover_linha_assinada_422_nomeando(client, auth_editor):
    """Porta 2: replace-all (chave depends_on presente) que TIRARIA a linha
    assinada → 422 com a MESMA mensagem literal da porta 1; a 067 fica como
    estava (o DELETE nunca roda)."""
    db = FakePipeDb11(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X"),
                   "PAI_Y": _linha_pipeline(pipeline_name="PAI_Y")},
        nos={7: {"malha": "M1"}})
    db.pipelines["PIPE_A"]["depends_on"] = "PAI_X,PAI_Y"
    db.dependencias = [
        {"pipeline": "PIPE_A", "depende_de": "PAI_X", "origem_no": 7},
        {"pipeline": "PIPE_A", "depende_de": "PAI_Y"}]
    with _patch_pipes_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(depends_on="PAI_Y"))
    assert r.status_code == 422
    assert "Aguarde #7" in r.json()["detail"]
    assert "'M1'" in r.json()["detail"]
    assert {"pipeline": "PIPE_A", "depende_de": "PAI_X",
            "origem_no": 7} in db.dependencias


def test_register_mantendo_a_assinada_preserva_a_assinatura(client, auth_editor):
    """Porta 2, o caminho permitido: manter o chip da assinada na lista NÃO a
    re-grava sem dono (adoção silenciosa morta no §1.4) — só as manuais são
    substituídas pelo replace-all."""
    db = FakePipeDb11(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X"),
                   "PAI_Y": _linha_pipeline(pipeline_name="PAI_Y")},
        nos={7: {"malha": "M1"}})
    db.pipelines["PIPE_A"]["depends_on"] = "PAI_X"
    db.dependencias = [
        {"pipeline": "PIPE_A", "depende_de": "PAI_X", "origem_no": 7}]
    with _patch_pipes_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(depends_on="PAI_X,PAI_Y"))
    assert r.status_code == 200
    assert sorted((d["pipeline"], d["depende_de"], d.get("origem_no"))
                  for d in db.dependencias) == [
        ("PIPE_A", "PAI_X", 7),         # assinatura PRESERVADA
        ("PIPE_A", "PAI_Y", None)]      # a nova nasce manual
    assert db.pipelines["PIPE_A"]["depends_on"] == "PAI_X,PAI_Y"


def test_register_sem_a_075_segue_o_replace_all_de_sempre(client, auth_editor):
    """Deploy parcial (sem a coluna origem_no): o register se comporta byte a
    byte como antes da F11 — o guard é best-effort de propósito."""
    db = FakePipeDb11(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X")},
        com_075=False)
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(depends_on=""))
    assert r.status_code == 200
    assert db.dependencias == []


# ── porta 3: GET /pipelines/dependencias/estado marca o compilado ────────────

def test_estado_marca_predecessor_compilado_com_compilada_por(client, auth_editor):
    """Porta 3: o estado devolve compilada_por ADITIVO no predecessor
    compilado ({malha, no}) — é o contrato que o modal F5 (front na F12) usa
    para travar o chip; o predecessor manual segue SEM a chave."""
    db = FakePipeDb11(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X"),
                   "PAI_Y": _linha_pipeline(pipeline_name="PAI_Y")},
        nos={7: {"malha": "M1"}})
    db.dependencias = [
        {"pipeline": "PIPE_A", "depende_de": "PAI_X", "origem_no": 7},
        {"pipeline": "PIPE_A", "depende_de": "PAI_Y"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200
    item = next(i for i in r.json()["data"] if i["pipeline_name"] == "PIPE_A")
    por_nome = {p["nome"]: p for p in item["predecessores"]}
    assert por_nome["PAI_X"]["compilada_por"] == {"malha": "M1", "no": 7}
    assert "compilada_por" not in por_nome["PAI_Y"]


def test_estado_sem_a_075_nao_tem_a_chave(client, auth_editor):
    """Sem a coluna (deploy parcial), o SQL é o de sempre e a chave não
    aparece — contrato aditivo de verdade."""
    db = FakePipeDb11(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X")},
        com_075=False)
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200
    item = next(i for i in r.json()["data"] if i["pipeline_name"] == "PIPE_A")
    assert all("compilada_por" not in p for p in item["predecessores"])
