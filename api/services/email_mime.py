"""api/services/email_mime.py — as regras PURAS do e-mail do Orquestra
(spec docs/spec-notificacao-email.md, F1): validação de endereços, domínios e
anexo, e a montagem da mensagem MIME que vai ao `sendmail -t -i` via stdin.

Por que MIME pelo Python e não `mailx`: a variante de `mailx` instalada muda o
significado de `-a` (anexo × cabeçalho), e montar a mensagem aqui deixa HTML e
anexo previsíveis. E por que via stdin: NENHUM campo do usuário vai para a
linha de comando — assunto, destinatários e corpo vivem nos cabeçalhos/corpo
da mensagem, e quebras de linha são recusadas onde virariam cabeçalho novo.

⚠️ ESPELHO: dags/utils/email_envio.py (o worker) carrega uma cópia destas
funções, porque api/ e dags/ rodam em containers diferentes e o repo nunca
importou uma árvore da outra. tests/test_email_mime.py confere as duas.
Mudou aqui, muda lá.
"""
from __future__ import annotations

import mimetypes
import posixpath
import re
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

LIMITE_ASSUNTO = 500          # NVARCHAR(500) em etl_email_log.assunto (UTF-16)
LIMITE_CORPO = 20000
LIMITE_DESTINATARIOS = 50
LIMITE_ANEXO_MB_MIN = 1
LIMITE_ANEXO_MB_MAX = 25
LIMITE_ANEXO_MB_PADRAO = 5
LIMITE_NOME_ANEXO = 200

# Endereço simples: local@dominio.tld, sem espaços, sem quebras, sem aspas.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# Raiz de anexo: caminho absoluto Unix sem espaços/aspas/`..` (como Pathname).
RAIZ_RE = re.compile(r"^/[^\s'\"]*[^\s'\"/]$|^/$")
# Nome do anexo: livre, mas UM nome (sem barra, sem `..`, sem quebra de linha).
# Placeholders `{odate}` etc. são permitidos — resolvidos na hora do envio.
NOME_ANEXO_PROIBIDO_RE = re.compile(r"[/\\\r\n\x00]")
# Placeholder `{nome}` como o nó de notificação usa.
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
# Cabeçalhos que só a montagem define: um `cabecalho_extra` com `Bcc` seria
# entregue pelo `-t`; `To` duplicado explode na stdlib.
CABECALHOS_RESERVADOS = {"from", "to", "cc", "bcc", "subject", "date", "message-id", "mime-version",
                         "return-path", "sender", "reply-to"}


def _sem_quebra(valor: str) -> bool:
    """`splitlines()` cobre o que a política do EmailMessage recusa num
    cabeçalho (\r, \n, \x0b, \x0c, \x1c–\x1e, \x85, \u2028, \u2029) — só
    \r/\n deixaria a régua aceitar o que a montagem depois recusaria."""
    return len(valor.splitlines()) <= 1 and "\r" not in valor and "\n" not in valor


def validar_email(valor) -> str | None:
    """Endereço normalizado (strip, minúsculo no domínio) ou None."""
    s = str(valor or "").strip()
    if not s or not _sem_quebra(s) or len(s) > 254 or not EMAIL_RE.match(s):
        return None
    local, _, dominio = s.rpartition("@")
    return f"{local}@{dominio.lower()}"


def normalizar_lista(valor) -> list[str]:
    """Aceita lista, ou texto com vírgula/;/quebra de linha; sem vazios."""
    if valor is None:
        return []
    if isinstance(valor, str):
        partes = re.split(r"[,\n;]+", valor)
    elif isinstance(valor, (list, tuple)):
        partes = [str(p) for p in valor]
    else:
        return [str(valor)]
    return [p.strip() for p in partes if str(p).strip()]


def validar_destinatarios(valor, dominios_permitidos=None) -> tuple[list[str], list[str]]:
    """(válidos sem duplicata, erros). Domínios permitidos vazios = qualquer."""
    erros: list[str] = []
    validos: list[str] = []
    dominios = {d.strip().lower().lstrip("@") for d in (dominios_permitidos or []) if str(d).strip()}
    for bruto in normalizar_lista(valor):
        e = validar_email(bruto)
        if not e:
            erros.append(f"endereço inválido: '{bruto[:80]}'")
            continue
        if dominios and e.rpartition("@")[2] not in dominios:
            erros.append(f"domínio não permitido: '{e}' (permitidos: {', '.join(sorted(dominios))})")
            continue
        if e.lower() in {v.lower() for v in validos}:
            continue
        validos.append(e)
    if len(validos) > LIMITE_DESTINATARIOS:
        erros.append(f"no máximo {LIMITE_DESTINATARIOS} destinatários")
    return validos, erros


def validar_raizes(valor) -> tuple[list[str], list[str]]:
    """Raízes permitidas para anexos: caminhos absolutos, sem duplicata."""
    erros: list[str] = []
    saida: list[str] = []
    for bruto in normalizar_lista(valor):
        r = bruto.rstrip("/") or "/"
        if not RAIZ_RE.match(r) or "/../" in r + "/" or r.startswith("/..") or "/./" in r + "/":
            erros.append(f"raiz inválida: '{bruto[:120]}' (caminho absoluto, sem espaços, aspas, '.' ou '..')")
            continue
        r = posixpath.normpath(r)
        if r == "/":
            erros.append("raiz inválida: '/' abriria o servidor inteiro — use uma pasta")
            continue
        if r not in saida:
            saida.append(r)
    return saida, erros


def validar_dominios(valor) -> tuple[list[str], list[str]]:
    erros: list[str] = []
    saida: list[str] = []
    for bruto in normalizar_lista(valor):
        d = bruto.strip().lower().lstrip("@")
        if not re.match(r"^[a-z0-9.\-]+\.[a-z]{2,}$", d):
            erros.append(f"domínio inválido: '{bruto[:80]}'")
            continue
        if d not in saida:
            saida.append(d)
    return saida, erros


def validar_limite_anexo(valor) -> tuple[int | None, str | None]:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None, "limite de anexo deve ser um inteiro em MB"
    if not (LIMITE_ANEXO_MB_MIN <= n <= LIMITE_ANEXO_MB_MAX):
        return None, f"limite de anexo entre {LIMITE_ANEXO_MB_MIN} e {LIMITE_ANEXO_MB_MAX} MB"
    return n, None


def validar_assunto(valor) -> tuple[str | None, str | None]:
    s = str(valor or "").strip()
    if not s:
        return None, "assunto obrigatório"
    if not _sem_quebra(s):
        return None, "assunto não pode ter quebra de linha"
    if len(s.encode("utf-16-le")) // 2 > LIMITE_ASSUNTO:
        return None, f"assunto com mais de {LIMITE_ASSUNTO} caracteres"
    return s, None


def validar_corpo(valor) -> tuple[str | None, str | None]:
    s = str(valor or "")
    if not s.strip():
        return None, "corpo obrigatório"
    if len(s) > LIMITE_CORPO:
        return None, f"corpo com mais de {LIMITE_CORPO} caracteres"
    return s.replace("\r\n", "\n"), None


def validar_anexo_cadastro(raiz, nome, raizes_permitidas: list[str]) -> tuple[dict | None, list[str]]:
    """Regra do CADASTRO (decisão do usuário): a raiz tem de ser uma das
    permitidas; o NOME é livre — pode não existir ainda (o arquivo nasce na
    corrida) e pode ter placeholders — mas é UM nome: sem barra, sem `..`,
    sem quebra de linha. Existência e tamanho são conferidos só na hora."""
    erros: list[str] = []
    r = str(raiz or "").strip().rstrip("/") or ""
    n = str(nome or "").strip()
    if not r and not n:
        return None, []
    if not r:
        erros.append("anexo: escolha a raiz permitida")
    elif r not in (raizes_permitidas or []):
        erros.append(f"anexo: raiz '{r}' não está entre as permitidas no Admin › E-mail")
    if not n:
        erros.append("anexo: informe o nome do arquivo")
    elif NOME_ANEXO_PROIBIDO_RE.search(n) or n in (".", "..") or ".." in n.split("."):
        erros.append("anexo: o nome não pode ter barra, '..' nem quebra de linha")
    elif len(n) > LIMITE_NOME_ANEXO:
        erros.append(f"anexo: nome com mais de {LIMITE_NOME_ANEXO} caracteres")
    if erros:
        return None, erros
    return {"raiz": r, "nome": n}, []


def caminho_do_anexo(raiz: str, nome_resolvido: str, raizes_permitidas: list[str]) -> str | None:
    """Caminho final DEPOIS de trocar os placeholders do nome: só vale se
    continuar dentro da raiz (um placeholder não pode inserir `..` ou `/`)."""
    if (NOME_ANEXO_PROIBIDO_RE.search(nome_resolvido or "") or not nome_resolvido
            or nome_resolvido in (".", "..") or ".." in nome_resolvido.split(".")):
        return None
    caminho = posixpath.normpath(posixpath.join(raiz, nome_resolvido))
    for r in raizes_permitidas or []:
        base = posixpath.normpath(r.rstrip("/") or "/")
        # Sempre DENTRO da raiz (nunca a própria raiz — isso seria um diretório).
        if caminho != base and caminho.startswith(base.rstrip("/") + "/"):
            return caminho
    return None


def interpolar(texto: str, mapa: dict) -> str:
    """`{chave}` → valor; chave desconhecida fica INTACTA (regra do nó de
    notificação: o e-mail sai com `{variavel_errada}` visível)."""
    def _sub(m):
        chave = m.group(1)
        return str(mapa[chave]) if chave in mapa and mapa[chave] is not None else m.group(0)
    return PLACEHOLDER_RE.sub(_sub, texto or "")


def montar_mensagem(remetente: str, destinatarios: list[str], assunto: str, corpo: str,
                    html: bool = False, anexo_nome: str | None = None,
                    anexo_bytes: bytes | None = None, cabecalho_extra: dict | None = None) -> bytes:
    """A mensagem RFC 5322/MIME, em bytes, pronta para `sendmail -t -i`
    (que lê os destinatários do cabeçalho To:). Sempre há `text/plain`; com
    `html=True` o corpo vai como alternativa `text/html` (o texto simples é o
    HTML sem tags). Anexo com nome e tipo pelo `mimetypes`."""
    rem = validar_email(remetente)
    if not rem:
        raise ValueError("remetente inválido")
    dest, erros = validar_destinatarios(destinatarios)
    if erros or not dest:
        raise ValueError("; ".join(erros) or "sem destinatário")
    assunto_ok, erro = validar_assunto(assunto)
    if erro:
        raise ValueError(erro)
    msg = EmailMessage()
    msg["From"] = rem
    msg["To"] = ", ".join(dest)
    msg["Subject"] = assunto_ok
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=rem.rpartition("@")[2])
    msg["X-Orquestra"] = "1"
    for k, v in (cabecalho_extra or {}).items():
        nome = str(k)
        if (re.match(r"^[A-Za-z][A-Za-z0-9\-]*$", nome) and nome.lower() not in CABECALHOS_RESERVADOS
                and not nome.lower().startswith("content-") and _sem_quebra(str(v))):
            msg[nome] = str(v)
    corpo = corpo or ""
    if html:
        texto = re.sub(r"<[^>]+>", "", corpo)
        msg.set_content(texto, subtype="plain", charset="utf-8")
        msg.add_alternative(corpo, subtype="html", charset="utf-8")
    else:
        msg.set_content(corpo, subtype="plain", charset="utf-8")
    if anexo_nome and anexo_bytes is not None:
        tipo, _ = mimetypes.guess_type(anexo_nome)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(anexo_bytes, maintype=maintype, subtype=subtype, filename=anexo_nome)
    return msg.as_bytes()
