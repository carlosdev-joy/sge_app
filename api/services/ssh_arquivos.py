"""api/services/ssh_arquivos.py — arquivos de servidores Unix por SFTP (tela Utilitários).

Spec: docs/spec-utilitarios-arquivos.md. Diferente de `ssh_datastage.py` (que roda
`dsjob` por shell com allowlist de subcomandos), aqui NÃO existe comando: tudo é
SFTP (`normalize`, `stat`, `open`, `listdir`). Entrada do usuário nunca vira linha
de shell.

Duas camadas, de propósito:
  * funções PURAS (validação de caminho, raízes, codificação, últimas linhas) —
    testáveis sem SSH; é onde mora a política;
  * o acesso ao servidor, atrás de `conexao_sftp(servidor)`, que os testes
    substituem por um cliente em memória (o paramiko não está no ambiente de
    teste — `tests/test_ds_console.py` documenta isso).

Servidores: `SERVIDORES` é o registro. Hoje só 'datastage', cujas credenciais são
as MESMAS variáveis do Console (DS_SSH_*). Servidor novo = entrada nova aqui; os
endpoints e a tela não mudam.

Política de caminho (a ordem importa):
  1. validação LEXICAL (absoluto, `normpath`, sem `\\0`, nome sem `/`) — 422;
  2. conferência LEXICAL contra as raízes ativas — 403 ANTES de tocar o servidor,
     para um caminho fora das raízes nem revelar se existe;
  3. no servidor, `realpath` DE CIMA PARA BAIXO: a raiz, depois cada pasta, depois
     o arquivo — e a conferência de novo a cada nível. É o que barra symlink
     apontando para fora SEM revelar se o que vem depois do link existe (um
     `realpath` só do caminho inteiro responderia 403 quando o alvo existe e 404
     quando não — um oráculo). As raízes também são resolvidas no servidor: raiz
     que é symlink continua valendo.

Comprimentos: `caminho` e `detalhe` da auditoria são NVARCHAR — contam unidades
UTF-16, não code points. Um caminho com 600 emojis tem 610 caracteres Python e
1.210 unidades: passaria na validação e ESTOURARIA a coluna, e a auditoria da
tentativa sumiria. Por isso `utf16_len`/`cortar_utf16`, e não `len`/`[:n]`.

⚠️ O paramiko é BLOQUEANTE: quem chama a partir de um endpoint `async` faz isso num
executor dedicado (`routers/utilitarios.py`) — o Console chama direto e segura a
API inteira por até 120 s; não repetir.
"""
from __future__ import annotations

import errno
import hashlib
import logging
import os
import posixpath
import re
import stat as statmod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger("orquestra-api")

# NVARCHAR(1000) de etl_utilitario_arquivo_log.caminho — em unidades UTF-16.
LIMITE_CAMINHO = 1000
# NVARCHAR(800) de etl_utilitario_raiz.caminho: 800×2 + servidor 50×2 = 1.700 bytes,
# o máximo de uma chave de índice não clusterizado no SQL Server.
LIMITE_RAIZ = 800
# NAME_MAX do Linux, em BYTES (UTF-8).
LIMITE_NOME_BYTES = 255
TETO_PADRAO_KB = 2048
# 16 MB: acima disso "últimas N linhas" transferiria dezenas de MB por pedido.
TETO_MAX_KB = 16384
ULTIMAS_LINHAS_MAX = 100_000
# "Últimas N linhas" lê só um bloco do fim: no mínimo 256 KB, ~512 B por linha pedida.
TAIL_BLOCO_MIN = 256 * 1024
TAIL_BYTES_POR_LINHA = 512
# Quantos bytes o teste "é texto?" olha.
AMOSTRA_TEXTO = 8192
# Bytes de controle aceitos num arquivo de texto: tab, LF, CR, FF, ESC (cor de terminal).
_CONTROLE_OK = frozenset((9, 10, 13, 12, 27))
# Pastas do sistema que nunca podem ser raiz — o admin decide o resto (spec §6, risco 1).
RAIZES_PROIBIDAS = (
    "/etc", "/root", "/proc", "/sys", "/dev", "/boot",
    "/bin", "/sbin", "/lib", "/lib64", "/usr", "/run", "/var/run",
)

CODIFICACOES = {
    "utf-8": "utf-8", "utf8": "utf-8",
    "latin-1": "latin-1", "latin1": "latin-1", "iso-8859-1": "latin-1",
}


class ArquivoError(Exception):
    """Erro de política/validação/servidor — vira HTTPException no router.

    `resultado` é o que a auditoria grava: 'negado' (política — fora das raízes)
    ou 'erro' (validação, não existe, binário, SSH…). `interno` é o detalhe que
    vai ao log e à auditoria mas NÃO à resposta (host, porta, erro cru do
    paramiko)."""

    def __init__(self, status: int, detail: str, *, resultado: str = "erro",
                 interno: str | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.resultado = resultado
        self.interno = interno
        # Dados que a resposta leva além da frase (ex.: o 409 da gravação diz o
        # tamanho e a data do arquivo que já existe).
        self.extra = extra


# ── Servidores ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Credencial:
    host: str
    port: int
    user: str
    password: str | None
    key_file: str | None


def _cred_datastage() -> Credencial | None:
    """As mesmas variáveis do Console DataStage (services/ssh_datastage.py)."""
    host = (os.getenv("DS_SSH_HOST") or "").strip()
    user = (os.getenv("DS_SSH_USER") or "").strip()
    if not host or not user:
        return None
    try:
        port = int(os.getenv("DS_SSH_PORT") or 22)
    except ValueError:
        port = 22
    return Credencial(
        host=host, port=port, user=user,
        password=os.getenv("DS_SSH_PASSWORD") or None,
        key_file=os.getenv("DS_SSH_KEY_FILE") or None,
    )


# Registro de servidores: id → {label, credencial()}. Adicionar servidor = adicionar
# uma entrada; `servidores_disponiveis()` e o campo Servidor da tela seguem sozinhos.
SERVIDORES: dict[str, dict] = {
    "datastage": {"label": "Servidor DataStage", "credencial": _cred_datastage},
}


def servidores_disponiveis() -> list[dict]:
    return [
        {"id": sid, "label": s["label"], "configurado": s["credencial"]() is not None}
        for sid, s in SERVIDORES.items()
    ]


def servidor_valido(bruto) -> str:
    sid = str(bruto or "").strip() or "datastage"
    if sid not in SERVIDORES:
        raise ArquivoError(422, f"Servidor desconhecido: {sid!r}.")
    return sid


def credencial(servidor: str) -> Credencial:
    cred = SERVIDORES[servidor_valido(servidor)]["credencial"]()
    if cred is None:
        raise ArquivoError(
            503,
            "Servidor não configurado nesta instância da API — defina DS_SSH_HOST e "
            "DS_SSH_USER (e DS_SSH_PASSWORD ou DS_SSH_KEY_FILE) no ambiente.")
    return cred


# ── Funções puras: comprimento em unidades UTF-16 ────────────────────────────

def utf16_len(s: str) -> int:
    """Quantas unidades UTF-16 (= o que NVARCHAR(n) conta) a string ocupa."""
    return len(s.encode("utf-16-le", errors="surrogatepass")) // 2


def cortar_utf16(s: str, n: int) -> str:
    """Corta em `n` unidades UTF-16 sem partir um par substituto (emoji ao meio)."""
    if not s:
        return s
    b = s.encode("utf-16-le", errors="surrogatepass")
    if len(b) <= n * 2:
        return s
    b = b[: n * 2]
    ultimo = int.from_bytes(b[-2:], "little")
    if 0xD800 <= ultimo <= 0xDBFF:  # ficou só a metade alta de um par
        b = b[:-2]
    return b.decode("utf-16-le", errors="ignore")


# ── Funções puras: caminho ───────────────────────────────────────────────────

def normalizar_diretorio(bruto) -> str:
    """Pasta absoluta e normalizada (`//`, `/./` e `..` resolvidos LEXICALMENTE).

    `..` não é recusado aqui de propósito: depois de normalizar, quem decide é a
    conferência contra as raízes — `/dados/bi/../../etc` vira `/etc` e cai fora.

    Barras iniciais são colapsadas ANTES do `normpath`: o POSIX preserva
    exatamente duas (`//x` fica `//x`), e `//` passaria pela guarda "raiz não pode
    ser a barra" liberando o servidor inteiro."""
    s = str(bruto or "").strip()
    if not s:
        raise ArquivoError(422, "Informe a pasta.")
    if "\0" in s:
        raise ArquivoError(422, "Pasta inválida.")
    if not s.startswith("/"):
        raise ArquivoError(422, "A pasta precisa ser um caminho absoluto (começar com /).")
    s = posixpath.normpath("/" + s.lstrip("/"))
    if utf16_len(s) > LIMITE_CAMINHO:
        raise ArquivoError(422, f"Caminho longo demais (máximo {LIMITE_CAMINHO} caracteres).")
    return s


def normalizar_raiz(bruto) -> str:
    """Raiz = pasta normalizada, que não seja a barra nem pasta do sistema."""
    s = normalizar_diretorio(bruto)
    if s == "/":
        raise ArquivoError(422, "A raiz não pode ser a barra (/): escolha uma pasta.")
    if utf16_len(s) > LIMITE_RAIZ:
        raise ArquivoError(422, f"Raiz longa demais (máximo {LIMITE_RAIZ} caracteres).")
    for proibida in RAIZES_PROIBIDAS:
        if s == proibida or s.startswith(proibida + "/"):
            raise ArquivoError(
                422, f"{proibida} é pasta do sistema e não pode ser raiz dos Utilitários.")
    return s


def validar_nome(bruto) -> str:
    s = str(bruto or "").strip()
    if not s:
        raise ArquivoError(422, "Informe o nome do arquivo.")
    if "/" in s or "\0" in s or s in (".", ".."):
        raise ArquivoError(422, "Nome de arquivo inválido: sem barra, e não pode ser '.' nem '..'.")
    if any(ord(c) < 32 or ord(c) == 127 for c in s):
        # Quebra de linha ou ESC no nome vira arquivo que engana o `ls` de quem
        # opera o servidor; na F1 só lia, na F4 CRIA.
        raise ArquivoError(422, "Nome de arquivo inválido: sem caracteres de controle.")
    if len(s.encode("utf-8")) > LIMITE_NOME_BYTES:
        raise ArquivoError(422, f"Nome longo demais (máximo {LIMITE_NOME_BYTES} bytes).")
    return s


def montar_caminho(diretorio: str, nome: str) -> str:
    caminho = posixpath.join(diretorio, nome)
    if utf16_len(caminho) > LIMITE_CAMINHO:
        raise ArquivoError(422, f"Caminho longo demais (máximo {LIMITE_CAMINHO} caracteres).")
    return caminho


def raiz_de(caminho: str, raizes) -> str | None:
    """A raiz sob a qual `caminho` está, ou None.

    Comparação por COMPONENTE, não por prefixo de string: `/dados2/x` NÃO está
    abaixo de `/dados`. Raiz que normalize para `/` é ignorada — liberar tudo
    não é raiz."""
    for bruta in raizes:
        r = posixpath.normpath("/" + str(bruta).lstrip("/"))
        if r == "/":
            continue
        if caminho == r or caminho.startswith(r + "/"):
            return r
    return None


def preparar_leitura(diretorio, nome, raizes) -> tuple[str, str]:
    """Valida e confere LEXICALMENTE, antes de qualquer SSH. Devolve (caminho, raiz).

    422 em entrada inválida; 403 (`negado`) fora das raízes — sem tocar o servidor,
    para não revelar se o arquivo existe."""
    caminho = montar_caminho(normalizar_diretorio(diretorio), validar_nome(nome))
    raiz = raiz_de(caminho, raizes)
    if raiz is None:
        raise ArquivoError(403, "Fora dos diretórios liberados.", resultado="negado")
    return caminho, raiz


def extensao_de(nome: str) -> str | None:
    base = posixpath.basename(nome or "")
    if "." not in base or base.startswith(".") and base.count(".") == 1:
        return None
    ext = base.rsplit(".", 1)[1].strip().lower()
    return ext or None


# ── Funções puras: conteúdo ──────────────────────────────────────────────────

def eh_texto(dados: bytes) -> bool:
    """Heurística: sem NUL e com poucos bytes de controle nos primeiros 8 KB."""
    amostra = dados[:AMOSTRA_TEXTO]
    if not amostra:
        return True
    if b"\0" in amostra:
        return False
    controle = sum(1 for b in amostra if b < 32 and b not in _CONTROLE_OK)
    return controle / len(amostra) < 0.10


def codificacao_valida(pedida) -> str | None:
    """None = detectar. Senão, um dos nomes canônicos de CODIFICACOES — ou 422.

    Pura, para o router recusar ANTES de gastar uma leitura SSH inteira."""
    if pedida is None or pedida == "":
        return None
    if not isinstance(pedida, str):
        raise ArquivoError(422, "Codificação não suportada: use utf-8 ou latin-1.")
    cod = CODIFICACOES.get(pedida.strip().lower())
    if not cod:
        raise ArquivoError(422, "Codificação não suportada: use utf-8 ou latin-1.")
    return cod


def decidir_codificacao(dados: bytes, pedida: str | None = None) -> tuple[str, str]:
    """(texto, codificação usada).

    Sem pedido: UTF-8 estrito e, se não for, Latin-1 (nunca falha — todo byte é
    válido em Latin-1). O servidor do DataStage costuma ser Latin-1; a tela mostra
    qual valeu. Com pedido: usa o pedido e, se não couber, diz a posição."""
    cod = codificacao_valida(pedida)
    if cod:
        try:
            return _decodificar(dados, cod), cod
        except UnicodeDecodeError as e:
            raise ArquivoError(
                422,
                f"O arquivo não está em {cod} (byte inválido na posição {e.start}). "
                "Tente a outra codificação.")
    try:
        return _decodificar(dados, "utf-8"), "utf-8"
    except UnicodeDecodeError:
        return dados.decode("latin-1"), "latin-1"


def _decodificar(dados: bytes, cod: str) -> str:
    # utf-8-sig engole o BOM quando há e é idêntico ao utf-8 quando não há.
    return dados.decode("utf-8-sig" if cod == "utf-8" else cod)


def ultimas_linhas(dados: bytes, n: int) -> bytes:
    """As últimas `n` linhas COMPLETAS (mantém o `\\n` final, se havia).

    Menos de `n` linhas → devolve tudo."""
    if n <= 0 or not dados:
        return b""
    idx = len(dados) - (1 if dados.endswith(b"\n") else 0)
    vistas = 0
    while vistas < n:
        pos = dados.rfind(b"\n", 0, idx)
        if pos == -1:
            return dados
        vistas += 1
        idx = pos
    return dados[idx + 1:]


def tamanho_bloco_tail(tamanho: int, teto_bytes: int, ultimas: int) -> int:
    """Quanto ler do fim para "últimas N linhas": limitado pelo arquivo, pelo teto
    e por uma estimativa por linha — nunca o teto inteiro à toa."""
    return max(0, min(tamanho, teto_bytes, max(TAIL_BLOCO_MIN, ultimas * TAIL_BYTES_POR_LINHA)))


def contar_linhas(texto: str) -> int:
    if not texto:
        return 0
    return texto.count("\n") + (0 if texto.endswith("\n") else 1)


def formatar_tamanho(n: int) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB".replace(".", ",")
    return f"{n / (1024 * 1024):.1f} MB".replace(".", ",")


def _mtime_iso(st) -> str | None:
    mt = getattr(st, "st_mtime", None)
    if not mt:
        return None
    try:
        return datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


# ── Acesso ao servidor (cliente injetável) ───────────────────────────────────

def _erro_servidor(e: Exception, caminho: str, *, acao: str = "acessar",
                   diagnostico: str | None = None) -> ArquivoError:
    """Traduz o erro do SFTP. O caminho já está dentro da raiz, então pode
    aparecer; o `repr` do erro vai ao log/auditoria, não à resposta.

    O protocolo SFTP esconde o errno de quase tudo: pasta somente leitura,
    disco cheio e cota estourada chegam como um `Failure` sem número. Por isso
    a frase genérica nomeia as causas comuns e, quando quem chama conseguiu
    um `diagnostico` (ver `diagnostico_pasta`), usa a causa exata."""
    if isinstance(e, UnicodeDecodeError):
        return ArquivoError(
            422, "O servidor devolveu um nome de arquivo ou pasta fora do UTF-8 nesse "
                 "caminho; renomeie-o no servidor.", interno=f"{caminho}: {e}")
    num = getattr(e, "errno", None)
    if num == errno.ENOENT:
        return ArquivoError(404, f"Arquivo não encontrado: {caminho}")
    if num in (errno.EACCES, errno.EPERM):
        return ArquivoError(403, f"O usuário SSH não tem permissão para {acao} {caminho}.")
    if num == errno.EROFS:
        return ArquivoError(403, f"Não dá para {acao} {caminho}: o sistema de arquivos está montado somente leitura.")
    if num in (errno.ENOSPC, errno.EDQUOT):
        return ArquivoError(507, f"Não dá para {acao} {caminho}: sem espaço livre (ou cota estourada) no servidor.")
    causa = diagnostico or ("causas comuns: sistema de arquivos somente leitura, disco cheio ou cota "
                            "estourada — confira no servidor")
    return ArquivoError(
        502, f"O servidor recusou {acao} {caminho}: {causa}.",
        interno=f"{caminho}: {e!r}")


def diagnostico_pasta(sftp, pasta: str) -> str | None:
    """Pergunta ao OpenSSH (extensão `statvfs@openssh.com`) POR QUE uma gravação
    falhou: sistema de arquivos somente leitura ou sem espaço. Melhor esforço —
    o paramiko não expõe a extensão, então o pedido vai pela requisição bruta;
    servidor sem a extensão (ou qualquer tropeço) devolve None e a mensagem
    fica com as causas comuns."""
    try:
        # 200 = SSH_FXP_EXTENDED (paramiko.sftp.CMD_EXTENDED); a constante fica
        # aqui para o serviço não depender do paramiko fora da conexão.
        _tipo, msg = sftp._request(200, "statvfs@openssh.com", pasta)  # noqa: SLF001
        # f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_favail, f_fsid, f_flag, f_namemax
        campos = [int(msg.get_int64()) for _ in range(11)]
    except Exception:
        return None
    if campos[9] & 0x1:  # SSH2_FXE_STATVFS_ST_RDONLY
        return "o sistema de arquivos está montado somente leitura"
    if campos[4] == 0:
        return "não há espaço livre no disco"
    return None


def _normalize(sftp, caminho: str) -> str:
    try:
        return posixpath.normpath(str(sftp.normalize(caminho)))
    except (OSError, UnicodeDecodeError) as e:
        raise _erro_servidor(e, caminho) from e


def _stat(sftp, caminho: str):
    try:
        return sftp.stat(caminho)
    except (OSError, UnicodeDecodeError) as e:
        raise _erro_servidor(e, caminho) from e


def raizes_no_servidor(sftp, raizes) -> list[str]:
    """As raízes lexicais MAIS o que o servidor diz que elas são (uma raiz pode ser
    symlink: `/dados → /u01/dados`). Raiz que o servidor não resolve não soma nada."""
    reais = [posixpath.normpath("/" + str(r).lstrip("/")) for r in raizes]
    for r in list(reais):
        try:
            real = _normalize(sftp, r)
        except ArquivoError:
            continue
        if real != "/" and real not in reais:
            reais.append(real)
    return reais


def resolver_real(sftp, caminho: str, raizes) -> str:
    """`realpath` DE CIMA PARA BAIXO + conferência a cada nível (ver cabeçalho)."""
    raiz = raiz_de(caminho, raizes)
    if raiz is None:
        raise ArquivoError(403, "Fora dos diretórios liberados.", resultado="negado")
    reais = raizes_no_servidor(sftp, raizes)
    fora = ArquivoError(
        403, "Fora dos diretórios liberados (o caminho real aponta para fora da raiz).",
        resultado="negado")

    atual = raiz
    real = _normalize(sftp, atual)
    if raiz_de(real, reais) is None:
        raise fora
    resto = caminho[len(raiz):].strip("/")
    for parte in (resto.split("/") if resto else []):
        atual = posixpath.join(atual, parte)
        real = _normalize(sftp, atual)
        if raiz_de(real, reais) is None:
            raise fora
    return real


def ler_arquivo(sftp, caminho: str, raizes, *, teto_bytes: int,
                ultimas: int | None = None, codificacao: str | None = None) -> dict:
    """Lê `caminho` (já validado por `preparar_leitura`) e devolve o contrato do
    endpoint: caminho real, tamanho, linhas, codificação, truncado, mtime, conteúdo."""
    real = resolver_real(sftp, caminho, raizes)
    st = _stat(sftp, real)
    if statmod.S_ISDIR(getattr(st, "st_mode", 0) or 0):
        raise ArquivoError(422, f"{real} é uma pasta, não um arquivo.")
    tamanho = int(getattr(st, "st_size", 0) or 0)
    if tamanho > teto_bytes and not ultimas:
        raise ArquivoError(
            413,
            f"Arquivo de {formatar_tamanho(tamanho)}, acima do teto de "
            f"{formatar_tamanho(teto_bytes)}. Use 'últimas N linhas' para ver o fim dele.")

    truncado = False
    try:
        with sftp.open(real, "rb") as f:
            if ultimas:
                bloco = tamanho_bloco_tail(tamanho, teto_bytes, ultimas)
                inicio = tamanho - bloco
                if inicio > 0:
                    # Um byte a mais, antes do bloco: se for `\n`, o bloco começa em
                    # linha inteira; senão o pedaço até o primeiro `\n` é meia linha.
                    f.seek(inicio - 1)
                    dados = f.read(bloco + 1)
                    if dados[:1] == b"\n":
                        dados = dados[1:]
                    else:
                        corte = dados.find(b"\n")
                        dados = dados[corte + 1:] if corte >= 0 else b""
                    if not dados:
                        # O bloco inteiro cabia dentro de UMA linha (a última, com ou
                        # sem `\n` no fim): não há linha completa para mostrar.
                        raise ArquivoError(
                            413,
                            f"A última linha do arquivo tem mais de {formatar_tamanho(bloco)} "
                            "— não dá para mostrar por 'últimas N linhas'.")
                else:
                    dados = f.read(tamanho) if tamanho else b""
                dados = ultimas_linhas(dados, ultimas)
                truncado = len(dados) < tamanho
            else:
                prefetch = getattr(f, "prefetch", None)
                if prefetch and tamanho:
                    prefetch(tamanho)
                dados = f.read(tamanho) if tamanho else b""
    except (OSError, UnicodeDecodeError) as e:
        raise _erro_servidor(e, real) from e

    if not eh_texto(dados):
        raise ArquivoError(
            415, "O arquivo não é texto (parece binário) — os Utilitários só abrem texto.")
    texto, cod = decidir_codificacao(dados, codificacao)
    return {
        "caminho": real,
        "tamanho_bytes": tamanho,
        "linhas": contar_linhas(texto),
        "codificacao": cod,
        "truncado": truncado,
        "modificado_em": _mtime_iso(st),
        "conteudo": texto,
    }


def testar_raiz(sftp, caminho: str) -> dict:
    """O que o botão Testar do Admin mostra: existe? é pasta? o usuário SSH lê?

    O `realpath` do OpenSSH tolera o ÚLTIMO componente ausente (devolve o caminho
    como veio), então "não existe" pode aparecer no `normalize` OU no `stat`."""
    lexical = posixpath.normpath("/" + str(caminho).lstrip("/"))
    nao_existe = {"existe": False, "eh_pasta": False, "legivel": False,
                  "caminho_real": None, "detalhe": "a pasta não existe no servidor"}
    try:
        real = _normalize(sftp, lexical)
    except ArquivoError as e:
        if e.status == 404:
            return nao_existe
        if e.status == 403:
            return {"existe": True, "eh_pasta": None, "legivel": False, "caminho_real": None,
                    "detalhe": "o usuário SSH não tem permissão para resolver o caminho"}
        raise
    try:
        st = _stat(sftp, real)
    except ArquivoError as e:
        if e.status == 404:
            return nao_existe
        raise
    link = f"é um link para {real}; " if real != lexical else ""
    eh_pasta = bool(statmod.S_ISDIR(getattr(st, "st_mode", 0) or 0))
    if not eh_pasta:
        return {"existe": True, "eh_pasta": False, "legivel": False, "caminho_real": real,
                "detalhe": link + "o caminho existe, mas é um arquivo — uma raiz precisa ser pasta"}
    try:
        sftp.listdir(real)
        legivel, detalhe = True, "existe e é legível pelo usuário SSH"
    except (OSError, UnicodeDecodeError):
        legivel, detalhe = False, "existe, mas o usuário SSH não consegue listar a pasta"
    return {"existe": True, "eh_pasta": True, "legivel": legivel,
            "caminho_real": real, "detalhe": link + detalhe}


# ── Gravação (F4) ────────────────────────────────────────────────────────────

def normalizar_conteudo(texto: str) -> str:
    """CRLF/CR → LF e `\\n` final (arquivo não vazio): o que o Windows cola no
    editor não pode virar `\\r` no servidor Unix."""
    t = str(texto or "").replace("\r\n", "\n").replace("\r", "\n")
    if t and not t.endswith("\n"):
        t += "\n"
    return t


def codificar_conteudo(texto: str, cod: str) -> bytes:
    """Bytes na codificação escolhida. Caractere que não existe em Latin-1 é
    recusado NOMEANDO a posição — gravar `?` no lugar seria corromper o dado."""
    try:
        return texto.encode(cod)
    except UnicodeEncodeError as e:
        linha = texto.count("\n", 0, e.start) + 1
        raise ArquivoError(
            422,
            f"O texto tem um caractere que não existe em {cod} na linha {linha} "
            f"(posição {e.start}: {texto[e.start]!r}). Grave em utf-8 ou troque o caractere.",
            # A auditoria não leva nem um caractere do conteúdo — só onde está.
            interno=f"caractere fora de {cod} na linha {linha}, posição {e.start}") from None


# O `.tmp` e o `.bak-<ts>` são o nome + sufixo: precisam caber em NAME_MAX também.
RESERVA_SUFIXOS_BYTES = 40


def validar_extensao_gravacao(bruta, permitidas) -> str:
    """Minúsculas, sem ponto, regex do servidor; e tem de estar na lista do admin."""
    s = str(bruta or "").strip().lower().lstrip(".")
    if not s or not re.match(r"^[a-z0-9]{1,15}$", s):
        raise ArquivoError(422, "Extensão inválida: só letras minúsculas e números, sem ponto, até 15 caracteres.")
    if s not in set(permitidas or ()):
        raise ArquivoError(
            422, f"Extensão '{s}' não liberada — o admin inclui em Admin › Utilitários.")
    return s


def nome_backup(caminho: str, agora: datetime | None = None) -> str:
    """`<caminho>.bak-<AAAAMMDDHHMMSS>-<ms>` — com milissegundos: duas sobrescritas
    no mesmo segundo não podem disputar o mesmo nome de backup."""
    agora = agora or datetime.now()
    return f"{caminho}.bak-{agora:%Y%m%d%H%M%S}-{agora.microsecond // 1000:03d}"


def nome_temporario(caminho: str, marca: str) -> str:
    pasta, nome = posixpath.split(caminho)
    return posixpath.join(pasta, f".{nome}.tmp-{marca}")


def preparar_gravacao(diretorio, nome, extensao, raizes, extensoes) -> tuple[str, str]:
    """Valida e confere LEXICALMENTE antes do SSH. Devolve (caminho, raiz).

    O nome final é `<nome>.<extensao>`; a extensão precisa estar na lista do
    admin. 422 em entrada inválida; 403 (`negado`) fora das raízes."""
    base = validar_nome(nome)
    ext = validar_extensao_gravacao(extensao, extensoes)
    completo = validar_nome(f"{base}.{ext}")
    if len(completo.encode("utf-8")) > LIMITE_NOME_BYTES - RESERVA_SUFIXOS_BYTES:
        raise ArquivoError(
            422,
            f"Nome longo demais para gravar (máximo {LIMITE_NOME_BYTES - RESERVA_SUFIXOS_BYTES} "
            "bytes): o servidor precisa de espaço para o .tmp e o .bak.")
    caminho = montar_caminho(normalizar_diretorio(diretorio), completo)
    raiz = raiz_de(caminho, raizes)
    if raiz is None:
        raise ArquivoError(403, "Fora dos diretórios liberados.", resultado="negado")
    return caminho, raiz


def _substituir(sftp, tmp: str, destino: str) -> None:
    """`tmp` vira `destino` de uma vez. `posix_rename` (extensão do OpenSSH)
    sobrescreve atomicamente; sem ela, remove e renomeia (janela mínima)."""
    posix = getattr(sftp, "posix_rename", None)
    if callable(posix):
        posix(tmp, destino)
        return
    try:
        sftp.remove(destino)
    except OSError as e:
        if getattr(e, "errno", None) != errno.ENOENT:
            raise
    sftp.rename(tmp, destino)


def gravar_arquivo(sftp, caminho: str, raizes, dados: bytes, *, sobrescrever: bool,
                   backup: bool, marca: str, agora: datetime | None = None) -> dict:
    """Grava `dados` em `caminho` (já validado por `preparar_gravacao`).

    Ordem: pasta resolvida de cima para baixo (symlink para fora barra aqui) →
    destino existe? (409 sem `sobrescrever`; symlink de destino também é
    conferido) → escreve num `.tmp` na MESMA pasta → cópia de segurança do
    original (rename) → `tmp` vira o destino de uma vez. Quem lê o arquivo no
    meio vê o antigo ou o novo, nunca metade. Falha no meio: o original volta,
    o `.tmp` some."""
    pasta, nome = posixpath.split(caminho)
    real_pasta = resolver_real(sftp, pasta, raizes)
    st_pasta = _stat(sftp, real_pasta)
    if not statmod.S_ISDIR(getattr(st_pasta, "st_mode", 0) or 0):
        raise ArquivoError(422, f"{real_pasta} não é uma pasta.")
    real = posixpath.join(real_pasta, nome)

    # O que existe no destino? `lstat` para enxergar um LINK; se for link para
    # dentro das raízes, o arquivo que se grava é o ALVO (é o que `ler` mostra
    # e o que um job usa); link para fora é negado.
    try:
        st_l = sftp.lstat(real)
    except (OSError, UnicodeDecodeError) as e:
        if getattr(e, "errno", None) == errno.ENOENT:
            st_l = None
        else:
            raise _erro_servidor(e, real) from e
    if st_l is not None and statmod.S_ISLNK(getattr(st_l, "st_mode", 0) or 0):
        alvo = _normalize(sftp, real)
        if raiz_de(alvo, raizes_no_servidor(sftp, raizes)) is None:
            raise ArquivoError(
                403, "Fora dos diretórios liberados (o arquivo é um link para fora da raiz).",
                resultado="negado")
        real = alvo

    existente: dict | None = None
    modo_antigo: int | None = None
    try:
        st = sftp.stat(real)
    except (OSError, UnicodeDecodeError) as e:
        if getattr(e, "errno", None) == errno.ENOENT:
            st = None  # não existe (ou link quebrado apontando para dentro): cria
        else:
            raise _erro_servidor(e, real) from e
    if st is not None:
        modo = getattr(st, "st_mode", 0) or 0
        if statmod.S_ISDIR(modo):
            raise ArquivoError(422, f"Já existe uma PASTA em {real}.")
        modo_antigo = modo & 0o7777
        existente = {"tamanho_bytes": int(getattr(st, "st_size", 0) or 0),
                     "modificado_em": _mtime_iso(st)}
        if not sobrescrever:
            raise ArquivoError(
                409, "O arquivo já existe. Confirme para gravar por cima.",
                extra={"existente": existente})

    tmp = nome_temporario(real, marca)

    def _apagar_tmp() -> None:
        try:
            sftp.remove(tmp)
        except Exception:
            pass

    def _erro_gravacao(e: Exception) -> ArquivoError:
        # Sem errno (o `Failure` genérico do SFTP), vale perguntar ao servidor
        # se a pasta é somente leitura ou está sem espaço — é o que o usuário
        # precisa ler na tela, não "detalhe no log".
        if isinstance(e, (OSError, UnicodeDecodeError)):
            diag = diagnostico_pasta(sftp, real_pasta) if getattr(e, "errno", None) is None else None
            return _erro_servidor(e, real, acao="gravar em", diagnostico=diag)
        return ArquivoError(502, "Falha ao gravar no servidor — detalhe registrado no log da API.",
                            interno=f"{real}: {e!r}")

    try:
        with sftp.open(tmp, "wb") as f:
            f.write(dados)
        if modo_antigo is not None:
            # Sobrescrever troca o inode: sem isto um arquivo 0775 do grupo (ou
            # um .sh com +x) sairia 0644 e o job que escreve nele passaria a
            # falhar. O dono não dá para preservar por SFTP: passa a ser o
            # usuário SSH (documentado na spec).
            sftp.chmod(tmp, modo_antigo)
    except Exception as e:
        _apagar_tmp()
        raise _erro_gravacao(e) from e

    backup_criado: str | None = None
    try:
        if existente is not None and backup:
            bak = nome_backup(real, agora)
            try:
                sftp.rename(real, bak)
            except OSError:
                # Nome de backup já tomado (duas gravações no mesmo instante):
                # tenta uma vez com a marca do pedido, que é única.
                bak = f"{bak}-{marca}"
                sftp.rename(real, bak)
            backup_criado = bak
            try:
                _substituir(sftp, tmp, real)
            except Exception:
                # Devolve o original antes de propagar: sem isto o arquivo
                # sumiria do lugar e ficaria só como `.bak`.
                try:
                    sftp.rename(bak, real)
                except Exception:
                    pass
                raise
        else:
            _substituir(sftp, tmp, real)
    except Exception as e:
        _apagar_tmp()
        raise _erro_gravacao(e) from e

    return {
        "caminho": real,
        "tamanho_bytes": len(dados),
        "sha256": hashlib.sha256(dados).hexdigest(),
        "criado": existente is None,
        "backup": backup_criado,
    }


# ── Listagem de pasta (F6 — navegador) ──────────────────────────────────────

LISTAGEM_MAX = 2000
# Links resolvidos por listagem (cada um custa uma ida ao servidor); os demais
# aparecem como link sem alvo, e o clique neles diz o que são.
LINKS_RESOLVIDOS_MAX = 200


def preparar_pasta(diretorio, raizes) -> tuple[str, str]:
    """Valida e confere LEXICALMENTE uma pasta, antes de qualquer SSH. (caminho, raiz)."""
    caminho = normalizar_diretorio(diretorio)
    raiz = raiz_de(caminho, raizes)
    if raiz is None:
        raise ArquivoError(403, "Fora dos diretórios liberados.", resultado="negado")
    return caminho, raiz


def tipo_de_modo(st_mode: int) -> str:
    if statmod.S_ISLNK(st_mode):
        return "link"
    if statmod.S_ISDIR(st_mode):
        return "pasta"
    if statmod.S_ISREG(st_mode):
        return "arquivo"
    return "outro"


def ordenar_entradas(entradas: list[dict]) -> list[dict]:
    """Pastas primeiro (link para pasta conta como pasta), depois por nome sem
    diferenciar caixa — a ordem que o olho espera num navegador de arquivos."""
    def chave(e: dict):
        eh_pasta = e["tipo"] == "pasta" or (e["tipo"] == "link" and e.get("alvo") == "pasta")
        return (0 if eh_pasta else 1, str(e["nome"]).casefold(), str(e["nome"]))
    return sorted(entradas, key=chave)


def listar_pasta(sftp, caminho: str, raizes, *, mostrar_ocultos: bool = False,
                 limite: int = LISTAGEM_MAX) -> dict:
    """Entradas de uma pasta abaixo de uma raiz (já conferida por `preparar_pasta`).

    Ocultos (`.`) ficam de fora por padrão e são contados; links são mostrados e só
    ganham `alvo` ('pasta' | 'arquivo') quando apontam para DENTRO das raízes —
    é o `alvo` que autoriza o navegador a descer. `pai` nunca sobe acima da raiz."""
    real = resolver_real(sftp, caminho, raizes)
    st = _stat(sftp, real)
    if not statmod.S_ISDIR(getattr(st, "st_mode", 0) or 0):
        raise ArquivoError(422, f"{real} é um arquivo, não uma pasta.")
    try:
        brutos = list(sftp.listdir_attr(real))
    except (OSError, UnicodeDecodeError) as e:
        raise _erro_servidor(e, real) from e

    reais = raizes_no_servidor(sftp, raizes)
    raiz = raiz_de(real, reais)
    entradas: list[dict] = []
    ocultos = 0
    links_resolvidos = 0
    for a in brutos:
        nome = str(getattr(a, "filename", "") or "")
        if nome in ("", ".", ".."):
            continue
        if nome.startswith(".") and not mostrar_ocultos:
            ocultos += 1
            continue
        modo = int(getattr(a, "st_mode", 0) or 0)
        tipo = tipo_de_modo(modo)
        e: dict = {
            "nome": nome,
            "tipo": tipo,
            "tamanho_bytes": int(getattr(a, "st_size", 0) or 0) if tipo == "arquivo" else None,
            "modificado_em": _mtime_iso(a),
        }
        if tipo == "link":
            e["alvo"] = None
            if links_resolvidos < LINKS_RESOLVIDOS_MAX:
                links_resolvidos += 1
                try:
                    alvo = _normalize(sftp, posixpath.join(real, nome))
                    if raiz_de(alvo, reais) is not None:
                        st_a = _stat(sftp, alvo)
                        tipo_alvo = tipo_de_modo(int(getattr(st_a, "st_mode", 0) or 0))
                        if tipo_alvo in ("pasta", "arquivo"):
                            e["alvo"] = tipo_alvo
                            if tipo_alvo == "arquivo":
                                e["tamanho_bytes"] = int(getattr(st_a, "st_size", 0) or 0)
                except ArquivoError:
                    pass  # quebrado, sem permissão ou fora: fica como link sem alvo
        entradas.append(e)

    entradas = ordenar_entradas(entradas)
    truncado = len(entradas) > limite
    if truncado:
        entradas = entradas[:limite]
    pai = None
    if raiz is not None and real != raiz:
        candidato = posixpath.dirname(real)
        if raiz_de(candidato, reais) is not None:
            pai = candidato
    return {
        "caminho_real": real,
        "raiz": raiz,
        "pai": pai,
        "entradas": entradas,
        "ocultos_omitidos": ocultos,
        "truncado": truncado,
    }


def _known_hosts() -> str | None:
    """DS_SSH_KNOWN_HOSTS: quando definida, só host key conhecida entra (RejectPolicy).
    Ausente = paridade com o Console (AutoAddPolicy). Arquivo ilegível é erro de
    configuração — 503, antes de qualquer conexão."""
    caminho = (os.getenv("DS_SSH_KNOWN_HOSTS") or "").strip()
    if not caminho:
        return None
    if not os.path.isfile(caminho):
        raise ArquivoError(
            503, "DS_SSH_KNOWN_HOSTS aponta para um arquivo que a API não consegue ler.",
            interno=caminho)
    return caminho


@contextmanager
def conexao_sftp(servidor: str):
    """Abre SSH+SFTP no servidor e fecha ao sair. Os testes substituem esta função.

    503 sem credencial (antes de importar o paramiko); 502 em falha de conexão —
    com host/porta/erro cru só no log e na auditoria, nunca na resposta.

    O canal SFTP é aberto À MÃO, com timeout ANTES do subsistema: `open_sftp()`
    espera o `sftp` do servidor sem limite, e um DataStage com o home em NFS
    pendurado seguraria a thread para sempre."""
    cred = credencial(servidor)
    known = _known_hosts()
    import paramiko  # import tardio: só existe em runtime, não nos testes

    client = paramiko.SSHClient()
    if known:
        client.load_host_keys(known)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=cred.host, port=cred.port, username=cred.user,
            password=cred.password, key_filename=cred.key_file,
            timeout=10, banner_timeout=15, auth_timeout=15,
        )
        transporte = client.get_transport()
        transporte.set_keepalive(15)
        canal = transporte.open_session(timeout=10)
        canal.settimeout(60)
        canal.invoke_subsystem("sftp")
        sftp = paramiko.SFTPClient(canal)
    except Exception as e:
        client.close()
        log.warning("Utilitários: falha ao conectar por SSH em %s:%s (%s): %r",
                    cred.host, cred.port, servidor, e)
        raise ArquivoError(
            502, "Falha ao conectar ao servidor por SSH — detalhe registrado no log da API.",
            interno=f"{cred.host}:{cred.port}: {e!r}") from e
    try:
        yield sftp
    finally:
        try:
            sftp.close()
        finally:
            client.close()
