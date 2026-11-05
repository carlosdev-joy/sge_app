"""Agente Terminal, F3 — execução de LEITURA no servidor (spec docs/spec-agente-terminal.md).

Cobre: registro próprio de servidores, executor SSH (limites; paramiko é dublê), orquestração
(`ferramenta_servidor_exec`: classificar → auditar → executar → finalizar) e a FIAÇÃO em `conversar` — em
especial que NENHUM outro agente consegue usar `servidor_exec`. A prova com SSH de verdade (canários) está em
`scripts/prova_agente_terminal_ssh.py`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import agentes_registro as reg  # noqa: E402
from services import agentes_terminal as aterm  # noqa: E402
from services import agentes_terminal_ssh as tssh  # noqa: E402
from services import ssh_arquivos as arq  # noqa: E402
from tests.test_agentes_execucao import _conversar, _pedido, _Provedor  # noqa: E402

ENV_AF = {"AF_SSH_HOST": "af.interno", "AF_SSH_USER": "orq_ro", "AF_SSH_PASSWORD": "NUNCA-APARECE"}
LIMPAR = ["DS_SSH_HOST", "DS_SSH_USER", "DS_SSH_PORT", "DS_SSH_PASSWORD", "DS_SSH_KEY_FILE", "DS_SSH_KNOWN_HOSTS",
          "AF_SSH_HOST", "AF_SSH_USER", "AF_SSH_PORT", "AF_SSH_PASSWORD", "AF_SSH_KEY_FILE", "AF_SSH_KNOWN_HOSTS",
          "TERMINAL_RAIZES_AIRFLOW", "TERMINAL_RAIZES_DATASTAGE"]


@pytest.fixture(autouse=True)
def _env_limpo(monkeypatch):
    for k in LIMPAR:
        monkeypatch.delenv(k, raising=False)


def _com_airflow(monkeypatch, **extra):
    for k, v in {**ENV_AF, **extra}.items():
        monkeypatch.setenv(k, v)


# ═══════════ 1. registro de servidores ══════════════════════════════════

def test_sem_variaveis_nenhum_servidor_configurado():
    assert tssh.servidores() == {}
    assert all(not s["configurado"] for s in tssh.listar())


def test_servidor_configurado_por_ambiente_e_listagem_sem_segredo(monkeypatch):
    _com_airflow(monkeypatch, AF_SSH_PORT="2222")
    srv = tssh.servidores()["airflow"]
    assert (srv.host, srv.port, srv.user) == ("af.interno", 2222, "orq_ro")
    saida = str(tssh.listar())
    for segredo in ("af.interno", "orq_ro", "NUNCA-APARECE"):
        assert segredo not in saida, "a listagem não pode vazar host/usuário/senha"
    assert {s["id"]: s["configurado"] for s in tssh.listar()} == {"datastage": False, "airflow": True}


def test_o_registro_e_proprio_e_nao_vaza_para_utilitarios():
    """`ssh_arquivos.SERVIDORES` alimenta o seletor de Utilitários: o Airflow do Terminal NÃO pode entrar ali."""
    assert "airflow" not in arq.SERVIDORES
    assert set(arq.SERVIDORES) == {"datastage"}


def test_datastage_reaproveita_as_variaveis_do_console(monkeypatch):
    monkeypatch.setenv("DS_SSH_HOST", "sshd-amostra")
    monkeypatch.setenv("DS_SSH_USER", "orquestra")
    assert set(tssh.servidores()) == {"datastage"}


def test_raizes_por_servidor_e_a_raiz_inteira_nunca_vale(monkeypatch):
    _com_airflow(monkeypatch, TERMINAL_RAIZES_AIRFLOW="/opt/airflow, /var//log/ ,/, relativo,/home/../srv")
    assert tssh.servidores()["airflow"].raizes == ("/opt/airflow", "/var/log", "/srv")
    _com_airflow(monkeypatch, TERMINAL_RAIZES_AIRFLOW="/, nada")
    assert tssh.servidores()["airflow"].raizes == tssh.RAIZES_PADRAO


# ═══════════ 2. executor (paramiko é dublê) ═════════════════════════════

class _Canal:
    def __init__(self, blocos=(), erros=(), codigo=0, travar=False):
        self.blocos, self.erros, self.codigo, self.travar = list(blocos), list(erros), codigo, travar
        self.fechado = self.eof_enviado = False
        self.comando = None

    def settimeout(self, _t): pass
    def exec_command(self, c): self.comando = c
    def shutdown_write(self): self.eof_enviado = True
    def recv_ready(self): return bool(self.blocos)
    def recv_stderr_ready(self): return bool(self.erros)
    def recv(self, n): return self.blocos.pop(0)
    def recv_stderr(self, n): return self.erros.pop(0)
    def exit_status_ready(self): return not self.travar and not self.blocos and not self.erros
    def recv_exit_status(self): return self.codigo
    def close(self): self.fechado = True


class _Cliente:
    def __init__(self, canal):
        self.canal, self.fechou = canal, False

    def get_transport(self):
        return MagicMock(open_session=lambda timeout=10: self.canal)

    def close(self): self.fechou = True


def _srv():
    return tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, None, ("/opt",))


def _roda(monkeypatch, canal, **kw):
    cli = _Cliente(canal)
    monkeypatch.setattr(tssh, "_conectar", lambda srv: cli)
    return tssh.executar_bloqueante(_srv(), "ls /opt", **kw), cli


def test_executor_le_stdout_stderr_e_codigo(monkeypatch):
    canal = _Canal(blocos=[b"abc\n", "ação\n".encode()], erros=[b"aviso\n"], codigo=3)
    res, cli = _roda(monkeypatch, canal)
    assert (res.stdout, res.stderr, res.exit_code) == ("abc\nação\n", "aviso\n", 3)
    assert not res.truncada and not res.estourou_tempo
    assert canal.comando == tssh.embrulhar("ls /opt", tssh.TIMEOUT_PADRAO_S) and canal.eof_enviado, "stdin fechado de imediato"
    assert canal.fechado and cli.fechou


def test_executor_corta_no_limite_de_bytes_e_fecha_o_canal(monkeypatch):
    canal = _Canal(blocos=[b"x" * 5000] * 50, travar=True)
    res, cli = _roda(monkeypatch, canal, max_bytes=20_000)
    assert res.truncada and len(res.stdout) <= 20_000 and canal.fechado and cli.fechou


def test_executor_estoura_o_tempo_e_fecha_o_canal(monkeypatch):
    canal = _Canal(travar=True)
    res, cli = _roda(monkeypatch, canal, timeout_s=0)
    assert res.estourou_tempo and res.exit_code is None and canal.fechado and cli.fechou


def test_executor_decodifica_bytes_invalidos_sem_levantar(monkeypatch):
    res, _ = _roda(monkeypatch, _Canal(blocos=[b"\xff\xfeok"]))
    assert "ok" in res.stdout


@pytest.fixture
def paramiko_falso(monkeypatch):
    """`paramiko` não está instalado no ambiente de testes (o import em `_conectar` é tardio): módulo falso."""
    import types

    class _Boom:
        def set_missing_host_key_policy(self, p): pass
        def load_host_keys(self, p): pass
        def connect(self, **kw): raise OSError("[Errno 111] Connection refused host=af.interno user=orq_ro")
    mod = types.SimpleNamespace(SSHClient=_Boom, RejectPolicy=object, AutoAddPolicy=object)
    monkeypatch.setitem(sys.modules, "paramiko", mod)
    return mod


def test_falha_de_conexao_nao_vaza_host_nem_usuario(monkeypatch, paramiko_falso):
    monkeypatch.setenv("TERMINAL_SSH_AUTO_ADD", "1")
    with pytest.raises(tssh.TerminalSshErro) as e:
        tssh._conectar(tssh.ServidorTerminal("airflow", "AF", "af.interno", 22, "orq_ro", "x", None, None, ("/opt",)))
    assert "af.interno" not in str(e.value) and "orq_ro" not in str(e.value) and "OSError" in str(e.value)


def test_sem_known_hosts_a_conexao_falha_fechada(monkeypatch, paramiko_falso):
    """A senha nunca segue para um host impostor: sem known_hosts (e sem o opt-in explícito de DEV) nem conecta."""
    chamou = []
    paramiko_falso.SSHClient.connect = lambda self, **kw: chamou.append(kw)
    with pytest.raises(tssh.TerminalSshErro) as e:
        tssh._conectar(tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", "senha", None, None, ("/opt",)))
    assert "known_hosts" in str(e.value) and chamou == []
    monkeypatch.setenv("TERMINAL_SSH_AUTO_ADD", "0")
    with pytest.raises(tssh.TerminalSshErro):
        tssh._conectar(tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", "senha", None, None, ("/opt",)))


def test_known_hosts_configurado_e_ilegivel_recusa_antes_de_conectar(paramiko_falso):
    with pytest.raises(tssh.TerminalSshErro):
        tssh._conectar(tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, "/nao/existe", ("/opt",)))


# ═══════════ 3. orquestração ════════════════════════════════════════════

class _Banco:
    """abrir_conn de teste: registra o SQL e os parâmetros (para provar que segredo nunca chega ao banco)."""
    def __init__(self, falha=False):
        self.sqls, self.varridas, self.falha, self.rowcount = [], [], falha, 1

    def abrir(self):
        if self.falha:
            raise RuntimeError("banco fora")
        banco = self

        class _Cur:
            rowcount = 1
            def execute(self, sql, params=None):
                (banco.varridas if "interrompido:" in sql else banco.sqls).append((sql, list(params or [])))
            def close(self): pass

        class _Conn:
            def commit(self): pass
            def close(self): pass
        return _Conn(), _Cur()

    def tudo(self) -> str:
        return " ".join(f"{s} {p}" for s, p in self.sqls)


@pytest.fixture
def servidor(monkeypatch):
    srv = tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, None, ("/opt", "/var/log"))
    monkeypatch.setattr(tssh, "servidores", lambda: {"airflow": srv})
    return srv


def _executor(monkeypatch, stdout="", stderr="", codigo=0, **kw):
    chamadas = []

    async def _exec(srv, linha, **k):
        chamadas.append(linha)
        return tssh.ResultadoExec(stdout, stderr, codigo, kw.get("truncada", False), kw.get("estourou", False), 12)
    monkeypatch.setattr(tssh, "executar", _exec)
    return chamadas


def _ferr(banco, **args):
    return asyncio.run(aterm.ferramenta_servidor_exec(banco.abrir, args, matricula="DEV1", conversa_id="conv-1",
                                                      ssh_max=3, espera_max_s=5))


def test_leitura_audita_executa_e_finaliza(monkeypatch, servidor):
    exec_ = _executor(monkeypatch, stdout="linha1\nlinha2\n")
    banco = _Banco()
    r = _ferr(banco, comando="tail -n 5 /var/log/a.log")
    assert exec_ == ["tail -n 5 /var/log/a.log"]
    assert "linha1" in r["texto"] and "código de saída: 0" in r["texto"] and "servidor: airflow" in r["texto"]
    ins, upd = banco.sqls
    assert ins[0].startswith("INSERT INTO dbo.etl_agente_terminal_cmd") and "executando" in ins[1]
    assert "leitura" in ins[1] and "DEV1" in ins[1] and "conv-1" in ins[1]
    assert upd[0].startswith("UPDATE") and "executado" in upd[1]


def test_so_os_tokens_classificados_vao_ao_shell(monkeypatch, servidor):
    exec_ = _executor(monkeypatch, stdout="ok")
    _ferr(_Banco(), comando="grep -E 'a|b' /var/log/a.log")
    assert exec_ == ["grep -E -e 'a|b' /var/log/a.log"]


def test_escrita_nao_executa_nem_registra(monkeypatch, servidor):
    exec_ = _executor(monkeypatch)
    banco = _Banco()
    r = _ferr(banco, comando="systemctl restart airflow")
    assert exec_ == [] and banco.sqls == []
    assert "altera o servidor" in r["texto"] and "Não foi executado nem registrado" in r["texto"]


@pytest.mark.parametrize("comando", ["cat /opt/app/.env", "rm -rf /", "sudo ls", "env", "docker inspect x"])
def test_proibido_e_registrado_como_bloqueado_e_nunca_executa(monkeypatch, servidor, comando):
    exec_ = _executor(monkeypatch)
    banco = _Banco()
    r = _ferr(banco, comando=comando)
    assert exec_ == [] and "Nada foi executado" in r["texto"]
    [ins] = banco.sqls
    assert "proibido" in ins[1] and "bloqueado" in ins[1]


def test_comando_com_segredo_nunca_executa_e_o_segredo_nao_chega_ao_banco_nem_ao_modelo(monkeypatch, servidor):
    exec_ = _executor(monkeypatch)
    banco = _Banco()
    r = _ferr(banco, comando="mysql -u root -pHUNTER2 -e 'select 1'")
    assert exec_ == [] and "HUNTER2" not in r["texto"] and "HUNTER2" not in banco.tudo()
    assert "segredo" in r["texto"]


def test_sem_auditoria_nao_executa(monkeypatch, servidor):
    exec_ = _executor(monkeypatch, stdout="x")
    r = _ferr(_Banco(falha=True), comando="ls /opt")
    assert exec_ == [] and "auditoria" in r["texto"].lower() and "não foi executado" in r["texto"]


def test_saida_e_redigida_antes_de_filtrar_e_cortar(monkeypatch, servidor):
    _executor(monkeypatch, stdout="ok\npassword: hunter2\nDB_TOKEN=abc999\nmysql -pSENHA9 db\nfim\n")
    banco = _Banco()
    r = _ferr(banco, comando="cat /opt/app/log.txt")
    for segredo in ("hunter2", "abc999", "SENHA9"):
        assert segredo not in r["texto"] and segredo not in banco.tudo()
    assert "ok" in r["texto"] and "fim" in r["texto"]


def test_filtros_em_python_sem_regex(monkeypatch, servidor):
    _executor(monkeypatch, stdout="\n".join(f"linha {i} {'ERRO' if i % 10 == 0 else 'ok'}" for i in range(1, 101)))
    r = _ferr(_Banco(), comando="cat /opt/a.log", filtrar="erro", ultimas=3)
    corpo = r["texto"]
    assert "linha 100 ERRO" in corpo and "linha 80 ERRO" in corpo and "linha 70" not in corpo
    assert "linha(s) fora do filtro" in corpo
    r = _ferr(_Banco(), comando="cat /opt/a.log", primeiras=2)
    assert "linha 1 ok" in r["texto"] and "linha 3" not in r["texto"]
    r = _ferr(_Banco(), comando="cat /opt/a.log", filtrar=".*(a+)+$")  # "regex" é texto literal: nenhum casamento, sem travar
    assert "linha 1" not in r["texto"]


def test_codigo_diferente_de_zero_vira_falhou_e_o_modelo_ve_o_codigo(monkeypatch, servidor):
    _executor(monkeypatch, stderr="ls: cannot access\n", codigo=2)
    banco = _Banco()
    r = _ferr(banco, comando="ls /opt/nao-existe")
    assert "código de saída: 2" in r["texto"] and "cannot access" in r["texto"]
    assert "falhou" in banco.sqls[1][1]


def test_estouro_de_tempo_e_truncamento_sao_avisados(monkeypatch, servidor):
    _executor(monkeypatch, stdout="x", codigo=None, estourou=True, truncada=True)
    r = _ferr(_Banco(), comando="cat /opt/a")
    assert "interrompido" in r["texto"] and "cortada no servidor" in r["texto"]


@pytest.mark.parametrize("erro,trecho", [(af.ServidorOcupado("Servidor ocupado"), "ocupado"),
                                         (tssh.TerminalSshErro("Não foi possível conectar"), "conectar"),
                                         (RuntimeError("segredo-do-driver"), "RuntimeError")])
def test_falhas_do_executor_viram_texto_e_fecham_o_registro(monkeypatch, servidor, erro, trecho):
    async def _boom(*a, **k):
        raise erro
    monkeypatch.setattr(tssh, "executar", _boom)
    banco = _Banco()
    r = _ferr(banco, comando="ls /opt")
    assert trecho in r["texto"] and "segredo-do-driver" not in r["texto"]
    assert "falhou" in banco.sqls[-1][1], "o registro nunca fica preso em `executando`"


def test_cancelamento_fecha_o_registro_e_propaga(monkeypatch, servidor):
    async def _cancela(*a, **k):
        raise asyncio.CancelledError()
    monkeypatch.setattr(tssh, "executar", _cancela)
    banco = _Banco()
    with pytest.raises(asyncio.CancelledError):
        _ferr(banco, comando="ls /opt")
    assert "falhou" in banco.sqls[-1][1]


def test_entradas_invalidas_nao_tocam_servidor_nem_banco(monkeypatch, servidor):
    exec_ = _executor(monkeypatch)
    banco = _Banco()
    assert "Informe o comando" in _ferr(banco, comando="  ")["texto"]
    assert "Servidor 'xx'" in _ferr(banco, comando="ls /opt", servidor="xx")["texto"]
    assert "maior que" in _ferr(banco, comando="ls /opt " + "a" * 2500)["texto"]
    r = asyncio.run(aterm.ferramenta_servidor_exec(banco.abrir, {"comando": "ls /opt"}, matricula="", conversa_id=None,
                                                   ssh_max=3, espera_max_s=5))
    assert "identificar o usuário" in r["texto"]
    assert exec_ == [] and banco.sqls == []


def test_sem_servidor_configurado_diz_isso(monkeypatch):
    monkeypatch.setattr(tssh, "servidores", lambda: {})
    r = _ferr(_Banco(), comando="ls /opt")
    assert "Nenhum servidor está configurado" in r["texto"]


def test_servidor_padrao_e_o_primeiro_configurado(monkeypatch, servidor):
    exec_ = _executor(monkeypatch, stdout="x")
    _ferr(_Banco(), comando="ls /opt")
    assert exec_  # sem args.servidor usa o único configurado


# ═══════════ 4. FIAÇÃO em `conversar` ═══════════════════════════════════

@pytest.fixture
def sem_aprendizado(monkeypatch):
    monkeypatch.setattr(svc, "_recuperar_seguro", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_registrar_seguro", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_erro_conhecido_seguro", lambda *a, **k: None)


@pytest.fixture
def espiao(monkeypatch):
    chamadas = []

    async def _ferr_falsa(abrir, args, **kw):
        chamadas.append((args, kw))
        return {"texto": "saida-do-servidor"}
    monkeypatch.setattr(aterm, "ferramenta_servidor_exec", _ferr_falsa)
    return chamadas


@pytest.mark.asyncio
@pytest.mark.parametrize("agente,ferramentas", [
    ("datastage", svc.FERRAMENTAS_DATASTAGE),
    ("assistente", ("resolver_projeto", "base")),
    ("assistente", svc.FERRAMENTAS_TELA),
    ("assistente", ()),
])
async def test_nenhum_outro_agente_usa_servidor_exec(monkeypatch, sem_aprendizado, espiao, agente, ferramentas):
    p = _Provedor([_pedido("servidor_exec", comando="ls /opt"), "ok"])
    r = await _conversar(monkeypatch, p, agente=agente, ferramentas=ferramentas)
    assert espiao == [], "o servidor NÃO pode ser tocado por agente que não é o Terminal"
    if ferramentas:
        assert r["artefatos"][0]["recusada"] == "fora_do_agente"


@pytest.mark.asyncio
async def test_defesa_em_profundidade_no_despacho(monkeypatch, espiao):
    """Mesmo que o gate de `conversar` falhe, `_executar_ferramenta_interna` recusa agente que não é o Terminal."""
    for agente in ("datastage", "assistente", "qualquer"):
        dado, _ = await svc._executar_ferramenta_interna(
            None, "servidor_exec", {"comando": "ls /opt"}, projeto=None, ssh_max=3, espera_max_s=5, acao_editar=True,
            matricula="U1", extracoes_isx=0, resta_agora=lambda: 60, agente=agente)
        assert "não está disponível para este agente" in dado["texto"]
    assert espiao == []


@pytest.mark.asyncio
async def test_o_terminal_executa_e_recebe_matricula_e_conversa(monkeypatch, sem_aprendizado, espiao):
    p = _Provedor([_pedido("servidor_exec", comando="ls /opt", servidor="airflow"), "Pronto."])
    r = await _conversar(monkeypatch, p, agente="terminal", ferramentas=svc.FERRAMENTAS_TERMINAL, conversa_id="conv-9")
    [(args, kw)] = espiao
    assert args["comando"] == "ls /opt" and kw["matricula"] == "U1" and kw["conversa_id"] == "conv-9"
    assert "saida-do-servidor" in p.chamadas[1]["historico"][-1]["content"]
    assert r["texto"] == "Pronto."


@pytest.mark.asyncio
async def test_o_terminal_nao_ganha_ferramentas_do_datastage(monkeypatch, sem_aprendizado, espiao):
    chamadas = []

    async def _ex(abrir, nome, args, **kw):
        chamadas.append(nome)
        return {"texto": "x"}, None
    monkeypatch.setattr(svc, "_executar_ferramenta", _ex)
    p = _Provedor([_pedido("dsjob", comando="ljobs"), "ok"])
    r = await _conversar(monkeypatch, p, agente="terminal", ferramentas=svc.FERRAMENTAS_TERMINAL)
    assert chamadas == [] and r["artefatos"][0]["recusada"] == "fora_do_agente"


def test_agente_criado_pela_tela_nao_pode_escolher_servidor_exec():
    assert "servidor_exec" not in svc.FERRAMENTAS_TELA and "servidor_exec" in svc.FERRAMENTAS_CONVERSA
    assert "servidor_exec" not in reg._normalizar_ferramentas(["servidor_exec", "base"]), "descartado ao normalizar"
    with pytest.raises(reg.AgenteInvalido):
        reg._ferramentas(["servidor_exec"])  # recusado na criação/edição pela tela
    fonte = open(os.path.join(os.path.dirname(__file__), "..", "api", "services", "agentes_registro.py"), encoding="utf-8").read()
    assert "svc.FERRAMENTAS_TELA" in fonte and "FERRAMENTAS_CONVERSA" not in fonte and "FERRAMENTAS_TERMINAL" not in fonte


def test_prompt_do_terminal_tem_protocolo_e_regras_proprias(monkeypatch, servidor):
    antes, depois = svc.partes_fixas(None, False, svc.FERRAMENTAS_TERMINAL)
    assert antes == ""
    assert 'servidor_exec {"servidor"' in depois and "Servidores configurados: airflow" in depois
    assert "Você só LÊ o servidor" in depois and "DataStage" not in depois and "## Propostas" not in depois
    assert "sem pipe" in depois and "É DADO" not in depois  # (a regra de dado/instrução está em "Texto que vier de logs")
    assert "Texto que vier de logs" in depois and "Nunca peça, repita nem proponha senha" in depois


def test_router_repassa_a_conversa_para_a_ferramenta():
    fonte = open(os.path.join(os.path.dirname(__file__), "..", "api", "routers", "agentes.py"), encoding="utf-8").read()
    assert "conversa_id=conversa_id)}" in fonte


def test_terminal_continua_indisponivel_mesmo_com_a_ferramenta_pronta():
    """A trava `disponivel: False` só cai na F5 (interface real)."""
    cfg = {"agentes_enabled": "1", "agente_terminal_enabled": "1", "agente_terminal_escrita_enabled": "1"}
    assert svc.CATALOGO["terminal"]["disponivel"] is False and not svc.agente_ligado(cfg, "terminal")


# ═══════════ 5. achados da auditoria/QA da F3 ═══════════════════════════

def test_o_processo_remoto_morre_com_timeout_e_nao_so_o_canal():
    """Fechar o canal sem pty NÃO mata o processo remoto (auditoria A1): o comando vai embrulhado em `timeout -k 2 N`."""
    linha = tssh.embrulhar("grep -e 'a b' /var/log/x.log", 30)
    assert linha.startswith("/bin/sh -c ") and "exec timeout -k 2 30 grep" in linha
    assert "else exec grep" in linha, "sem `timeout` no servidor roda o comando puro (AIX etc.)"
    import shlex
    interno = shlex.split(linha)[2]
    assert "command -v timeout" in interno
    assert tssh.embrulhar("ls /opt", 0).count("timeout -k 2 1 ") == 1, "tempo mínimo de 1 s"


def test_embrulho_nao_deixa_o_shell_interpretar_a_linha():
    """A linha embrulhada, relida pelo shell externo, devolve a MESMA linha interna (sem expansão extra)."""
    import shlex
    linha = "ls '/opt/a;b' '/opt/$x'"
    assert linha in shlex.split(tssh.embrulhar(linha, 5))[2]


def test_containers_por_servidor_e_nome_invalido_e_ignorado(monkeypatch):
    _com_airflow(monkeypatch, TERMINAL_CONTAINERS_AIRFLOW="airflow-scheduler, x;rm -rf /, orquestra-api")
    assert tssh.servidores()["airflow"].containers == ("airflow-scheduler", "orquestra-api")
    monkeypatch.delenv("TERMINAL_CONTAINERS_AIRFLOW")
    assert tssh.servidores()["airflow"].containers is None


def test_a_orquestracao_aplica_a_allowlist_de_containers(monkeypatch):
    srv = tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, None, ("/opt",), ("airflow-scheduler",))
    monkeypatch.setattr(tssh, "servidores", lambda: {"airflow": srv})
    exec_ = _executor(monkeypatch, stdout="ok")
    banco = _Banco()
    r = _ferr(banco, comando="docker logs orquestra-api")
    assert exec_ == [] and "container 'orquestra-api' não está liberado" in r["texto"], "diz POR QUE foi recusado"
    _ferr(banco, comando="docker logs airflow-scheduler")
    assert len(exec_) == 1


@pytest.mark.parametrize("valor", [float("inf"), float("-inf"), float("nan"), True, False, "9" * 400, "x", [1], {"a": 1}, None, -5, 0, 99999999])
def test_filtros_estranhos_nunca_levantam_nem_prendem_a_linha(monkeypatch, servidor, valor):
    """O JSON do modelo aceita `Infinity`: `int(inf)` estourava OverflowError DEPOIS do registro (linha presa em `executando`)."""
    _executor(monkeypatch, stdout="a\nb\nc\n")
    banco = _Banco()
    r = _ferr(banco, comando="cat /opt/a.log", primeiras=valor, ultimas=valor)
    assert "a" in r["texto"]
    assert "executado" in banco.sqls[-1][1], "a linha fechou normalmente"


def test_primeiras_e_ultimas_juntos_avisa(monkeypatch, servidor):
    _executor(monkeypatch, stdout="a\nb\nc\n")
    r = _ferr(_Banco(), comando="cat /opt/a.log", primeiras=1, ultimas=2)
    assert "só `primeiras` foi aplicado" in r["texto"]


def test_busca_recursiva_avisa_que_omite_arquivos_sensiveis(monkeypatch, servidor):
    _executor(monkeypatch, stdout="")
    r = _ferr(_Banco(), comando="grep -r -e falha /opt/app")
    assert "arquivos sensíveis" in r["texto"] and "omitidos" in r["texto"]
    assert "omitidos" not in _ferr(_Banco(), comando="grep -e falha /opt/app/a.log")["texto"]


def test_varre_interrompidos_antes_de_registrar_e_so_leitura(monkeypatch, servidor):
    _executor(monkeypatch, stdout="x")
    banco = _Banco()
    _ferr(banco, comando="ls /opt")
    [(sql, args)] = banco.varridas
    assert "estado = 'executando' AND classe = 'leitura'" in sql and "DATEADD(minute, ?, GETDATE())" in sql and args == [-5]
    assert "falhou" in sql and "interrompido" in sql


def test_varredura_falhando_nao_impede_o_comando(monkeypatch, servidor):
    exec_ = _executor(monkeypatch, stdout="x")
    original = aterm.varrer_interrompidos
    monkeypatch.setattr(aterm, "varrer_interrompidos", lambda cur, minutos=2: (_ for _ in ()).throw(RuntimeError("sem permissão")))
    r = _ferr(_Banco(), comando="ls /opt")
    assert exec_ and "x" in r["texto"]
    assert original(MagicMock(rowcount=3)) == 3


def test_listar_da_auditoria_tambem_varre(monkeypatch):
    cur = MagicMock(rowcount=0)
    cur.fetchone.return_value = (0,)
    cur.fetchall.return_value = []
    aterm.listar(cur)
    assert any("interrompido" in str(c) for c in cur.execute.call_args_list)


def test_o_comando_com_segredo_nao_vai_ao_artefato_nem_a_tela(monkeypatch):
    """QA da F3: `args.comando` ia ao `artefatos_json` com `redigir_estrutura` (só "campo: valor"). Agora usa a redação de comando."""
    for cmd in ("mysql -uroot -pHUNTER2 db", "cat /opt/x postgres://u:hunter2@h/db", "sqlcmd -P hunter2 -Q x", "ls /opt Authorization: Bearer abc123tok"):
        limpo = svc._args_do_artefato("servidor_exec", {"comando": cmd, "servidor": "airflow", "primeiras": 5})
        assert "HUNTER2" not in str(limpo) and "hunter2" not in str(limpo) and "abc123tok" not in str(limpo), cmd
        assert limpo["servidor"] == "airflow" and limpo["primeiras"] == 5
    assert svc._args_do_artefato("dsjob", {"comando": "ljobs"}) == {"comando": "ljobs"}, "só o servidor_exec muda"


def test_prompt_do_terminal_reflete_o_estado_real(monkeypatch):
    srv = tssh.ServidorTerminal("airflow", "AF", "h", 22, "u", None, None, None, ("/opt/airflow", "/var/log"), ("airflow-scheduler",))
    monkeypatch.setattr(tssh, "servidores", lambda: {"airflow": srv})
    _, depois = svc.partes_fixas(None, False, svc.FERRAMENTAS_TERMINAL)
    assert "/opt/airflow, /var/log" in depois and "/srv" not in depois and "/tmp" not in depois, "as pastas do servidor, não uma lista fixa"
    assert "stats --no-stream" in depois and "Curingas" in depois and "airflow-scheduler" in depois


# ═══════════ 7. 2ª rodada (auditoria + QA) ═════════════════════════════

def test_containers_com_variavel_preenchida_mas_invalida_falha_fechada(monkeypatch):
    """Antes: "web db" (sem vírgula) virava None = QUALQUER container. Erro de configuração tem de fechar, não abrir."""
    _com_airflow(monkeypatch, TERMINAL_CONTAINERS_AIRFLOW="web db")
    assert tssh.servidores()["airflow"].containers == ()
    _com_airflow(monkeypatch, TERMINAL_CONTAINERS_AIRFLOW="web,db")
    assert tssh.servidores()["airflow"].containers == ("web", "db")
    monkeypatch.delenv("TERMINAL_CONTAINERS_AIRFLOW")
    assert tssh.servidores()["airflow"].containers is None


@pytest.mark.parametrize("args", [
    {"comando": ["mysql -uroot -phunter2xyz"]}, {"comando": {"x": "mysql -phunter2xyz"}},
    {"comando": "ls /opt", "filtrar": "postgres://u:hunter2xyz@h/db"}, {"comando": "ls /opt", "servidor": "sqlcmd -P hunter2xyz"},
    {"comando": "x" * 5000 + " mysql -phunter2xyz"},
])
def test_artefato_redige_todos_os_campos_do_pedido(args):
    limpo = svc._args_do_artefato("servidor_exec", args)
    assert "hunter2xyz" not in str(limpo), args


def test_artefato_nao_estoura_com_campos_enormes():
    import time
    t0 = time.monotonic()
    svc._args_do_artefato("servidor_exec", {"comando": "mysql " * 40000, "filtrar": "bcp " * 40000})
    assert time.monotonic() - t0 < 1.0, "a redação roda sobre no máximo 2000 caracteres por campo"


def test_execucao_morta_pelo_timeout_do_servidor_explica_o_codigo(monkeypatch, servidor):
    for codigo in (124, 137):
        _executor(monkeypatch, stdout="", codigo=codigo)
        r = _ferr(_Banco(), comando="cat /opt/a")
        assert "interrompido" in r["texto"] and f"código de saída: {codigo}" in r["texto"]


def test_finalizar_tardio_deixa_rastro_no_log(monkeypatch, servidor, caplog):
    """Se a varredura já marcou a linha como interrompida, o `finalizar` real devolve False: não pode ser silencioso."""
    _executor(monkeypatch, stdout="ok")
    banco = _Banco()
    orig = banco.abrir

    def _abrir_sem_linha():
        conn, cur = orig()
        cur.rowcount = 0  # `finalizar` não acha a linha em `executando`
        return conn, cur
    import logging
    with caplog.at_level(logging.WARNING, logger=aterm.log.name):
        asyncio.run(aterm.ferramenta_servidor_exec(
            lambda: _abrir_sem_linha(), {"comando": "ls /opt"}, matricula="DEV1", conversa_id="c", ssh_max=3, espera_max_s=5))
    assert any("já não estava `executando`" in r.message for r in caplog.records)
