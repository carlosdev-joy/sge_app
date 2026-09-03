"""Utilitários de arquivos — F1 (spec docs/spec-utilitarios-arquivos.md).

Três camadas, na ordem em que a política é aplicada:

  1. funções PURAS de `services/ssh_arquivos.py` — caminho, raízes, codificação,
     últimas linhas. É aqui que `..`, symlink, `/dados2` × `/dados` e Latin-1 são
     decididos, e é por isso que elas não precisam de SSH para serem provadas;
  2. `ler_arquivo` / `testar_raiz` sobre um cliente SFTP EM MEMÓRIA (o paramiko
     não está no ambiente de teste — `tests/test_ds_console.py` documenta isso);
  3. os endpoints de `routers/utilitarios.py` com banco falso (cursor que responde
     por trecho do SQL) e autenticação sobrescrita — inclusive a AUDITORIA, que
     tem de existir em toda saída (ok, negado, erro).

Padrão de `tests/test_admin_conexoes.py`: TestClient do conftest, `get_db_conn`
mockado no módulo do router, `get_current_user` via dependency_overrides.
"""
from __future__ import annotations

import errno
import io
import os
import posixpath
import stat as statmod
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_ADMIN, PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services import ssh_arquivos as svc

RAIZES = ["/dados/bi", "/dados/param"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Funções puras
# ═══════════════════════════════════════════════════════════════════════════

class TestCaminho:
    def test_normaliza_barras_e_ponto(self):
        assert svc.normalizar_diretorio("/dados//bi/./2026/") == "/dados/bi/2026"

    def test_dois_pontos_resolvem_lexicalmente_e_caem_fora_da_raiz(self):
        # NÃO é 422: vira /etc e é a conferência de raízes que nega (403).
        assert svc.normalizar_diretorio("/dados/bi/../../etc") == "/etc"
        with pytest.raises(svc.ArquivoError) as exc:
            svc.preparar_leitura("/dados/bi/../../etc", "passwd", RAIZES)
        assert exc.value.status == 403
        assert exc.value.resultado == "negado"

    @pytest.mark.parametrize("bruto", ["", "   ", "dados/bi", "relativa", "/dados\0/bi"])
    def test_pasta_invalida_422(self, bruto):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_diretorio(bruto)
        assert exc.value.status == 422

    def test_caminho_longo_422(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_diretorio("/" + "a" * 1001)
        assert exc.value.status == 422

    def test_raiz_nao_pode_ser_a_barra(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_raiz("/")
        assert exc.value.status == 422
        assert svc.normalizar_raiz("/dados/bi/") == "/dados/bi"

    @pytest.mark.parametrize("nome", ["", "a/b", "../x", ".", "..", "x\0y", "n" * 256])
    def test_nome_invalido_422(self, nome):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.validar_nome(nome)
        assert exc.value.status == 422

    def test_nome_com_espaco_e_acento_e_aceito(self):
        assert svc.validar_nome("  relatório final.txt ") == "relatório final.txt"

    def test_prefixo_enganoso_nao_esta_abaixo_da_raiz(self):
        # /dados2 NÃO está sob /dados — comparação por componente, não por string.
        assert svc.raiz_de("/dados2/x.txt", ["/dados"]) is None
        assert svc.raiz_de("/dados/x.txt", ["/dados"]) == "/dados"
        assert svc.raiz_de("/dados", ["/dados"]) == "/dados"

    def test_raiz_com_barra_final_cadastrada_ainda_casa(self):
        assert svc.raiz_de("/dados/bi/x.txt", ["/dados/bi/"]) == "/dados/bi"

    def test_preparar_leitura_dentro_da_raiz(self):
        caminho, raiz = svc.preparar_leitura("/dados/bi/2026/", "carga.txt", RAIZES)
        assert caminho == "/dados/bi/2026/carga.txt"
        assert raiz == "/dados/bi"

    def test_preparar_leitura_sem_raizes_nega(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.preparar_leitura("/dados/bi", "x.txt", [])
        assert exc.value.status == 403

    @pytest.mark.parametrize("nome,ext", [
        ("carga.txt", "txt"), ("a.b.LOG", "log"), ("semext", None),
        (".oculto", None), (".oculto.txt", "txt"), ("x.", None),
    ])
    def test_extensao_de(self, nome, ext):
        assert svc.extensao_de(nome) == ext


class TestConteudo:
    def test_texto_e_binario(self):
        assert svc.eh_texto(b"linha\n\tcom tab e \x1b[31mcor\x1b[0m\n")
        assert svc.eh_texto(b"")
        assert not svc.eh_texto(b"\x00\x00BIN")
        assert not svc.eh_texto(bytes(range(1, 32)) * 10)

    def test_codificacao_utf8_estrito_depois_latin1(self):
        assert svc.decidir_codificacao("ação".encode("utf-8")) == ("ação", "utf-8")
        assert svc.decidir_codificacao("ação".encode("latin-1")) == ("ação", "latin-1")

    def test_bom_utf8_e_engolido(self):
        texto, cod = svc.decidir_codificacao(b"\xef\xbb\xbfabc")
        assert (texto, cod) == ("abc", "utf-8")

    def test_codificacao_pedida_que_nao_cabe_diz_a_posicao(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.decidir_codificacao(b"ab\xe7\xe3o", "utf-8")
        assert exc.value.status == 422
        assert "posição 2" in exc.value.detail

    def test_codificacao_pedida_desconhecida_422(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.decidir_codificacao(b"x", "utf-16")
        assert exc.value.status == 422

    @pytest.mark.parametrize("pedida", ["latin1", "LATIN-1", "iso-8859-1"])
    def test_apelidos_de_latin1(self, pedida):
        assert svc.decidir_codificacao(b"\xe7", pedida) == ("ç", "latin-1")

    def test_ultimas_linhas_em_borda(self):
        assert svc.ultimas_linhas(b"a\nb\nc\n", 2) == b"b\nc\n"
        assert svc.ultimas_linhas(b"a\nb\nc", 1) == b"c"
        assert svc.ultimas_linhas(b"a\nb\nc\n", 3) == b"a\nb\nc\n"
        assert svc.ultimas_linhas(b"a\nb\nc\n", 99) == b"a\nb\nc\n"
        assert svc.ultimas_linhas(b"", 5) == b""
        assert svc.ultimas_linhas(b"abc", 0) == b""

    def test_contar_linhas(self):
        assert svc.contar_linhas("") == 0
        assert svc.contar_linhas("a") == 1
        assert svc.contar_linhas("a\nb\n") == 2
        assert svc.contar_linhas("a\nb") == 2

    def test_formatar_tamanho(self):
        assert svc.formatar_tamanho(512) == "512 B"
        assert svc.formatar_tamanho(1536) == "1,5 KB"
        assert svc.formatar_tamanho(5 * 1024 * 1024) == "5,0 MB"


class TestServidores:
    def test_registro_so_tem_datastage(self):
        assert list(svc.SERVIDORES) == ["datastage"]
        assert svc.servidor_valido(None) == "datastage"
        assert svc.servidor_valido(" datastage ") == "datastage"

    def test_servidor_desconhecido_422(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.servidor_valido("outro")
        assert exc.value.status == 422

    def test_sem_variaveis_nao_esta_configurado(self, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        monkeypatch.delenv("DS_SSH_USER", raising=False)
        assert svc.servidores_disponiveis() == [
            {"id": "datastage", "label": "Servidor DataStage", "configurado": False}]
        with pytest.raises(svc.ArquivoError) as exc:
            svc.credencial("datastage")
        assert exc.value.status == 503

    def test_com_variaveis_esta_configurado(self, monkeypatch):
        monkeypatch.setenv("DS_SSH_HOST", "srv")
        monkeypatch.setenv("DS_SSH_USER", "u")
        monkeypatch.setenv("DS_SSH_PORT", "2222")
        cred = svc.credencial("datastage")
        assert (cred.host, cred.port, cred.user) == ("srv", 2222, "u")
        assert svc.servidores_disponiveis()[0]["configurado"] is True

    def test_conexao_real_sem_credencial_e_503_antes_do_paramiko(self, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        with pytest.raises(svc.ArquivoError) as exc:
            with svc.conexao_sftp("datastage"):
                pass
        assert exc.value.status == 503


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cliente SFTP em memória
# ═══════════════════════════════════════════════════════════════════════════

class _Attrs:
    def __init__(self, st_mode, st_size=0, st_mtime=1_756_900_000):
        self.st_mode, self.st_size, self.st_mtime = st_mode, st_size, st_mtime


class FakeSftp:
    """Árvore: caminho → bytes (arquivo) | None (pasta) | ('link', destino).

    `normalize` resolve symlinks componente a componente, como o realpath do
    servidor. Pastas em `ilegiveis` recusam `listdir` (EACCES)."""

    def __init__(self, arvore: dict, ilegiveis=()):
        self.arvore = dict(arvore)
        self.ilegiveis = set(ilegiveis)
        for p in list(self.arvore):
            # garante as pastas intermediárias
            d = posixpath.dirname(p)
            while d and d != "/":
                self.arvore.setdefault(d, None)
                d = posixpath.dirname(d)
        self.arvore.setdefault("/", None)
        self.fechado = False

    def _resolver(self, caminho: str) -> str:
        atual = "/"
        for comp in [c for c in caminho.split("/") if c]:
            atual = posixpath.join(atual, comp)
            if atual not in self.arvore:
                raise OSError(errno.ENOENT, "No such file")
            v = self.arvore[atual]
            if isinstance(v, tuple) and v[0] == "link":
                atual = self._resolver(v[1])
        return atual

    def normalize(self, caminho):
        return self._resolver(posixpath.normpath(caminho))

    def stat(self, caminho):
        real = self._resolver(caminho)
        v = self.arvore[real]
        if v is None:
            return _Attrs(statmod.S_IFDIR | 0o755)
        return _Attrs(statmod.S_IFREG | 0o644, st_size=len(v))

    def listdir(self, caminho):
        real = self._resolver(caminho)
        if real in self.ilegiveis:
            raise OSError(errno.EACCES, "Permission denied")
        pref = real.rstrip("/") + "/"
        return sorted({p[len(pref):].split("/")[0] for p in self.arvore if p.startswith(pref)})

    def open(self, caminho, modo="rb"):
        real = self._resolver(caminho)
        v = self.arvore[real]
        if v is None:
            raise OSError(errno.EISDIR, "Is a directory")
        return io.BytesIO(v)

    def close(self):
        self.fechado = True


ARVORE = {
    "/dados/bi/2026/cargas/carga_utf8.txt": "linha 1\nação\nfim\n".encode("utf-8"),
    "/dados/bi/consulta.sql": b"SELECT 1;\n",
    "/dados/bi/imagem.bin": b"\x00\x00BIN\x00" + bytes(range(256)),
    "/dados/bi/logs/grande.log": b"".join(f"linha {i:06d}\n".encode() for i in range(1, 5001)),
    "/dados/bi/link_fora": ("link", "/fora"),
    "/dados/param/parametros_latin1.param": "DESCRICAO=ação\n".encode("latin-1"),
    "/dados/param/sem_acesso": None,
    "/fora/segredo.txt": b"nao pode\n",
    "/dados2/x.txt": b"prefixo enganoso\n",
}
TETO = 16 * 1024  # 16 KB — grande.log tem 5.000 linhas × 13 bytes = 65 KB


@pytest.fixture
def sftp():
    return FakeSftp(ARVORE, ilegiveis={"/dados/param/sem_acesso"})


class TestLerArquivo:
    def test_le_utf8_com_linhas_e_mtime(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/bi/2026/cargas/carga_utf8.txt", RAIZES, teto_bytes=TETO)
        assert r["conteudo"] == "linha 1\nação\nfim\n"
        assert r["codificacao"] == "utf-8"
        assert r["linhas"] == 3
        assert r["truncado"] is False
        assert r["caminho"] == "/dados/bi/2026/cargas/carga_utf8.txt"
        assert r["modificado_em"]

    def test_latin1_detectado(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/param/parametros_latin1.param", RAIZES, teto_bytes=TETO)
        assert r["conteudo"] == "DESCRICAO=ação\n"
        assert r["codificacao"] == "latin-1"

    def test_symlink_para_fora_da_raiz_403_negado(self, sftp):
        # Lexicalmente /dados/bi/link_fora/segredo.txt está sob a raiz — só o
        # realpath do servidor revela que aponta para /fora.
        caminho, _ = svc.preparar_leitura("/dados/bi/link_fora", "segredo.txt", RAIZES)
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, caminho, RAIZES, teto_bytes=TETO)
        assert exc.value.status == 403
        assert exc.value.resultado == "negado"

    def test_nao_existe_404(self, sftp):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, "/dados/bi/nao_existe.txt", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 404

    def test_pasta_422(self, sftp):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, "/dados/bi/logs", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 422

    def test_binario_415(self, sftp):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, "/dados/bi/imagem.bin", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 415

    def test_acima_do_teto_413_sem_ultimas_linhas(self, sftp):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, "/dados/bi/logs/grande.log", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 413
        assert "últimas N linhas" in exc.value.detail

    def test_ultimas_linhas_le_so_o_fim_e_marca_truncado(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/bi/logs/grande.log", RAIZES, teto_bytes=TETO, ultimas=200)
        assert r["truncado"] is True
        assert r["linhas"] == 200
        assert r["conteudo"].startswith("linha 004801\n")
        assert r["conteudo"].endswith("linha 005000\n")
        assert r["tamanho_bytes"] == 65_000

    def test_ultimas_linhas_em_arquivo_pequeno_nao_trunca(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/bi/consulta.sql", RAIZES, teto_bytes=TETO, ultimas=200)
        assert r["truncado"] is False
        assert r["conteudo"] == "SELECT 1;\n"

    def test_codificacao_pedida_vale(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/param/parametros_latin1.param", RAIZES,
                            teto_bytes=TETO, codificacao="latin-1")
        assert r["codificacao"] == "latin-1"
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(sftp, "/dados/param/parametros_latin1.param", RAIZES,
                            teto_bytes=TETO, codificacao="utf-8")
        assert exc.value.status == 422


class TestTestarRaiz:
    def test_pasta_legivel(self, sftp):
        r = svc.testar_raiz(sftp, "/dados/bi/")
        assert r["existe"] and r["eh_pasta"] and r["legivel"]
        assert r["caminho_real"] == "/dados/bi"

    def test_pasta_ilegivel(self, sftp):
        r = svc.testar_raiz(sftp, "/dados/param/sem_acesso")
        assert r["existe"] and r["eh_pasta"] and not r["legivel"]

    def test_nao_existe(self, sftp):
        r = svc.testar_raiz(sftp, "/nada")
        assert r["existe"] is False and r["caminho_real"] is None

    def test_arquivo_nao_e_raiz(self, sftp):
        r = svc.testar_raiz(sftp, "/dados/bi/consulta.sql")
        assert r["existe"] and not r["eh_pasta"] and not r["legivel"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class _Cursor:
    """Cursor falso que responde por TRECHO do SQL, na ordem das regras.

    `auditoria` guarda os parâmetros de cada INSERT no log — é o que os testes
    de endpoint conferem em toda saída."""

    def __init__(self, regras=None, *, tabelas=3):
        self.regras = list(regras or [])
        self.tabelas = tabelas
        self.auditoria: list[list] = []
        self.executados: list[tuple[str, list]] = []
        self._rows: list = []
        self.rowcount = 0
        self.description = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.executados.append((s, list(params or [])))
        self._rows, self.rowcount = [], 1
        if "INFORMATION_SCHEMA.TABLES" in s:
            self._rows = [(self.tabelas,)]
            return
        if "INSERT INTO dbo.etl_utilitario_arquivo_log" in s:
            self.auditoria.append(list(params or []))
            return
        for trecho, resposta in self.regras:
            if trecho in s:
                if callable(resposta):
                    resposta = resposta(params)
                if isinstance(resposta, int):
                    self.rowcount = resposta
                else:
                    self._rows = list(resposta)
                return

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


def _conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


REGRAS_CONFIG = [
    ("FROM dbo.etl_utilitario_raiz WHERE ativo = 1",
     [(1, "datastage", "/dados/bi"), (2, "datastage", "/dados/param")]),
    ("SELECT extensao FROM dbo.etl_utilitario_extensao", [("sql",), ("txt",)]),
    ("FROM dbo.etl_app_config", [("utilitarios_arquivo_max_kb", "16"),
                                 ("utilitarios_arquivo_backup", "0")]),
]


def _auth(app, perms, perfil="x"):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "C012345", "perfil": perfil, "permissoes": list(perms)}


@pytest.fixture
def auth_operador(app):
    _auth(app, ["tela_utilitarios", PERM_EXECUTAR], "operador")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_dev(app):
    _auth(app, ["tela_utilitarios", PERM_EDITAR], "desenvolvedor")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_admin(app):
    _auth(app, [PERM_ADMIN, PERM_EDITAR], "admin")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    _auth(app, [], "consulta")
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def sftp_falso(monkeypatch, sftp):
    """Substitui a conexão real pelo cliente em memória."""
    @contextmanager
    def _cm(servidor):
        assert servidor == "datastage"
        yield sftp
    monkeypatch.setattr(svc, "conexao_sftp", _cm)
    return sftp


def _post_ler(client, cur, body):
    with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
        return client.post("/utilitarios/arquivo/ler", json=body)


class TestPermissao:
    def test_consulta_nao_entra(self, client, auth_consulta):
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.get("/utilitarios/config").status_code == 403
            assert client.post("/utilitarios/arquivo/ler", json={}).status_code == 403

    def test_sem_auth_401(self, client):
        assert client.get("/utilitarios/config").status_code == 401

    def test_operador_le_mas_nao_grava(self, client, auth_operador):
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/config")
        assert r.status_code == 200
        assert r.json()["pode_gravar"] is False

    def test_admin_sem_recurso_entra_pelo_acao_admin(self, client, auth_admin):
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/config")
        assert r.status_code == 200
        assert r.json()["pode_gravar"] is True

    def test_endpoints_admin_exigem_admin(self, client, auth_dev):
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.get("/utilitarios/admin/raizes").status_code == 403
            assert client.post("/utilitarios/admin/raizes", json={"caminho": "/x"}).status_code == 403
            assert client.patch("/utilitarios/admin/raizes/1", json={"ativo": False}).status_code == 403
            assert client.post("/utilitarios/admin/raizes/1/testar").status_code == 403
            assert client.get("/utilitarios/admin/extensoes").status_code == 403
            assert client.post("/utilitarios/admin/extensoes", json={"extensao": "sh"}).status_code == 403
            assert client.delete("/utilitarios/admin/extensoes/txt").status_code == 403
            assert client.put("/utilitarios/admin/config", json={}).status_code == 403


class TestConfig:
    def test_config_devolve_raizes_extensoes_e_teto(self, client, auth_dev, monkeypatch):
        monkeypatch.setenv("DS_SSH_HOST", "srv")
        monkeypatch.setenv("DS_SSH_USER", "u")
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/config")
        assert r.status_code == 200
        j = r.json()
        assert j["servidores"] == [{"id": "datastage", "label": "Servidor DataStage", "configurado": True}]
        assert [x["caminho"] for x in j["raizes"]] == ["/dados/bi", "/dados/param"]
        assert j["extensoes"] == ["sql", "txt"]
        assert j["tamanho_max_kb"] == 16
        assert j["backup_ao_sobrescrever"] is False
        assert j["pode_gravar"] is True

    def test_sem_migration_105_responde_503_nomeando(self, client, auth_dev):
        cur = _Cursor(REGRAS_CONFIG, tabelas=0)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/config")
        assert r.status_code == 503
        assert "105" in r.json()["detail"]

    def test_teto_invalido_cai_no_default_e_clampa(self, client, auth_dev):
        regras = REGRAS_CONFIG[:2] + [("FROM dbo.etl_app_config", [("utilitarios_arquivo_max_kb", "abc")])]
        cur = _Cursor(regras)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.get("/utilitarios/config").json()["tamanho_max_kb"] == svc.TETO_PADRAO_KB
        regras = REGRAS_CONFIG[:2] + [("FROM dbo.etl_app_config", [("utilitarios_arquivo_max_kb", "999999999")])]
        cur = _Cursor(regras)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.get("/utilitarios/config").json()["tamanho_max_kb"] == svc.TETO_MAX_KB


class TestLerEndpoint:
    def test_le_e_audita_ok(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi/2026/cargas", "nome": "carga_utf8.txt"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["conteudo"] == "linha 1\nação\nfim\n"
        assert j["codificacao"] == "utf-8"
        assert j["linhas"] == 3
        assert isinstance(j["duracao_ms"], int)
        assert len(cur.auditoria) == 1
        usuario, servidor, acao, caminho, tamanho, sha, resultado, detalhe, dur = cur.auditoria[0]
        assert (usuario, servidor, acao, resultado) == ("C012345", "datastage", "ler", "ok")
        assert caminho == "/dados/bi/2026/cargas/carga_utf8.txt"
        assert tamanho == len("linha 1\nação\nfim\n".encode("utf-8"))
        assert sha is None

    def test_fora_das_raizes_403_negado_sem_tocar_o_servidor(self, client, auth_operador, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi/../../etc", "nome": "passwd"})
        assert r.status_code == 403
        assert chamou == []  # negado LEXICALMENTE: nenhum SSH aberto
        assert cur.auditoria[0][6] == "negado"
        assert cur.auditoria[0][3] == "/dados/bi/../../etc/passwd"  # o caminho PEDIDO

    def test_prefixo_enganoso_403(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados2", "nome": "x.txt"})
        assert r.status_code == 403

    def test_symlink_para_fora_403_audita_negado_com_caminho_pedido(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi/link_fora", "nome": "segredo.txt"})
        assert r.status_code == 403
        assert cur.auditoria[0][6] == "negado"
        assert cur.auditoria[0][3] == "/dados/bi/link_fora/segredo.txt"

    def test_raiz_desativada_nao_libera(self, client, auth_operador, sftp_falso):
        regras = [("FROM dbo.etl_utilitario_raiz WHERE ativo = 1", [(2, "datastage", "/dados/param")])] + REGRAS_CONFIG[1:]
        cur = _Cursor(regras)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 403

    def test_sem_nenhuma_raiz_403_aponta_o_admin(self, client, auth_operador, sftp_falso):
        regras = [("FROM dbo.etl_utilitario_raiz WHERE ativo = 1", [])] + REGRAS_CONFIG[1:]
        cur = _Cursor(regras)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 403
        assert "Admin" in r.json()["detail"]
        assert cur.auditoria[0][6] == "negado"

    def test_404_e_auditado_como_erro(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "nao_existe.txt"})
        assert r.status_code == 404
        assert cur.auditoria[0][6] == "erro"

    def test_413_e_ultimas_linhas(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi/logs", "nome": "grande.log"})
        assert r.status_code == 413
        assert "16,0 KB" in r.json()["detail"]
        r = _post_ler(client, cur, {"diretorio": "/dados/bi/logs", "nome": "grande.log", "ultimas_linhas": 200})
        assert r.status_code == 200
        assert r.json()["truncado"] is True
        assert r.json()["linhas"] == 200
        assert "truncado" in (cur.auditoria[-1][7] or "")

    def test_415_binario(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "imagem.bin"})
        assert r.status_code == 415

    @pytest.mark.parametrize("body", [
        {"diretorio": "", "nome": "x"}, {"diretorio": "/dados/bi", "nome": ""},
        {"diretorio": "/dados/bi", "nome": "a/b"}, {"diretorio": "relativa", "nome": "x"},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": "abc"},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": 0.5},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": -1},
        {"diretorio": "/dados/bi", "nome": "x", "servidor": "outro"},
    ])
    def test_422_de_validacao(self, client, auth_operador, sftp_falso, body):
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_ler(client, cur, body).status_code == 422

    def test_servidor_nao_configurado_503(self, client, auth_operador, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 503
        assert cur.auditoria[0][6] == "erro"

    def test_falha_ssh_502(self, client, auth_operador, monkeypatch):
        @contextmanager
        def _cm(servidor):
            raise svc.ArquivoError(502, "Falha ao conectar por SSH em srv:22: boom")
            yield  # pragma: no cover
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 502
        assert cur.auditoria[0][6] == "erro"

    def test_auditoria_que_falha_nao_derruba_a_leitura(self, client, auth_operador, sftp_falso):
        class _CursorSemLog(_Cursor):
            def execute(self, sql, params=None):
                if "etl_utilitario_arquivo_log" in str(sql):
                    raise RuntimeError("log fora do ar")
                return super().execute(sql, params)
        cur = _CursorSemLog(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 200


class TestAdminRaizes:
    def test_lista_inclui_inativas(self, client, auth_admin):
        cur = _Cursor([("FROM dbo.etl_utilitario_raiz ORDER BY",
                        [(1, "datastage", "/dados/bi", 1, "ADM", None),
                         (2, "datastage", "/velha", 0, "ADM", None)])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/admin/raizes")
        assert r.status_code == 200
        assert [x["ativo"] for x in r.json()] == [True, False]

    def test_incluir_normaliza_e_devolve_id(self, client, auth_admin):
        cur = _Cursor([("SELECT id, ativo FROM dbo.etl_utilitario_raiz", []),
                       ("INSERT INTO dbo.etl_utilitario_raiz", [(7,)])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.post("/utilitarios/admin/raizes", json={"caminho": "/dados//bi/"})
        assert r.status_code == 200, r.text
        assert r.json() == {"id": 7, "servidor": "datastage", "caminho": "/dados/bi"}
        insert = [e for e in cur.executados if "INSERT INTO dbo.etl_utilitario_raiz" in e[0]][0]
        assert insert[1] == ["datastage", "/dados/bi", "C012345"]

    @pytest.mark.parametrize("caminho", ["", "dados/bi", "/", "/dados/bi/../.."])
    def test_incluir_caminho_invalido_422(self, client, auth_admin, caminho):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.post("/utilitarios/admin/raizes", json={"caminho": caminho})
        assert r.status_code == 422, caminho

    def test_incluir_repetida_409_diz_o_estado(self, client, auth_admin):
        cur = _Cursor([("SELECT id, ativo FROM dbo.etl_utilitario_raiz", [(3, 0)])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.post("/utilitarios/admin/raizes", json={"caminho": "/dados/bi"})
        assert r.status_code == 409
        assert "inativa" in r.json()["detail"]

    def test_desativar_e_reativar(self, client, auth_admin):
        cur = _Cursor([("UPDATE dbo.etl_utilitario_raiz SET ativo", 1)])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.patch("/utilitarios/admin/raizes/3", json={"ativo": False})
            assert r.status_code == 200 and r.json()["ativo"] is False
            assert client.patch("/utilitarios/admin/raizes/3", json={"ativo": "sim"}).status_code == 422
        cur = _Cursor([("UPDATE dbo.etl_utilitario_raiz SET ativo", 0)])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.patch("/utilitarios/admin/raizes/99", json={"ativo": True}).status_code == 404

    def test_testar_raiz_audita(self, client, auth_admin, sftp_falso):
        cur = _Cursor([("SELECT servidor, caminho FROM dbo.etl_utilitario_raiz WHERE id",
                        [("datastage", "/dados/param/sem_acesso")])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.post("/utilitarios/admin/raizes/2/testar")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["existe"] and j["eh_pasta"] and j["legivel"] is False
        assert cur.auditoria[0][2] == "testar"

    def test_testar_raiz_inexistente_404(self, client, auth_admin, sftp_falso):
        cur = _Cursor([("SELECT servidor, caminho FROM dbo.etl_utilitario_raiz WHERE id", [])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.post("/utilitarios/admin/raizes/99/testar").status_code == 404


class TestAdminExtensoes:
    def test_lista(self, client, auth_admin):
        cur = _Cursor([("SELECT extensao, criado_por, criado_em", [("sql", "migration-105", None)])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/admin/extensoes")
        assert r.json() == [{"extensao": "sql", "criado_por": "migration-105", "criado_em": None}]

    def test_incluir_normaliza_maiuscula_e_ponto(self, client, auth_admin):
        cur = _Cursor([("SELECT 1 FROM dbo.etl_utilitario_extensao", [])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.post("/utilitarios/admin/extensoes", json={"extensao": " .SH "})
        assert r.status_code == 200
        assert r.json()["extensao"] == "sh"

    @pytest.mark.parametrize("ext", ["", "a.b", "a b", "ção", "x" * 16, "a/b"])
    def test_incluir_invalida_422(self, client, auth_admin, ext):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.post("/utilitarios/admin/extensoes", json={"extensao": ext}).status_code == 422

    def test_incluir_repetida_409(self, client, auth_admin):
        cur = _Cursor([("SELECT 1 FROM dbo.etl_utilitario_extensao", [(1,)])])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.post("/utilitarios/admin/extensoes", json={"extensao": "txt"}).status_code == 409

    def test_excluir(self, client, auth_admin):
        cur = _Cursor([("DELETE FROM dbo.etl_utilitario_extensao", 1)])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.delete("/utilitarios/admin/extensoes/txt").status_code == 200
        cur = _Cursor([("DELETE FROM dbo.etl_utilitario_extensao", 0)])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.delete("/utilitarios/admin/extensoes/nada").status_code == 404


class TestAdminConfig:
    def test_grava_as_duas_chaves(self, client, auth_admin):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.put("/utilitarios/admin/config", json={"tamanho_max_kb": 4096, "backup_ao_sobrescrever": False})
        assert r.status_code == 200
        merges = [e for e in cur.executados if "MERGE dbo.etl_app_config" in e[0]]
        assert [m[1][:2] for m in merges] == [["utilitarios_arquivo_max_kb", "4096"],
                                              ["utilitarios_arquivo_backup", "0"]]

    @pytest.mark.parametrize("body", [
        {"tamanho_max_kb": "x", "backup_ao_sobrescrever": True},
        {"tamanho_max_kb": 0, "backup_ao_sobrescrever": True},
        {"tamanho_max_kb": 10 ** 9, "backup_ao_sobrescrever": True},
        {"tamanho_max_kb": 10, "backup_ao_sobrescrever": "sim"},
    ])
    def test_422(self, client, auth_admin, body):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.put("/utilitarios/admin/config", json=body).status_code == 422
