"""
Testes do PythonScriptOperator (nó Python v2 — execução remota via SSH).

Contrato:
  - modo 'arquivo': command = "<interp> <script_path>" (shlex.quote em runtime);
  - modo 'codigo': publica <destino>/<arquivo> via SFTP (mkdir -p antes; falha
    ALTA se o mkdir falhar) e roda "cd <destino> && <interp> <arquivo>";
  - template_ext = () — caminho terminando em .py/.sh nunca vira arquivo de
    template Jinja (mesma regressão do ShellOperator).

Airflow stubado (mesmo padrão do test_shell_operator.py); o SSHHook usado no
_publicar_arquivo é substituído por um fake com client/sftp gravadores.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


def _ensure_module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


def _stub_airflow():
    _ensure_module("airflow")
    _ensure_module("airflow.exceptions").AirflowException = type(
        "AirflowException", (Exception,), {})
    _ensure_module("airflow.models").BaseOperator = type(
        "BaseOperator", (), {"__init__": lambda self, *a, **k: None})
    _ensure_module("airflow.providers.microsoft.mssql.hooks.mssql").MsSqlHook = type(
        "MsSqlHook", (), {})

    class _FakeSSHOperator:
        template_fields = ("command", "environment", "remote_host")
        template_ext = (".sh",)

        def __init__(self, *a, command=None, ssh_conn_id=None, **k):
            self.command = command
            self.ssh_conn_id = ssh_conn_id
            self.log = types.SimpleNamespace(info=lambda *a, **k: None)

        def execute(self, context):
            return "exec-ssh"

    _ensure_module("airflow.providers.ssh.operators.ssh").SSHOperator = _FakeSSHOperator
    # módulo do hook existe; a classe é trocada por teste (monkeypatch)
    _ensure_module("airflow.providers.ssh.hooks.ssh").SSHHook = type("SSHHook", (), {})


@pytest.fixture(scope="module")
def job_operators():
    _stub_airflow()
    path = _ROOT / "dags/utils/job_operators.py"
    spec = importlib.util.spec_from_file_location("job_operators_py_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("utils", types.ModuleType("utils"))
    spec.loader.exec_module(mod)
    return mod


# ── Fakes do SSH (client/sftp) ───────────────────────────────────────────────

class _FakeChannel:
    def __init__(self, rc):
        self._rc = rc

    def recv_exit_status(self):
        return self._rc


class _FakeStream:
    def __init__(self, rc=0, data=b""):
        self.channel = _FakeChannel(rc)
        self._data = data

    def read(self):
        return self._data


class _FakeSFTPFile(io.BytesIO):
    def __init__(self, registro, path):
        super().__init__()
        self._registro = registro
        self._path = path

    def __exit__(self, *a):
        self._registro[self._path] = self.getvalue()
        return False

    def __enter__(self):
        return self


class _FakeSFTP:
    def __init__(self, registro):
        self._registro = registro
        self.fechado = False

    def open(self, path, mode):
        assert mode == "wb"
        return _FakeSFTPFile(self._registro, path)

    def close(self):
        self.fechado = True


class _FakeClient:
    def __init__(self, mkdir_rc=0):
        self.mkdir_rc = mkdir_rc
        self.comandos = []
        self.arquivos: dict[str, bytes] = {}
        self.sftp = _FakeSFTP(self.arquivos)

    def exec_command(self, cmd):
        self.comandos.append(cmd)
        return None, _FakeStream(self.mkdir_rc), _FakeStream(data=b"sem permissao")

    def open_sftp(self):
        return self.sftp

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _instala_fake_hook(client):
    class _FakeHook:
        def __init__(self, ssh_conn_id=None):
            self.ssh_conn_id = ssh_conn_id

        def get_conn(self):
            return client

    sys.modules["airflow.providers.ssh.hooks.ssh"].SSHHook = _FakeHook
    return client


# ── Construção do comando ────────────────────────────────────────────────────

def test_modo_arquivo_monta_comando_quotado(job_operators):
    op = job_operators.PythonScriptOperator(
        modo="arquivo", script_path="/opt/scripts/carga diaria.py",
        ssh_conn_id="ssh_x")
    assert op.command == "python3 '/opt/scripts/carga diaria.py'"


def test_modo_codigo_monta_cd_e_interpretador_custom(job_operators):
    op = job_operators.PythonScriptOperator(
        modo="codigo", destino_dir="/opt/scripts", arquivo="gerado.py",
        codigo="print(1)", interpretador="/usr/bin/python3.11", ssh_conn_id="ssh_x")
    assert op.command == "cd /opt/scripts && /usr/bin/python3.11 gerado.py"


def test_template_ext_vazio(job_operators):
    assert job_operators.PythonScriptOperator.template_ext == ()


# ── Publicação (modo codigo) ─────────────────────────────────────────────────

def test_codigo_publica_via_sftp_e_executa(job_operators):
    client = _instala_fake_hook(_FakeClient(mkdir_rc=0))
    codigo = "print('olá çãé')\n"
    op = job_operators.PythonScriptOperator(
        modo="codigo", destino_dir="/opt/scripts", arquivo="gerado.py",
        codigo=codigo, ssh_conn_id="ssh_x")
    resultado = op.execute({})
    assert resultado == "exec-ssh"                      # rodou o SSHOperator depois
    assert client.comandos == ["mkdir -p /opt/scripts"]  # criou o diretório antes
    assert client.arquivos["/opt/scripts/gerado.py"] == codigo.encode("utf-8")
    assert client.sftp.fechado is True


def test_codigo_mkdir_falha_alto_sem_executar(job_operators):
    _instala_fake_hook(_FakeClient(mkdir_rc=1))
    op = job_operators.PythonScriptOperator(
        modo="codigo", destino_dir="/opt/negado", arquivo="x.py",
        codigo="print(1)", ssh_conn_id="ssh_x")
    with pytest.raises(RuntimeError, match="mkdir -p .* falhou .*sem permissao"):
        op.execute({})


def test_modo_arquivo_nao_publica_nada(job_operators):
    client = _instala_fake_hook(_FakeClient())
    op = job_operators.PythonScriptOperator(
        modo="arquivo", script_path="/opt/x.py", ssh_conn_id="ssh_x")
    assert op.execute({}) == "exec-ssh"
    assert client.comandos == [] and client.arquivos == {}
