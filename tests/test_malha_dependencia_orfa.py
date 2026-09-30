"""
Linha ÓRFÃ da 067: dependência assinada por um Aguarde (origem_no) cujo desenho
NÃO a produz. Visto em produção (Carga_Vida, 30/09/2026): a dependência era
real — o motor a obedecia — mas

  • o GET da malha a escondia (pulava a seta direta "porque o nó a desenha");
  • puxar a seta direta respondia "já existia" e ela sumia na recarga;
  • o PRÓXIMO gesto em qualquer Aguarde da malha a apagava em silêncio.

Regra nova: órfã é dependência do operador. Aparece como seta direta marcada,
é assumida como MANUAL por quem a puxa, sobrevive (como manual) aos gestos do
Aguarde e pode ser excluída pela porta de sempre. O que o gesto de fato tira do
desenho continua sendo removido — a régua é o desenho GRAVADO antes do gesto.
"""
import os

os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from unittest.mock import patch

from tests.test_malhas_f10 import _aresta, _cria_no, _monta_malha
from tests.test_malhas_f11 import (FakeCur as FakeCurF11, FakeDb as FakeDbF11,
                                   _delete_dep, _linhas_067, _pipes,
                                   auth_editor)  # noqa: F401  (fixture)


class FakeCur(FakeCurF11):
    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        if s.startswith("UPDATE dbo.etl_pipeline_dependencia SET origem_no = NULL"):
            dep, pred, no = params
            n = 0
            for d in self.db.dependencias:
                if (d["pipeline"].casefold() == dep.casefold()
                        and d["depende_de"].casefold() == pred.casefold()
                        and d.get("origem_no") == no):
                    d["origem_no"] = None
                    n += 1
            self.rowcount = n
            self._rows = []
            return
        super().execute(sql, params)


class FakeDb(FakeDbF11):
    def cursor(self):
        super().cursor()            # mantém o snapshot do rollback
        return FakeCur(self)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _malha_com_aguarde(client, db):
    """A,B → W → D. Compila (D,A) e (D,B) assinadas por W."""
    _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_D"])
    w = _cria_no(client, "M1", "aguarde")
    _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w})
    aid_b = _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w}).json()["id"]
    _aresta(client, "M1", {"no": w}, {"pipeline": "PIPE_D"})
    return w, aid_b


def _semear_orfa(db, w):
    """(B depende de A) assinada por W — que não tem saída para B."""
    db.dependencias.append({"pipeline": "PIPE_B", "depende_de": "PIPE_A",
                            "origem_no": w})
    db.pipelines["PIPE_B"]["depends_on"] = "PIPE_A"


def test_get_mostra_a_orfa_como_seta_direta_marcada(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        d = client.get("/malhas/M1").json()
    # a órfã aparece; as compiladas de verdade seguem SEM seta direta
    assert d["arestas"] == [{"pipeline_name": "PIPE_B", "depende_de": "PIPE_A",
                             "orfa": {"no": w}}]
    aviso = [a for a in d["avisos"] if a.get("tipo") == "orfa"]
    assert len(aviso) == 1 and aviso[0]["no"] == w and aviso[0]["nivel"] == "forte"
    assert "PIPE_A" in aviso[0]["mensagem"] and "PIPE_B" in aviso[0]["mensagem"]


def test_puxar_a_seta_sobre_a_orfa_assume_como_manual(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        r = client.post("/dependencias", json={
            "pipeline_name": "PIPE_B", "depende_de": "PIPE_A"})
        d = client.get("/malhas/M1").json()
    assert r.status_code == 200
    assert r.json()["ja_existia"] is True and r.json()["adotada"] is True
    assert ("PIPE_B", "PIPE_A", None) in _linhas_067(db)
    # agora é seta direta comum, sem marca e sem aviso
    assert d["arestas"] == [{"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"}]
    assert not [a for a in d["avisos"] if a.get("tipo") == "orfa"]


def test_puxar_a_seta_sobre_par_compilado_de_verdade_nao_muda_nada(client, auth_editor):
    """(D,A) é produzida pelo desenho de W: continua dele, e a resposta diz
    quem a garante — a tela não desenha uma seta que sumiria na recarga."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        r = client.post("/dependencias", json={
            "pipeline_name": "PIPE_D", "depende_de": "PIPE_A"})
    assert r.status_code == 200
    assert r.json()["ja_existia"] is True and "adotada" not in r.json()
    assert r.json()["compilada_por"] == {"malha": "M1", "no": w}
    assert ("PIPE_D", "PIPE_A", w) in _linhas_067(db)


def test_gesto_no_aguarde_preserva_a_orfa_e_remove_so_o_que_ele_tirou(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, aid_b = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        r_dry = client.delete(f"/malhas/M1/arestas/{aid_b}?dry_run=true")
        assert ("PIPE_B", "PIPE_A", w) in _linhas_067(db)      # dry_run não grava
        r = client.delete(f"/malhas/M1/arestas/{aid_b}")
    for resp in (r_dry, r):
        assert resp.status_code == 200
        # o gesto tirou B→W: (D,B) sai. A órfã NÃO entra na lista de remoção.
        assert resp.json()["efeito"]["dependencias_remover"] == [
            {"dependente": "PIPE_D", "predecessor": "PIPE_B"}]
        assert any("dependência manual" in a["mensagem"]
                   for a in resp.json()["avisos"])
    assert _linhas_067(db) == [("PIPE_B", "PIPE_A", None), ("PIPE_D", "PIPE_A", w)]
    assert db.pipelines["PIPE_B"]["depends_on"] == "PIPE_A"    # CSV intocado


def test_excluir_o_aguarde_dono_nao_leva_a_orfa(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        r = client.delete(f"/malhas/M1/nos/{w}")
    assert r.status_code == 200, r.text
    assert _linhas_067(db) == [("PIPE_B", "PIPE_A", None)]


def test_orfa_pode_ser_excluida_pela_porta_de_sempre(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        r = _delete_dep(client, {"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"})
        # a compilada de verdade segue recusada (Decisão 4)
        r2 = _delete_dep(client, {"pipeline_name": "PIPE_D", "depende_de": "PIPE_A"})
    assert r.status_code == 200, r.text
    assert r2.status_code == 422
    assert ("PIPE_B", "PIPE_A", w) not in _linhas_067(db)
    assert ("PIPE_D", "PIPE_A", w) in _linhas_067(db)


def test_criar_aresta_que_nao_compila_nada_ainda_assim_adota_a_orfa(client, auth_editor):
    """Achado da revisão: gesto de CRIAR aresta sem criar/remover/transferir
    devolvia o aviso "mantida como manual" e não gravava — a mensagem mentia
    e se repetia a cada gesto."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        w, _ = _malha_com_aguarde(client, db)
        _semear_orfa(db, w)
        w2 = _cria_no(client, "M1", "aguarde")
        r = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w2})
        d = client.get("/malhas/M1").json()
    assert r.status_code == 200, r.text
    assert ("PIPE_B", "PIPE_A", None) in _linhas_067(db)
    assert {"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"} in d["arestas"]
    assert not [a for a in d["avisos"] if a.get("tipo") == "orfa"]
