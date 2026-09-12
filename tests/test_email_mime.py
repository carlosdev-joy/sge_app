"""E-mail — as regras puras e a entrega (F1 da spec docs/spec-notificacao-email.md).

O que se prende:

  1. **Anti-drift API × worker**: o bloco puro de `dags/utils/email_envio.py`
     é IDÊNTICO ao de `api/services/email_mime.py` (constantes e código de cada
     função) — os dois containers não se importam, e uma régua que diverge
     aceita na tela o que o disparo recusa.
  2. **Nada do usuário vira comando**: `comando_sendmail` é fixo (`<bin> -t -i`),
     a mensagem vai pelo stdin, e cabeçalhos com quebra de linha são recusados
     antes (assunto, remetente, destinatário) — o vetor de injeção de
     cabeçalho/comando não existe.
  3. **Régua**: endereço, duplicata por caixa, domínios permitidos, raízes
     (absolutas, sem `..`), limite 1–25 MB, assunto ≤ 500 UTF-16, corpo ≤ 20k,
     anexo do cadastro = raiz permitida + nome LIVRE (pode não existir, pode
     ter placeholder, mas sem barra/`..`), caminho resolvido preso à raiz.
  4. **MIME**: From/To/Subject/Date/Message-ID, texto simples sempre, HTML como
     alternativa, anexo com tipo pelo nome, bytes prontos para o sendmail.
  5. **`enviar()`**: escreve os bytes no stdin, fecha o canal de escrita, lê rc
     e stderr; rc != 0 volta para quem chama decidir.
"""
from __future__ import annotations

import email
import email.policy
import errno
import inspect
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))
sys.path.insert(0, str(RAIZ / "dags"))

from services import email_mime as em  # noqa: E402
from utils import email_envio as ew  # noqa: E402


# ═══════════ 1. anti-drift ═══════════════════════════════════════════════════

FUNCOES = ["_sem_quebra", "validar_email", "normalizar_lista", "validar_destinatarios", "validar_raizes", "validar_dominios",
           "validar_limite_anexo", "validar_assunto", "validar_corpo", "pasta_do_anexo", "validar_anexo_cadastro",
           "caminho_do_anexo", "interpolar", "documento_html", "montar_mensagem"]
CONSTANTES = ["LIMITE_ASSUNTO", "LIMITE_CORPO", "LIMITE_DESTINATARIOS", "LIMITE_ANEXO_MB_MIN", "LIMITE_ANEXO_MB_MAX",
              "LIMITE_ANEXO_MB_PADRAO", "LIMITE_NOME_ANEXO", "LIMITE_PASTA_ANEXO"]


@pytest.mark.parametrize("nome", FUNCOES)
def test_funcao_identica_na_api_e_no_worker(nome):
    assert inspect.getsource(getattr(em, nome)) == inspect.getsource(getattr(ew, nome)), nome


@pytest.mark.parametrize("nome", CONSTANTES + ["EMAIL_RE", "RAIZ_RE", "NOME_ANEXO_PROIBIDO_RE", "PLACEHOLDER_RE"])
def test_constante_identica_na_api_e_no_worker(nome):
    a, b = getattr(em, nome), getattr(ew, nome)
    assert (a.pattern if hasattr(a, "pattern") else a) == (b.pattern if hasattr(b, "pattern") else b), nome


# ═══════════ 2. nada do usuário vira comando ═════════════════════════════════

def test_comando_sendmail_e_fixo_e_valida_o_binario_e_o_remetente():
    assert ew.comando_sendmail("orquestra@cvp.com.br", "/usr/sbin/sendmail") == "/usr/sbin/sendmail -t -i -f orquestra@cvp.com.br"
    assert ew.comando_sendmail("Orq+x@CVP.com.br", "/usr/sbin/sendmail.postfix") == "/usr/sbin/sendmail.postfix -t -i -f Orq+x@cvp.com.br"
    for ruim in ("sendmail", "/usr/sbin/sendmail; rm -rf /", "/usr/../bin/x", "/usr/sbin/send mail"):
        with pytest.raises(ValueError):
            ew.comando_sendmail("a@x.com", ruim)
    # o remetente é o ÚNICO argumento vindo de configuração: allowlist antes, citado depois
    for ruim in ("a@x.com; id", "a@x.com`id`", "$(id)@x.com", "a b@x.com", "", "a@x.com\n-C/etc/passwd"):
        with pytest.raises(ValueError):
            ew.comando_sendmail(ruim, "/usr/sbin/sendmail")
    assert ew.comando_sendmail("a@x.com", "") == f"{ew.SENDMAIL_BIN} -t -i -f a@x.com"   # binário vazio = o do ambiente


@pytest.mark.parametrize("campo, valor", [("assunto", "Teste\nBcc: x@y.com"), ("assunto", "a\rb")])
def test_cabecalho_com_quebra_de_linha_e_recusado(campo, valor):
    assert em.validar_assunto(valor)[1] == "assunto não pode ter quebra de linha"
    with pytest.raises(ValueError):
        em.montar_mensagem("a@x.com", ["b@x.com"], valor, "corpo")


def test_sem_quebra_cobre_o_que_a_stdlib_recusa():
    """Tudo que `splitlines()` separa viraria cabeçalho novo na montagem."""
    for sep in ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x85", "\u2028", "\u2029"):
        assert em.validar_assunto(f"a{sep}b")[1] == "assunto não pode ter quebra de linha", repr(sep)
    assert em.validar_assunto("a b")[1] is None


def test_remetente_e_destinatario_com_quebra_sao_invalidos():
    assert em.validar_email("a@x.com\nBcc: c@x.com") is None
    assert em.validar_email("a@x.com\rBcc: c@x.com") is None
    assert em.validar_email("a@x.com\r") == "a@x.com"            # quebra SÓ na ponta é aparada, não injeta
    assert em.validar_destinatarios(["ok@x.com", "a@x.com\nBcc: c@x.com"])[1]


def test_cabecalho_extra_so_aceita_nome_e_valor_sem_quebra():
    m = email.message_from_bytes(em.montar_mensagem("a@x.com", ["b@x.com"], "s", "c",
                                                     cabecalho_extra={"X-Run": "abc", "Bad Name": "1", "X-Q": "a\nb"}),
                                 policy=email.policy.default)
    assert m["X-Run"] == "abc" and m["Bad Name"] is None and m["X-Q"] is None
    # cabeçalhos estruturais nunca: um Bcc extra seria ENTREGUE pelo -t
    m = email.message_from_bytes(em.montar_mensagem("a@x.com", ["b@x.com"], "s", "c",
                                                     cabecalho_extra={"Bcc": "z@x.com", "bcc": "y@x.com", "To": "w@x.com",
                                                                      "Content-Type": "text/html", "X-Ok": "1"}),
                                 policy=email.policy.default)
    assert m["Bcc"] is None and m["To"] == "b@x.com" and m["X-Ok"] == "1" and m.get_content_type() == "text/plain"


# ═══════════ 3. régua ════════════════════════════════════════════════════════

@pytest.mark.parametrize("valor, esperado", [
    ("Joao.Silva@CaixaVidaEPrevidencia.com.br", "Joao.Silva@caixavidaeprevidencia.com.br"),
    ("  a@x.io  ", "a@x.io"), ("a+b@x.co", "a+b@x.co"),
    ("sem-arroba", None), ("a@", None), ("a@x", None), ("a b@x.com", None), ("a@x.com,b@x.com", None),
    ("'a'@x.com", None), ("", None), (None, None), ("a" * 250 + "@x.com", None),
])
def test_validar_email(valor, esperado):
    assert em.validar_email(valor) == esperado


def test_destinatarios_texto_lista_duplicata_e_dominios():
    validos, erros = em.validar_destinatarios("A@X.com; b@y.org\n a@x.com , ruim", ["x.com", "@Y.ORG"])
    assert validos == ["A@x.com", "b@y.org"] and erros == ["endereço inválido: 'ruim'"]
    validos, erros = em.validar_destinatarios(["a@x.com", "b@z.net"], ["x.com"])
    assert validos == ["a@x.com"] and erros == ["domínio não permitido: 'b@z.net' (permitidos: x.com)"]
    assert em.validar_destinatarios(None) == ([], [])
    muitos = [f"u{i}@x.com" for i in range(51)]
    assert any("no máximo 50" in e for e in em.validar_destinatarios(muitos)[1])


def test_raizes_dominios_limite_assunto_corpo():
    assert em.validar_raizes("/dados/saida/\n/opt/IBM/dados;/dados/saida") == (["/dados/saida", "/opt/IBM/dados"], [])
    _, erros = em.validar_raizes(["relativo", "/com espaco/x", "/a/../b", "/x'y", "/", "/a/./b"])
    assert len(erros) == 6 and any("servidor inteiro" in e for e in erros)
    assert em.validar_raizes("//dados//saida/") == (["//dados/saida"], []) or em.validar_raizes("/dados//saida/") == (["/dados/saida"], [])
    assert em.validar_dominios("caixavidaeprevidencia.com.br, @X.IO") == (["caixavidaeprevidencia.com.br", "x.io"], [])
    assert em.validar_dominios(["ruim"])[1]
    assert em.validar_limite_anexo("5") == (5, None) and em.validar_limite_anexo(0)[1] and em.validar_limite_anexo(26)[1]
    assert em.validar_limite_anexo("x")[1]
    assert em.validar_assunto("  ok ")[0] == "ok" and em.validar_assunto("")[1] == "assunto obrigatório"
    assert em.validar_assunto("🙂" * 251)[1] == "assunto com mais de 500 caracteres"   # UTF-16: 502 unidades
    assert em.validar_corpo("a\r\nb")[0] == "a\nb" and em.validar_corpo("  ")[1] and em.validar_corpo("x" * 20001)[1]


def test_anexo_do_cadastro_raiz_permitida_e_nome_livre():
    raizes = ["/dados/saida", "/opt/IBM/dados"]
    assert em.validar_anexo_cadastro("/dados/saida/", "relatorio_{odate}.xlsx", raizes) == (
        {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"}, [])
    assert em.validar_anexo_cadastro("", "", raizes) == (None, [])               # sem anexo
    assert em.validar_anexo_cadastro("/tmp", "x.csv", raizes)[1] == ["anexo: a pasta '/tmp' não está entre as permitidas no Admin › E-mail"]
    assert em.validar_anexo_cadastro("/dados/saida", "", raizes)[1] == ["anexo: informe o nome do arquivo"]
    for nome in ("sub/x.csv", "..", "../x", "x\ny", "a\\b", "."):
        _, erros = em.validar_anexo_cadastro("/dados/saida", nome, raizes)
        assert erros and "barra" in erros[0], nome
    assert em.validar_anexo_cadastro("/dados/saida", "x" * 201, raizes)[1]
    assert em.validar_anexo_cadastro("/dados/saida", "..x..csv", raizes)[1] == []   # pontos no nome não são traversal


def test_caminho_do_anexo_resolvido_preso_a_raiz():
    raizes = ["/dados/saida"]
    assert em.caminho_do_anexo("/dados/saida", "rel_2026-09-10.xlsx", raizes) == "/dados/saida/rel_2026-09-10.xlsx"
    assert em.caminho_do_anexo("/dados/saida", "../etc/passwd", raizes) is None
    assert em.caminho_do_anexo("/dados/saida", "..", raizes) is None
    assert em.caminho_do_anexo("/dados/saida", "", raizes) is None
    assert em.caminho_do_anexo("/dados/saidax", "a.csv", raizes) is None       # prefixo parecido não vale
    assert em.caminho_do_anexo("/dados/saida", "a/b.csv", raizes) is None
    assert em.caminho_do_anexo("/dados/saida", ".", raizes) is None          # "." seria o próprio diretório
    assert em.caminho_do_anexo("/dados/saida/", "x.csv", ["/dados/saida/"]) == "/dados/saida/x.csv"


def test_interpolar_mantem_placeholder_desconhecido():
    assert em.interpolar("Carga {pipeline} em {data} {nada} {linhas}", {"pipeline": "P", "data": "10/09/2026", "linhas": None}) \
        == "Carga P em 10/09/2026 {nada} {linhas}"


# ═══════════ 4. MIME ═════════════════════════════════════════════════════════

def test_montar_mensagem_texto_html_e_anexo():
    raw = em.montar_mensagem("Orq@X.com", ["a@x.com", "A@X.COM", "b@y.org"], "Carga OK", "<b>Olá</b> mundo",
                             html=True, anexo_nome="rel.xlsx", anexo_bytes=b"\x00\x01")
    m = email.message_from_bytes(raw, policy=email.policy.default)
    assert m["From"] == "Orq@x.com" and m["To"] == "a@x.com, b@y.org" and m["Subject"] == "Carga OK"
    assert m["Date"] and m["Message-ID"].endswith("@x.com>") and m["X-Orquestra"] == "1"
    partes = {p.get_content_type(): p for p in m.walk()}
    assert "text/plain" in partes and "text/html" in partes
    assert partes["text/plain"].get_content().strip() == "Olá mundo"
    anexos = [p for p in m.walk() if p.get_filename()]
    assert anexos[0].get_filename() == "rel.xlsx" and anexos[0].get_payload(decode=True) == b"\x00\x01"
    assert anexos[0].get_content_type() in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            "application/octet-stream")
    simples = email.message_from_bytes(em.montar_mensagem("a@x.com", ["b@x.com"], "s", "linha1\nlinha2"), policy=email.policy.default)
    assert simples.get_content_type() == "text/plain" and simples.get_content() == "linha1\nlinha2\n"


def test_montar_mensagem_recusa_remetente_e_destinatario_invalidos():
    with pytest.raises(ValueError):
        em.montar_mensagem("ruim", ["b@x.com"], "s", "c")
    with pytest.raises(ValueError):
        em.montar_mensagem("a@x.com", [], "s", "c")
    with pytest.raises(ValueError):
        em.montar_mensagem("a@x.com", ["ruim"], "s", "c")


# ═══════════ 5. enviar() ═════════════════════════════════════════════════════

class _Canal:
    def __init__(self, rc):
        self.rc, self.fechado = rc, False

    def shutdown_write(self):
        self.fechado = True

    def recv_exit_status(self):
        return self.rc


class _Fluxo:
    def __init__(self, canal, dados=b""):
        self.channel, self._dados, self.escrito = canal, dados, b""

    def write(self, b):
        self.escrito += b

    def read(self):
        return self._dados


class _Cliente:
    def __init__(self, rc=0, stderr=b""):
        self.canal = _Canal(rc)
        self.stdin, self.stdout, self.stderr = _Fluxo(self.canal), _Fluxo(self.canal), _Fluxo(self.canal, stderr)
        self.comandos = []

    def exec_command(self, cmd, timeout=None):
        self.comandos.append((cmd, timeout))
        return self.stdin, self.stdout, self.stderr


def test_enviar_escreve_no_stdin_fecha_e_le_rc():
    c = _Cliente(rc=0)
    r = ew.enviar(c, b"From: a@x.com\nTo: b@x.com\nSubject: s\n\ncorpo", "a@x.com", timeout=30, binario="/usr/sbin/sendmail")
    assert c.comandos == [("/usr/sbin/sendmail -t -i -f a@x.com", 30)]
    assert c.stdin.escrito.startswith(b"From: a@x.com") and c.canal.fechado
    assert r["exit_code"] == 0 and r["stderr"] == "" and isinstance(r["duration_ms"], int)
    c = _Cliente(rc=75, stderr=b"deferred: relay down")
    r = ew.enviar(c, b"x", "a@x.com", binario="/usr/sbin/sendmail")
    assert r["exit_code"] == 75 and r["stderr"] == "deferred: relay down"


def test_enviar_com_stdin_fechado_pelo_sendmail_e_diagnostico_e_nao_rede():
    class _FluxoQueFecha(_Fluxo):
        def write(self, b):
            raise OSError("Socket is closed")
    c = _Cliente(rc=0)
    c.stdin = _FluxoQueFecha(c.canal)
    r = ew.enviar(c, b"x" * 10, "a@x.com", binario="/usr/sbin/sendmail")
    assert r["exit_code"] == -1 and "fechou a entrada" in r["stderr"]


# ═══════════ anexo pelo SFTP (F2) ════════════════════════════════════════════

class _Stat:
    def __init__(self, size, mode=0o100644):
        self.st_size, self.st_mode = size, mode


class _Arquivo:
    def __init__(self, dados):
        self.dados = dados

    def read(self):
        return self.dados

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Sftp:
    """SFTP de mentira: `arquivos` mapeia caminho -> (bytes, modo)."""

    def __init__(self, arquivos=None, erro_stat=None, links=None, sem_normalize=False):   # noqa: D107
        self.arquivos = arquivos or {}
        self.erro_stat = erro_stat
        self.abertos = []
        # `links` mapeia link de DIRETÓRIO -> alvo real, como no servidor.
        self.links = links or {}
        self.sem_normalize = sem_normalize

    def stat(self, caminho):
        if self.erro_stat:
            raise self.erro_stat
        # `stat` SEGUE link (é `lstat` que não segue) — é justamente por isso
        # que a régua lexical do cadastro não basta.
        caminho = self._real(caminho)
        if caminho not in self.arquivos:
            raise IOError(errno.ENOENT, f"No such file: {caminho}")   # como o paramiko
        dados, modo = self.arquivos[caminho]
        return _Stat(len(dados), modo)

    def open(self, caminho, modo="rb"):
        self.abertos.append(caminho)
        return _Arquivo(self.arquivos[self._real(caminho)][0])

    def _real(self, caminho):
        for link, alvo in (self.links or {}).items():
            if caminho == link or caminho.startswith(link.rstrip("/") + "/"):
                return alvo.rstrip("/") + caminho[len(link.rstrip("/")):]
        return caminho

    def normalize(self, caminho):
        """`realpath` do servidor: resolve o link de DIRETÓRIO, como o OpenSSH."""
        if self.sem_normalize:
            raise IOError("não implementado")
        return self._real(caminho)


RAIZES = ["/dados/saida"]
MAPA = {"odate": "20260911", "pipeline": "CARGA_VIDA"}


def test_resolver_anexo_le_o_arquivo_do_dia():
    sftp = _Sftp({"/dados/saida/relatorio_20260911.xlsx": (b"conteudo", 0o100644)})
    dados, aviso, det = ew.resolver_anexo(sftp, "/dados/saida", "relatorio_{odate}.xlsx", RAIZES, 5, MAPA)
    assert dados == b"conteudo" and aviso is None
    assert det == {"caminho": "/dados/saida/relatorio_20260911.xlsx", "bytes": 8}


def test_resolver_anexo_ausente_nao_derruba_a_corrida():
    dados, aviso, det = ew.resolver_anexo(_Sftp(), "/dados/saida", "relatorio_{odate}.xlsx", RAIZES, 5, MAPA)
    assert dados is None and "não encontrado" in aviso and det["bytes"] is None
    assert det["caminho"] == "/dados/saida/relatorio_20260911.xlsx"      # o log diz ONDE procurou


def test_resolver_anexo_recusa_placeholder_que_escapa_da_raiz():
    sftp = _Sftp({"/etc/passwd": (b"root:x:0:0", 0o100644)})
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "{fuga}", RAIZES, 5, {"fuga": "../../etc/passwd"})
    assert dados is None and "sai da raiz permitida" in aviso and sftp.abertos == []


def test_resolver_anexo_recusa_o_que_nao_e_arquivo_regular():
    """Ressalva da revisão da F1: `sftp.open()` num diretório pendura ou lê lixo."""
    sftp = _Sftp({"/dados/saida/pasta": (b"", 0o040755)})
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "pasta", RAIZES, 5, MAPA)
    assert dados is None and "não é um arquivo" in aviso and sftp.abertos == []


def test_resolver_anexo_respeita_o_limite_do_admin_antes_de_ler():
    grande = b"x" * (2 * 1024 * 1024 + 1)
    sftp = _Sftp({"/dados/saida/base.csv": (grande, 0o100644)})
    dados, aviso, det = ew.resolver_anexo(sftp, "/dados/saida", "base.csv", RAIZES, 2, MAPA)
    assert dados is None and "maior que o limite" in aviso
    assert sftp.abertos == [] and det["bytes"] == len(grande)       # mediu pelo stat, não leu
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "base.csv", RAIZES, 5, MAPA)
    assert dados == grande and aviso is None


def test_resolver_anexo_com_sftp_fora_do_ar_avisa_o_motivo():
    """`IOError` É `OSError` no Python 3 — só o errno separa 'não existe' de
    'canal caído', e confundir os dois esconderia falha de infraestrutura."""
    sftp = _Sftp(erro_stat=OSError(errno.EPIPE, "Socket is closed"))
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "x.csv", RAIZES, 5, MAPA)
    # o Python promove OSError(EPIPE) a BrokenPipeError — o aviso nomeia a classe real
    assert dados is None and "não pôde ser consultado" in aviso and "BrokenPipeError" in aviso
    assert "não encontrado" not in aviso
    sftp = _Sftp(erro_stat=PermissionError(errno.EACCES, "Permission denied"))
    _, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "x.csv", RAIZES, 5, MAPA)
    assert "não pôde ser consultado" in aviso and "PermissionError" in aviso


def test_resolver_anexo_vazio_avisa_em_vez_de_anexar_zero_byte():
    sftp = _Sftp({"/dados/saida/vazio.csv": (b"", 0o100644)})
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "vazio.csv", RAIZES, 5, MAPA)
    assert dados is None and "vazio" in aviso


def test_ancora_link_de_diretorio_que_sai_da_raiz_e_recusado_no_envio(monkeypatch):
    """⛔ Âncora. A régua do cadastro é LEXICAL — não há SSH no salvar — e com
    subpasta livre (F3) um link de diretório dentro da raiz
    (`/dados/saida/corrente -> /u02/outra_area`, comum no DataStage) passa no
    texto. O `stat` segue o link e leria um arquivo de FORA das pastas
    liberadas. O navegador de pastas já recusa entrar nesse link; aqui o
    equivalente é perguntar o caminho real ao servidor antes de ler."""
    sftp = _Sftp({"/u02/outra_area/segredo.csv": (b"dado de fora", 0o100644)},
                 links={"/dados/saida/corrente": "/u02/outra_area"})
    dados, aviso, det = ew.resolver_anexo(
        sftp, "/dados/saida/corrente", "segredo.csv", RAIZES, 5, MAPA)
    assert dados is None and sftp.abertos == []
    assert "fora das pastas liberadas" in aviso and "/u02/outra_area/segredo.csv" in aviso
    assert det["caminho"] == "/u02/outra_area/segredo.csv"    # o log diz o que era de verdade


def test_link_que_continua_dentro_da_raiz_segue_valendo():
    """Link para outra pasta DA MESMA raiz é legítimo e não pode virar recusa —
    senão a correção acima quebraria quem já usa link para organizar."""
    sftp = _Sftp({"/dados/saida/2026/rel.csv": (b"ok", 0o100644)},
                 links={"/dados/saida/corrente": "/dados/saida/2026"})
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida/corrente", "rel.csv", RAIZES, 5, MAPA)
    assert dados == b"ok" and aviso is None


def test_servidor_sem_realpath_nao_bloqueia_o_envio():
    """A conferência é defesa em profundidade: servidor que não implemente
    `realpath` cai na régua lexical, que é o que já valia antes."""
    sftp = _Sftp({"/dados/saida/rel.csv": (b"ok", 0o100644)}, sem_normalize=True)
    dados, aviso, _ = ew.resolver_anexo(sftp, "/dados/saida", "rel.csv", RAIZES, 5, MAPA)
    assert dados == b"ok" and aviso is None


# ═══════════ 6. documento HTML para o Outlook (F3 da spec de tabela do SQL) ══

def test_fragmento_vira_documento_com_o_head_que_o_outlook_precisa():
    """Sem `<head>`, o Outlook desktop dimensiona formas com o DPI do WINDOWS.

    Numa tela a 125% — o padrão em notebook corporativo — o cabeçalho saía menor
    que a largura da mensagem e sobrava uma faixa de outra cor ao lado dele. O
    `<o:PixelsPerInch>96</o:PixelsPerInch> `é o que fixa a escala."""
    doc = em.documento_html('<table><tr><td>oi</td></tr></table>')
    assert doc.startswith("<!DOCTYPE html>")
    assert "<o:PixelsPerInch>96</o:PixelsPerInch>" in doc
    assert 'charset="utf-8"' in doc
    # pede aos clientes que respeitam a diretiva para não inverter as cores:
    # a inversão PARCIAL é o que deixava o cabeçalho com dois tons de azul
    assert 'content="light only"' in doc
    assert "<table><tr><td>oi</td></tr></table>" in doc
    assert doc.count("<body") == 1


def test_corpo_que_ja_e_documento_volta_intacto():
    """Embrulhar de novo criaria um segundo `<body>`, cujos atributos o cliente
    descarta em silêncio — o defeito que a prévia em iframe já pagou."""
    for pronto in ('<html><body>x</body></html>',
                   '<!DOCTYPE html>\n<HTML lang="pt-br"><body>x</body></HTML>'):
        assert em.documento_html(pronto) == pronto


def test_o_texto_simples_nao_arrasta_o_head_para_dentro():
    """Quem lê em texto puro não pode receber `PixelsPerInch` e `DOCTYPE`: o
    alternativo text/plain sai do corpo ORIGINAL, não do documento embrulhado."""
    bruto = em.montar_mensagem("orquestra@cvp.com.br", ["ana@cvp.com.br"], "Assunto",
                               '<table><tr><td>Carga OK</td></tr></table>', html=True)
    msg = email.message_from_bytes(bruto, policy=email.policy.default)
    texto = msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Carga OK" in texto
    assert "PixelsPerInch" not in texto and "DOCTYPE" not in texto
    assert "PixelsPerInch" in html          # no HTML, sim
