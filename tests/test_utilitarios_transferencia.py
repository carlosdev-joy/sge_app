"""Utilitários — transferência de arquivos: F1 (download) e F3 (upload) pela API
(spec docs/spec-utilitarios-transferencia.md).

Mesmas três camadas de tests/test_utilitarios_arquivos.py — de onde vêm o
FakeSftp, a árvore de amostra, o cursor falso e as autenticações:

  1. funções PURAS: `content_disposition` (o nome do arquivo num cabeçalho
     HTTP), `extensao_para_envio`/`preparar_envio` (nome completo vindo do PC);
  2. `baixar_arquivo` e `enviar_arquivo` sobre o SFTP em memória: binário desce
     e sobe, o 413 acontece ANTES de abrir o arquivo, arquivo que encolheu no
     meio é 502, spool que mente é 502 sem deixar `.tmp`, erro LOCAL não vira
     erro do servidor, e a política de caminho é a mesma do `ler`/`gravar`;
  3. `GET /utilitarios/arquivo/baixar` e `PUT /utilitarios/arquivo/enviar`:
     cabeçalhos, 411/413 pelo Content-Length ANTES do corpo, corpo que mente
     (400/413), auditoria em toda saída, vaga de transferência (503 na hora,
     devolvida em sucesso, erro e 504), spool que vai para o disco, degradações.
"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import io
import logging
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

from starlette.requests import ClientDisconnect

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


# ═══════════════════════════════════════════════════════════════════════════
# 4. Upload (F3) — funções puras
# ═══════════════════════════════════════════════════════════════════════════

class TestPrepararEnvio:
    def test_extensao_e_a_ultima_comparada_em_minusculas_e_o_nome_fica_como_esta(self):
        assert svc.extensao_para_envio("Relatorio.TXT", ["txt"]) == "txt"
        assert svc.extensao_para_envio("dados.tar.gz", ["gz"]) == "gz"
        caminho, raiz = svc.preparar_envio("/dados/bi/2026/", " Relatorio.TXT ", RAIZES, ["txt"])
        assert (caminho, raiz) == ("/dados/bi/2026/Relatorio.TXT", "/dados/bi")

    @pytest.mark.parametrize("nome", ["README", ".bashrc", "arquivo.", "sem_ponto"])
    def test_sem_extensao_422(self, nome):
        with pytest.raises(svc.ArquivoError) as ei:
            svc.extensao_para_envio(nome, ["txt", "sh"])
        assert ei.value.status == 422 and "sem extensão" in ei.value.detail

    def test_extensao_fora_da_lista_422_nomeando_a_ultima(self):
        with pytest.raises(svc.ArquivoError) as ei:
            svc.extensao_para_envio("x.txt.sh", ["txt"])
        assert ei.value.status == 422 and "'sh' não liberada" in ei.value.detail
        with pytest.raises(svc.ArquivoError) as ei:
            svc.extensao_para_envio("relatório.ção", ["ção"])   # fora da régua do servidor
        assert ei.value.status == 422

    def test_preparar_envio_fora_das_raizes_403_negado_e_nome_ruim_422(self):
        with pytest.raises(svc.ArquivoError) as ei:
            svc.preparar_envio("/etc", "x.txt", RAIZES, ["txt"])
        assert ei.value.status == 403 and ei.value.resultado == "negado"
        for ruim in ("a/b.txt", "..", "‮txt.exe", "x\ny.txt", ""):
            with pytest.raises(svc.ArquivoError) as ei:
                svc.preparar_envio("/dados/bi", ruim, RAIZES, ["txt", "exe"])
            assert ei.value.status == 422, ruim

    def test_nome_longo_deixa_espaco_para_tmp_e_bak(self):
        ok = "a" * (255 - 40 - 4) + ".txt"
        assert svc.preparar_envio("/dados/bi", ok, RAIZES, ["txt"])[0].endswith(ok)
        with pytest.raises(svc.ArquivoError) as ei:
            svc.preparar_envio("/dados/bi", "a" * (255 - 40 - 3) + ".txt", RAIZES, ["txt"])
        assert ei.value.status == 422 and ".tmp e o .bak" in ei.value.detail


# ═══════════════════════════════════════════════════════════════════════════
# 5. Upload (F3) — serviço sobre o SFTP em memória
# ═══════════════════════════════════════════════════════════════════════════

BINARIO = bytes(range(256)) * 40 + b"\x00\x00fim"


def _enviar(fake, caminho, dados=BINARIO, *, tamanho=None, origem=None, **kw):
    kw.setdefault("sobrescrever", False)
    kw.setdefault("backup", True)
    origem = io.BytesIO(dados) if origem is None else origem
    return svc.enviar_arquivo(fake, caminho, RAIZES, origem, len(dados) if tamanho is None else tamanho,
                              marca="t", **kw)


class TestEnviarArquivo:
    def test_binario_sobe_em_blocos_com_sha256_sem_deixar_tmp(self, monkeypatch):
        monkeypatch.setattr(svc, "BLOCO_TRANSFERENCIA", 7)
        fake = FakeSftp(ARVORE)
        r = _enviar(fake, "/dados/bi/2026/Carga.BIN")
        assert r == {"caminho": "/dados/bi/2026/Carga.BIN", "tamanho_bytes": len(BINARIO),
                     "sha256": hashlib.sha256(BINARIO).hexdigest(), "criado": True, "backup": None}
        assert fake.arvore["/dados/bi/2026/Carga.BIN"] == BINARIO
        assert not [p for p in fake.arvore if ".tmp-" in p]
        # Arquivo novo nasce com o modo do umask do sshd (o fake registra 0644): nunca +x.
        assert not (fake.modos.get("/dados/bi/2026/Carga.BIN", 0o644) & 0o111)

    def test_arquivo_vazio(self):
        fake = FakeSftp(ARVORE)
        r = _enviar(fake, "/dados/bi/vazio.txt", b"")
        assert r["tamanho_bytes"] == 0 and fake.arvore["/dados/bi/vazio.txt"] == b""

    def test_existente_409_com_o_que_existe(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/consulta.sql")
        assert ei.value.status == 409
        assert ei.value.extra["existente"]["tamanho_bytes"] == 10
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"

    def test_sobrescreve_com_backup_e_preserva_o_modo(self):
        fake = FakeSftp(ARVORE, modos={"/dados/bi/consulta.sql": 0o664})
        r = _enviar(fake, "/dados/bi/consulta.sql", b"SELECT 9;\n", sobrescrever=True)
        assert r["criado"] is False and r["backup"].startswith("/dados/bi/consulta.sql.bak-")
        assert fake.arvore[r["backup"]] == b"SELECT 1;\n"
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 9;\n"
        assert fake.modos["/dados/bi/consulta.sql"] == 0o664
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_falha_so_no_posix_rename_devolve_o_original(self):
        fake = FakeSftp(ARVORE, falhar_posix_rename=True)
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/consulta.sql", b"SELECT 9;\n", sobrescrever=True)
        assert ei.value.status == 502
        assert fake.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        assert not [p for p in fake.arvore if ".tmp-" in p or ".bak-" in p]

    def test_spool_menor_que_o_tamanho_502_sem_deixar_tmp_nem_destino(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/2026/curto.bin", b"abc", tamanho=10)
        assert ei.value.status == 502 and "não bate" in ei.value.detail
        assert "esperava 10 bytes, gravou 3" in ei.value.interno
        assert "/dados/bi/2026/curto.bin" not in fake.arvore
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_erro_local_do_spool_e_502_da_api_nao_do_servidor(self):
        class _Quebrado(io.BytesIO):
            def read(self, n=-1):
                raise OSError(errno.EIO, "Input/output error")
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/2026/x.bin", b"abc", origem=_Quebrado())
        assert ei.value.status == 502 and "temporário na API" in ei.value.detail
        assert ei.value.interno.startswith("spool:")
        assert not [p for p in fake.arvore if ".tmp-" in p]

    def test_pasta_somente_leitura_diz_a_causa(self):
        fake = FakeSftp(ARVORE, somente_leitura={"/dados/bi/2026"})
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/2026/x.bin", b"abc")
        assert ei.value.status == 502 and "somente leitura" in ei.value.detail

    def test_link_para_fora_403_e_gravar_arquivo_continua_igual(self):
        fake = FakeSftp(ARVORE)
        with pytest.raises(svc.ArquivoError) as ei:
            _enviar(fake, "/dados/bi/link_fora/x.bin", b"abc")
        assert ei.value.status == 403 and ei.value.resultado == "negado"
        r = svc.gravar_arquivo(fake, "/dados/bi/2026/texto.txt", RAIZES, b"oi\n",
                               sobrescrever=False, backup=True, marca="t")
        assert r["tamanho_bytes"] == 3 and r["sha256"] == hashlib.sha256(b"oi\n").hexdigest()
        assert fake.arvore["/dados/bi/2026/texto.txt"] == b"oi\n"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Upload (F3) — endpoint
# ═══════════════════════════════════════════════════════════════════════════

def _put_enviar(client, cur, params, content=b"", headers=None):
    with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
        return client.put("/utilitarios/arquivo/enviar", params=params, content=content,
                          headers={"Content-Type": "application/octet-stream", **(headers or {})})


ENVIAR_OK = {"diretorio": "/dados/bi/2026", "nome": "Relatorio.TXT"}


class TestEnviarEndpoint:
    def test_dev_envia_binario_com_nome_como_esta_e_audita_com_hash(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)   # extensões: sql, txt
        r = _put_enviar(client, cur, ENVIAR_OK, BINARIO)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["caminho"] == "/dados/bi/2026/Relatorio.TXT" and j["criado"] is True and j["backup"] is None
        assert j["tamanho_bytes"] == len(BINARIO) and j["sha256"] == hashlib.sha256(BINARIO).hexdigest()
        assert isinstance(j["duracao_ms"], int)
        assert sftp_falso.arvore["/dados/bi/2026/Relatorio.TXT"] == BINARIO
        usuario, servidor, acao, caminho, tamanho, sha, resultado, detalhe, dur = cur.auditoria[0]
        assert (acao, resultado, caminho, tamanho, detalhe) == ("enviar", "ok", "/dados/bi/2026/Relatorio.TXT", len(BINARIO), "criado")
        assert sha == hashlib.sha256(BINARIO).hexdigest()
        assert _vagas_livres() == 2

    def test_operador_403_negado_antes_de_tudo(self, client, auth_operador, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        assert r.status_code == 403 and "acao_editar" in r.json()["detail"]
        assert chamou == [] and cur.auditoria[0][2] == "enviar" and cur.auditoria[0][6] == "negado"

    def test_extensao_fora_da_lista_e_sem_extensao_422(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, {**ENVIAR_OK, "nome": "script.SH"}, b"x")
        assert r.status_code == 422 and "'sh' não liberada" in r.json()["detail"]
        r = _put_enviar(client, cur, {**ENVIAR_OK, "nome": "README"}, b"x")
        assert r.status_code == 422 and "sem extensão" in r.json()["detail"]
        assert len(cur.auditoria) == 2 and all(a[6] == "erro" for a in cur.auditoria)
        assert not [p for p in sftp_falso.arvore if p.endswith(("script.SH", "README"))]

    def test_fora_das_raizes_403_negado_sem_ssh(self, client, auth_dev, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, {**ENVIAR_OK, "diretorio": "/dados/bi/../../etc"}, b"x")
        assert r.status_code == 403 and chamou == []
        assert cur.auditoria[0][6] == "negado" and cur.auditoria[0][3] == "/dados/bi/../../etc/Relatorio.TXT"

    def test_content_length_acima_do_teto_413_antes_de_ler_o_corpo(self, client, auth_dev, monkeypatch):
        chamou = []

        @contextmanager
        def _cm(servidor):
            chamou.append(servidor)
            yield FakeSftp(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm)
        criados = []
        original_cls = rt.tempfile.SpooledTemporaryFile

        def _spool(*a, **kw):
            s = original_cls(*a, **kw)
            criados.append(s)
            return s
        monkeypatch.setattr(rt.tempfile, "SpooledTemporaryFile", _spool)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x", headers={"Content-Length": str(svc.TRANSFERENCIA_MAX_BYTES + 1)})
        assert r.status_code == 413, r.text
        assert "acima do teto" in r.json()["detail"] and f"({svc.TRANSFERENCIA_MAX_BYTES + 1} bytes)" in r.json()["detail"]
        assert criados == [] and chamou == []       # nem spool, nem SSH: o corpo não foi lido
        assert cur.auditoria[0][6] == "erro" and cur.auditoria[0][3] == "/dados/bi/2026/Relatorio.TXT"
        assert _vagas_livres() == 2

    def test_content_length_no_teto_exato_passa(self, client, auth_dev, sftp_falso, monkeypatch):
        monkeypatch.setattr(svc, "TRANSFERENCIA_MAX_BYTES", 5)
        cur = _Cursor(REGRAS_CONFIG)
        assert _put_enviar(client, cur, ENVIAR_OK, b"12345").status_code == 200
        assert _put_enviar(client, cur, {**ENVIAR_OK, "nome": "b.txt"}, b"123456").status_code == 413

    def test_corpo_menor_que_o_declarado_400_sem_gravar(self, client, auth_dev, sftp_falso):
        """No HTTP/1.1 real o h11/httptools enquadram pelo Content-Length e o
        cliente que mente vê 400 do próprio servidor HTTP (ou ClientDisconnect);
        este ramo é o cinto para o transporte ASGI direto — o TestClient o aciona."""
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"0123456789", headers={"Content-Length": "100"})
        assert r.status_code == 400, r.text
        assert "chegaram 10 de 100 bytes" in r.json()["detail"]
        assert "/dados/bi/2026/Relatorio.TXT" not in sftp_falso.arvore
        assert not [p for p in sftp_falso.arvore if ".tmp-" in p]
        assert cur.auditoria[0][6] == "erro" and _vagas_livres() == 2

    def test_corpo_maior_que_o_declarado_413(self, client, auth_dev, sftp_falso):
        """Idem: inalcançável no HTTP/1.1 real; prova o cinto pelo transporte ASGI."""
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"0123456789", headers={"Content-Length": "3"})
        assert r.status_code == 413, r.text
        assert "passou do tamanho declarado" in r.json()["detail"]
        assert "/dados/bi/2026/Relatorio.TXT" not in sftp_falso.arvore and _vagas_livres() == 2

    def test_sem_content_length_411_e_invalido_422(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, iter([b"abc"]))      # chunked: sem Content-Length
        assert r.status_code == 411, r.text
        assert "Content-Length" in r.json()["detail"]
        r = _put_enviar(client, cur, ENVIAR_OK, b"abc", headers={"Content-Length": "abc"})
        assert r.status_code == 422
        assert len(cur.auditoria) == 2 and all(a[2] == "enviar" for a in cur.auditoria)

    def test_corpo_vazio_cria_arquivo_de_zero_bytes(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, {**ENVIAR_OK, "nome": "vazio.txt"}, b"")
        assert r.status_code == 200 and r.json()["tamanho_bytes"] == 0
        assert sftp_falso.arvore["/dados/bi/2026/vazio.txt"] == b""

    def test_409_e_sobrescrever_com_backup_audita_sobrescrito(self, client, auth_dev, sftp_falso):
        regras = REGRAS_CONFIG[:2] + [("FROM dbo.etl_app_config", [("utilitarios_arquivo_max_kb", "16"),
                                                                    ("utilitarios_arquivo_backup", "1")])]
        cur = _Cursor(regras)
        params = {"diretorio": "/dados/bi", "nome": "consulta.sql"}
        r = _put_enviar(client, cur, params, b"SELECT 9;\n")
        assert r.status_code == 409
        assert r.json()["detail"]["mensagem"].startswith("O arquivo já existe")
        assert r.json()["detail"]["existente"]["tamanho_bytes"] == 10
        assert sftp_falso.arvore["/dados/bi/consulta.sql"] == b"SELECT 1;\n"
        r = _put_enviar(client, cur, {**params, "sobrescrever": "true"}, b"SELECT 9;\n")
        assert r.status_code == 200, r.text
        assert r.json()["criado"] is False and r.json()["backup"].startswith("/dados/bi/consulta.sql.bak-")
        assert sftp_falso.arvore["/dados/bi/consulta.sql"] == b"SELECT 9;\n"
        assert cur.auditoria[-1][7].startswith("sobrescrito; backup /dados/bi/consulta.sql.bak-")

    def test_spool_acima_da_memoria_vai_para_o_disco_e_sobe_inteiro(self, client, auth_dev, sftp_falso, monkeypatch):
        monkeypatch.setattr(rt, "_SPOOL_MEMORIA", 1024)
        criados = []
        original_cls = rt.tempfile.SpooledTemporaryFile

        def _spool(*a, **kw):
            s = original_cls(*a, **kw)
            criados.append(s)
            return s
        monkeypatch.setattr(rt.tempfile, "SpooledTemporaryFile", _spool)
        cur = _Cursor(REGRAS_CONFIG)
        grande = BINARIO * 8   # ~82 KB
        r = _put_enviar(client, cur, {**ENVIAR_OK, "nome": "grande.txt"}, grande)
        assert r.status_code == 200
        assert sftp_falso.arvore["/dados/bi/2026/grande.txt"] == grande
        assert criados[0]._rolled is True and criados[0].closed  # noqa: SLF001

    def test_sem_vaga_503_na_hora(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        try:
            r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        finally:
            rt._VAGAS_TRANSFERENCIA.release()
            rt._VAGAS_TRANSFERENCIA.release()
        assert r.status_code == 503 and "transferências em andamento" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro"

    def test_timeout_504_devolve_a_vaga(self, client, auth_dev, monkeypatch):
        class _Lento(FakeSftp):
            def normalize(self, caminho):
                time.sleep(0.3)
                return super().normalize(caminho)
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(_Lento(ARVORE)))
        monkeypatch.setattr(rt, "_TIMEOUT_TRANSFERENCIA_S", 0.05)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        assert r.status_code == 504 and cur.auditoria[0][6] == "erro"
        assert _vagas_livres() == 2
        time.sleep(0.5)  # a thread presa termina antes do próximo teste

    def test_inesperado_502_generico(self, client, auth_dev, monkeypatch):
        class _Quebra(FakeSftp):
            def normalize(self, caminho):
                raise RuntimeError("boom")
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(_Quebra(ARVORE)))
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        assert r.status_code == 502
        assert r.json()["detail"] == "Falha ao enviar o arquivo — detalhe registrado no log da API."
        assert cur.auditoria[0][7].startswith("inesperado:") and _vagas_livres() == 2

    def test_pasta_inexistente_404(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, {**ENVIAR_OK, "diretorio": "/dados/bi/nao_existe"}, b"x")
        assert r.status_code == 404 and cur.auditoria[0][6] == "erro"

    def test_servidor_nao_configurado_503_depois_de_receber_o_corpo(self, client, auth_dev, monkeypatch):
        """Sem `sftp_falso`: a `conexao_sftp` real recusa antes de importar o paramiko."""
        monkeypatch.delenv("DS_SSH_HOST", raising=False)
        monkeypatch.delenv("DS_SSH_USER", raising=False)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        assert r.status_code == 503 and "não configurado" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro" and _vagas_livres() == 2

    def test_consulta_403_sem_auth_401_sem_migration_503(self, client, auth_consulta):
        cur = _Cursor(REGRAS_CONFIG)
        assert _put_enviar(client, cur, ENVIAR_OK, b"x").status_code == 403
        assert cur.auditoria == []

    def test_sem_auth_401(self, client):
        assert client.put("/utilitarios/arquivo/enviar", params=ENVIAR_OK, content=b"x").status_code == 401

    def test_sem_migration_105_503(self, client, auth_dev, sftp_falso):
        cur = _Cursor(REGRAS_CONFIG, tabelas=0)
        r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        assert r.status_code == 503 and "105" in r.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. Upload (F3) — achados das revisões: ordem, drenagem, vaga, desistência, 504
# ═══════════════════════════════════════════════════════════════════════════

class TestEnviarRevisao:
    def test_permissao_vem_antes_do_content_length(self, client, auth_operador, sftp_falso):
        """Operador com corpo chunked ouve 403, não 411."""
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, iter([b"abc"]))
        assert r.status_code == 403 and cur.auditoria[0][6] == "negado"

    def test_erro_antes_do_corpo_drena_o_corpo_quando_ele_cabe(self, client, auth_operador, sftp_falso, monkeypatch):
        """Responder com corpo pendente vira 502 HTML do nginx: os erros drenam antes."""
        drenados = []

        async def _fake(request):
            drenados.append(request.headers.get("content-length"))
        monkeypatch.setattr(rt, "_drenar", _fake)
        cur = _Cursor(REGRAS_CONFIG)
        assert _put_enviar(client, cur, ENVIAR_OK, b"x" * 10).status_code == 403
        assert drenados == ["10"]

    def test_422_drena_mas_413_acima_do_teto_e_411_nao(self, client, auth_dev, sftp_falso, monkeypatch):
        drenados = []

        async def _fake(request):
            drenados.append(1)
        monkeypatch.setattr(rt, "_drenar", _fake)
        cur = _Cursor(REGRAS_CONFIG)
        assert _put_enviar(client, cur, {**ENVIAR_OK, "nome": "x.exe"}, b"xx").status_code == 422
        assert drenados == [1]
        assert _put_enviar(client, cur, ENVIAR_OK, b"x",
                           headers={"Content-Length": str(svc.TRANSFERENCIA_MAX_BYTES + 1)}).status_code == 413
        assert _put_enviar(client, cur, ENVIAR_OK, iter([b"abc"])).status_code == 411
        assert drenados == [1]   # acima do teto e sem tamanho: recusa na hora, sem drenar

    def test_drenar_consome_o_corpo_e_engole_erro(self):
        class _Req:
            def __init__(self, pedacos, quebrar=False):
                self._p, self.lidos, self.quebrar = pedacos, 0, quebrar

            def stream(self):
                async def gen():
                    for p in self._p:
                        self.lidos += len(p)
                        yield p
                    if self.quebrar:
                        raise ClientDisconnect()
                return gen()
        req = _Req([b"ab", b"cd"])
        asyncio.run(rt._drenar(req))
        assert req.lidos == 4
        asyncio.run(rt._drenar(_Req([b"ab"], quebrar=True)))   # não levanta

    def test_vaga_so_depois_do_corpo_inteiro_no_spool(self, client, auth_dev, sftp_falso, monkeypatch):
        """A vaga mede o SFTP, não a rede: um cliente lento não segura vaga."""
        ordem = []
        original_cls = rt.tempfile.SpooledTemporaryFile

        class _Spool(original_cls):
            def write(self, b):
                ordem.append("corpo")
                return super().write(b)
        monkeypatch.setattr(rt.tempfile, "SpooledTemporaryFile", _Spool)

        class _Sem:
            def acquire(self, blocking=True):
                ordem.append("vaga")
                return True

            def release(self):
                ordem.append("solta")
        monkeypatch.setattr(rt, "_VAGAS_TRANSFERENCIA", _Sem())
        cur = _Cursor(REGRAS_CONFIG)
        assert _put_enviar(client, cur, ENVIAR_OK, b"0123456789").status_code == 200
        assert ordem[0] == "corpo" and ordem.index("vaga") > ordem.index("corpo") and ordem[-1] == "solta"
        assert ordem.count("vaga") == 1 and ordem.count("solta") == 1

    def test_sem_vaga_nao_devolve_o_que_nao_tomou(self, client, auth_dev, sftp_falso):
        """BoundedSemaphore: um release a mais lançaria ValueError (502)."""
        cur = _Cursor(REGRAS_CONFIG)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        assert rt._VAGAS_TRANSFERENCIA.acquire(blocking=False)
        try:
            r = _put_enviar(client, cur, ENVIAR_OK, b"x")
        finally:
            rt._VAGAS_TRANSFERENCIA.release()
            rt._VAGAS_TRANSFERENCIA.release()
        assert r.status_code == 503 and _vagas_livres() == 2

    def test_cliente_desiste_400_auditado_sem_traceback(self, client, auth_dev, sftp_falso, monkeypatch, caplog):
        async def _stream(self):
            yield b"abc"
            raise ClientDisconnect()
        monkeypatch.setattr(rt.Request, "stream", _stream)
        cur = _Cursor(REGRAS_CONFIG)
        with caplog.at_level(logging.WARNING, logger="orquestra-api"):
            r = _put_enviar(client, cur, ENVIAR_OK, b"abcdefghij")
        assert r.status_code == 400
        assert cur.auditoria[0][6] == "erro" and "desistiu após 3 de 10 bytes" in cur.auditoria[0][7]
        assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
        assert _vagas_livres() == 2 and "/dados/bi/2026/Relatorio.TXT" not in sftp_falso.arvore

    def test_corpo_que_para_de_chegar_408_sem_tomar_vaga(self, client, auth_dev, sftp_falso, monkeypatch):
        async def _stream(self):
            yield b"abc"
            await asyncio.sleep(0.3)
            yield b"defghij"
        monkeypatch.setattr(rt.Request, "stream", _stream)
        monkeypatch.setattr(rt, "_TIMEOUT_CORPO_S", 0.05)
        cur = _Cursor(REGRAS_CONFIG)
        r = _put_enviar(client, cur, ENVIAR_OK, b"abcdefghij")
        assert r.status_code == 408 and "nenhum dado chegou" in r.json()["detail"]
        assert cur.auditoria[0][6] == "erro" and _vagas_livres() == 2
        assert "/dados/bi/2026/Relatorio.TXT" not in sftp_falso.arvore

    def test_504_no_meio_da_escrita_apaga_o_tmp_e_registra_o_desfecho_tardio(self, client, auth_dev, monkeypatch):
        """A thread sobrevive ao 504: o próximo `read` no spool fechado falha, o
        `.tmp` some e o desfecho entra na auditoria (achado das duas revisões)."""
        class _Lento(FakeSftp):
            def _abrir_para_escrita(self, caminho):
                escritor = super()._abrir_para_escrita(caminho)
                original = escritor.write

                def devagar(b):
                    time.sleep(0.2)
                    return original(b)
                escritor.write = devagar
                return escritor
        fake = _Lento(ARVORE)
        monkeypatch.setattr(svc, "conexao_sftp", _cm_de(fake))
        monkeypatch.setattr(svc, "BLOCO_TRANSFERENCIA", 4)
        monkeypatch.setattr(rt, "_TIMEOUT_TRANSFERENCIA_S", 0.05)
        cur = _Cursor(REGRAS_CONFIG)
        with patch("routers.utilitarios.get_db_conn", return_value=_conn(cur)):
            r = client.put("/utilitarios/arquivo/enviar", params=ENVIAR_OK, content=b"0123456789ab",
                           headers={"Content-Type": "application/octet-stream"})
            assert r.status_code == 504
            assert _vagas_livres() == 2
            for _ in range(60):
                if len(cur.auditoria) >= 2:
                    break
                time.sleep(0.05)
        assert not [p for p in fake.arvore if ".tmp-" in p]
        assert "/dados/bi/2026/Relatorio.TXT" not in fake.arvore
        assert len(cur.auditoria) == 2, cur.auditoria
        assert cur.auditoria[0][6] == "erro" and "não respondeu" in cur.auditoria[0][7]
        assert cur.auditoria[1][6] == "erro" and "após o 504" in cur.auditoria[1][7]

    def test_tmp_e_criado_com_exclusividade(self):
        class _Modos(FakeSftp):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.modos_abertura = []

            def open(self, caminho, modo="rb"):
                self.modos_abertura.append((caminho, modo))
                return super().open(caminho, modo)
        fake = _Modos(ARVORE)
        _enviar(fake, "/dados/bi/2026/x.bin", b"abc")
        assert [m for c, m in fake.modos_abertura if ".tmp-" in c] == ["wxb"]
        svc.gravar_arquivo(fake, "/dados/bi/2026/y.txt", RAIZES, b"oi\n", sobrescrever=False, backup=True, marca="t")
        assert [m for c, m in fake.modos_abertura if ".tmp-" in c] == ["wxb", "wxb"]

    def test_spool_fechado_no_download_vira_502_local(self, sftp):
        """ValueError do spool fechado por um 504 não é erro do servidor."""
        fechado = io.BytesIO()
        fechado.close()
        with pytest.raises(svc.ArquivoError) as ei:
            svc.baixar_arquivo(sftp, "/dados/bi/consulta.sql", RAIZES, teto_bytes=TETO, destino=fechado)
        assert ei.value.status == 502 and "temporário na API" in ei.value.detail
