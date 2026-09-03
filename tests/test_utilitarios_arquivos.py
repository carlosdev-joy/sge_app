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
import hashlib
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

    def test_barras_iniciais_colapsam(self):
        # POSIX preserva `//` no normpath; aqui é sempre UMA barra.
        assert svc.normalizar_diretorio("//dados//bi") == "/dados/bi"
        assert svc.normalizar_diretorio("///") == "/"

    def test_raiz_dupla_barra_nao_libera_o_servidor(self):
        # `//` passava pela guarda "raiz não pode ser /" e casava com TUDO.
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_raiz("//")
        assert exc.value.status == 422
        assert svc.raiz_de("/etc/passwd", ["//"]) is None
        assert svc.raiz_de("/etc/passwd", ["/"]) is None
        assert svc.raiz_de("/dados/bi/x", ["//dados/bi"]) == "/dados/bi"

    @pytest.mark.parametrize("raiz", ["/etc", "/etc/ssh", "/usr/local/x", "/dev", "/var/run/x", "/root"])
    def test_raiz_de_pasta_do_sistema_422(self, raiz):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_raiz(raiz)
        assert exc.value.status == 422

    @pytest.mark.parametrize("raiz", ["/opt/IBM/InformationServer/Server/Projects", "/var/log", "/dados", "/home/ds"])
    def test_raiz_legitima_passa(self, raiz):
        assert svc.normalizar_raiz(raiz) == raiz

    def test_raiz_longa_422_no_limite_do_indice(self):
        assert svc.normalizar_raiz("/" + "a" * 799) == "/" + "a" * 799
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_raiz("/" + "a" * 801)
        assert exc.value.status == 422

    def test_comprimento_conta_unidades_utf16(self):
        # 600 emojis = 610 code points, mas 1.210 unidades UTF-16 (o que NVARCHAR conta).
        assert svc.utf16_len("😀") == 2
        assert svc.utf16_len("abc") == 3
        with pytest.raises(svc.ArquivoError) as exc:
            svc.normalizar_diretorio("/" + "😀" * 500)  # 1 + 1.000 unidades > 1.000
        assert exc.value.status == 422
        assert svc.normalizar_diretorio("/" + "😀" * 499)

    def test_cortar_utf16_nao_parte_emoji(self):
        assert svc.cortar_utf16("a😀b", 2) == "a"
        assert svc.cortar_utf16("a😀b", 3) == "a😀"
        assert svc.cortar_utf16("abc", 5) == "abc"
        assert svc.cortar_utf16("", 5) == ""
        assert svc.utf16_len(svc.cortar_utf16("😀" * 700, 1000)) <= 1000

    def test_nome_limite_em_bytes(self):
        assert svc.validar_nome("ç" * 127)          # 254 bytes
        with pytest.raises(svc.ArquivoError) as exc:
            svc.validar_nome("ç" * 128)             # 256 bytes > NAME_MAX
        assert exc.value.status == 422


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

    def test_codificacao_valida_e_pura(self):
        assert svc.codificacao_valida(None) is None
        assert svc.codificacao_valida("") is None
        assert svc.codificacao_valida(" UTF8 ") == "utf-8"
        for ruim in (["utf-8"], 7, "utf-16"):
            with pytest.raises(svc.ArquivoError) as exc:
                svc.codificacao_valida(ruim)
            assert exc.value.status == 422

    def test_bloco_do_tail_e_limitado(self):
        assert svc.tamanho_bloco_tail(5_040_000, 65_536, 200) == 65_536       # teto
        assert svc.tamanho_bloco_tail(1_000, 100, 10) == 100                  # teto menor
        assert svc.tamanho_bloco_tail(10 ** 7, 16 * 2 ** 20, 200) == 256 * 1024   # mínimo
        assert svc.tamanho_bloco_tail(10 ** 8, 16 * 2 ** 20, 100_000) == 16 * 2 ** 20  # teto de novo
        assert svc.tamanho_bloco_tail(0, 100, 10) == 0


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

    def test_known_hosts_ilegivel_e_503_antes_do_paramiko(self, monkeypatch):
        monkeypatch.setenv("DS_SSH_HOST", "srv")
        monkeypatch.setenv("DS_SSH_USER", "u")
        monkeypatch.setenv("DS_SSH_KNOWN_HOSTS", "/nao/existe/known_hosts")
        with pytest.raises(svc.ArquivoError) as exc:
            with svc.conexao_sftp("datastage"):
                pass
        assert exc.value.status == 503
        assert "DS_SSH_KNOWN_HOSTS" in exc.value.detail
        assert "/nao/existe" not in exc.value.detail  # o caminho fica no `interno`
        assert exc.value.interno == "/nao/existe/known_hosts"


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

    def __init__(self, arvore: dict, ilegiveis=(), *, sem_posix_rename=False, falhar_rename=False,
                 falhar_escrita=False, falhar_posix_rename=False, falhar_chmod=False, modos=None):
        self.arvore = dict(arvore)
        self.ilegiveis = set(ilegiveis)
        # Botões de sabotagem da gravação (F4): servidor sem a extensão
        # posix-rename, rename que falha, escrita recusada, SÓ o posix_rename
        # falhando (é o que prova o rollback do backup), chmod recusado.
        self.sem_posix_rename = sem_posix_rename
        self.falhar_rename = falhar_rename
        self.falhar_escrita = falhar_escrita
        self.falhar_posix_rename = falhar_posix_rename
        self.falhar_chmod = falhar_chmod
        # Modo (permissões) por arquivo; o padrão é 0644, como o umask do sshd.
        self.modos: dict[str, int] = dict(modos or {})
        self.renames: list[tuple[str, str]] = []
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
        """Como o realpath do OpenSSH: resolve o que existe e TOLERA só o último
        componente ausente (devolve pai resolvido + nome); componente
        intermediário ausente é ENOENT. Foi a divergência que escondeu o defeito
        do Testar (revisão adversarial da F1)."""
        caminho = posixpath.normpath(caminho)
        try:
            return self._resolver(caminho)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            pai, ultimo = posixpath.split(caminho)
            if not ultimo or pai == caminho:
                raise
            return posixpath.join(self._resolver(pai), ultimo)

    def stat(self, caminho):
        real = self._resolver(caminho)
        v = self.arvore[real]
        if v is None:
            return _Attrs(statmod.S_IFDIR | 0o755)
        return _Attrs(statmod.S_IFREG | self.modos.get(real, 0o644), st_size=len(v))

    def chmod(self, caminho, modo):
        if self.falhar_chmod:
            raise OSError(errno.EACCES, "Permission denied")
        real = self._resolver(caminho)
        self.modos[real] = modo

    def listdir(self, caminho):
        real = self._resolver(caminho)
        if real in self.ilegiveis:
            raise OSError(errno.EACCES, "Permission denied")
        pref = real.rstrip("/") + "/"
        return sorted({p[len(pref):].split("/")[0] for p in self.arvore if p.startswith(pref)})

    def open(self, caminho, modo="rb"):
        if "w" in modo:
            return self._abrir_para_escrita(caminho)
        real = self._resolver(caminho)
        v = self.arvore[real]
        if v is None:
            raise OSError(errno.EISDIR, "Is a directory")
        return io.BytesIO(v)

    # ── escrita (F4) — espelha o que o sftp-server do OpenSSH faz ────────────
    def _pai_e_nome(self, caminho):
        caminho = posixpath.normpath(caminho)
        pai, nome = posixpath.split(caminho)
        real_pai = self._resolver(pai)            # ENOENT se a pasta não existe
        if self.arvore.get(real_pai, "x") is not None:
            raise OSError(errno.ENOTDIR, "Not a directory")
        return real_pai, nome

    def _abrir_para_escrita(self, caminho):
        if self.falhar_escrita:
            raise OSError(errno.EACCES, "Permission denied")
        real_pai, nome = self._pai_e_nome(caminho)
        destino = posixpath.join(real_pai, nome)
        arvore = self.arvore

        class _Escritor(io.BytesIO):
            def close(_self):
                arvore[destino] = _self.getvalue()
                super().close()

            def __exit__(_self, *exc):
                _self.close()
                return False
        return _Escritor()

    def lstat(self, caminho):
        real_pai, nome = self._pai_e_nome(caminho)
        alvo = posixpath.join(real_pai, nome)
        if alvo not in self.arvore:
            raise OSError(errno.ENOENT, "No such file")
        v = self.arvore[alvo]
        if isinstance(v, tuple) and v[0] == "link":
            return _Attrs(statmod.S_IFLNK | 0o777)
        if v is None:
            return _Attrs(statmod.S_IFDIR | 0o755)
        return _Attrs(statmod.S_IFREG | 0o644, st_size=len(v))

    def rename(self, de, para):
        """Como o SFTP RENAME padrão: recusa quando o destino existe."""
        if self.falhar_rename:
            raise OSError("Failure")
        real_pai, nome = self._pai_e_nome(de)
        origem = posixpath.join(real_pai, nome)
        if origem not in self.arvore:
            raise OSError(errno.ENOENT, "No such file")
        pai_d, nome_d = self._pai_e_nome(para)
        destino = posixpath.join(pai_d, nome_d)
        if destino in self.arvore:
            raise OSError("Failure")
        self.arvore[destino] = self.arvore.pop(origem)
        if origem in self.modos:
            self.modos[destino] = self.modos.pop(origem)
        self.renames.append((origem, destino))

    def posix_rename(self, de, para):
        """Extensão posix-rename@openssh.com: sobrescreve o destino de uma vez."""
        if self.sem_posix_rename:
            raise AttributeError("posix_rename não suportado")
        if self.falhar_rename or self.falhar_posix_rename:
            raise OSError("Failure")
        real_pai, nome = self._pai_e_nome(de)
        origem = posixpath.join(real_pai, nome)
        if origem not in self.arvore:
            raise OSError(errno.ENOENT, "No such file")
        pai_d, nome_d = self._pai_e_nome(para)
        destino = posixpath.join(pai_d, nome_d)
        self.arvore[destino] = self.arvore.pop(origem)
        self.modos[destino] = self.modos.pop(origem, 0o644)
        self.renames.append((origem, destino))

    def remove(self, caminho):
        real_pai, nome = self._pai_e_nome(caminho)
        alvo = posixpath.join(real_pai, nome)
        if alvo not in self.arvore:
            raise OSError(errno.ENOENT, "No such file")
        if self.arvore[alvo] is None:
            raise OSError(errno.EISDIR, "Is a directory")
        del self.arvore[alvo]

    def close(self):
        self.fechado = True


class FakeSftpSemPosixRename(FakeSftp):
    """Servidor sem a extensão: o atributo NÃO existe (é o que `getattr` vê)."""
    posix_rename = None  # type: ignore[assignment]


ARVORE = {
    "/dados/bi/2026/cargas/carga_utf8.txt": "linha 1\nação\nfim\n".encode("utf-8"),
    "/dados/bi/consulta.sql": b"SELECT 1;\n",
    "/dados/bi/imagem.bin": b"\x00\x00BIN\x00" + bytes(range(256)),
    "/dados/bi/logs/grande.log": b"".join(f"linha {i:06d}\n".encode() for i in range(1, 5001)),
    "/dados/bi/link_fora": ("link", "/fora"),
    "/dados/bi/2026/link_outra_raiz": ("link", "/dados/param"),
    "/dados/link_raiz": ("link", "/dados/param"),
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

    def test_raiz_que_e_symlink_continua_valendo(self, sftp):
        # Admin cadastra /dados/link_raiz; no servidor é um link para /dados/param.
        r = svc.ler_arquivo(sftp, "/dados/link_raiz/parametros_latin1.param",
                            ["/dados/link_raiz"], teto_bytes=TETO)
        assert r["caminho"] == "/dados/param/parametros_latin1.param"
        assert r["codificacao"] == "latin-1"

    def test_symlink_para_outra_raiz_e_permitido(self, sftp):
        r = svc.ler_arquivo(sftp, "/dados/bi/2026/link_outra_raiz/parametros_latin1.param",
                            RAIZES, teto_bytes=TETO)
        assert r["caminho"] == "/dados/param/parametros_latin1.param"

    def test_oraculo_403_x_404_fechado(self, sftp):
        # Pelo link para fora, "existe" e "não existe" respondem IGUAL (403):
        # o prefixo /dados/bi/link_fora já sai da raiz e nada abaixo é consultado.
        for alvo in ("/dados/bi/link_fora/segredo.txt", "/dados/bi/link_fora/pasta_inexistente/x"):
            with pytest.raises(svc.ArquivoError) as exc:
                svc.ler_arquivo(sftp, alvo, RAIZES, teto_bytes=TETO)
            assert exc.value.status == 403, alvo
            assert exc.value.resultado == "negado"

    def test_tail_quando_o_bloco_comeca_exatamente_numa_linha(self):
        # 100 linhas × 10 bytes; teto 100 → o bloco começa no byte 900, que é o
        # INÍCIO da linha 90. Sem o byte extra, a primeira linha inteira era jogada fora.
        fake = FakeSftp({"/dados/bi/cem.txt": b"".join(b"L%08d\n" % i for i in range(100))})
        r = svc.ler_arquivo(fake, "/dados/bi/cem.txt", RAIZES, teto_bytes=100, ultimas=10)
        assert r["linhas"] == 10
        assert r["conteudo"].startswith("L00000090\n")
        assert r["truncado"] is True

    def test_tail_quando_o_bloco_comeca_no_meio_de_uma_linha(self):
        fake = FakeSftp({"/dados/bi/cem.txt": b"".join(b"L%08d\n" % i for i in range(100))})
        r = svc.ler_arquivo(fake, "/dados/bi/cem.txt", RAIZES, teto_bytes=95, ultimas=10)
        assert r["linhas"] == 9   # 95 bytes cobrem 9 linhas inteiras + meia — a meia sai
        assert r["conteudo"].startswith("L00000091\n")

    @pytest.mark.parametrize("dados", [b"x" * 200 + b"\n", b"x" * 200])
    def test_tail_linha_maior_que_o_bloco_e_413_e_nao_200_vazio(self, dados):
        fake = FakeSftp({"/dados/bi/longa.txt": dados})
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(fake, "/dados/bi/longa.txt", RAIZES, teto_bytes=50, ultimas=1)
        assert exc.value.status == 413
        assert "última linha" in exc.value.detail

    def test_nome_fora_do_utf8_no_servidor_e_422_nao_502(self):
        class _SftpNomeRuim(FakeSftp):
            def normalize(self, caminho):
                if caminho.endswith("ruim"):
                    raise UnicodeDecodeError("utf-8", b"\xe7", 0, 1, "invalid start byte")
                return super().normalize(caminho)
        fake = _SftpNomeRuim(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(fake, "/dados/bi/ruim", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 422
        assert "UTF-8" in exc.value.detail

    def test_erro_generico_do_servidor_nao_vai_na_resposta(self):
        class _SftpQuebrado(FakeSftp):
            def stat(self, caminho):
                raise OSError("Garbage packet received from srv:22")
        fake = _SftpQuebrado(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            svc.ler_arquivo(fake, "/dados/bi/consulta.sql", RAIZES, teto_bytes=TETO)
        assert exc.value.status == 502
        assert "srv:22" not in exc.value.detail
        assert "srv:22" in (exc.value.interno or "")


class TestGravarPuras:
    def test_normalizar_conteudo(self):
        assert svc.normalizar_conteudo("a\r\nb\rc") == "a\nb\nc\n"
        assert svc.normalizar_conteudo("a\n") == "a\n"
        assert svc.normalizar_conteudo("") == ""
        assert svc.normalizar_conteudo(None) == ""

    def test_codificar_latin1_recusa_caractere_fora_com_linha_e_posicao(self):
        assert svc.codificar_conteudo("ação\n", "latin-1") == "ação\n".encode("latin-1")
        with pytest.raises(svc.ArquivoError) as exc:
            svc.codificar_conteudo("ok\nvalor: 10€\n", "latin-1")
        assert exc.value.status == 422
        assert "linha 2" in exc.value.detail and "'€'" in exc.value.detail
        assert svc.codificar_conteudo("10€\n", "utf-8") == "10€\n".encode("utf-8")

    def test_extensao_precisa_estar_na_lista(self):
        assert svc.validar_extensao_gravacao(" .SQL ", ["sql", "txt"]) == "sql"
        with pytest.raises(svc.ArquivoError) as exc:
            svc.validar_extensao_gravacao("sh", ["sql", "txt"])
        assert exc.value.status == 422 and "'sh' não liberada" in exc.value.detail
        for ruim in ("", "a.b", "x" * 16):
            with pytest.raises(svc.ArquivoError):
                svc.validar_extensao_gravacao(ruim, ["sql"])

    def test_preparar_gravacao(self):
        caminho, raiz = svc.preparar_gravacao("/dados/bi/2026/", "carga", "txt", RAIZES, ["txt"])
        assert (caminho, raiz) == ("/dados/bi/2026/carga.txt", "/dados/bi")
        with pytest.raises(svc.ArquivoError) as exc:
            svc.preparar_gravacao("/etc", "x", "txt", RAIZES, ["txt"])
        assert exc.value.status == 403 and exc.value.resultado == "negado"
        with pytest.raises(svc.ArquivoError) as exc:
            svc.preparar_gravacao("/dados/bi", "a/b", "txt", RAIZES, ["txt"])
        assert exc.value.status == 422

    def test_nomes_de_backup_e_temporario(self):
        from datetime import datetime
        assert svc.nome_backup("/dados/bi/x.txt", datetime(2026, 9, 3, 10, 5, 7, 123456)) == "/dados/bi/x.txt.bak-20260903100507-123"
        assert svc.nome_temporario("/dados/bi/x.txt", "77-1") == "/dados/bi/.x.txt.tmp-77-1"

    def test_erro_de_codificacao_nao_leva_o_caractere_para_a_auditoria(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.codificar_conteudo("10€\n", "latin-1")
        assert "'€'" in exc.value.detail          # a resposta diz qual é
        assert "€" not in (exc.value.interno or "")  # a auditoria só diz onde
        assert "linha 1" in exc.value.interno


class TestGravarArquivo:
    def _gravar(self, fake, caminho, dados=b"novo\n", **kw):
        kw.setdefault("sobrescrever", False)
        kw.setdefault("backup", True)
        return svc.gravar_arquivo(fake, caminho, RAIZES, dados, marca="t", **kw)

    def test_cria_arquivo_novo_sem_deixar_tmp(self):
        fake = FakeSftp(ARVORE)
        r = self._gravar(fake, "/dados/bi/2026/novo.txt")
        assert r["criado"] is True and r["backup"] is None
        assert r["caminho"] == "/dados/bi/2026/novo.txt"
        assert fake.arvore["/dados/bi/2026/novo.txt"] == b"novo\n"
        assert r["sha256"] == hashlib.sha256(b"novo\n").hexdigest()
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_existente_sem_sobrescrever_409_com_o_que_existe(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/consulta.sql")
        assert exc.value.status == 409
        assert exc.value.extra == {"existente": {"tamanho_bytes": 10, "modificado_em": svc._mtime_iso(_Attrs(0))}}
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"   # nada mudou

    def test_sobrescreve_com_backup_byte_identico(self):
        fake = FakeSftp(ARVORE)
        from datetime import datetime
        r = svc.gravar_arquivo(fake, "/dados/bi/consulta.sql", RAIZES, b"SELECT 2;\n",
                               sobrescrever=True, backup=True, marca="t", agora=datetime(2026, 9, 3, 1, 2, 3))
        assert r["criado"] is False
        assert r["backup"] == "/dados/bi/consulta.sql.bak-20260903010203-000"
        assert fake.arvore["/dados/bi/consulta.sql.bak-20260903010203-000"] == b"SELECT 1;\n"
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 2;\n"
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_sobrescreve_sem_backup(self):
        fake = FakeSftp(ARVORE)
        r = self._gravar(fake, "/dados/bi/consulta.sql", b"SELECT 3;\n", sobrescrever=True, backup=False)
        assert r["backup"] is None
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 3;\n"
        assert not [p for p in fake.arvore if ".bak-" in p]

    def test_servidor_sem_posix_rename_cai_no_remove_e_rename(self):
        fake = FakeSftpSemPosixRename(ARVORE)
        r = self._gravar(fake, "/dados/bi/consulta.sql", b"SELECT 4;\n", sobrescrever=True, backup=False)
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 4;\n"
        assert r["criado"] is False

    def test_falha_no_rename_devolve_o_original_e_nao_deixa_tmp(self):
        fake = FakeSftp(ARVORE, falhar_rename=True)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/consulta.sql", b"SELECT 5;\n", sobrescrever=True, backup=True)
        assert exc.value.status == 502
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        assert not [p for p in fake.arvore if ".tmp-" in p or ".bak-" in p]

    def test_rollback_de_verdade_quando_so_o_posix_rename_falha(self):
        # Achado da revisão: com `falhar_rename` o 1º rename já falha e o original
        # nunca sai do lugar — o rollback (bak → real) não era exercitado.
        from datetime import datetime
        fake = FakeSftp(ARVORE, falhar_posix_rename=True)
        with pytest.raises(svc.ArquivoError) as exc:
            svc.gravar_arquivo(fake, "/dados/bi/consulta.sql", RAIZES, b"SELECT 5;\n",
                               sobrescrever=True, backup=True, marca="t", agora=datetime(2026, 9, 3, 1, 2, 3))
        assert exc.value.status == 502
        bak = "/dados/bi/consulta.sql.bak-20260903010203-000"
        assert fake.renames == [("/dados/bi/consulta.sql", bak), (bak, "/dados/bi/consulta.sql")]
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        assert not [p for p in fake.arvore if ".tmp-" in p or ".bak-" in p]

    def test_sobrescrever_preserva_as_permissoes_do_arquivo(self):
        # GRAVE da revisão: o inode novo nascia 0644 — um .param 0775 do grupo
        # deixava de ser gravável pelo job.
        fake = FakeSftp(ARVORE, modos={"/dados/bi/consulta.sql": 0o775})
        self._gravar(fake, "/dados/bi/consulta.sql", b"SELECT 6;\n", sobrescrever=True, backup=True)
        assert fake.modos["/dados/bi/consulta.sql"] == 0o775
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 6;\n"

    def test_chmod_recusado_aborta_sem_trocar_o_arquivo(self):
        fake = FakeSftp(ARVORE, modos={"/dados/bi/consulta.sql": 0o775}, falhar_chmod=True)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/consulta.sql", b"SELECT 7;\n", sobrescrever=True)
        assert exc.value.status == 403
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_backup_no_mesmo_instante_nao_da_502(self):
        from datetime import datetime
        fake = FakeSftp(ARVORE)
        mesmo = datetime(2026, 9, 3, 1, 2, 3, 456000)
        r1 = svc.gravar_arquivo(fake, "/dados/bi/consulta.sql", RAIZES, b"v1\n",
                                sobrescrever=True, backup=True, marca="m1", agora=mesmo)
        r2 = svc.gravar_arquivo(fake, "/dados/bi/consulta.sql", RAIZES, b"v2\n",
                                sobrescrever=True, backup=True, marca="m2", agora=mesmo)
        assert r1["backup"] == "/dados/bi/consulta.sql.bak-20260903010203-456"
        assert r2["backup"] == "/dados/bi/consulta.sql.bak-20260903010203-456-m2"
        assert fake.arvore[r1["backup"]] == b"SELECT 1;\n" and fake.arvore[r2["backup"]] == b"v1\n"
        assert fake.arvore["/dados/bi/consulta.sql"] == b"v2\n"

    def test_destino_link_para_dentro_grava_no_alvo(self):
        # `ler` segue o link; gravar também — senão o usuário edita o que leu e
        # o job (que usa o alvo) não vê a mudança.
        arvore = dict(ARVORE)
        arvore["/dados/bi/atalho.param"] = ("link", "/dados/param/parametros_latin1.param")
        fake = FakeSftp(arvore)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/atalho.param", b"x\n")
        assert exc.value.status == 409
        assert exc.value.extra["existente"]["tamanho_bytes"] == 15   # o ALVO, não o link
        r = self._gravar(fake, "/dados/bi/atalho.param", b"NOVO\n", sobrescrever=True)
        assert r["caminho"] == "/dados/param/parametros_latin1.param"
        assert fake.arvore["/dados/param/parametros_latin1.param"] == b"NOVO\n"
        assert fake.arvore["/dados/bi/atalho.param"] == ("link", "/dados/param/parametros_latin1.param")

    def test_destino_link_para_pasta_422(self):
        arvore = dict(ARVORE)
        arvore["/dados/bi/atalho.txt"] = ("link", "/dados/bi/logs")
        fake = FakeSftp(arvore)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/atalho.txt", sobrescrever=True)
        assert exc.value.status == 422

    def test_link_quebrado_para_dentro_e_substituido_por_arquivo(self):
        # O realpath do OpenSSH devolve o próprio caminho do link quebrado (o
        # alvo não resolve), o stat dá ENOENT e a gravação cria o arquivo NO
        # LUGAR do link — não há alvo para preservar.
        arvore = dict(ARVORE)
        arvore["/dados/bi/quebrado.txt"] = ("link", "/dados/bi/2026/nao_existe.txt")
        fake = FakeSftp(arvore)
        r = self._gravar(fake, "/dados/bi/quebrado.txt", b"vivo\n")
        assert r["criado"] is True and r["caminho"] == "/dados/bi/quebrado.txt"
        assert fake.arvore["/dados/bi/quebrado.txt"] == b"vivo\n"
        assert "/dados/bi/2026/nao_existe.txt" not in fake.arvore

    def test_nome_longo_demais_para_o_tmp_e_bak_422(self):
        with pytest.raises(svc.ArquivoError) as exc:
            svc.preparar_gravacao("/dados/bi", "a" * 230, "txt", RAIZES, ["txt"])
        assert exc.value.status == 422 and "215" in exc.value.detail
        assert svc.preparar_gravacao("/dados/bi", "a" * 211, "txt", RAIZES, ["txt"])

    def test_nome_com_controle_422(self):
        for ruim in ("qa\nquebra", "esc\x1b[31m", "del\x7f"):
            with pytest.raises(svc.ArquivoError) as exc:
                svc.validar_nome(ruim)
            assert exc.value.status == 422

    def test_falha_no_rename_sem_backup_tambem_limpa(self):
        fake = FakeSftp(ARVORE, falhar_rename=True)
        with pytest.raises(svc.ArquivoError):
            self._gravar(fake, "/dados/bi/2026/novo.txt")
        assert "/dados/bi/2026/novo.txt" not in fake.arvore
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_pasta_inexistente_404_sem_criar_pasta(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/nao_existe/x.txt")
        assert exc.value.status == 404
        assert "/dados/bi/nao_existe" not in fake.arvore

    def test_pasta_fora_da_raiz_e_symlink_para_fora_403(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/link_fora/x.txt")
        assert exc.value.status == 403 and exc.value.resultado == "negado"
        assert "/fora/x.txt" not in fake.arvore

    def test_destino_e_link_para_fora_403(self):
        arvore = dict(ARVORE)
        arvore["/dados/bi/segredo.txt"] = ("link", "/fora/segredo.txt")
        fake = FakeSftp(arvore)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/segredo.txt", sobrescrever=True)
        assert exc.value.status == 403
        assert fake.arvore["/fora/segredo.txt"] == b"nao pode\n"

    def test_destino_e_pasta_422(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/logs", sobrescrever=True)
        assert exc.value.status == 422

    def test_escrita_recusada_pelo_servidor_403_sem_tmp(self):
        fake = FakeSftp(ARVORE, falhar_escrita=True)
        with pytest.raises(svc.ArquivoError) as exc:
            self._gravar(fake, "/dados/bi/2026/novo.txt")
        assert exc.value.status == 403
        assert not [p for p in fake.arvore if ".tmp-" in p]


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

    def test_so_o_ultimo_componente_ausente_tambem_e_nao_existe(self, sftp):
        # O realpath do OpenSSH tolera o último componente ausente e devolve o
        # caminho; o "não existe" só aparece no stat. Antes virava 404 cru.
        r = svc.testar_raiz(sftp, "/dados/nao_existe")
        assert r["existe"] is False and r["caminho_real"] is None

    def test_raiz_symlink_diz_para_onde_aponta(self, sftp):
        r = svc.testar_raiz(sftp, "/dados/link_raiz/")
        assert r["existe"] and r["eh_pasta"] and r["legivel"]
        assert r["caminho_real"] == "/dados/param"
        assert r["detalhe"].startswith("é um link para /dados/param; ")


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
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": 2.5},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": True},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": -1},
        {"diretorio": "/dados/bi", "nome": "x", "ultimas_linhas": 100_001},
        {"diretorio": "/dados/bi", "nome": ["x"]}, {"diretorio": 5, "nome": "x"},
        {"diretorio": "/dados/bi", "nome": "x", "codificacao": ["utf-8"]},
        {"diretorio": "/dados/bi", "nome": "x", "codificacao": "utf-16"},
        {"diretorio": "/dados/bi", "nome": "x", "servidor": "outro"},
    ])
    def test_422_de_validacao_e_auditado(self, client, auth_operador, sftp_falso, body):
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_ler(client, cur, body).status_code == 422
        assert len(cur.auditoria) == 1
        assert cur.auditoria[0][6] == "erro"

    def test_ultimas_linhas_float_inteiro_e_string_sao_aceitos(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        for v in (200.0, "200"):
            r = _post_ler(client, cur, {"diretorio": "/dados/bi/logs", "nome": "grande.log", "ultimas_linhas": v})
            assert r.status_code == 200, v
            assert r.json()["linhas"] == 200

    def test_codificacao_invalida_e_recusada_sem_abrir_ssh(self, client, auth_operador, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql", "codificacao": "utf-16"})
        assert r.status_code == 422
        assert chamou == []

    def test_auditoria_corta_em_unidades_utf16_e_nao_some(self, client, auth_operador, sftp_falso):
        # 600 emojis: 623 code points, 1.223 unidades — o corte por code points
        # deixava o INSERT estourar e a auditoria da tentativa de traversal sumir.
        casos = [
            # o `..` engole os emojis no normpath → /etc → 403 negado (o pedido é o que se audita)
            ({"diretorio": "/dados/bi/" + "😀" * 600 + "/../../../etc", "nome": "passwd"}, 403, "negado"),
            # sem `..` o caminho normalizado continua com 1.210 unidades → 422 erro
            ({"diretorio": "/dados/bi/" + "😀" * 600, "nome": "x"}, 422, "erro"),
        ]
        for body, status, resultado in casos:
            cur = _Cursor(REGRAS_CONFIG)
            r = _post_ler(client, cur, body)
            assert r.status_code == status, body["diretorio"][:20]
            assert len(cur.auditoria) == 1
            assert cur.auditoria[0][6] == resultado
            caminho = cur.auditoria[0][3]
            assert svc.utf16_len(caminho) <= 1000
            caminho.encode("utf-16-le")  # sem par substituto partido

    def test_servidor_nao_configurado_503(self, client, auth_operador, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 503
        assert cur.auditoria[0][6] == "erro"

    def test_falha_ssh_502_generica_na_resposta_e_detalhada_na_auditoria(self, client, auth_operador, monkeypatch):
        @contextmanager
        def _cm(servidor):
            raise svc.ArquivoError(
                502, "Falha ao conectar ao servidor por SSH — detalhe registrado no log da API.",
                interno="srv:22: Authentication failed.")
            yield  # pragma: no cover
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 502
        assert "srv:22" not in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"
        assert cur.auditoria[0][7] == "srv:22: Authentication failed."

    def test_teto_de_tempo_vira_504(self, client, auth_operador, monkeypatch):
        import routers.utilitarios as rt
        monkeypatch.setattr(rt, "_TIMEOUT_S", 0.05)

        @contextmanager
        def _cm(servidor):
            import time as _t
            _t.sleep(0.3)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 504
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


def _post_gravar(client, cur, body):
    with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
        return client.post("/utilitarios/arquivo/gravar", json=body)


GRAVAR_OK = {"diretorio": "/dados/bi/2026", "nome": "novo", "extensao": "txt", "conteudo": "linha 1\r\nlinha 2"}


class TestGravarEndpoint:
    def test_operador_nao_grava_e_e_auditado_como_negado(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, GRAVAR_OK)
        assert r.status_code == 403
        assert "acao_editar" in r.json()["detail"]
        assert cur.auditoria[0][2] == "gravar" and cur.auditoria[0][6] == "negado"

    def test_dev_grava_com_lf_e_audita_com_hash(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, GRAVAR_OK)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["caminho"] == "/dados/bi/2026/novo.txt" and j["criado"] is True
        assert j["codificacao"] == "utf-8" and j["linhas"] == 2 and j["backup"] is None
        assert sftp_falso.arvore["/dados/bi/2026/novo.txt"] == b"linha 1\nlinha 2\n"
        usuario, servidor, acao, caminho, tamanho, sha, resultado, detalhe, dur = cur.auditoria[0]
        assert (acao, resultado, caminho, tamanho) == ("gravar", "ok", "/dados/bi/2026/novo.txt", 16)
        assert sha == hashlib.sha256(b"linha 1\nlinha 2\n").hexdigest()
        assert detalhe == "criado"

    def test_admin_tambem_grava(self, client, auth_admin, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_gravar(client, cur, GRAVAR_OK).status_code == 200

    def test_extensao_fora_da_lista_422(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)   # extensões cadastradas: sql, txt
        r = _post_gravar(client, cur, {**GRAVAR_OK, "extensao": "sh"})
        assert r.status_code == 422
        assert "'sh' não liberada" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"

    def test_existente_409_traz_o_que_existe_e_sobrescrever_grava_com_backup(self, client, auth_dev, sftp_falso):
        regras = REGRAS_CONFIG[:2] + [("FROM dbo.etl_app_config", [("utilitarios_arquivo_max_kb", "16"),
                                                                    ("utilitarios_arquivo_backup", "1")])]
        cur = _Cursor(regras)
        body = {"diretorio": "/dados/bi", "nome": "consulta", "extensao": "sql", "conteudo": "SELECT 9;"}
        r = _post_gravar(client, cur, body)
        assert r.status_code == 409
        assert r.json()["detail"]["mensagem"].startswith("O arquivo já existe")
        assert r.json()["detail"]["existente"]["tamanho_bytes"] == 10
        assert sftp_falso.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        r = _post_gravar(client, cur, {**body, "sobrescrever": True})
        assert r.status_code == 200, r.text
        assert r.json()["criado"] is False and r.json()["backup"].startswith("/dados/bi/consulta.sql.bak-")
        assert sftp_falso.arvore["/dados/bi/consulta.sql"] == b"SELECT 9;\n"
        assert "backup /dados/bi/consulta.sql.bak-" in cur.auditoria[-1][7]

    def test_backup_desligado_no_admin(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)   # utilitarios_arquivo_backup = 0
        body = {"diretorio": "/dados/bi", "nome": "consulta", "extensao": "sql", "conteudo": "SELECT 9;", "sobrescrever": True}
        r = _post_gravar(client, cur, body)
        assert r.status_code == 200 and r.json()["backup"] is None
        assert not [p for p in sftp_falso.arvore if ".bak-" in p]

    def test_latin1_grava_os_bytes_certos_e_recusa_caractere_fora(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, {**GRAVAR_OK, "conteudo": "ação", "codificacao": "latin-1"})
        assert r.status_code == 200
        assert sftp_falso.arvore["/dados/bi/2026/novo.txt"] == "ação\n".encode("latin-1")
        r = _post_gravar(client, cur, {**GRAVAR_OK, "nome": "outro", "conteudo": "10€", "codificacao": "latin-1"})
        assert r.status_code == 422 and "'€'" in r.json()["detail"]
        assert "/dados/bi/2026/outro.txt" not in sftp_falso.arvore

    def test_teto_413_e_nul_415(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)   # teto 16 KB
        r = _post_gravar(client, cur, {**GRAVAR_OK, "conteudo": "x" * (17 * 1024)})
        assert r.status_code == 413 and "acima do teto" in r.json()["detail"]
        r = _post_gravar(client, cur, {**GRAVAR_OK, "conteudo": "a\0b"})
        assert r.status_code == 415

    @pytest.mark.parametrize("body", [
        {**GRAVAR_OK, "conteudo": None}, {**GRAVAR_OK, "conteudo": 12},
        {**GRAVAR_OK, "sobrescrever": "sim"}, {**GRAVAR_OK, "nome": "a/b"},
        {**GRAVAR_OK, "nome": ""}, {**GRAVAR_OK, "extensao": "a.b"},
        {**GRAVAR_OK, "codificacao": "utf-16"}, {**GRAVAR_OK, "diretorio": "relativa"},
        {**GRAVAR_OK, "nome": ["a"]}, {**GRAVAR_OK, "nome": "qa\nquebra"},
        {**GRAVAR_OK, "extensao": 7}, {**GRAVAR_OK, "diretorio": None},
    ])
    def test_422_de_validacao_auditado(self, client, auth_dev, sftp_falso, body):
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_gravar(client, cur, body).status_code == 422
        assert len(cur.auditoria) == 1 and cur.auditoria[0][2] == "gravar"

    def test_fora_das_raizes_403_sem_ssh(self, client, auth_dev, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, {**GRAVAR_OK, "diretorio": "/etc"})
        assert r.status_code == 403 and chamou == []
        assert cur.auditoria[0][6] == "negado"

    def test_pasta_inexistente_404(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, {**GRAVAR_OK, "diretorio": "/dados/bi/nao_existe"})
        assert r.status_code == 404

    def test_servidor_nao_configurado_503(self, client, auth_dev, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_gravar(client, cur, GRAVAR_OK).status_code == 503


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

    @pytest.mark.parametrize("raiz_id", ["0", "-1", "99999999999999999999", "abc"])
    def test_id_fora_do_int_e_422_nao_500(self, client, auth_admin, sftp_falso, raiz_id):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.patch(f"/utilitarios/admin/raizes/{raiz_id}", json={"ativo": True}).status_code == 422
            assert client.post(f"/utilitarios/admin/raizes/{raiz_id}/testar").status_code == 422

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
        {"tamanho_max_kb": True, "backup_ao_sobrescrever": True},
        {"tamanho_max_kb": 2048.9, "backup_ao_sobrescrever": True},
        {"tamanho_max_kb": 10, "backup_ao_sobrescrever": "sim"},
    ])
    def test_422(self, client, auth_admin, body):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            assert client.put("/utilitarios/admin/config", json=body).status_code == 422

    @pytest.mark.parametrize("valor,esperado", [(2048.0, 2048), ("4096", 4096), (16384, 16384)])
    def test_inteiros_de_verdade_sao_aceitos(self, client, auth_admin, valor, esperado):
        cur = _Cursor([])
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.put("/utilitarios/admin/config", json={"tamanho_max_kb": valor, "backup_ao_sobrescrever": True})
        assert r.status_code == 200
        assert r.json()["tamanho_max_kb"] == esperado
