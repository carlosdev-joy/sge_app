"""Agente Terminal, F2 (fundação) — spec docs/spec-agente-terminal.md.

Catálogo, RBAC (uso × escrita), interruptores, auditoria (`agentes_terminal`), rota admin e
migrations 197/198. Banco e SQL Server são dublês: nada aqui executa comando em servidor.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_registro as reg  # noqa: E402
from services import agentes_terminal as aterm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
TERMINAL = svc.CATALOGO["terminal"]
LIGADO = {"agentes_enabled": "1", "agente_terminal_enabled": "1", "agente_terminal_escrita_enabled": "1"}


def _user(perfil="desenvolvedor", extras=("agente_terminal",), perms=("tela_agentes",)):
    return {"matricula": "DEV1", "perfil": perfil, "permissoes": list(perms), "permissoes_extra": list(extras)}


# ═══════════ 1. catálogo e config ═══════════════════════════════════════

def test_terminal_esta_no_catalogo_e_nasce_desligado():
    assert TERMINAL["recurso"] == "agente_terminal"
    assert TERMINAL["recurso_escrita"] == "agente_terminal_escrita"
    assert TERMINAL["acesso"] == "manual" and TERMINAL["concessao"] == "manual_por_usuario"
    assert TERMINAL["perfis_elegiveis"] == ("desenvolvedor",)
    assert svc.CONFIG_DEFAULTS["agente_terminal_enabled"] == "0"
    assert svc.CONFIG_DEFAULTS["agente_terminal_escrita_enabled"] == "0"
    assert not svc.agente_ligado({}, "terminal")
    assert not svc.agente_ligado({"agentes_enabled": "1"}, "terminal"), "o interruptor do agente é separado do geral"


def test_mapa_de_recursos_tem_os_dois_papeis_sem_colidir():
    mapa = svc.mapa_de_recursos()
    assert mapa["agente_terminal"][1] == "uso"
    assert mapa["agente_terminal_escrita"][1] == "escrita"
    assert mapa["agente_terminal_escrita"][0]["id"] == "terminal"


@pytest.mark.parametrize("agente_id", ["terminal", "terminal_escrita", "x_escrita", "escrita", "terminal_curador"])
def test_ids_que_colidiriam_com_o_terminal_sao_reservados(agente_id):
    """Um agente criado pela tela com `terminal_escrita` geraria o MESMO recurso do Terminal e o
    `mapa_de_recursos` derrubaria o catálogo inteiro ("recurso repetido")."""
    assert reg.id_reservado(agente_id)


def test_prompt_padrao_existe_para_o_terminal():
    from services import agentes_prompt as ap
    assert ap.tem_padrao("terminal")
    texto = ap.padrao("terminal")
    assert "instrução" in texto.lower() or "DADO" in texto  # tratar saída de comando como dado
    assert "senha" in texto.lower()


# ═══════════ 2. RBAC: uso × escrita ═════════════════════════════════════

def test_escrita_exige_uso_e_o_recurso_proprio_usuario_a_usuario():
    so_uso = _user(extras=("agente_terminal",))
    assert svc.motivo_sem_acesso(so_uso, TERMINAL) is None
    assert svc.motivo_sem_acesso(so_uso, TERMINAL, escrita=True)[0] == "agente_escrita_nao_liberada"
    ambos = _user(extras=("agente_terminal", "agente_terminal_escrita"))
    assert svc.motivo_sem_acesso(ambos, TERMINAL, escrita=True) is None
    so_escrita = _user(extras=("agente_terminal_escrita",))
    assert svc.motivo_sem_acesso(so_escrita, TERMINAL, escrita=True)[0] == "agente_nao_liberado", \
        "escrita sem o direito de usar o agente não vale"


def test_recurso_vindo_so_do_perfil_nao_da_escrita():
    """`permissoes` inclui o que vem do PERFIL; só `permissoes_extra` (por usuário) conta."""
    u = _user(extras=("agente_terminal",), perms=("tela_agentes", "agente_terminal_escrita"))
    assert svc.motivo_sem_acesso(u, TERMINAL, escrita=True)[0] == "agente_escrita_nao_liberada"


def test_admin_passa_e_perfil_nao_elegivel_nunca_escreve():
    assert svc.motivo_sem_acesso(_user(perfil="admin", extras=(), perms=(PERM_ADMIN,)), TERMINAL, escrita=True) is None
    for perfil in ("consulta", "operador", "analista"):
        u = _user(perfil=perfil, extras=("agente_terminal", "agente_terminal_escrita"))
        assert svc.motivo_sem_acesso(u, TERMINAL, escrita=True)[0] == "agente_nao_elegivel", perfil


def test_agente_sem_recurso_de_escrita_nunca_escreve():
    ds = svc.CATALOGO["datastage"]
    u = _user(extras=("agente_datastage", "agente_terminal_escrita"))
    assert svc.motivo_sem_acesso(u, ds, escrita=True) is not None


def test_elegibilidade_do_admin_user_perm_set_cobre_o_recurso_de_escrita():
    """`user_perm_set` recusa (422) conceder `agente_*` a perfil inelegível usando
    `agente_do_recurso` + `elegivel_por_perfil` — o recurso de escrita tem de passar por ali."""
    ag = svc.agente_do_recurso("agente_terminal_escrita")
    assert ag is not None and ag["id"] == "terminal"
    assert svc.elegivel_por_perfil("terminal", "desenvolvedor")
    assert not svc.elegivel_por_perfil("terminal", "operador")
    assert not svc.elegivel_por_perfil("terminal", "consulta")


def test_kill_switch_da_escrita(monkeypatch):
    monkeypatch.setitem(TERMINAL, "disponivel", True)
    assert svc.escrita_ligada(LIGADO, "terminal")
    assert not svc.escrita_ligada({**LIGADO, "agente_terminal_escrita_enabled": "0"}, "terminal")
    assert not svc.escrita_ligada({**LIGADO, "agente_terminal_enabled": "0"}, "terminal"), "agente desligado = sem escrita"
    assert not svc.escrita_ligada({**LIGADO, "agentes_enabled": "0"}, "terminal"), "geral desligado = sem escrita"
    assert not svc.escrita_ligada(LIGADO, "datastage"), "agente sem config_escrita nunca escreve"
    assert not svc.escrita_ligada(LIGADO, "inexistente")


def test_catalogo_do_usuario_informa_escrita_so_com_tudo_alinhado(monkeypatch):
    monkeypatch.setitem(TERMINAL, "disponivel", True)  # a trava da F2 é testada à parte
    u = _user(extras=("agente_terminal", "agente_terminal_escrita"))
    [item] = [a for a in svc.catalogo_do_usuario(u, LIGADO) if a["id"] == "terminal"]
    assert item["escrita"] is True
    [item] = [a for a in svc.catalogo_do_usuario(u, {**LIGADO, "agente_terminal_escrita_enabled": "0"}) if a["id"] == "terminal"]
    assert item["escrita"] is False, "kill switch desligado: o front não mostra os botões"
    [item] = [a for a in svc.catalogo_do_usuario(_user(), LIGADO) if a["id"] == "terminal"]
    assert item["escrita"] is False, "só uso, sem o recurso de escrita"
    assert not [a for a in svc.catalogo_do_usuario(u, {**LIGADO, "agente_terminal_enabled": "0"}) if a["id"] == "terminal"]


def test_require_agente_escrita_devolve_403_nomeado():
    import asyncio
    dep = svc.require_agente("terminal", escrita=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(dep(_user(extras=("agente_terminal",))))
    assert e.value.status_code == 403 and e.value.detail["code"] == "agente_escrita_nao_liberada"
    ok = _user(extras=("agente_terminal", "agente_terminal_escrita"))
    assert asyncio.run(dep(ok)) is ok


# ═══════════ 3. auditoria (service) ═════════════════════════════════════

def _cur(rowcount=1):
    cur = MagicMock()
    cur.rowcount = rowcount
    return cur


def test_preparar_comando_redige_normaliza_e_da_hash_estavel():
    t1, h1, red1 = aterm.preparar_comando("  ls -la /opt  ")
    assert t1 == "ls -la /opt" and len(h1) == 64 and red1 is False
    assert aterm.preparar_comando("ls -la /opt")[1] == h1, "o hash é do texto aparado"
    with pytest.raises(aterm.AuditoriaInvalida):
        aterm.preparar_comando("   ")


@pytest.mark.parametrize("comando,segredo", [
    ("mysql -u root -pHUNTER2 db", "HUNTER2"),
    ("docker login -u a -p hunter2", "hunter2"),
    ("sshpass -p hunter2 ssh x", "hunter2"),
    ("curl -u admin:hunter2 http://x", "hunter2"),
    ("curl http://user:hunter2@host/", "hunter2"),
    ("psql postgresql://u:hunter2@h/db", "hunter2"),
    ("dsjob -run -param DB_PASS=hunter2 p j", "hunter2"),
    ("curl -H 'Authorization: Bearer abc123SECRET' http://x", "abc123SECRET"),
    ("airflow dags list --token=ZZZ999", "ZZZ999"),
    ("app --password hunter2 --x 1", "hunter2"),
    ("curl -H 'password: hunter2' https://x", "hunter2"),
    # 2ª rodada do QA: aspas, @ na senha, cabeçalhos e clientes específicos
    ("mysql -p'x y' db", "x y"),
    ("sshpass -p 'a b' ssh h", "a b"),
    ("curl https://u:p@ss@host/x", "p@ss"),
    ("curl -u user:pa'ss' http://x", "ss'"),
    ('curl -H "X-Auth: s3cr3t" http://x', "s3cr3t"),
    ("curl -H 'Cookie: sessao=abc999' http://x", "abc999"),
    ("sqlcmd -S h -U u -P Hunter2 -Q 'select 1'", "Hunter2"),
    ("export TOKEN=abc999 && ls", "abc999"),
    ('app --password "a b c" --x 1', "a b c"),
])
def test_segredo_de_linha_de_comando_nunca_fica_em_claro(comando, segredo):
    """QA da F2: `af.redigir` só vê "campo: valor"; as formas de linha de comando precisam de regra própria."""
    texto, h, redigido = aterm.preparar_comando(comando)
    assert segredo not in texto and redigido is True
    assert segredo.encode() not in h.encode()


@pytest.mark.parametrize("comando", [
    "mkdir -p /opt/x", "ls -p /opt", "ssh -p 2222 host", "tail -n 50 /var/log/a.log",
    "dsjob -run -param X=1 proj job", "ps aux", "df -h",
    # 2ª rodada do QA: falsos positivos que inutilizariam a leitura quando a F3 ligar o agente
    "find / -name x -print", "ls -pa", "cp -pr a b", "sort -pk1 f", "grep -r token /opt", "ls /opt/tokens",
    "env | grep -i token", "echo $SECRET | wc -c", "ps -p 123", "docker ps --format '{{.Names}}'",
    "tail -f /var/log/x.log", "mysql -u root -e 'show databases'", "airflow dags list-runs -d malha"])
def test_comando_comum_nao_e_mascarado(comando):
    """Sem falso positivo nos comandos de todo dia (`-p` é porta/parents; `-param` é do dsjob)."""
    texto, _, redigido = aterm.preparar_comando(comando)
    assert texto == comando and redigido is False


def test_redacao_nao_tem_regex_catastrofica():
    import time
    for entrada in ("a" * 6000 + " -p " + "b" * 6000, "mysql " + "-x " * 3000 + "-p", "://" + "a:" * 3000, "Bearer " + "x" * 6000):
        t0 = time.monotonic()
        aterm.preparar_comando(entrada)
        assert time.monotonic() - t0 < 0.5, entrada[:30]


def test_comando_longo_e_cortado_por_utf16_sem_partir_caractere():
    texto, _, _ = aterm.preparar_comando("é" * 5000)
    assert texto == "é" * aterm.MAX_COMANDO
    emoji, _, _ = aterm.preparar_comando("😀" * 3000)  # 2 unidades UTF-16 cada
    assert len(emoji.encode("utf-16-le")) // 2 <= aterm.MAX_COMANDO
    assert set(emoji) == {"😀"}, "nenhum surrogate cortado ao meio"


def test_surrogate_solto_nao_vira_500():
    texto, h, _ = aterm.preparar_comando("echo x\ud83d")
    texto.encode("utf-8")  # o que se grava é codificável: nada de UnicodeEncodeError
    assert len(h) == 64


def test_registrar_estado_nasce_da_classe_e_so_a_proposta_ganha_prazo():
    cur = _cur()
    r = aterm.registrar(cur, conversa_id="c1", matricula="DEV1", servidor="airflow",
                        comando="airflow dags unpause x", classe="escrita")
    assert r["estado"] == "proposto" and r["validade_s"] == 120 and r["redigido"] is False
    assert aterm.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="ls",
                           classe="leitura")["estado"] == "executando"
    r3 = aterm.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="rm -rf /", classe="proibido")
    assert r3["estado"] == "bloqueado" and r3["validade_s"] is None


def test_horarios_vem_do_relogio_do_banco_nao_do_python():
    """O relógio da API anda horas fora do SQL Server no DEV (medido na Malha): o prazo é calculado no banco."""
    cur = _cur()
    aterm.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="x", classe="escrita")
    sql, args = cur.execute.call_args[0]
    assert "GETDATE()" in sql and "DATEADD(second, ?, GETDATE())" in sql
    assert not any(isinstance(a, datetime) for a in args)


def test_comando_com_segredo_so_pode_ser_registrado_como_proibido():
    cur = _cur()
    for classe in ("leitura", "escrita"):
        with pytest.raises(aterm.AuditoriaInvalida):
            aterm.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a",
                            comando="mysql -pHUNTER2", classe=classe)
    cur.execute.assert_not_called()
    r = aterm.registrar(cur, conversa_id=None, matricula="DEV1", servidor="a", comando="mysql -pHUNTER2", classe="proibido")
    assert r["redigido"] is True and "HUNTER2" not in r["comando"]
    assert "HUNTER2" not in str(cur.execute.call_args)


@pytest.mark.parametrize("campo,valor", [("classe", "qualquer"), ("matricula", "  ")])
def test_registrar_recusa_entrada_invalida_sem_tocar_o_banco(campo, valor):
    kw = dict(conversa_id=None, matricula="DEV1", servidor="s", comando="ls", classe="leitura")
    kw[campo] = valor
    cur = _cur()
    with pytest.raises(aterm.AuditoriaInvalida):
        aterm.registrar(cur, **kw)
    cur.execute.assert_not_called()


ID = "11111111-1111-1111-1111-111111111111"


def test_iniciar_so_libera_proposta_viva_de_escrita_sem_segredo():
    cur = _cur()
    assert aterm.iniciar(cur, ID, "DEV1") is True
    sql, args = cur.execute.call_args[0]
    for trecho in ("estado = 'proposto'", "classe = 'escrita'", "redigido = 0", "expira_em > GETDATE()"):
        assert trecho in sql, trecho
    assert args == ["DEV1", ID]
    cur.rowcount = 0
    assert aterm.iniciar(cur, ID, "DEV1") is False, "duplo clique / prazo vencido / já decidido"
    with pytest.raises(aterm.AuditoriaInvalida):
        aterm.iniciar(cur, ID, "  ")


@pytest.mark.parametrize("estado,de", [("executado", ("executando",)), ("falhou", ("executando",)),
                                       ("recusado", ("proposto",)), ("expirado", ("proposto",))])
def test_finalizar_so_anda_pelas_transicoes_permitidas(estado, de):
    cur = _cur()
    assert aterm.finalizar(cur, ID, estado, codigo_saida=0, duracao_ms=12, saida="ok") is True
    sql, args = cur.execute.call_args[0]
    assert f"estado IN ({','.join('?' for _ in de)})" in sql
    assert tuple(args[-len(de):]) == de, "executado/falhou só de executando; recusado/expirado só de proposto"
    cur.rowcount = 0
    assert aterm.finalizar(cur, ID, estado) is False, "replay: já era final"


def test_finalizar_nao_aceita_estado_que_nao_e_final_nem_id_ruim():
    for estado in ("proposto", "executando", "bloqueado", "confirmado"):
        with pytest.raises(aterm.AuditoriaInvalida):
            aterm.finalizar(_cur(), ID, estado)
    with pytest.raises(aterm.AuditoriaInvalida):
        aterm.finalizar(_cur(), "não-é-uuid", "executado")
    with pytest.raises(aterm.AuditoriaInvalida):
        aterm.iniciar(_cur(), "' OR 1=1 --", "DEV1")


def test_recusar_grava_quem_recusou():
    cur = _cur()
    aterm.finalizar(cur, ID, "recusado", decidido_por="DEV1")
    sql, args = cur.execute.call_args[0]
    assert "decidido_por = COALESCE(?, decidido_por)" in sql and "DEV1" in args


def test_listar_valida_antes_de_tocar_o_banco_e_limita():
    cur = _cur()
    for kw in ({"estado": "x"}, {"classe": "y"}, {"desde": "ontem"}, {"ate": "31/12/2026"}):
        with pytest.raises(aterm.AuditoriaInvalida):
            aterm.listar(cur, **kw)
    cur.execute.assert_not_called()
    cur.fetchone.return_value = (0,)
    cur.fetchall.return_value = []
    assert aterm.listar(cur, limite=10_000, offset=-5)["limite"] == aterm.LIMITE_MAX
    assert aterm.listar(cur, limite=0)["limite"] == 1


def test_listar_combina_filtros_e_trata_ate_como_inclusivo():
    cur = _cur()
    cur.fetchone.return_value = (1,)
    cur.fetchall.return_value = [(ID, "c1", "DEV1", "airflow", "ls", "leitura",
                                  "executado", None, 0, 5, "ok", "1.1.1.1", datetime(2026, 11, 4, 10), None, None, None)]
    out = aterm.listar(cur, matricula=" DEV1 ", estado="executado", classe="leitura", desde="2026-11-01", ate="2026-11-04")
    assert out["total"] == 1 and out["itens"][0]["criado_em"] == "2026-11-04T10:00:00"
    assert out["itens"][0]["cmd_id"] == ID
    sql, args = next(c[0] for c in cur.execute.call_args_list if "COUNT(*)" in c[0][0])  # a 1ª chamada é a varredura de interrompidos
    assert all(f"{c} = ?" in sql for c in ("matricula", "estado", "classe"))
    assert args[0] == "DEV1" and args[3] == datetime(2026, 11, 1) and args[4] == datetime(2026, 11, 5), \
        "`ate` é inclusivo: o filtro vai até < dia seguinte"


def test_valores_do_filtro_nunca_vao_no_texto_do_sql():
    cur = _cur()
    cur.fetchone.return_value = (0,)
    cur.fetchall.return_value = []
    aterm.listar(cur, matricula="x'; DROP TABLE t;--")
    for chamada in cur.execute.call_args_list:
        assert "DROP" not in chamada[0][0]


# ═══════════ 3b. trava de disponibilidade e kill switch ════════════════

def test_terminal_nao_esta_disponivel_ate_a_f5_mesmo_com_tudo_ligado():
    """QA da F2: sem ferramentas ele seria um chat que inventa comandos/saídas de servidor."""
    assert TERMINAL["disponivel"] is False
    assert svc.agente_ligado(LIGADO, "terminal") is False
    u = _user(extras=("agente_terminal", "agente_terminal_escrita"))
    assert not [a for a in svc.catalogo_do_usuario(u, LIGADO) if a["id"] == "terminal"]
    assert svc.escrita_ligada(LIGADO, "terminal") is False, "sem agente ligado não há escrita"


def test_agente_do_codigo_sem_a_flag_continua_disponivel():
    assert svc.agente_ligado({"agentes_enabled": "1", "agente_datastage_enabled": "1"}, "datastage") is True


def test_conversar_com_o_terminal_indisponivel_e_recusado(cliente, monkeypatch):
    """Rota genérica `/agentes/{id}/conversar`: ligado + permissão + admin NÃO abrem o Terminal.
    A config é a REAL do dublê (tudo ligado) — o 503 só pode vir da trava de disponibilidade — e um
    teste de mutação (flag removida) prova que sem ela a rota passaria da checagem."""
    c, estado = cliente
    estado["cur"].config = dict(LIGADO)
    for rota in ("/agentes/terminal/conversar", "/agentes/terminal/conversar/stream"):
        r = c.post(rota, json={"mensagem": "liste os containers"})
        assert r.status_code == 503, (rota, r.status_code, r.text)
        assert r.json()["detail"]["code"] in ("agente_desligado", "agente_indisponivel"), r.text
    # mutação: sem a trava, a MESMA requisição deixa de ser recusada por "desligado"
    monkeypatch.setitem(TERMINAL, "disponivel", True)
    r = c.post("/agentes/terminal/conversar", json={"mensagem": "liste os containers"})
    detalhe = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
    codigo = detalhe.get("code") if isinstance(detalhe, dict) else None
    assert codigo not in ("agente_desligado", "agente_indisponivel"), (r.status_code, r.text)


def test_exigir_escrita_aplica_o_kill_switch_ate_ao_admin(monkeypatch):
    monkeypatch.setitem(TERMINAL, "disponivel", True)
    ok = {**LIGADO}
    admin = {"matricula": "A", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}
    assert svc.exigir_escrita(admin, ok, "terminal")["id"] == "terminal"
    off = {**LIGADO, "agente_terminal_escrita_enabled": "0"}
    for quem in (admin, _user(extras=("agente_terminal", "agente_terminal_escrita"))):
        with pytest.raises(HTTPException) as e:
            svc.exigir_escrita(quem, off, "terminal")
        assert e.value.status_code == 503 and e.value.detail["code"] == "agente_escrita_desligada"
    with pytest.raises(HTTPException) as e:
        svc.exigir_escrita(_user(), ok, "terminal")  # sem o recurso de escrita
    assert e.value.status_code == 403 and e.value.detail["code"] == "agente_escrita_nao_liberada"
    with pytest.raises(HTTPException) as e:
        svc.exigir_escrita(admin, ok, "datastage")  # agente sem escrita
    assert e.value.status_code == 503


# ═══════════ 4. rota admin e config ═════════════════════════════════════

class _Cur:
    def __init__(self, tabela_ausente=False):
        self.tabela_ausente = tabela_ausente
        self.config: dict[str, str] = {}
        self.gravados: dict[str, str] = {}
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        s = sql.lower()
        if "etl_agente_terminal_cmd" in s and self.tabela_ausente:
            raise Exception("42S02", "Invalid object name 'dbo.etl_agente_terminal_cmd'")
        if "merge" in s and "etl_app_config" in s and len(params) >= 2:
            self.gravados[str(params[0])] = str(params[1])
            self._rows = []
        elif s.lstrip().startswith("select config_key") and "etl_app_config" in s:
            self._rows = [(k, v) for k, v in self.config.items() if k in params]  # a config que o teste definiu
        elif "count(*)" in s:
            self._rows = [(0,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        hook = getattr(self._cur, "commit_hook", None)
        if hook:
            hook()

    def close(self):
        pass


@pytest.fixture
def cliente():
    estado = {"perms": [PERM_ADMIN], "cur": _Cur()}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADM1", "perfil": "admin", "permissoes": estado["perms"], "permissoes_extra": []}
    with patch("routers.agentes.get_db_conn", side_effect=lambda: _Conn(estado["cur"])):
        yield TestClient(_app), estado
    _app.dependency_overrides.pop(get_current_user, None)


def test_auditoria_so_para_admin(cliente):
    c, estado = cliente
    estado["perms"] = ["tela_agentes"]
    assert c.get("/agentes/terminal/auditoria").status_code == 403


def test_auditoria_responde_e_valida_filtros(cliente):
    c, _ = cliente
    r = c.get("/agentes/terminal/auditoria", params={"estado": "executado", "limite": 10})
    assert r.status_code == 200 and r.json()["total"] == 0 and r.json()["itens"] == []
    r = c.get("/agentes/terminal/auditoria", params={"estado": "bobagem"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "auditoria_filtro_invalido"
    assert c.get("/agentes/terminal/auditoria", params={"desde": "ontem"}).status_code == 422
    assert c.get("/agentes/terminal/auditoria", params={"limite": 9999}).status_code == 422


def test_auditoria_sem_a_migration_degrada_em_503_nomeando_a_migration(cliente):
    c, estado = cliente
    estado["cur"] = _Cur(tabela_ausente=True)
    r = c.get("/agentes/terminal/auditoria")
    assert r.status_code == 503 and "197_agente_terminal" in r.json()["detail"]["message"]


def test_config_admin_grava_os_dois_interruptores_e_zero_desliga(cliente):
    c, estado = cliente
    r = c.post("/agentes/admin/config", json={"agente_terminal_enabled": True, "agente_terminal_escrita_enabled": "0"})
    assert r.status_code == 200
    assert estado["cur"].gravados == {"agente_terminal_enabled": "1", "agente_terminal_escrita_enabled": "0"}


def test_config_admin_get_traz_recurso_e_kill_switch_da_escrita(cliente):
    c, _ = cliente
    ag = {a["id"]: a for a in c.get("/agentes/admin/config").json()["agentes"]}
    assert ag["terminal"]["recurso_escrita"] == "agente_terminal_escrita"
    assert ag["terminal"]["config_escrita"] == "agente_terminal_escrita_enabled"
    assert ag["datastage"]["recurso_escrita"] is None and ag["datastage"]["config_escrita"] is None


# ═══════════ 5. migrations 197 (auditoria) e 198 (versão) ═══════════════

def _sql(nome):
    return (MIGS / nome).read_text(encoding="utf-8")


def test_migration_197_idempotente_e_alinhada_ao_service():
    sql = _sql("197_agente_terminal.sql")
    assert "IF OBJECT_ID('dbo.etl_agente_terminal_cmd', 'U') IS NULL" in sql
    assert sql.count("IF NOT EXISTS (SELECT 1 FROM sys.indexes") == 3
    assert not re.search(r"CREATE\s+(UNIQUE\s+)?(NONCLUSTERED\s+)?INDEX[^;]*\bWHERE\b", sql, re.I), "sem índice filtrado"
    # anti-drift: os CHECKs da tabela são exatamente os conjuntos do service
    classes = re.search(r"classe IN \(([^)]*)\)", sql).group(1)
    estados = re.search(r"estado IN\s*\(([^)]*)\)", sql, re.S).group(1)
    assert tuple(re.findall(r"'(\w+)'", classes)) == aterm.CLASSES
    assert tuple(re.findall(r"'(\w+)'", estados)) == aterm.ESTADOS
    # larguras: as constantes do service cabem nas colunas
    assert f"comando       NVARCHAR({aterm.MAX_COMANDO})" in sql
    assert f"motivo        NVARCHAR({aterm.MAX_MOTIVO})" in sql
    assert f"saida_resumo  NVARCHAR({aterm.MAX_SAIDA})" in sql
    assert "matricula     VARCHAR(20)" in sql and "hash          CHAR(64)" in sql
    # coerência classe × estado × segredo (QA da F2): o banco recusa o que a máquina de estados proíbe
    # T-SQL NÃO compara booleanos: `(a = b) = (c = d)` é erro de sintaxe (Msg 102) e derruba o CREATE TABLE
    # inteiro — provado no SQL Server do DEV na 2ª rodada do QA. A forma válida usa AND/OR.
    assert not re.search(r"\)\s*=\s*\(", sql), "comparação de booleanos não existe em T-SQL"
    assert ("CHECK\n            ((classe = 'proibido' AND estado = 'bloqueado') "
            "OR (classe <> 'proibido' AND estado <> 'bloqueado'))") in sql
    assert "CHECK (estado NOT IN ('proposto', 'recusado', 'expirado') OR classe = 'escrita')" in sql
    assert "CHECK (redigido = 0 OR classe = 'proibido')" in sql
    assert "redigido      BIT            NOT NULL" in sql
    # a máquina de estados do service é a que o CHECK espera
    assert aterm.NASCE_EM == {"escrita": "proposto", "leitura": "executando", "proibido": "bloqueado"}
    assert all(e in aterm.ESTADOS for e in aterm.NASCE_EM.values())
    assert set(aterm.DE_ONDE) <= set(aterm.ESTADOS_FINAIS)


def test_migration_198_versao_funcional_idempotente():
    sql = _sql("198_versao_agente_terminal_fundacao.sql")
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert "docs/release-notes/agente-terminal-f2.md" in sql
    assert (RAIZ / "docs/release-notes/agente-terminal-f2.md").is_file()
    assert sql.rstrip().endswith("GO") and "enviar" not in "198_versao_agente_terminal_fundacao.sql"
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';", p.read_text(encoding="utf-8")))]
    assert titulos.count("Agente Terminal — fundação") == 1 and len(set(titulos)) == len(titulos)


def test_front_e_back_concordam_nos_recursos_e_chaves():
    rbac = (RAIZ / "ui-react/src/lib/rbacRecursos.ts").read_text(encoding="utf-8")
    nav = (RAIZ / "ui-react/src/lib/adminNav.ts").read_text(encoding="utf-8")
    for rec in (TERMINAL["recurso"], TERMINAL["recurso_escrita"]):
        assert f"['{rec}'," in rbac, rec
    for chave in (TERMINAL["config_enabled"], TERMINAL["config_escrita"]):
        assert f"'{chave}'" in nav, chave


def test_aba_admin_tem_papel_e_interruptor_da_escrita():
    aba = (RAIZ / "ui-react/src/components/admin/AgentesTab.tsx").read_text(encoding="utf-8")
    assert "recurso_escrita: string | null" in aba and "config_escrita: string | null" in aba
    assert "...(ag.recurso_escrita ? [{ chave: `${ag.id}:escrita`" in aba
    assert "data-agentes-escrita-interruptor" in aba
    assert "salvar.mutate({ [chave]: e.target.checked })" in aba  # liga/desliga pelo mesmo caminho dos demais


def test_lista_admin_de_agentes_inclui_o_terminal_desligado(cliente):
    c, _ = cliente
    lista = {a["id"]: a for a in c.get("/agentes/admin/agentes").json()["agentes"]}
    t = lista["terminal"]
    assert t["origem"] == "codigo" and t["acesso"] == "manual" and t["ativo"] is False
    assert t["recurso"] == "agente_terminal" and t["perfis"] == ["desenvolvedor"] and t["ferramentas"] == ["servidor_exec"]


def test_aba_admin_trava_o_interruptor_do_agente_indisponivel():
    aba = (RAIZ / "ui-react/src/components/admin/AgentesTab.tsx").read_text(encoding="utf-8")
    assert "disponivel: boolean" in aba
    assert "|| !ag.disponivel}" in aba and "data-agentes-indisponivel" in aba


def test_config_admin_get_informa_disponibilidade(cliente):
    c, _ = cliente
    ag = {a["id"]: a for a in c.get("/agentes/admin/config").json()["agentes"]}
    assert ag["terminal"]["disponivel"] is False and ag["datastage"]["disponivel"] is True


# ═══════════ 6. redação da SAÍDA (auditoria da F3) ═════════════════════════

@pytest.mark.parametrize("entrada,segredo", [
    ("tok eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def456 fim", "abc123def456"),
    ("key AKIAIOSFODNN7EXAMPLE end", "AKIAIOSFODNN7EXAMPLE"),
    ("t ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
    ("xoxb-1234567890-abcdefghij", "xoxb-1234567890"),
    ("a\n-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkq\nxyz789\n-----END PRIVATE KEY-----\nb", "MIIEvQIBADANBgkq"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA9w0", "MIIEowIBAAKCAQEA9w0"),
    ("fernet_key = abcDEF123456==", "abcDEF123456"), ("access_key = AKxxxx999", "AKxxxx999"), ("private_key: x1y2z3w4", "x1y2z3w4"),
    ("DB_PASS: hunter2", "hunter2"), ("SESSION_ID=sess99887", "sess99887"),
    ("password:\n  hunter2\nuser: bob", "hunter2"),
    ("- name: DB_PASSWORD\n  value: hunter2\n- name: HOME\n  value: /x", "hunter2"),
    ("env:\n  - name: API_TOKEN\n    value: zz9top\n", "zz9top"),
    ("Server=h;Database=d;User Id=u;Password=Sup3rS3cret;Encrypt=yes", "Sup3rS3cret"),
    ("postgres://u:p4ss@h/db", "p4ss"), ("curl -H 'Authorization: Bearer abc123tok' x", "abc123tok"),
    # 2ª rodada: JSON com a chave entre aspas, auth em base64, block scalar do YAML, linha em branco, --flag composta, formatos novos
    ('{"db_pass":"Zx9secret","passphrase":"p4ssw0rd9","credential":"cr3d","access_key":"AKx99"}', "Zx9secret"),
    ('{"db_pass":"Zx9secret","passphrase":"p4ssw0rd9"}', "p4ssw0rd9"), ('{"a":1,"credential":"cr3d"}', "cr3d"),
    ('"auth": "dXNlcjpwYXNz"', "dXNlcjpwYXNz"), ("password: |\n  Zx9-Qm4\nuser: bob", "Zx9-Qm4"),
    ("password:\n\n  Zx9-Qm4", "Zx9-Qm4"), ("app --db-pass hunter9 --x 1", "hunter9"),
    ("k sk-abcdefghijklmnopqrstuvwxyz0123", "sk-abcdefghijklmnopqrstuvwxyz0123"), ("github_pat_11ABCDEFG0abcdefghijklmnopqrstuv", "github_pat_11ABCDEFG0"),
    ("glpat-abcdefghijklmnopqrst", "glpat-abcdefghijklmnopqrst"), ("hvs.CAESIabcdefghijklmnopqrstuv", "hvs.CAESIabcdefghijklmnopqrstuv"),
    ("AIzaSyA1234567890abcdefghijklmnopqrstuv", "AIzaSyA1234567890"), ("npm_abcdefghijklmnopqrstuvwxyz0123456789", "npm_abcdefghijklmnopqrstuvwxyz0123456789"),
    ("PuTTY-User-Key-File-2: ssh-rsa\nPrivate-Lines: 2\nAAAAB3Nza\nPrivate-MAC: 1a2b3c", "AAAAB3Nza"),
])
def test_saida_mascara_segredos_que_a_auditoria_achou(entrada, segredo):
    assert segredo not in aterm.redigir_saida(entrada), entrada


def test_saida_preserva_o_que_nao_e_segredo():
    out = aterm.redigir_saida("- name: HOME\n  value: /root\nseq 1 2 3\nuser: bob\n")
    assert "value: /root" in out and "seq 1 2 3" in out and "user: bob" in out


def test_redacao_da_saida_tem_tempo_limitado_em_entrada_hostil_de_64kb():
    """Antes: `"pass"*16000` (64 KB) levava 18 s e travava o loop da API (auditoria M2). Limite folgado, mas muito abaixo disso."""
    import time
    hostis = {"pass": "pass" * 16000, "a": "a" * 65536, "pass=": "pass=" + "a" * 65000, "BEGIN": "-----BEGIN PRIVATE KEY-----\n" * 2200,
              "eyJ": "eyJ" + "a" * 30000 + ".", "nl": "password:\n" * 6000, "dois-pontos": "x:" * 30000,
              "nome": ("a" * 40 + "pass" + "b" * 40 + " ") * 700, "url": "://a:" * 10000, "name": "name: DB_PASS\n" * 4000,
              "bearer": "bearer " * 9000, "mysql": "mysql " + "-x " * 20000 + "-p", "AKIA": "AKIA" * 16000, "yaml": "name: X_PASS\n  value: y\n" * 3000}
    for nome, entrada in hostis.items():
        t0 = time.monotonic()
        aterm.redigir_saida(entrada)
        assert time.monotonic() - t0 < 2.0, f"{nome}: {time.monotonic() - t0:.1f}s"


def test_redacao_da_saida_corta_a_entrada_enorme():
    assert len(aterm.redigir_saida("x" * 500_000)) <= 131_072


def _gatilhos():
    return ["mysql ", "mysqldump ", "mariadb ", "sqlcmd ", "bcp ", "sshpass ", "login ", "docker login ", "pass", "password", "token", "secret",
            "api_key", "fernet", "private_key", "name: ", "value: ", "password: ", "-p", "-P", "://", "a:", "bearer ", "Authorization: ",
            "Cookie: ", "eyJ", "AKIA", "ghp_", "github_pat_", "sk-", "-----BEGIN PRIVATE KEY-----\n", "PuTTY-User-Key-File-2:", "--password ",
            "--db-pass ", "Server=h;Password=", '"auth":', "name: X_PASS\n", "pwd=", '"db_pass":', "password: |\n"]


def test_redacao_nao_tem_regex_lenta_em_nenhuma_combinacao_de_gatilho():
    """Teste SISTEMÁTICO de ReDoS (a 2ª rodada da auditoria achou 3 regex de cliente que a 1ª não pegou): todo gatilho conhecido
    × vários preenchimentos × 3 layouts, em 64 KB, para `redigir_saida` E `redigir_comando`. Nenhuma combinação pode passar de 1 s."""
    import time
    N = 65536
    lentos = []
    for g in _gatilhos():
        for f in ("a", " ", "\n", ":"):
            M = N // 2  # o layout "mix" repete o gatilho muitas vezes: metade do tamanho já o exercita
            for nome, ent in (("rep", (g * (N // len(g) + 1))[:N]), ("fill", g + f * N), ("mix", ((g + f * 5) * (M // (len(g) + 5) + 1))[:M])):
                for fn in (aterm.redigir_saida, aterm.redigir_comando):
                    t0 = time.monotonic()
                    fn(ent)
                    dt = time.monotonic() - t0
                    if dt > 1.0:
                        lentos.append((g, f, nome, fn.__name__, round(dt, 1)))
    assert not lentos, lentos


def test_linha_gigante_e_cortada_antes_da_redacao():
    out = aterm.redigir_saida("a" * 50_000 + "\nsegunda linha password: hunter2\n")
    assert "…[linha cortada]" in out and "hunter2" not in out and "segunda linha" in out


def test_o_get_da_auditoria_comita_a_varredura(cliente):
    """QA da F3: o `listar` varre interrompidos (UPDATE); sem commit o ROLLBACK ao fechar a conexão desfazia."""
    c, estado = cliente
    commits = []
    estado["cur"].commit_hook = lambda: commits.append(1)
    r = c.get("/agentes/terminal/auditoria")
    assert r.status_code == 200 and commits, "o router precisa commitar"
