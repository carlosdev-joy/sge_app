"""Utilitários — transferência de arquivos, F1: download pela API
(spec docs/spec-utilitarios-transferencia.md).

Mesmas três camadas de tests/test_utilitarios_arquivos.py — de onde vêm o
FakeSftp, a árvore de amostra, o cursor falso e as autenticações:

  1. função PURA `content_disposition` (o nome do arquivo num cabeçalho HTTP);
  2. `baixar_arquivo` sobre o SFTP em memória: binário desce, o 413 acontece
     ANTES de abrir o arquivo, arquivo que encolheu no meio é 502, e a política
     de caminho é a mesma do `ler` (link para fora barra, link para outra raiz
     passa);
  3. `GET /utilitarios/arquivo/baixar`: cabeçalhos, auditoria `baixar` em toda
     saída, vaga de transferência (503 na hora, devolvida em sucesso, erro e
     504), spool que vai para o disco, degradações (sem SSH, sem migration).
"""
from __future__ import annotations

import errno
import hashlib
import io
import os
import re
import stat as statmod
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from routers import utilitarios as rt
from services import ssh_arquivos as svc
from tests.test_utilitarios_arquivos import (  # noqa: F401  (as fixtures entram pelo namespace)
    ARVORE, RAIZES, REGRAS_CONFIG, TETO, FakeSftp, _conn, _Cursor, _post_ler,
    auth_consulta, auth_dev, auth_operador, sftp, sftp_falso,
)

RAIZ_REPO = Path(__file__).resolve().parents[1]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Funções puras
# ═══════════════════════════════════════════════════════════════════════════

class TestContentDisposition:
    def test_ascii_simples(self):
        assert svc.content_disposition("carga.bin") == (
            "attachment; filename=\"carga.bin\"; filename*=UTF-8''carga.bin")

    def test_acento_e_espaco_vao_no_filename_estrela_e_o_resgate_e_ascii(self):
        cd = svc.content_disposition("relatório ção.txt")
        assert 'filename="relat_rio __o.txt"' in cd
        assert cd.endswith("filename*=UTF-8''relat%C3%B3rio%20%C3%A7%C3%A3o.txt")
        assert cd.isascii()  # cabeçalho HTTP não carrega UTF-8 cru

    def test_aspas_e_barra_invertida_nao_quebram_o_cabecalho(self):
        cd = svc.content_disposition('a"b\\c.txt')
        assert 'filename="a_b_c.txt"' in cd
        assert "filename*=UTF-8''a%22b%5Cc.txt" in cd

    def test_nome_vazio_ganha_resgate(self):
        assert svc.content_disposition("") == "attachment; filename=\"arquivo\"; filename*=UTF-8''"

    def test_caractere_de_formato_invisivel_vira_sublinhado_nos_dois_nomes(self):
        """U+202E inverte a leitura: "‮txt.exe" seria mostrado como "exe.txt"."""
        cd = svc.content_disposition("‮txt.exe")
        assert 'filename="_txt.exe"' in cd
        assert cd.endswith("filename*=UTF-8''_txt.exe")
        assert "%E2%80%AE" not in cd

    def test_cr_lf_nao_chegam_crus_ao_cabecalho(self):
        cd = svc.content_disposition("a\r\nX-Injected: 1")
        assert "\r" not in cd and "\n" not in cd
        assert 'filename="a__X-Injected: 1"' in cd


class TestValidarNomeFormatoInvisivel:
    @pytest.mark.parametrize("nome", ["‮txt.exe", "carga​.txt", "x­.bin"])
    def test_recusa_categoria_cf(self, nome):
        with pytest.raises(svc.ArquivoError) as ei:
            svc.validar_nome(nome)
        assert ei.value.status == 422
        assert "invisíveis" in ei.value.detail

    def test_acento_e_emoji_continuam_valendo(self):
        assert svc.validar_nome("relatório ção.txt") == "relatório ção.txt"
        assert svc.validar_nome("carga_😀.bin") == "carga_😀.bin"

    def test_teto_e_bloco_da_spec(self):
        assert svc.TRANSFERENCIA_MAX_BYTES == 50 * 1024 * 1024
        assert svc.BLOCO_TRANSFERENCIA == 256 * 1024

    def test_migration_105_acomoda_a_acao_nova_sem_check(self):
        """`acao` é VARCHAR(10) sem CHECK: 'baixar' cabe sem migration."""
        sql = (RAIZ_REPO / "sql/migrations/105_utilitarios_arquivos.sql").read_text(encoding="utf-8")
        assert re.search(r"\bacao\s+VARCHAR\(10\)", sql)
        assert not re.search(r"CHECK\s*\(", sql, re.IGNORECASE)
        assert len("baixar") <= 10


# ═══════════════════════════════════════════════════════════════════════════
# 2. Serviço sobre o SFTP em memória
# ═══════════════════════════════════════════════════════════════════════════

class FakeSftpContando(FakeSftp):
    """Conta os `open`: o 413 tem de acontecer ANTES de abrir o arquivo."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.abertos = 0

    def open(self, caminho, modo="rb"):
        self.abertos += 1
        return super().open(caminho, modo)


class FakeSftpEncolhe(FakeSftp):
    """`stat` diz 10 bytes a mais que o conteúdo: o arquivo encolheu entre o
    `stat` e o `read` (ou o servidor mentiu)."""

    def stat(self, caminho):
        st = super().stat(caminho)
        if statmod.S_ISREG(st.st_mode):
            st.st_size += 10
        return st


def _baixar(sftp_, caminho, teto=TETO):
    destino = io.BytesIO()
    r = svc.baixar_arquivo(sftp_, caminho, RAIZES, teto_bytes=teto, destino=destino)
    return r, destino.getvalue()


class TestBaixarArquivo:
    def test_binario_desce_integro_com_sha256(self, sftp):
        original = ARVORE["/dados/bi/imagem.bin"]
        r, dados = _baixar(sftp, "/dados/bi/imagem.bin")
        assert dados == original
        assert r["tamanho_bytes"] == len(original)
        assert r["sha256"] == hashlib.sha256(original).hexdigest()
        assert r["caminho"] == "/dados/bi/imagem.bin"
        assert r["modificado_em"]

    def test_texto_tambem_desce_sem_decodificar(self, sftp):
        original = ARVORE["/dados/param/parametros_latin1.param"]
        r, dados = _baixar(sftp, "/dados/param/parametros_latin1.param")
        assert dados == original  # bytes Latin-1 como estão, sem "codificacao"
        assert "codificacao" not in r and "conteudo" not in r

    def test_em_blocos_pequenos_o_resultado_e_o_mesmo(self, sftp, monkeypatch):
        monkeypatch.setattr(svc, "BLOCO_TRANSFERENCIA", 7)
        original = ARVORE["/dados/bi/logs/grande.log"]
        r, dados = _baixar(sftp, "/dados/bi/logs/grande.log", teto=10**9)
        assert dados == original
        assert r["sha256"] == hashlib.sha256(original).hexdigest()

    def test_arquivo_vazio(self):
        s = FakeSftp({**ARVORE, "/dados/bi/vazio.txt": b""})
        r, dados = _baixar(s, "/dados/bi/vazio.txt")
        assert dados == b""
        assert r["tamanho_bytes"] == 0
        assert r["sha256"] == hashlib.sha256(b"").hexdigest()

    def test_no_teto_exato_passa(self, sftp):
        tam = len(ARVORE["/dados/bi/consulta.sql"])
        r, _ = _baixar(sftp, "/dados/bi/consulta.sql", teto=tam)
        assert r["tamanho_bytes"] == tam

    def test_acima_do_teto_413_sem_abrir_o_arquivo(self):
        s = FakeSftpContando(ARVORE)
        tam = len(ARVORE["/dados/bi/logs/grande.log"])
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(s, "/dados/bi/logs/grande.log", teto=tam - 1)
        assert ei.value.status == 413
        assert s.abertos == 0
        assert "acima do teto" in ei.value.detail and "download" in ei.value.detail
        # No limite os dois arredondam para o mesmo "KB": os bytes exatos desempatam.
        assert f"({tam} bytes)" in ei.value.detail

    def test_erro_local_do_spool_e_502_da_api_nao_do_servidor(self, sftp):
        """`/tmp` da API cheio no rollover do spool NÃO pode virar "sem espaço
        no servidor" (507): o operador iria olhar o disco errado."""
        class _Cheio(io.BytesIO):
            def write(self, b):
                raise OSError(errno.ENOSPC, "No space left on device")
        with pytest.raises(svc.ArquivoError) as ei:
            svc.baixar_arquivo(sftp, "/dados/bi/consulta.sql", RAIZES, teto_bytes=TETO, destino=_Cheio())
        assert ei.value.status == 502
        assert "temporário na API" in ei.value.detail
        assert "servidor" not in ei.value.detail.split("—")[0]
        assert ei.value.interno and ei.value.interno.startswith("spool:")

    def test_pasta_422(self, sftp):
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(sftp, "/dados/bi/logs")
        assert ei.value.status == 422

    def test_nao_existe_404(self, sftp):
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(sftp, "/dados/bi/nao_existe.bin")
        assert ei.value.status == 404

    def test_link_para_fora_403_negado(self, sftp):
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(sftp, "/dados/bi/link_fora/segredo.txt")
        assert ei.value.status == 403
        assert ei.value.resultado == "negado"

    def test_link_para_outra_raiz_desce_pelo_alvo(self, sftp):
        r, dados = _baixar(sftp, "/dados/bi/2026/link_outra_raiz/parametros_latin1.param")
        assert r["caminho"] == "/dados/param/parametros_latin1.param"
        assert dados == ARVORE["/dados/param/parametros_latin1.param"]

    def test_fora_das_raizes_403_negado(self, sftp):
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(sftp, "/fora/segredo.txt")
        assert ei.value.status == 403
        assert ei.value.resultado == "negado"

    def test_arquivo_que_encolheu_502_com_interno(self):
        s = FakeSftpEncolhe(ARVORE)
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(s, "/dados/bi/consulta.sql", teto=10**6)
        assert ei.value.status == 502
        assert "mudou de tamanho" in ei.value.detail
        assert ei.value.interno and "esperava" in ei.value.interno

    def test_erro_do_servidor_ao_abrir_e_traduzido(self):
        class _Recusa(FakeSftp):
            def open(self, caminho, modo="rb"):
                raise OSError(errno.EACCES, "Permission denied")
        with pytest.raises(svc.ArquivoError) as ei:
            _baixar(_Recusa(ARVORE), "/dados/bi/consulta.sql")
        assert ei.value.status == 403
        assert "não tem permissão" in ei.value.detail

    def test_destino_recebe_so_o_que_o_stat_disse(self, sftp, monkeypatch):
        """Lê EXATAMENTE st_size: um log que cresce no meio sai como estava."""
        class _Cresce(FakeSftp):
            def open(self, caminho, modo="rb"):
                f = super().open(caminho, modo)
                return io.BytesIO(f.getvalue() + b"linha nova\n")
        original = ARVORE["/dados/bi/consulta.sql"]
        r, dados = _baixar(_Cresce(ARVORE), "/dados/bi/consulta.sql")
        assert dados == original
        assert r["tamanho_bytes"] == len(original)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Endpoint
# ═══════════════════════════════════════════════════════════════════════════

def _cm_de(sftp_):
    @contextmanager
    def _cm(servidor):
        assert servidor == "datastage"
        yield sftp_
    return _cm


def _get_baixar(client, cur, params):
    with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
        return client.get("/utilitarios/arquivo/baixar", params=params)


def _vagas_livres() -> int:
    return rt._VAGAS_TRANSFERENCIA._value  # noqa: SLF001


class TestBaixarEndpoint:
    def test_baixa_binario_com_cabecalhos_e_audita_ok(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "imagem.bin"})
        assert r.status_code == 200, r.text
        original = ARVORE["/dados/bi/imagem.bin"]
        assert r.content == original
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-length"] == str(len(original))
        assert r.headers["content-disposition"] == (
            "attachment; filename=\"imagem.bin\"; filename*=UTF-8''imagem.bin")
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-orquestra-sha256"] == hashlib.sha256(original).hexdigest()
        assert len(cur.auditoria) == 1
        usuario, servidor, acao, caminho, tamanho, sha, resultado, detalhe, dur = cur.auditoria[0]
        assert (usuario, servidor, acao, resultado) == ("C012345", "datastage", "baixar", "ok")
        assert caminho == "/dados/bi/imagem.bin"
        assert tamanho == len(original)
        assert sha == hashlib.sha256(original).hexdigest()
        assert isinstance(dur, int)
        assert _vagas_livres() == 2

    def test_o_que_o_ler_recusa_como_binario_o_baixar_entrega(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        assert _post_ler(client, cur, {"diretorio": "/dados/bi", "nome": "imagem.bin"}).status_code == 415
        assert _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "imagem.bin"}).status_code == 200

    def test_nome_com_acento_no_content_disposition(self, client, auth_dev, monkeypatch):
        s = FakeSftp({**ARVORE, "/dados/bi/relatório ção.txt": "ok\n".encode()})
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(s))
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "relatório ção.txt"})
        assert r.status_code == 200, r.text
        cd = r.headers["content-disposition"]
        assert 'filename="relat_rio __o.txt"' in cd
        assert "filename*=UTF-8''relat%C3%B3rio%20%C3%A7%C3%A3o.txt" in cd
        assert r.content == b"ok\n"

    def test_link_baixa_o_alvo_mas_o_nome_e_o_pedido(self, client, auth_operador, monkeypatch):
        s = FakeSftp({**ARVORE, "/dados/bi/atalho.param": ("link", "/dados/param/parametros_latin1.param")})
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(s))
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "atalho.param"})
        assert r.status_code == 200, r.text
        assert r.content == ARVORE["/dados/param/parametros_latin1.param"]
        assert 'filename="atalho.param"' in r.headers["content-disposition"]
        assert cur.auditoria[0][3] == "/dados/param/parametros_latin1.param"  # o REAL no rastro

    def test_fora_das_raizes_403_negado_sem_tocar_o_servidor(self, client, auth_operador, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi/../../etc", "nome": "passwd"})
        assert r.status_code == 403
        assert r.json()["detail"] == "Fora dos diretórios liberados."
        assert chamou == []
        assert cur.auditoria[0][2] == "baixar"
        assert cur.auditoria[0][6] == "negado"
        assert cur.auditoria[0][3] == "/dados/bi/../../etc/passwd"  # o caminho PEDIDO
        assert _vagas_livres() == 2  # negado antes de tomar vaga

    def test_symlink_para_fora_403_negado(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi/link_fora", "nome": "segredo.txt"})
        assert r.status_code == 403
        assert cur.auditoria[0][6] == "negado"
        assert cur.auditoria[0][3] == "/dados/bi/link_fora/segredo.txt"

    def test_nao_existe_404_audita_erro_e_devolve_a_vaga(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "nada.bin"})
        assert r.status_code == 404
        assert "não encontrado" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"
        assert cur.auditoria[0][3] == "/dados/bi/nada.bin"
        assert _vagas_livres() == 2

    def test_pasta_422(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "logs"})
        assert r.status_code == 422
        assert "é uma pasta" in r.json()["detail"]

    def test_acima_do_teto_413_sem_abrir_o_arquivo(self, client, auth_operador, monkeypatch):
        s = FakeSftpContando(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(s))
        monkeypatch.setattr(svc, "TRANSFERENCIA_MAX_BYTES", 100)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi/logs", "nome": "grande.log"})
        assert r.status_code == 413
        assert "acima do teto" in r.json()["detail"]
        assert s.abertos == 0
        assert cur.auditoria[0][6] == "erro"
        assert cur.auditoria[0][3] == "/dados/bi/logs/grande.log"

    def test_422_sem_pasta_sem_nome_ou_nome_invalido_audita(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"nome": "x.bin"})
        assert r.status_code == 422 and "Informe a pasta" in r.json()["detail"]
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi"})
        assert r.status_code == 422 and "nome do arquivo" in r.json()["detail"]
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": ".."})
        assert r.status_code == 422
        r = _get_baixar(client, cur, {"diretorio": "dados/bi", "nome": "x.bin"})
        assert r.status_code == 422 and "absoluto" in r.json()["detail"]
        assert len(cur.auditoria) == 4
        assert all(a[2] == "baixar" and a[6] == "erro" for a in cur.auditoria)

    def test_servidor_desconhecido_422_audita_com_o_nome_pedido(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"servidor": "outro", "diretorio": "/dados/bi", "nome": "x"})
        assert r.status_code == 422
        assert cur.auditoria[0][1] == "outro"

    def test_sem_raiz_para_o_servidor_403_negado(self, client, auth_operador, sftp_falso):
        regras = [("FROM dbo.etl_utilitario_raiz WHERE ativo = 1", [])] + REGRAS_CONFIG[1:]
        cur = _Cursor(regras)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 403
        assert "cadastre uma raiz" in r.json()["detail"]
        assert cur.auditoria[0][6] == "negado"

    def test_sem_vaga_503_na_hora_e_audita(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        try:
            t0 = time.time()
            r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
            dur = time.time() - t0
        finally:
            rt._VAGAS_TRANSFERENCIA.release()
            rt._VAGAS_TRANSFERENCIA.release()
        assert r.status_code == 503
        assert dur < 1
        assert "transferências em andamento" in r.json()["detail"]
        assert cur.auditoria[0][2] == "baixar" and cur.auditoria[0][6] == "erro"
        assert cur.auditoria[0][3] == "/dados/bi/consulta.sql"
        # Vaga devolvida: o próximo pedido passa.
        assert _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"}).status_code == 200
        assert _vagas_livres() == 2

    def test_timeout_504_devolve_a_vaga(self, client, auth_operador, monkeypatch):
        class _Lento(FakeSftp):
            def open(self, caminho, modo="rb"):
                time.sleep(0.3)
                return super().open(caminho, modo)
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(_Lento(ARVORE)))
        monkeypatch.setattr(rt, "_TIMEOUT_TRANSFERENCIA_S", 0.05)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 504
        assert "não respondeu em 0.05 s" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"
        assert _vagas_livres() == 2
        time.sleep(0.4)  # a thread presa termina antes do próximo teste

    def test_timeout_da_leitura_de_texto_continua_o_de_90_s(self):
        assert rt._TIMEOUT_S == 90
        assert rt._TIMEOUT_TRANSFERENCIA_S == 240
        assert rt._TIMEOUT_TRANSFERENCIA_S < 300  # proxy_read_timeout do nginx

    def test_inesperado_502_generico_com_interno_na_auditoria(self, client, auth_operador, monkeypatch):
        class _Quebra(FakeSftp):
            def open(self, caminho, modo="rb"):
                raise RuntimeError("boom")
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(_Quebra(ARVORE)))
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 502
        assert r.json()["detail"] == "Falha ao baixar o arquivo — detalhe registrado no log da API."
        assert cur.auditoria[0][7].startswith("inesperado:")
        assert _vagas_livres() == 2

    def test_ssh_nao_configurado_503_antes_de_qualquer_conexao(self, client, auth_operador, monkeypatch):
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        monkeypatch.delenv("DS_SSH_USER", raising=False)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 503
        assert "não configurado" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"
        assert _vagas_livres() == 2

    def test_spool_acima_da_memoria_vai_para_o_disco_e_desce_inteiro(self, client, auth_operador, sftp_falso, monkeypatch):
        """Intercepta o construtor: sem isto o teste passaria mesmo se o spool
        nunca rolasse para o disco (achado da revisão adversarial)."""
        monkeypatch.setattr(rt, "_SPOOL_MEMORIA", 1024)
        criados: list[tuple] = []
        original_cls = rt.tempfile.SpooledTemporaryFile

        def _spool(*a, **kw):
            s = original_cls(*a, **kw)
            criados.append((s, kw.get("max_size")))
            return s
        monkeypatch.setattr(rt.tempfile, "SpooledTemporaryFile", _spool)
        cur = _Cursor(REGRAS_CONFIG)
        original = ARVORE["/dados/bi/logs/grande.log"]
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi/logs", "nome": "grande.log"})
        assert r.status_code == 200
        assert r.content == original
        assert r.headers["content-length"] == str(len(original))
        assert len(criados) == 1
        spool, max_size = criados[0]
        assert max_size == 1024
        assert spool._rolled is True  # noqa: SLF001  (65 KB > 1 KB: foi para o disco)
        assert spool.closed  # o gerador fechou no fim

    def test_spool_pequeno_fica_em_memoria_e_tambem_fecha(self, client, auth_operador, sftp_falso, monkeypatch):
        criados: list = []
        original_cls = rt.tempfile.SpooledTemporaryFile

        def _spool(*a, **kw):
            s = original_cls(*a, **kw)
            criados.append(s)
            return s
        monkeypatch.setattr(rt.tempfile, "SpooledTemporaryFile", _spool)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 200
        assert criados[0]._rolled is False  # noqa: SLF001
        assert criados[0].closed

    def test_erro_pre_ssh_nao_vaza_o_interno_na_resposta(self, client, auth_operador, sftp_falso, monkeypatch):
        """`interno` é da auditoria; a resposta leva só o `detail` (auditoria de segurança)."""
        def _boom(*a, **kw):
            raise svc.ArquivoError(422, "frase pública", interno="segredo host:22")
        monkeypatch.setattr(svc, "preparar_leitura", _boom)
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "x.bin"})
        assert r.status_code == 422
        assert r.json()["detail"] == "frase pública"
        assert cur.auditoria[0][7] == "segredo host:22"

    def test_gravar_tambem_nao_vaza_o_interno_pre_ssh(self, client, auth_dev, sftp_falso, monkeypatch):
        from tests.test_utilitarios_arquivos import _post_gravar

        def _boom(*a, **kw):
            raise svc.ArquivoError(422, "frase pública", interno="segredo host:22")
        monkeypatch.setattr(svc, "preparar_gravacao", _boom)
        cur = _Cursor(REGRAS_CONFIG)
        r = _post_gravar(client, cur, {"diretorio": "/dados/bi", "nome": "x", "extensao": "txt", "conteudo": "a"})
        assert r.status_code == 422
        assert r.json()["detail"] == "frase pública"
        assert cur.auditoria[0][7] == "segredo host:22"

    def test_nome_com_formato_invisivel_422_no_endpoint(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "‮txt.exe"})
        assert r.status_code == 422
        assert "invisíveis" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"

    def test_consulta_403(self, client, auth_consulta):
        cur = _Cursor(REGRAS_CONFIG)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 403
        assert cur.auditoria == []  # barrado na dependência, antes do handler

    def test_sem_auth_401(self, client):
        assert client.get("/utilitarios/arquivo/baixar", params={"diretorio": "/x", "nome": "y"}).status_code == 401

    def test_sem_migration_105_503(self, client, auth_operador, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG, tabelas=0)
        r = _get_baixar(client, cur, {"diretorio": "/dados/bi", "nome": "consulta.sql"})
        assert r.status_code == 503
        assert "105" in r.json()["detail"]

    def test_config_traz_o_teto_de_transferencia(self, client, auth_dev):
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.get("/utilitarios/config")
        assert r.status_code == 200
        assert r.json()["transferencia_max_kb"] == 51200
