"""Testes do EmailOperator — o nó `email` do pipeline em tempo de corrida
(spec docs/spec-notificacao-email.md, F2).

O que estes testes prendem, porque é o que a spec promete e o que quebraria em
silêncio:
  * a config vem do BANCO a cada corrida (mudar destinatário na tela vale já
    na próxima execução, sem republicar a DAG);
  * união das listas do nó e do fluxo, sem duplicata, com 'incluir os
    destinatários do fluxo' respeitado;
  * canal desligado → task `skipped` (não é falha);
  * anexo ausente → e-mail SAI sem anexo, `status='sem_anexo'` no log;
  * sendmail com rc != 0 ou SSH fora → task FALHA, mas com a linha gravada
    em etl_email_log (decisão §8: toda falha de envio falha a task);
  * placeholders resolvidos no assunto, no corpo e no NOME do anexo.

Airflow stubado no mesmo padrão de tests/test_python_script_operator.py.
"""
from __future__ import annotations

import importlib.util
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


class _Skip(Exception):
    """AirflowSkipException de mentira."""


def _stub_airflow():
    _ensure_module("airflow")
    _ensure_module("airflow.exceptions").AirflowSkipException = _Skip
    _ensure_module("airflow.exceptions").AirflowException = type("AirflowException", (Exception,), {})

    class _BaseOperator:
        def __init__(self, *a, task_id=None, trigger_rule=None, **k):
            self.task_id = task_id
            self.log = types.SimpleNamespace(info=lambda *a, **k: None,
                                             warning=lambda *a, **k: None)
    _ensure_module("airflow.models").BaseOperator = _BaseOperator
    # MsSqlHook NÃO é stubado de propósito: o operador só o importa dentro de
    # `_hook`, que todo teste aqui substitui. Trocar o atributo no módulo real
    # vazaria para os outros arquivos de teste (que esperam o MagicMock global).
    _ensure_module("airflow.providers.ssh.hooks.ssh")


@pytest.fixture(scope="module")
def mod():
    """Carrega o operador com o Airflow stubado e `utils` apontando para
    dags/utils — e DESFAZ tudo no fim.

    A restauração não é zelo: sem ela, o `utils` fabricado aqui fica em
    sys.modules e quebra todo teste posterior que importe `utils.*` de verdade
    (foram 73 falhas em outros arquivos até isto ser corrigido)."""
    criados = [m for m in ("utils", "airflow", "airflow.exceptions", "airflow.models",
                           "airflow.providers", "airflow.providers.microsoft",
                           "airflow.providers.microsoft.mssql",
                           "airflow.providers.microsoft.mssql.hooks",
                           "airflow.providers.microsoft.mssql.hooks.mssql",
                           "airflow.providers.ssh", "airflow.providers.ssh.hooks",
                           "airflow.providers.ssh.hooks.ssh")]
    antes = {m: sys.modules.get(m) for m in criados}
    # Atributos que este arquivo TROCA em módulos que podem já existir (o
    # MagicMock global dos testes de factory). Restaurar o módulo não desfaz a
    # mutação do atributo — é preciso guardar o valor.
    _sentinela = object()
    attrs_antes = []
    for nome_mod, attr in (("airflow.models", "BaseOperator"),
                           ("airflow.exceptions", "AirflowSkipException"),
                           ("airflow.exceptions", "AirflowException"),
                           ("airflow.providers.ssh.hooks.ssh", "SSHHook")):
        m_ = sys.modules.get(nome_mod)
        attrs_antes.append((nome_mod, attr, getattr(m_, attr, _sentinela) if m_ is not None else _sentinela))
    _stub_airflow()
    utils = _ensure_module("utils")
    path_antes = getattr(utils, "__path__", None)
    utils.__path__ = [str(_ROOT / "dags/utils")]        # para `from utils import email_envio`
    spec = importlib.util.spec_from_file_location("email_operator_test",
                                                  _ROOT / "dags/utils/email_operator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("utils.email_envio", None)
    for nome_mod, attr, valor in attrs_antes:
        m_ = sys.modules.get(nome_mod)
        if m_ is None:
            continue
        if valor is _sentinela:
            try:
                delattr(m_, attr)
            except AttributeError:
                pass
        else:
            setattr(m_, attr, valor)
    for nome, prev in antes.items():
        if prev is None:
            sys.modules.pop(nome, None)
        else:
            sys.modules[nome] = prev
    if antes.get("utils") is not None:
        if path_antes is None:
            try:
                del sys.modules["utils"].__path__
            except AttributeError:
                pass
        else:
            sys.modules["utils"].__path__ = path_antes


# ── dublês do banco e do SSH ────────────────────────────────────────────────

CONFIG_LIGADA = {
    "email_habilitado": "1",
    "email_remetente": "orquestra@cvp.com.br",
    "email_limite_anexo_mb": "5",
    "email_anexo_raizes": '["/dados/saida"]',
    "email_dominios_permitidos": '[]',
}
NO_PADRAO = {
    "assunto": "Carga {pipeline} concluída - {data}",
    "corpo": "A carga terminou com {linhas} linhas em {duracao}.",
    "html": False,
    "destinatarios": ["ana@cvp.com.br"],
    "incluir_pipeline": True,
    "anexo": None,
}


class _Hook:
    def __init__(self, config=None, no=None, lista_pipeline=None, erro_lista=False,
                 data_referencia="2026-09-11", status_geral="SUCCESS", rows_out=None):
        self.config = dict(CONFIG_LIGADA if config is None else config)
        self.no = NO_PADRAO if no is None else no
        self.lista_pipeline = ["carlos@cvp.com.br"] if lista_pipeline is None else lista_pipeline
        self.erro_lista = erro_lista
        self.data_referencia = data_referencia
        self.status_geral = status_geral
        self.rows_out = rows_out          # fallback de {linhas} por etl_ds_job_log
        self.consultas: list[str] = []
        self.inseridos: list[tuple] = []

    def get_records(self, sql, parameters=None):
        assert "%s" in sql, "dags/ fala pymssql: placeholder é %s, não ?"
        return [(k, v) for k, v in self.config.items()]

    def get_first(self, sql, parameters=None):
        import json as _json
        assert "%s" in sql
        self.consultas.append(sql)
        if "notify_json" in sql:
            return (_json.dumps(self.no),) if self.no is not None else None
        if "email_destinatarios" in sql:
            if self.erro_lista:
                raise Exception("Invalid column name 'email_destinatarios'")
            return (_json.dumps(self.lista_pipeline),) if self.lista_pipeline else (None,)
        if "data_referencia" in sql:
            return (self.data_referencia,) if self.data_referencia else None
        if "etl_job_execution" in sql:
            return (self.status_geral,) if self.status_geral else None
        if "etl_ds_job_log" in sql:
            return (self.rows_out,) if self.rows_out is not None else None
        return None

    def run(self, sql, parameters=None):
        assert "INSERT INTO dbo.etl_email_log" in sql and "%s" in sql
        self.inseridos.append(parameters)


class _Canal:
    def __init__(self, rc):
        self.rc = rc

    def recv_exit_status(self):
        return self.rc

    def shutdown_write(self):
        pass


class _Fluxo:
    def __init__(self, canal, dados=b""):
        self.channel, self._dados, self.escrito = canal, dados, b""

    def write(self, b):
        self.escrito += b

    def read(self):
        return self._dados


class _Sftp:
    def __init__(self, arquivos):
        self.arquivos = arquivos

    def stat(self, caminho):
        import errno
        if caminho not in self.arquivos:
            raise IOError(errno.ENOENT, "No such file")
        return types.SimpleNamespace(st_size=len(self.arquivos[caminho]), st_mode=0o100644)

    def open(self, caminho, modo="rb"):
        import io as _io
        class _F(_io.BytesIO):
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
        return _F(self.arquivos[caminho])

    def close(self):
        pass


class _Client:
    def __init__(self, rc=0, stderr=b"", arquivos=None, erro_conexao=None):
        self.rc, self.stderr_dados = rc, stderr
        self.arquivos = arquivos or {}
        self.erro_conexao = erro_conexao
        self.comandos: list[str] = []
        self.enviado = b""

    def exec_command(self, cmd, timeout=None):
        self.comandos.append(cmd)
        canal = _Canal(self.rc)
        entrada = _Fluxo(canal)
        self._entrada = entrada
        return entrada, _Fluxo(canal), _Fluxo(canal, self.stderr_dados)

    def open_sftp(self):
        return _Sftp(self.arquivos)

    def __enter__(self):
        if self.erro_conexao:
            raise self.erro_conexao
        return self

    def __exit__(self, *a):
        return False


def _preparar(mod, monkeypatch, hook, client):
    monkeypatch.setattr(mod.EmailOperator, "_hook", lambda self: hook)

    class _SSHHook:
        def __init__(self, ssh_conn_id=None):
            self.ssh_conn_id = ssh_conn_id

        def get_conn(self):
            return client
    sys.modules["airflow.providers.ssh.hooks.ssh"].SSHHook = _SSHHook
    return mod.EmailOperator(task_id="avisa", pipeline_name="CARGA_VIDA",
                             job_name="avisa", ssh_conn_id="ssh_lnxprd021")


class _Ti:
    def __init__(self, xcoms=None):
        self.xcoms = xcoms or {}

    def xcom_pull(self, task_ids=None):
        return self.xcoms.get(task_ids)


def _contexto(xcoms=None, run_id="manual__2026-09-11"):
    import datetime as dt
    return {"ti": _Ti(xcoms), "ds_nodash": "20260911", "ts_nodash": "20260911T060000",
            "dag_run": types.SimpleNamespace(run_id=run_id,
                                             start_date=dt.datetime(2026, 9, 11, 6, 0, 0))}


# ── testes ──────────────────────────────────────────────────────────────────

def test_envia_unindo_as_listas_do_no_e_do_fluxo(mod, monkeypatch):
    hook, client = _Hook(), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    # É ASSIM que o factory liga o nó: `t_end_<job> >> t_email_<no>`, e o
    # task_id do t_end é `log_end_<job>` (ver test_dag_factory_email).
    op.upstream_task_ids = {"log_end_CARGA"}
    saida = op.execute(_contexto(xcoms={"CARGA": '{"rows_out": 4200}'}))

    assert saida["destinatarios"] == ["ana@cvp.com.br", "carlos@cvp.com.br"]
    assert saida["status"] == "enviado"
    # o comando é o mesmo da F1, com o envelope-from do Admin
    assert client.comandos == ["/usr/sbin/sendmail -t -i -f orquestra@cvp.com.br"]
    corpo = client._entrada.escrito.decode()
    assert "Subject: Carga CARGA_VIDA" in corpo.replace("\n ", "")
    assert "4200 linhas" in corpo            # {linhas} veio do XCom do upstream
    assert "X-Orquestra-Pipeline: CARGA_VIDA" in corpo
    assert hook.inseridos and hook.inseridos[0][9] == "enviado"


def test_nao_herda_a_lista_do_fluxo_quando_desmarcado(mod, monkeypatch):
    no = dict(NO_PADRAO, incluir_pipeline=False)
    hook, client = _Hook(no=no), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    assert op.execute(_contexto())["destinatarios"] == ["ana@cvp.com.br"]


def test_duplicata_entre_as_duas_listas_vira_um_destinatario(mod, monkeypatch):
    hook = _Hook(no=dict(NO_PADRAO, destinatarios=["Ana@CVP.com.br"]),
                 lista_pipeline=["ana@cvp.com.br"])
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    assert op.execute(_contexto())["destinatarios"] == ["Ana@cvp.com.br"]


def test_canal_desligado_pula_a_task_em_vez_de_falhar(mod, monkeypatch):
    hook = _Hook(config=dict(CONFIG_LIGADA, email_habilitado="0"))
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    with pytest.raises(_Skip):
        op.execute(_contexto())
    assert hook.inseridos == []          # pulado não é envio: nada no log


def test_sem_a_migration_111_a_mensagem_nomeia_a_migration(mod, monkeypatch):
    op = _preparar(mod, monkeypatch, _Hook(config={}), _Client(rc=0))
    with pytest.raises(RuntimeError, match="migration 111"):
        op.execute(_contexto())


def test_sem_destinatario_em_lugar_nenhum_falha_com_mensagem_clara(mod, monkeypatch):
    hook = _Hook(no=dict(NO_PADRAO, destinatarios=[]), lista_pipeline=[])
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    with pytest.raises(RuntimeError, match="sem destinatário"):
        op.execute(_contexto())


def test_dominio_barrado_depois_do_cadastro_falha_em_vez_de_enviar_parcial(mod, monkeypatch):
    hook = _Hook(config=dict(CONFIG_LIGADA, email_dominios_permitidos='["parceiro.com.br"]'))
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    with pytest.raises(RuntimeError, match="Destinatários recusados"):
        op.execute(_contexto())


def test_anexo_do_dia_vai_junto_com_o_nome_resolvido(mod, monkeypatch):
    no = dict(NO_PADRAO, anexo={"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"})
    hook = _Hook(no=no)
    client = _Client(rc=0, arquivos={"/dados/saida/relatorio_20260911.xlsx": b"planilha"})
    op = _preparar(mod, monkeypatch, hook, client)
    saida = op.execute(_contexto())
    assert saida["anexo"] == "/dados/saida/relatorio_20260911.xlsx" and saida["status"] == "enviado"
    assert 'filename="relatorio_20260911.xlsx"' in client._entrada.escrito.decode()
    assert hook.inseridos[0][7] == "/dados/saida/relatorio_20260911.xlsx"


def test_anexo_ausente_envia_sem_anexo_e_registra_sem_anexo(mod, monkeypatch):
    """Decisão do usuário: o arquivo pode ainda não existir — o aviso é do log,
    não da corrida."""
    no = dict(NO_PADRAO, anexo={"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"})
    hook, client = _Hook(no=no), _Client(rc=0, arquivos={})
    op = _preparar(mod, monkeypatch, hook, client)
    saida = op.execute(_contexto())
    assert saida["status"] == "sem_anexo" and saida["anexo"] is None
    assert hook.inseridos[0][9] == "sem_anexo" and "não encontrado" in hook.inseridos[0][10]
    assert client._entrada.escrito                      # o e-mail SAIU


def test_sendmail_com_rc_diferente_de_zero_falha_a_task_mas_grava_o_log(mod, monkeypatch):
    hook = _Hook()
    client = _Client(rc=75, stderr=b"deferred: relay down")
    op = _preparar(mod, monkeypatch, hook, client)
    with pytest.raises(RuntimeError, match="rc=75"):
        op.execute(_contexto())
    assert hook.inseridos[0][9] == "falhou" and "relay down" in hook.inseridos[0][10]


def test_ssh_fora_do_ar_falha_a_task_mas_grava_o_log(mod, monkeypatch):
    hook = _Hook()
    client = _Client(erro_conexao=OSError("Connection refused"))
    op = _preparar(mod, monkeypatch, hook, client)
    with pytest.raises(RuntimeError, match="Falha ao enviar"):
        op.execute(_contexto())
    assert hook.inseridos[0][9] == "falhou" and "Connection refused" in hook.inseridos[0][10]


def test_coluna_da_lista_do_fluxo_ausente_nao_derruba_o_envio(mod, monkeypatch):
    """Sem a 111 a coluna não existe; o nó ainda envia para a lista própria."""
    hook = _Hook(erro_lista=True)
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    assert op.execute(_contexto())["destinatarios"] == ["ana@cvp.com.br"]


def test_falha_ao_gravar_o_log_nao_derruba_um_envio_que_deu_certo(mod, monkeypatch):
    hook = _Hook()

    def _explode(sql, parameters=None):
        raise Exception("deadlock")
    hook.run = _explode
    op = _preparar(mod, monkeypatch, hook, _Client(rc=0))
    assert op.execute(_contexto())["status"] == "enviado"


def test_placeholder_desconhecido_fica_intacto_e_nao_quebra(mod, monkeypatch):
    no = dict(NO_PADRAO, assunto="Fim de {pipeline} {variavel_errada}", corpo="ok")
    hook, client = _Hook(no=no), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.execute(_contexto())
    assert "{variavel_errada}" in client._entrada.escrito.decode()


# ═══════════ placeholders vindos do banco (achados da revisão da F2) ═════════

def test_linhas_vem_do_job_e_nao_do_log_end(mod, monkeypatch):
    """⛔ Âncora: o factory liga o e-mail ao `t_end_<job>`, cujo task_id é
    `log_end_<job>` — e o `rows_out` está no XCom do task_id `<job>`. Ler o
    task_id cru deixava `{linhas}` SEMPRE vazio, sem aviso nenhum."""
    hook, client = _Hook(), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.upstream_task_ids = {"log_end_CARGA_VIDA"}
    assert op._jobs_a_montante() == ["CARGA_VIDA"]
    op.execute(_contexto(xcoms={"CARGA_VIDA": '{"rows_out": 1234}'}))
    assert "1234 linhas" in client._entrada.escrito.decode()


def test_linhas_cai_para_o_log_do_datastage_quando_nao_ha_xcom(mod, monkeypatch):
    """Mesmo fallback do nó de notificação Teams."""
    hook, client = _Hook(rows_out=987), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.upstream_task_ids = {"log_end_CARGA"}
    op.execute(_contexto(xcoms={}))
    assert "987 linhas" in client._entrada.escrito.decode()


def test_sem_linhas_em_lugar_nenhum_o_texto_sai_sem_o_numero(mod, monkeypatch):
    hook, client = _Hook(), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.upstream_task_ids = {"log_end_CARGA"}
    op.execute(_contexto(xcoms={}))
    corpo = client._entrada.escrito.decode()
    assert "com  linhas" in corpo and "{linhas}" not in corpo


def test_odate_e_a_data_de_referencia_da_corrida_nao_a_logica(mod, monkeypatch):
    """⛔ Âncora: `ds_nodash` é o INÍCIO do intervalo — num pipeline diário ele
    é o dia ANTERIOR, e o anexo `relatorio_{odate}.xlsx` apontaria para o
    arquivo de ontem. O ODATE do produto vive em etl_pipeline_execucao."""
    no = dict(NO_PADRAO, corpo="odate={odate}",
              anexo={"raiz": "/dados/saida", "nome": "rel_{odate}.csv"})
    hook = _Hook(no=no, data_referencia="2026-09-11")
    client = _Client(rc=0, arquivos={"/dados/saida/rel_20260911.csv": b"x"})
    op = _preparar(mod, monkeypatch, hook, client)
    ctx = _contexto()
    ctx["ds_nodash"] = "20260910"            # a data lógica, um dia atrás
    saida = op.execute(ctx)
    assert "odate=20260911" in client._entrada.escrito.decode()
    assert saida["anexo"] == "/dados/saida/rel_20260911.csv"


def test_odate_cai_para_o_fim_do_intervalo_sem_linha_de_corrida(mod, monkeypatch):
    import datetime as dt
    hook = _Hook(no=dict(NO_PADRAO, corpo="odate={odate}"), data_referencia=None)
    client = _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    ctx = _contexto()
    ctx["data_interval_end"] = dt.datetime(2026, 9, 11, 6, 0, 0)
    op.execute(ctx)
    assert "odate=20260911" in client._entrada.escrito.decode()


def test_status_vem_do_banco_e_nao_afirma_sucesso_quando_algo_falhou(mod, monkeypatch):
    """⛔ Âncora: com um nó Aguarde de política 'todas_terminarem', o e-mail
    roda DEPOIS de uma etapa que falhou. Um {status} fixo em 'concluído'
    mandaria um aviso de sucesso para um fluxo quebrado."""
    hook = _Hook(no=dict(NO_PADRAO, assunto="[Orquestra] {pipeline} — {status}"),
                 status_geral="FAILED")
    client = _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.execute(_contexto())
    # o travessão viaja codificado no cabeçalho; o que importa é o STATUS
    bruto = client._entrada.escrito.decode().replace("\n ", "")
    assert "FAILED" in bruto and "concluído" not in bruto


def test_duracao_nunca_sai_negativa(mod, monkeypatch):
    """Relógio do worker atrás do início do run imprimiria '-1:16:26'."""
    import datetime as dt
    hook, client = _Hook(no=dict(NO_PADRAO, corpo="dur={duracao}")), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    ctx = _contexto()
    ctx["dag_run"] = types.SimpleNamespace(
        run_id="x", start_date=dt.datetime.now() + dt.timedelta(hours=3))
    op.execute(ctx)
    assert "dur=00:00:00" in client._entrada.escrito.decode()


def test_falha_de_ssh_ao_buscar_o_anexo_ainda_grava_o_log(mod, monkeypatch):
    """Sem isto, a mesma falha de conexão era registrada no envio e ignorada
    na busca do anexo — a corrida sumia de etl_email_log."""
    no = dict(NO_PADRAO, anexo={"raiz": "/dados/saida", "nome": "x.csv"})
    hook = _Hook(no=no)

    class _ClientQueExplodeNoSftp(_Client):
        def open_sftp(self):
            raise OSError("Connection reset by peer")
    client = _ClientQueExplodeNoSftp(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    saida = op.execute(_contexto())
    assert saida["status"] == "sem_anexo"
    assert hook.inseridos[0][9] == "sem_anexo" and "não pôde ser buscado" in hook.inseridos[0][10]
    assert client._entrada.escrito            # o e-mail SAIU mesmo assim
