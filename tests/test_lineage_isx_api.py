"""Lineage automático via ISX — F2 (spec docs/spec-lineage-isx.md): os endpoints.

Padrão de tests/test_malhas.py: TestClient do conftest, `get_db_conn` mockado em
services.lineage_isx, autenticação por dependency_overrides. Os transportes REST e
SSH são substituídos por fakes em memória (a API REST de amostra do engine e um
"istool" que devolve o .isx sintético) — nenhum teste toca rede ou banco.

O dublê do banco é ESTATAL (FakeDb): cabeçalhos em `etl_ds_job_isx` e linhas em
`etl_job_lineage` em memória, com a semântica case-insensitive da colação, para que
extrair → cache → force → consultar exercitem o SQL real do serviço de ponta a ponta.
"""
from __future__ import annotations

import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user
from routers import lineage as rt_lineage
from routers import lineage_isx as rt
from services import lineage_isx as svc

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "dags") not in sys.path:
    sys.path.insert(0, str(ROOT / "dags"))
from tests.test_lineage_isx_engine import AMBIENTE, ISX_PJB, ISX_SJB, ROTAS  # noqa: E402

PIPE = "PIPE_VIDA"
JOB = "SsdVidaDimePessoa02Ftp"
SEQ = "SeqSsdVidaDime"
_ROTAS = dict(ROTAS)
_ROTAS["folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime/contents"] = {"children": [
    *ROTAS["folders/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime/contents"]["children"],
    {"id": f"jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5C{SEQ}", "jobType": "SEQUENCE",
     "lastModifiedTimestamp": "2026-08-05T12:00:00.000+0000", "name": SEQ},
]}
_ROTAS[f"jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5C{SEQ}"] = {
    "name": SEQ, "jobType": "SEQUENCE", "folderPath": "\\Jobs\\SsdVida\\_Dime",
    "shortDescription": "seq", "lastModified": {"timestamp": "2026-08-05T12:00:00.000+0000"}}


# ═══════════════════════════════════════════════════════════════════════════
# dublês
# ═══════════════════════════════════════════════════════════════════════════

class FakeDb:
    def __init__(self, pipelines=None, jobs=None, com_tabela=True, chave_mapa="stage_type"):
        # pipelines: {nome: project_name}; jobs: {(pipeline, job): {"job_type", "execution_order"}}
        self.pipelines = dict(pipelines or {PIPE: "BI_VIDA"})
        self.jobs = dict(jobs or {(PIPE, JOB): {"job_type": "datastage", "execution_order": 1},
                                  (PIPE, SEQ): {"job_type": "datastage", "execution_order": 2}})
        self.com_tabela = com_tabela
        self.chave_mapa = chave_mapa
        self.mapa = [("ODBCConnectorPX", "Banco de Dados ODBC", "banco", "ambos")]
        self.cabecalhos: dict[tuple, dict] = {}
        self.linhas: list[dict] = []
        self.commits = 0
        self.rollbacks = 0
        self.falhar_insert_linha = False
        self.lock_ocupado = False       # sp_getapplock devolve -1: outra extração do mesmo job
        self.locks: list[str] = []
        self._id = 0

    def _ci(self, d, chave):
        for k in d:
            kk = tuple(x.casefold() for x in k) if isinstance(k, tuple) else k.casefold()
            alvo = tuple(x.casefold() for x in chave) if isinstance(chave, tuple) else chave.casefold()
            if kk == alvo:
                return k
        return None

    def cursor(self):
        return FakeCur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass

    def linhas_do(self, pipeline, job, metodo=None):
        return [l for l in self.linhas if l["pipeline_name"].casefold() == pipeline.casefold()
                and l["job_name"].casefold() == job.casefold() and (metodo is None or l["extraction_method"] == metodo)]

    def semear_linha(self, pipeline, job, metodo, direction="origem", object_name="TB_MANUAL"):
        self._id += 1
        self.linhas.append({"id": self._id, "pipeline_name": pipeline, "job_name": job, "direction": direction,
                            "object_type": "Tabela", "object_name": object_name, "stage_name": None,
                            "stage_type_raw": None, "database_name": None, "sql_expression": None,
                            "file_path": None, "extraction_method": metodo, "columns_json": None,
                            "input_columns_json": None, "apt_code": None, "expressions_json": None,
                            "stage_internal_id": None, "extracted_at": None})


_COLS_INSERT = ["pipeline_name", "job_name", "direction", "object_type", "object_name", "stage_name",
                "stage_type_raw", "database_name", "sql_expression", "file_path", "extraction_method",
                "columns_json", "input_columns_json", "apt_code", "expressions_json", "stage_internal_id"]
_RANK = {"origem": 1, "transformacao": 2, "destino": 3}


class FakeCur:
    def __init__(self, db: FakeDb):
        self.db = db
        self._rows: list = []
        self.rowcount = -1

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        p = list(params or [])
        self._rows = []
        self.rowcount = -1

        if "OBJECT_ID('dbo.etl_ds_job_isx'" in s:
            self._rows = [(1,)] if db.com_tabela else [(None,)]
        elif "sp_getapplock" in s:
            assert "@LockOwner = 'Transaction'" in s and "@LockTimeout = 0" in s and p[0].startswith("isx:")
            db.locks.append(p[0])
            self._rows = [(-1 if db.lock_ocupado else 0,)]
        elif "FROM dbo.etl_pipeline_job j JOIN dbo.etl_pipeline p" in s:
            k = db._ci(db.jobs, (p[0], p[1]))
            if k:   # grafia CANÔNICA do banco nas duas últimas colunas (colação CI)
                self._rows = [(db.pipelines[db._ci(db.pipelines, k[0])], db.jobs[k]["job_type"], k[0], k[1])]
        elif s.startswith("SELECT id, pipeline_name") and "FROM dbo.etl_ds_job_isx WHERE" in s:
            k = db._ci(db.cabecalhos, (p[0], p[1]))
            if k:
                self._rows = [tuple(db.cabecalhos[k].get(c) for c in svc._COLS_CAB)]  # noqa: SLF001
        elif s.startswith("SELECT COUNT(*) FROM dbo.etl_job_lineage l"):
            self._rows = [(len(db.linhas_do(p[0], p[1], "isx_auto")),)]
        elif "COL_LENGTH('dbo.etl_stage_type_map'" in s:
            self._rows = [(4, None)] if db.chave_mapa == "type_raw" else [(None, 4)]
        elif "FROM dbo.etl_stage_type_map" in s:
            assert s.startswith(f"SELECT {db.chave_mapa},"), s
            self._rows = list(db.mapa)
        elif s.startswith("DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = ? AND job_name = ? AND extraction_method = 'isx_auto'"):
            antes = len(db.linhas)
            db.linhas = [l for l in db.linhas if not (l["pipeline_name"].casefold() == p[0].casefold()
                                                        and l["job_name"].casefold() == p[1].casefold()
                                                        and l["extraction_method"] == "isx_auto")]
            self.rowcount = antes - len(db.linhas)
        elif s.startswith("INSERT INTO dbo.etl_job_lineage"):
            if db.falhar_insert_linha:
                raise RuntimeError("Msg 8152: String or binary data would be truncated")
            assert len(p) == len(_COLS_INSERT), (len(p), s)
            db._id += 1
            db.linhas.append({"id": db._id, **dict(zip(_COLS_INSERT, p)), "extracted_at": "2026-09-08 00:00:00"})
            self.rowcount = 1
        elif s.startswith("UPDATE dbo.etl_ds_job_isx SET"):
            campos = re.findall(r"(\w+) = \?", s.split(" WHERE ")[0])
            k = db._ci(db.cabecalhos, (p[-2], p[-1]))
            if k:
                db.cabecalhos[k].update(dict(zip(campos, p)))
                db.cabecalhos[k]["extracted_at"] = "2026-09-08 00:00:00"
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif s.startswith("INSERT INTO dbo.etl_ds_job_isx"):
            campos = re.search(r"\((.*?)\) VALUES", s).group(1).split(", ")
            campos = [c for c in campos if c != "extracted_at"]
            assert len(campos) == len(p), (campos, p)
            db._id += 1
            db.cabecalhos[(p[0], p[1])] = {"id": db._id, **dict(zip(campos, p)), "extracted_at": "2026-09-08 00:00:00"}
            self.rowcount = 1
        elif s.startswith("SELECT direction, object_type") and "FROM dbo.etl_job_lineage WHERE" in s:
            ls = sorted(db.linhas_do(p[0], p[1], "isx_auto"), key=lambda l: (_RANK.get(l["direction"], 9), l["id"]))
            self._rows = [tuple(l.get(c) for c in svc._COLS_LINHA) for l in ls]  # noqa: SLF001
        elif s.startswith("SELECT project_name FROM dbo.etl_pipeline WHERE"):
            k = db._ci(db.pipelines, p[0])
            self._rows = [(db.pipelines[k],)] if k else []
        elif "FROM dbo.etl_pipeline_job j LEFT JOIN dbo.etl_ds_job_isx c" in s:
            for (pipe, job), info in sorted(db.jobs.items(), key=lambda kv: (kv[1]["execution_order"], kv[0][1])):
                if pipe.casefold() != p[0].casefold():
                    continue
                kc = db._ci(db.cabecalhos, (pipe, job))
                c = db.cabecalhos.get(kc) or {}
                self._rows.append((job, info["execution_order"], info["job_type"], c.get("status"), c.get("ds_job_type"),
                                   c.get("ds_last_modified"), c.get("extracted_at"), c.get("extracted_by"), c.get("erro"),
                                   c.get("ds_folder_path"), len(db.linhas_do(pipe, job, "isx_auto"))))
        elif "FROM dbo.etl_pipeline_job j LEFT JOIN dbo.etl_job_lineage l" in s:
            # GET /lineage: preferência por isx_auto quando o job tem
            assert "NOT EXISTS" in s and "x.extraction_method = 'isx_auto'" in s
            for (pipe, job), info in sorted(db.jobs.items(), key=lambda kv: (kv[1]["execution_order"], kv[0][1])):
                if pipe.casefold() != p[0].casefold():
                    continue
                todas = db.linhas_do(pipe, job)
                tem_isx = any(l["extraction_method"] == "isx_auto" for l in todas)
                ls = [l for l in todas if l["extraction_method"] == "isx_auto"] if tem_isx else todas
                if not ls:
                    self._rows.append((info["execution_order"], job, info["job_type"]) + (None,) * 15)
                for l in ls:
                    self._rows.append((info["execution_order"], job, info["job_type"], l["direction"], l["object_name"],
                                       l["object_type"], l["stage_type_raw"], None, None, l["stage_name"],
                                       l["stage_type_raw"], l["database_name"], l["sql_expression"], l["file_path"],
                                       None, l["extracted_at"], l["extraction_method"], l["columns_json"]))
        else:
            raise AssertionError(f"SQL inesperado no dublê: {s[:140]}")


class FakeSsh:
    """Um 'istool' em memória: `-datastage …/JOB.ext` → devolve `arquivos[JOB]`;
    sem o job → rc 1 'No assets matched' (como o istool); `erro` força outra falha."""

    def __init__(self, arquivos: dict[str, bytes], erro: tuple | None = None, demora: float = 0.0):
        self.arquivos = arquivos
        self.erro = erro
        self.demora = demora
        self.comandos: list[str] = []
        self.conexoes = 0
        self.removidos: list[str] = []

    @contextmanager
    def __call__(self):
        self.conexoes += 1
        sftp_arquivos: dict[str, bytes] = {}
        eu = self

        class Sftp:
            def stat(self, caminho):
                if caminho not in sftp_arquivos:
                    raise OSError(2, "No such file")
                return type("St", (), {"st_size": len(sftp_arquivos[caminho])})()

            def open(self, caminho, modo="rb"):
                dados = sftp_arquivos[caminho]

                class F:
                    def read(self, n=-1):
                        return dados if n < 0 else dados[:n]

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False
                return F()

            def remove(self, caminho):
                eu.removidos.append(caminho)
                sftp_arquivos.pop(caminho, None)

        def executar(cmd, teto):
            eu.comandos.append(cmd)
            if eu.demora:
                time.sleep(eu.demora)
            if eu.erro:
                return eu.erro
            ds = re.search(r"-datastage '?([^' ]+)'?", cmd).group(1)
            job = ds.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if job not in eu.arquivos:
                return 1, "", f"IISCOM000: No assets matched {ds}"
            archive = re.search(r"-archive (\S+)", cmd).group(1)
            archive = archive[len('"$HOME"/'):] if archive.startswith('"$HOME"/') else archive
            sftp_arquivos[archive] = eu.arquivos[job]
            return 0, "Exported 1 asset", ""
        yield executar, Sftp()


class FakeRest:
    def __init__(self, rotas=None):
        self.rotas = _ROTAS if rotas is None else rotas
        self.chamadas: list[str] = []

    @contextmanager
    def __call__(self, cfg):
        def rest(caminho):
            self.chamadas.append(caminho)
            return self.rotas.get(caminho)
        yield rest


# ═══════════════════════════════════════════════════════════════════════════
# fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def ambiente(monkeypatch):
    for k, v in AMBIENTE.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def db(monkeypatch, ambiente):
    banco = FakeDb()
    monkeypatch.setattr(svc, "get_db_conn", lambda: banco)
    monkeypatch.setattr(rt_lineage, "get_db_conn", lambda: banco)
    return banco


@pytest.fixture
def ssh(monkeypatch):
    fake = FakeSsh({JOB: ISX_PJB, SEQ: ISX_SJB})
    monkeypatch.setattr(svc, "ssh_transport", fake)
    return fake


@pytest.fixture
def rest(monkeypatch):
    fake = FakeRest()
    monkeypatch.setattr(svc, "rest_transport", fake)
    return fake


def _auth(app, perms, perfil):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "C012345", "perfil": perfil, "permissoes": list(perms)}


@pytest.fixture
def auth_dev(app):
    _auth(app, [PERM_EDITAR], "desenvolvedor")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    _auth(app, [], "consulta")
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _extrair(client, job=JOB, force=False, pipeline=PIPE):
    return client.post("/lineage/isx/extrair", json={"pipeline_name": pipeline, "job_name": job, "force": force})


# ═══════════════════════════════════════════════════════════════════════════
# 1. extrair
# ═══════════════════════════════════════════════════════════════════════════

class TestExtrair:
    def test_grava_cabecalho_e_linhas(self, client, db, ssh, rest, auth_dev):
        r = _extrair(client)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["cache_hit"] is False and b["status"] == "ok" and b["job_type"] == "PARALLEL"
        assert b["ds_project"] == "BI_VIDA" and b["ds_folder_path"] == "\\Jobs\\SsdVida\\_Dime"
        assert b["ds_last_modified"] == "2026-08-04T03:37:15.253+0000" and b["extracted_by"] == "C012345"
        assert b["job_description"] == "ETL de amostra" and len(b["parameters"]) == 4 and len(b["flow"]) == 2
        assert [s["stage_name"] for s in b["stages"]] == ["DM_119_INFO", "TrfNlist", "DST_FTP_NLIST", "TB_DEST", "Misterio"]
        por = {s["stage_name"]: s for s in b["stages"]}
        assert por["DM_119_INFO"]["object_type"] == "Banco de Dados ODBC"     # rótulo do mapa do banco
        assert por["DM_119_INFO"]["sql_expression"].startswith("select distinct") and por["DM_119_INFO"]["database_name"] == "Ssd"
        assert por["TB_DEST"]["object_name"] == "dbo.TB_DESTINO"              # tabela-alvo vira o objeto
        assert por["DST_FTP_NLIST"]["object_name"] == "#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds"
        assert por["TrfNlist"]["apt_code"].startswith("mainloop") and len(por["TrfNlist"]["expressions"]) == 2
        assert por["TrfNlist"]["input_columns"] == [{"name": "CPF_CNPJ", "type": "string", "length": 20}]
        assert b["nao_reconhecidos"] == [{"stage": "Misterio", "stage_type": "PxAlienStage", "motivo": "tipo fora do mapa"}]
        assert "SEGREDO" not in r.text and "OFUSCADO" not in r.text
        # banco: 5 linhas isx_auto, cabeçalho ok, uma transação
        assert len(db.linhas_do(PIPE, JOB, "isx_auto")) == 5 and db.commits == 1 and db.rollbacks == 0
        cab = db.cabecalhos[(PIPE, JOB)]
        assert cab["status"] == "ok" and cab["erro"] is None and cab["isx_sha256"] and cab["extracted_by"] == "C012345"
        # DataStage: BFS (3 pastas) + metadados; um export .pjb; temporário removido
        assert rest.chamadas[:3] == list(ROTAS)[:3] and rest.chamadas[3].startswith("jobdesigns/")
        assert len(ssh.comandos) == 1 and (ssh.comandos[0].endswith(f"/{JOB}.pjb'") or ssh.comandos[0].endswith(f"/{JOB}.pjb"))
        assert "-authfile" in ssh.comandos[0] and "-password" not in ssh.comandos[0] and len(ssh.removidos) == 1
        assert db.locks == [db.locks[0]] and db.locks[0].startswith("isx:") and len(db.locks[0]) == 44

    def test_grafia_do_job_vem_do_banco(self, client, db, ssh, rest, auth_dev):
        # a colação é CI, o DataStage não: o nome cadastrado é o que vai ao istool e à chave do cabeçalho
        r = _extrair(client, job=JOB.lower(), pipeline=PIPE.lower())
        assert r.status_code == 200, r.text
        assert r.json()["job_name"] == JOB and r.json()["pipeline_name"] == PIPE
        assert f"/{JOB}.pjb" in ssh.comandos[0] and (PIPE, JOB) in db.cabecalhos and (PIPE.lower(), JOB.lower()) not in db.cabecalhos

    def test_duas_extracoes_do_mesmo_job_a_segunda_recebe_409(self, client, db, ssh, rest, auth_dev):
        db.lock_ocupado = True
        r = _extrair(client)
        assert r.status_code == 409 and "Outra extração" in r.json()["detail"]
        assert db.rollbacks == 1 and db.commits == 0 and db.linhas_do(PIPE, JOB) == [] and (PIPE, JOB) not in db.cabecalhos

    def test_segunda_chamada_e_cache_e_force_reextrai(self, client, db, ssh, rest, auth_dev):
        db.semear_linha(PIPE, JOB, "manual")
        db.semear_linha(PIPE, JOB, "dsx_auto", object_name="TB_DSX")
        assert _extrair(client).status_code == 200
        n_ssh, n_rest = len(ssh.comandos), len(rest.chamadas)
        r = _extrair(client)
        assert r.status_code == 200 and r.json()["cache_hit"] is True
        assert len(ssh.comandos) == n_ssh                                     # cache: sem tocar o SSH
        assert len(rest.chamadas) == n_rest + 1 and rest.chamadas[-1].startswith("jobdesigns/")   # só conferiu o timestamp
        assert len(r.json()["stages"]) == 5
        r = _extrair(client, force=True)
        assert r.status_code == 200 and r.json()["cache_hit"] is False and len(ssh.comandos) == n_ssh + 1
        # linhas manual/dsx_auto do job continuam; as isx_auto foram substituídas (não duplicadas)
        assert {l["extraction_method"] for l in db.linhas_do(PIPE, JOB)} == {"manual", "dsx_auto", "isx_auto"}
        assert len(db.linhas_do(PIPE, JOB, "isx_auto")) == 5 and len(db.linhas_do(PIPE, JOB, "manual")) == 1

    def test_sequence_tenta_qjb_e_devolve_filhos(self, client, db, ssh, rest, auth_dev):
        r = _extrair(client, job=SEQ)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["job_type"] == "SEQUENCE" and b["children"] == [{"job_name": JOB, "activity": "Act_Pessoa"}]
        assert f"/{SEQ}.qjb" in ssh.comandos[0]
        assert db.cabecalhos[(PIPE, SEQ)]["ds_job_type"] == "SEQUENCE"

    def test_job_fora_de_pipeline_422_e_nome_invalido_422_antes_do_ssh(self, client, db, ssh, rest, auth_dev):
        r = _extrair(client, job="JobQueNaoEstaNoPipeline")
        assert r.status_code == 422 and "não está mapeado no pipeline" in r.json()["detail"]
        r = _extrair(client, job="x; id")
        assert r.status_code == 422
        r = _extrair(client, pipeline="")
        assert r.status_code == 422
        assert ssh.comandos == [] and rest.chamadas == [] and db.cabecalhos == {}

    def test_pipeline_sem_project_name_422(self, client, db, ssh, rest, auth_dev):
        db.pipelines[PIPE] = ""
        r = _extrair(client)
        assert r.status_code == 422 and "project_name" in r.json()["detail"]

    def test_job_que_a_api_nao_acha_404_e_cabecalho_erro(self, client, db, ssh, rest, auth_dev):
        db.jobs[(PIPE, "JobFantasma")] = {"job_type": "datastage", "execution_order": 3}
        r = _extrair(client, job="JobFantasma")
        assert r.status_code == 404 and "JobFantasma" in r.json()["detail"] and "BI_VIDA" in r.json()["detail"]
        cab = db.cabecalhos[(PIPE, "JobFantasma")]
        assert cab["status"] == "erro" and "JobFantasma" in cab["erro"] and cab["extracted_by"] == "C012345"
        assert ssh.comandos == []

    def test_istool_falha_502_frase_publica_e_cabecalho_erro(self, client, db, rest, auth_dev, monkeypatch):
        ssh = FakeSsh({}, erro=(1, "", "Login failed for user: detalhe secreto"))
        monkeypatch.setattr(svc, "ssh_transport", ssh)
        r = _extrair(client)
        assert r.status_code == 502 and "secreto" not in r.text and "istool" in r.json()["detail"]
        cab = db.cabecalhos[(PIPE, JOB)]
        assert cab["status"] == "erro" and "istool" in cab["erro"] and cab["extracted_by"] == "C012345"
        assert cab["ds_folder_path"] == "\\Jobs\\SsdVida\\_Dime" and cab["ds_job_type"] == "PARALLEL"   # o que já se sabia fica
        assert db.linhas_do(PIPE, JOB) == []
        # istool que não acha o asset (extensão errada, pasta errada) → 404, sem 502
        monkeypatch.setattr(svc, "ssh_transport", FakeSsh({}))
        r = _extrair(client)
        assert r.status_code == 404 and "istool" in r.json()["detail"]

    def test_erro_nao_apaga_a_ultima_extracao_boa(self, client, db, ssh, rest, auth_dev, monkeypatch):
        assert _extrair(client).status_code == 200
        monkeypatch.setattr(svc, "ssh_transport", FakeSsh({}, erro=(1, "", "Login failed")))
        assert _extrair(client, force=True).status_code == 502
        assert db.cabecalhos[(PIPE, JOB)]["status"] == "erro"
        assert len(db.linhas_do(PIPE, JOB, "isx_auto")) == 5                 # linhas boas ficam
        assert client.get(f"/lineage/isx/job?pipeline_name={PIPE}&job_name={JOB}").json()["status"] == "erro"

    def test_gravacao_que_falha_faz_rollback_e_500(self, client, db, ssh, rest, auth_dev):
        db.falhar_insert_linha = True
        r = _extrair(client)
        assert r.status_code == 500 and "RuntimeError" in r.json()["detail"] and "8152" not in r.text
        assert db.rollbacks == 1 and db.commits == 0 and (PIPE, JOB) not in db.cabecalhos

    def test_503_sem_configuracao_nao_registra_tentativa(self, client, db, ssh, rest, auth_dev, monkeypatch):
        monkeypatch.delenv("DS_ENGINE")
        monkeypatch.delenv("DS_ISTOOL_AUTHFILE")
        r = _extrair(client)
        assert r.status_code == 503 and "DS_ENGINE" in r.json()["detail"] and "DS_ISTOOL_AUTHFILE" in r.json()["detail"]
        assert db.cabecalhos == {} and ssh.comandos == []

    def test_ds_api_url_com_credencial_embutida_503(self, client, db, ssh, rest, auth_dev, monkeypatch):
        monkeypatch.setenv("DS_API_URL", "http://amostra:amostra@ds-api-amostra:9443/ibm/iis/ds/api")
        r = _extrair(client)
        assert r.status_code == 503 and "DS_API_USER" in r.json()["detail"] and "amostra:amostra" not in r.text
        assert db.cabecalhos == {} and rest.chamadas == []

    def test_migration_pendente_503(self, client, db, ssh, rest, auth_dev):
        db.com_tabela = False
        r = _extrair(client)
        assert r.status_code == 503 and "106" in r.json()["detail"]

    def test_504_registra_erro_no_cabecalho(self, client, db, rest, auth_dev, monkeypatch):
        monkeypatch.setattr(rt, "_TETO_EXTRAIR_S", 0.2)
        ssh = FakeSsh({JOB: ISX_PJB}, demora=0.6)
        monkeypatch.setattr(svc, "ssh_transport", ssh)
        r = _extrair(client)
        assert r.status_code == 504 and "0.2 s" in r.json()["detail"]
        assert db.cabecalhos[(PIPE, JOB)]["status"] == "erro" and "não terminou" in db.cabecalhos[(PIPE, JOB)]["erro"]
        time.sleep(0.7)   # a thread presa termina e vai ao log, não à resposta

    def test_permissao_e_autenticacao(self, client, db, ssh, rest, auth_consulta):
        r = _extrair(client)
        assert r.status_code == 403 and "acao_editar" in r.json()["detail"]
        assert ssh.comandos == []

    def test_sem_token_401_em_todos(self, client, db, ssh, rest, app):
        app.dependency_overrides.pop(get_current_user, None)
        assert _extrair(client).status_code == 401
        assert client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name={JOB}").status_code == 401
        assert client.get(f"/lineage/isx/job?pipeline_name={PIPE}&job_name={JOB}").status_code == 401
        assert client.get(f"/lineage/isx/pipeline?pipeline_name={PIPE}").status_code == 401
        assert client.get(f"/lineage?pipeline_name={PIPE}").status_code == 401
        # os vizinhos DSX do mesmo router (Impacto por Campo chama pelo apiFetch, com token)
        assert client.get("/lineage/dsx-files").status_code == 401
        assert client.get("/lineage/dsx-folders?dsx=x").status_code == 401
        assert client.get("/lineage/field-impact?dsx=x&campo=y").status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 2. localizar, consultar, pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestConsultas:
    def test_localizar(self, client, db, ssh, rest, auth_dev):
        r = client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name={JOB}")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["encontrado"] is True and b["folder_path"] == "\\Jobs\\SsdVida\\_Dime" and b["job_type"] == "PARALLEL"
        assert b["last_modified"] == "2026-08-04T03:37:15.253+0000" and b["api_id"].startswith("jobdesigns/")
        assert b["description"] == "d" and len(rest.chamadas) == 4        # BFS + metadados
        # depois de extrair, a pasta é conhecida: confere direto (1 chamada)
        assert _extrair(client).status_code == 200
        rest.chamadas.clear()
        assert client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name={JOB}").json()["encontrado"] is True
        assert len(rest.chamadas) == 1 and rest.chamadas[0].startswith("jobdesigns/")
        # job do pipeline que o DataStage não tem
        db.jobs[(PIPE, "Sumido")] = {"job_type": "datastage", "execution_order": 9}
        r = client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name=Sumido")
        assert r.status_code == 200 and r.json()["encontrado"] is False and "folder_path" not in r.json()
        # fora do pipeline → 422; nada gravado
        assert client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name=Outro").status_code == 422
        assert (PIPE, "Sumido") not in db.cabecalhos

    def test_localizar_pasta_conhecida_desatualizada_cai_na_busca(self, client, db, ssh, rest, auth_dev):
        db.cabecalhos[(PIPE, JOB)] = {"pipeline_name": PIPE, "job_name": JOB, "ds_folder_path": "\\Jobs\\Antiga", "status": "ok"}
        r = client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name={JOB}")
        assert r.status_code == 200 and r.json()["encontrado"] is True and r.json()["folder_path"] == "\\Jobs\\SsdVida\\_Dime"
        assert rest.chamadas[0] == f"jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CAntiga%5C{JOB}" and len(rest.chamadas) == 5

    def test_detalhe_sem_folder_path_mantem_a_pasta_conhecida(self, client, db, ssh, rest, auth_dev, monkeypatch):
        rotas = dict(_ROTAS)
        detalhe = dict(rotas[f"jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5C{JOB}"])
        detalhe.pop("folderPath")
        rotas[f"jobdesigns/AMOSTRA.DEV%5CBI_VIDA%5CJobs%5CSsdVida%5C_Dime%5C{JOB}"] = detalhe
        monkeypatch.setattr(svc, "rest_transport", FakeRest(rotas))
        db.cabecalhos[(PIPE, JOB)] = {"pipeline_name": PIPE, "job_name": JOB, "ds_folder_path": "\\Jobs\\SsdVida\\_Dime", "status": "ok"}
        r = client.get(f"/lineage/isx/localizar?pipeline_name={PIPE}&job_name={JOB}")
        assert r.status_code == 200 and r.json()["folder_path"] == "\\Jobs\\SsdVida\\_Dime"
        r = _extrair(client, force=True)
        assert r.status_code == 200 and r.json()["ds_folder_path"] == "\\Jobs\\SsdVida\\_Dime"

    def test_job_e_pipeline(self, client, db, ssh, rest, auth_dev):
        r = client.get(f"/lineage/isx/job?pipeline_name={PIPE}&job_name={JOB}")
        assert r.status_code == 404 and "ainda não tem extração" in r.json()["detail"]
        assert _extrair(client).status_code == 200
        r = client.get(f"/lineage/isx/job?pipeline_name={PIPE}&job_name={JOB}")
        assert r.status_code == 200 and len(r.json()["stages"]) == 5 and r.json()["status"] == "ok" and "cache_hit" not in r.json()
        r = client.get(f"/lineage/isx/pipeline?pipeline_name={PIPE}")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["ds_project"] == "BI_VIDA" and [j["job_name"] for j in b["jobs"]] == [JOB, SEQ]
        assert b["jobs"][0]["isx"]["status"] == "ok" and b["jobs"][0]["isx"]["linhas"] == 5 and b["jobs"][0]["isx"]["extracted_by"] == "C012345"
        assert b["jobs"][1]["isx"] is None
        assert client.get("/lineage/isx/pipeline?pipeline_name=NaoExiste").status_code == 404
        assert client.get("/lineage/isx/pipeline?pipeline_name=").status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 3. GET /lineage prefere ISX
# ═══════════════════════════════════════════════════════════════════════════

class TestGetLineage:
    def test_prefere_isx_por_job(self, client, db, ssh, rest, auth_dev):
        db.semear_linha(PIPE, JOB, "manual", object_name="TB_MANUAL_J1")
        db.semear_linha(PIPE, SEQ, "manual", object_name="TB_MANUAL_SEQ")
        assert _extrair(client).status_code == 200
        r = client.get(f"/lineage?pipeline_name={PIPE}")
        assert r.status_code == 200, r.text
        jobs = {j["job_name"]: j for j in r.json()["jobs"]}
        metodos_j = {x["extraction_method"] for g in ("origens", "transformacoes", "destinos") for x in jobs[JOB][g]}
        assert metodos_j == {"isx_auto"} and "TB_MANUAL_J1" not in r.text
        assert [x["object_name"] for x in jobs[SEQ]["origens"]] == ["TB_MANUAL_SEQ"]     # sem ISX: as linhas de sempre
        assert [x["object_name"] for x in jobs[JOB]["destinos"]][:1] == ["#PSetSsdVida.ParmDirDst#DST_FTP_NLIST.ds"]

    def test_sql_e_assinatura(self):
        assert "NOT EXISTS" in rt_lineage._SQL_LINEAGE and "x.extraction_method = 'isx_auto'" in rt_lineage._SQL_LINEAGE  # noqa: SLF001
        import inspect
        assert "get_current_user" in inspect.getsource(rt_lineage.get_lineage)


# ═══════════════════════════════════════════════════════════════════════════
# 4. serviço: transportes reais (código-fonte) e anti-drift
# ═══════════════════════════════════════════════════════════════════════════

def test_transporte_ssh_desliga_agente_e_chaves_automaticas():
    fonte = (ROOT / "api" / "services" / "lineage_isx.py").read_text(encoding="utf-8")
    assert "allow_agent=False" in fonte and "look_for_keys=False" in fonte
    assert "credencial(\"datastage\")" in fonte and "RejectPolicy" in fonte
    assert "recv_exit_status()" in fonte and fonte.index("out.read()") < fonte.index("recv_exit_status()")
    assert "trust_env=False" in fonte                                        # nunca pelo proxy corporativo
    assert "DS_SSH_KNOWN_HOSTS" in fonte and "sp_getapplock" in fonte        # aviso no arranque; lock por job
    router = (ROOT / "api" / "routers" / "lineage_isx.py").read_text(encoding="utf-8")
    assert "fut.cancel()" in router                                          # fila cancelada após o 504


def test_router_registrado_e_sem_segredo():
    main = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert main.count("lineage_isx") == 2
    for arquivo in ("api/routers/lineage_isx.py", "api/services/lineage_isx.py"):
        fonte = (ROOT / arquivo).read_text(encoding="utf-8")
        assert re.search(r"(?i)(password|senha)\s*=\s*['\"][^'\"]+['\"]", fonte) is None, arquivo
        assert ".intranet" not in fonte and "lnxprd" not in fonte
    smoke = ROOT / "scripts" / "smoke_lineage_isx.sh"
    assert smoke.is_file() and os.access(smoke, os.X_OK)
    texto = smoke.read_text(encoding="utf-8")
    for trecho in ("/lineage/isx/localizar", "/lineage/isx/extrair", "/lineage/isx/pipeline", "/lineage?pipeline_name", "force"):
        assert trecho in texto, trecho


def test_executor_dedicado_e_tetos():
    # 2 por processo: produção roda uvicorn --workers 2 → 4 JVMs do istool no total (spec §3)
    assert rt._EXECUTOR_ISX._max_workers == 2 and rt._TETO_EXTRAIR_S == 60  # noqa: SLF001
    assert '"--workers", "2"' in (ROOT / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert rt._EXECUTOR_ISX is not getattr(sys.modules.get("routers.utilitarios"), "_EXECUTOR", None)  # noqa: SLF001


def test_object_name_e_cortes():
    assert svc._object_name({"sql_tag": "TableName", "sql_expression": "dbo.T\n", "stage_name": "S"}) == "dbo.T"  # noqa: SLF001
    assert svc._object_name({"classe": "arquivo", "file_path": "/a/b.ds", "stage_name": "S"}) == "/a/b.ds"  # noqa: SLF001
    assert svc._object_name({"classe": "banco", "stage_name": "S", "sql_tag": "SelectStatement"}) == "S"  # noqa: SLF001
    assert svc._c("x" * 700, "file_path") == "x" * 500 and svc._c("", "erro") is None and svc._c(None, "erro") is None  # noqa: SLF001
    linhas, nao = svc._linhas("P", "J", {"stages": [{"stage_name": "Dimensões", "stage_type_raw": "PxDataSet",  # noqa: SLF001
                                                      "direction": "destino", "file_path": "/x/ação.ds", "classe": "arquivo"}],
                                          "nao_reconhecidos": []})
    assert len(linhas) == 1 and linhas[0][4] == "/x/ação.ds"
    assert [n["motivo"][:9] for n in nao] == ["stage_nam", "file_path"]
