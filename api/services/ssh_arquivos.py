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
  3. `realpath` NO SERVIDOR (`sftp.normalize`) e conferência de novo — é o que
     barra symlink apontando para fora da raiz.

⚠️ O paramiko é BLOQUEANTE: quem chama a partir de um endpoint `async` faz isso em
`asyncio.to_thread` (o Console chama direto e segura a API inteira por até 120 s —
não repetir).
"""
from __future__ import annotations

import errno
import os
import posixpath
import stat as statmod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

# Larguras das colunas de dbo.etl_utilitario_raiz.caminho / _arquivo_log.caminho.
LIMITE_CAMINHO = 1000
# NAME_MAX do Linux.
LIMITE_NOME = 255
TETO_PADRAO_KB = 2048
TETO_MAX_KB = 102400
ULTIMAS_LINHAS_MAX = 100_000
# Quantos bytes o teste "é texto?" olha.
AMOSTRA_TEXTO = 8192
# Bytes de controle aceitos num arquivo de texto: tab, LF, CR, FF, ESC (cor de terminal).
_CONTROLE_OK = frozenset((9, 10, 13, 12, 27))

CODIFICACOES = {
    "utf-8": "utf-8", "utf8": "utf-8",
    "latin-1": "latin-1", "latin1": "latin-1", "iso-8859-1": "latin-1",
}


class ArquivoError(Exception):
    """Erro de política/validação/servidor — vira HTTPException no router.

    `resultado` é o que a auditoria grava: 'negado' (política — fora das raízes)
    ou 'erro' (validação, não existe, binário, SSH…)."""

    def __init__(self, status: int, detail: str, *, resultado: str = "erro"):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.resultado = resultado


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


# ── Funções puras: caminho ───────────────────────────────────────────────────

def normalizar_diretorio(bruto) -> str:
    """Pasta absoluta e normalizada (`//`, `/./` e `..` resolvidos LEXICALMENTE).

    `..` não é recusado aqui de propósito: depois de normalizar, quem decide é a
    conferência contra as raízes — `/dados/bi/../../etc` vira `/etc` e cai fora."""
    s = str(bruto or "").strip()
    if not s:
        raise ArquivoError(422, "Informe a pasta.")
    if "\0" in s:
        raise ArquivoError(422, "Pasta inválida.")
    if not s.startswith("/"):
        raise ArquivoError(422, "A pasta precisa ser um caminho absoluto (começar com /).")
    s = posixpath.normpath(s)
    if len(s) > LIMITE_CAMINHO:
        raise ArquivoError(422, f"Caminho longo demais (máximo {LIMITE_CAMINHO} caracteres).")
    return s


def normalizar_raiz(bruto) -> str:
    """Raiz = pasta normalizada que não seja a barra (liberar `/` é liberar tudo)."""
    s = normalizar_diretorio(bruto)
    if s == "/":
        raise ArquivoError(422, "A raiz não pode ser a barra (/): escolha uma pasta.")
    return s


def validar_nome(bruto) -> str:
    s = str(bruto or "").strip()
    if not s:
        raise ArquivoError(422, "Informe o nome do arquivo.")
    if "/" in s or "\0" in s or s in (".", ".."):
        raise ArquivoError(422, "Nome de arquivo inválido: sem barra, e não pode ser '.' nem '..'.")
    if len(s) > LIMITE_NOME:
        raise ArquivoError(422, f"Nome longo demais (máximo {LIMITE_NOME} caracteres).")
    return s


def montar_caminho(diretorio: str, nome: str) -> str:
    caminho = posixpath.join(diretorio, nome)
    if len(caminho) > LIMITE_CAMINHO:
        raise ArquivoError(422, f"Caminho longo demais (máximo {LIMITE_CAMINHO} caracteres).")
    return caminho


def raiz_de(caminho: str, raizes) -> str | None:
    """A raiz sob a qual `caminho` está, ou None.

    Comparação por COMPONENTE, não por prefixo de string: `/dados2/x` NÃO está
    abaixo de `/dados`."""
    for bruta in raizes:
        r = posixpath.normpath(str(bruta))
        if caminho == r or caminho.startswith(r.rstrip("/") + "/"):
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


def decidir_codificacao(dados: bytes, pedida: str | None = None) -> tuple[str, str]:
    """(texto, codificação usada).

    Sem pedido: UTF-8 estrito e, se não for, Latin-1 (nunca falha — todo byte é
    válido em Latin-1). O servidor do DataStage costuma ser Latin-1; a tela mostra
    qual valeu. Com pedido: usa o pedido e, se não couber, diz a posição."""
    if pedida:
        cod = CODIFICACOES.get(str(pedida).strip().lower())
        if not cod:
            raise ArquivoError(422, "Codificação não suportada: use utf-8 ou latin-1.")
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

def _erro_servidor(e: OSError, caminho: str) -> ArquivoError:
    num = getattr(e, "errno", None)
    if num == errno.ENOENT:
        return ArquivoError(404, f"Arquivo não encontrado: {caminho}")
    if num == errno.EACCES:
        return ArquivoError(403, f"O usuário SSH não tem permissão para acessar {caminho}.")
    return ArquivoError(502, f"Falha ao acessar {caminho} no servidor: {e}")


def resolver_real(sftp, caminho: str, raizes) -> str:
    """`realpath` no servidor + conferência contra as raízes (barra symlink para fora)."""
    try:
        real = sftp.normalize(caminho)
    except OSError as e:
        raise _erro_servidor(e, caminho) from e
    real = posixpath.normpath(str(real))
    if raiz_de(real, raizes) is None:
        raise ArquivoError(
            403, "Fora dos diretórios liberados (o caminho real aponta para fora da raiz).",
            resultado="negado")
    return real


def _stat(sftp, caminho: str):
    try:
        return sftp.stat(caminho)
    except OSError as e:
        raise _erro_servidor(e, caminho) from e


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
                # Lê só um bloco do FIM (no máximo o teto) e recorta as linhas.
                bloco = min(tamanho, teto_bytes)
                if tamanho > bloco:
                    f.seek(tamanho - bloco)
                dados = f.read(bloco) if bloco else b""
                if tamanho > bloco:
                    # O bloco começou no meio de uma linha: descarta o pedaço.
                    corte = dados.find(b"\n")
                    dados = dados[corte + 1:] if corte >= 0 else b""
                dados = ultimas_linhas(dados, ultimas)
                truncado = len(dados) < tamanho
            else:
                prefetch = getattr(f, "prefetch", None)
                if prefetch and tamanho:
                    prefetch(tamanho)
                dados = f.read(tamanho) if tamanho else b""
    except OSError as e:
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
    """O que o botão Testar do Admin mostra: existe? é pasta? o usuário SSH lê?"""
    try:
        real = posixpath.normpath(str(sftp.normalize(caminho)))
    except OSError as e:
        num = getattr(e, "errno", None)
        if num == errno.ENOENT:
            return {"existe": False, "eh_pasta": False, "legivel": False,
                    "caminho_real": None, "detalhe": "a pasta não existe no servidor"}
        if num == errno.EACCES:
            return {"existe": True, "eh_pasta": None, "legivel": False,
                    "caminho_real": None,
                    "detalhe": "o usuário SSH não tem permissão para resolver o caminho"}
        raise ArquivoError(502, f"Falha ao testar {caminho} no servidor: {e}") from e
    st = _stat(sftp, real)
    eh_pasta = bool(statmod.S_ISDIR(getattr(st, "st_mode", 0) or 0))
    if not eh_pasta:
        return {"existe": True, "eh_pasta": False, "legivel": False, "caminho_real": real,
                "detalhe": "o caminho existe, mas é um arquivo — uma raiz precisa ser pasta"}
    try:
        sftp.listdir(real)
        legivel, detalhe = True, "existe e é legível pelo usuário SSH"
    except OSError:
        legivel, detalhe = False, "existe, mas o usuário SSH não consegue listar a pasta"
    return {"existe": True, "eh_pasta": True, "legivel": legivel,
            "caminho_real": real, "detalhe": detalhe}


@contextmanager
def conexao_sftp(servidor: str):
    """Abre SSH+SFTP no servidor e fecha ao sair. Os testes substituem esta função.

    503 sem credencial (antes de importar o paramiko); 502 em falha de conexão."""
    cred = credencial(servidor)
    import paramiko  # import tardio: só existe em runtime, não nos testes

    client = paramiko.SSHClient()
    # Paridade com o Console DataStage; known_hosts fixo é melhoria transversal (spec §8).
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=cred.host, port=cred.port, username=cred.user,
            password=cred.password, key_filename=cred.key_file,
            timeout=10, banner_timeout=15, auth_timeout=15,
        )
        sftp = client.open_sftp()
        canal = sftp.get_channel()
        if canal is not None:
            canal.settimeout(60)
    except Exception as e:
        client.close()
        raise ArquivoError(502, f"Falha ao conectar por SSH em {cred.host}:{cred.port}: {e}") from e
    try:
        yield sftp
    finally:
        try:
            sftp.close()
        finally:
            client.close()
