"""dags/utils/email_envio.py — ESPELHO de api/services/email_mime.py para o
worker do Airflow (spec docs/spec-notificacao-email.md): as mesmas regras puras
de endereço, domínio, anexo e a montagem MIME, mais `enviar()` — a entrega ao
`sendmail -t -i -f <remetente>` do servidor do DataStage pelo stdin da sessão SSH.

⚠️ api/ e dags/ rodam em containers diferentes e o repo nunca importou uma
árvore da outra: tests/test_email_mime.py confere que o bloco puro aqui é
IDÊNTICO ao da API (valores e código). Mudou lá, muda aqui.
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
# Pasta do anexo: com subpasta o caminho ficou livre, e `etl_email_log.anexo_path`
# tem 500 — o teto aqui deixa margem para o nome do arquivo.
LIMITE_PASTA_ANEXO = 300

# Endereço simples: local@dominio.tld, sem espaços, sem quebras, sem aspas.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# Raiz de anexo: caminho absoluto Unix sem espaços/aspas/`..` (como Pathname).
RAIZ_RE = re.compile(r"^/[^\s'\"]*[^\s'\"/]$|^/$")
# Nome do anexo: livre, mas UM nome (sem barra, sem `..`, sem quebra de linha).
# Placeholders `{odate}` etc. são permitidos — resolvidos na hora do envio.
NOME_ANEXO_PROIBIDO_RE = re.compile(r"[/\\\r\n\x00]")
# Placeholder `{nome}` como o nó de notificação usa.
# `{chave}` e `{chave:QUALIFICADOR}` — o qualificador nasceu com `{tabela:NO_SQL}`,
# que aponta para UM nó SQL a montante quando há mais de um. Nome de nó é
# maiúsculo e pode ter dígito, `_` e `-`; a chave em si segue minúscula.
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)(?::([A-Za-z0-9_\-]{1,128}))?\}")
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


def pasta_do_anexo(bruta, raizes_permitidas: list[str]) -> str | None:
    """Normaliza a pasta do anexo e confere que ela é uma raiz permitida **ou
    uma pasta abaixo dela**. `None` = fora das permitidas (ou malformada).

    Subpasta é o caso normal desde o seletor de arquivo: quem navega desce da
    raiz até onde o arquivo está. O ENVIO sempre aceitou isso —
    `caminho_do_anexo` mede o caminho final contra as raízes —, era só o
    cadastro que exigia a raiz exata e recusava no salvar o que a corrida
    entregaria sem reclamar.

    Três cuidados que a comparação por texto exige:
      * **barras iniciais colapsadas** antes de comparar: o POSIX trata `//x`
        como caminho próprio e o `normpath` PRESERVA as duas barras, então uma
        raiz gravada como `//dados/saida` nunca casaria com o `/dados/saida`
        que o navegador devolve — e o save recusaria o caminho que a própria
        tela acabou de entregar;
      * **raiz que normaliza para `/` (ou vazia) é ignorada**: `startswith("/")`
        aceitaria o servidor inteiro. `validar_raizes` já barra `/`, mas quem
        escreve direto no `etl_app_config` passa por fora dela — é a mesma
        guarda que `ssh_arquivos.raiz_de` tem do lado dos Utilitários;
      * **teto de tamanho**: sem raiz exata o caminho ficou livre, e o
        `anexo_path` do log tem 500."""
    p = str(bruta or "").strip().rstrip("/")
    if not p.startswith("/") or "\\" in p or "\n" in p or "\r" in p or "\x00" in p:
        return None
    if ".." in p.split("/"):
        return None
    if len(p.encode("utf-16-le")) // 2 > LIMITE_PASTA_ANEXO:
        return None
    caminho = posixpath.normpath(re.sub(r"^/+", "/", p))
    for r in raizes_permitidas or []:
        base = posixpath.normpath(re.sub(r"^/+", "/", str(r).strip().rstrip("/") or "/"))
        if base in ("", "/", "."):
            continue
        if caminho == base or caminho.startswith(base + "/"):
            return caminho
    return None


def validar_anexo_cadastro(raiz, nome, raizes_permitidas: list[str]) -> tuple[dict | None, list[str]]:
    """Regra do CADASTRO (decisão do usuário): a pasta tem de estar dentro de
    uma das permitidas; o NOME é livre — pode não existir ainda (o arquivo
    nasce na corrida) e pode ter placeholders — mas é UM nome: sem barra, sem
    `..`, sem quebra de linha. Existência e tamanho são conferidos só na
    hora."""
    erros: list[str] = []
    r = str(raiz or "").strip().rstrip("/") or ""
    n = str(nome or "").strip()
    if not r and not n:
        return None, []
    if not r:
        erros.append("anexo: escolha a pasta permitida")
    else:
        pasta = pasta_do_anexo(r, raizes_permitidas)
        if pasta is None:
            erros.append(f"anexo: a pasta '{r}' não está entre as permitidas no Admin › E-mail")
        else:
            r = pasta
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
    notificação: o e-mail sai com `{variavel_errada}` visível).

    Com qualificador, a chave procurada é a COMPLETA (`tabela:NO_SQL`) e nunca a
    base: `{tabela:XPTO}` apontando para um nó que não existe tem de aparecer
    literal no e-mail, e não silenciosamente virar a tabela de outro nó — quem
    escreveu o marcador pediu aquele nó, não "qualquer um"."""
    def _sub(m):
        chave = f"{m.group(1)}:{m.group(2)}" if m.group(2) else m.group(1)
        return str(mapa[chave]) if chave in mapa and mapa[chave] is not None else m.group(0)
    return PLACEHOLDER_RE.sub(_sub, texto or "")


def documento_html(corpo: str) -> str:
    """Corpo HTML → documento COMPLETO, com o `<head>` que o Outlook precisa.

    O corpo do modelo é um fragmento (começa direto no `<table>`) e ia cru para
    o `text/html`. Sem `<head>`, o Outlook desktop (motor do Word) fica sem o
    `<o:PixelsPerInch>96</o:PixelsPerInch>`, e passa a dimensionar formas e
    tamanhos com o DPI do WINDOWS: numa tela em 125% — o padrão de notebook
    corporativo — o cabeçalho sai menor que a largura da mensagem e sobra uma
    faixa de outra cor ao lado dele.

    `color-scheme: light only` pede aos clientes que respeitam a diretiva
    (Outlook novo, Apple Mail) que NÃO invertam as cores no modo escuro: a
    inversão parcial é o que deixava o cabeçalho com dois tons de azul.

    ⚠️ Corpo que JÁ é documento volta intacto. Embrulhar de novo criaria um
    segundo `<body>`, cujos atributos o cliente descarta em silêncio — o mesmo
    defeito que a prévia em iframe pagou na F1 da spec de modelos."""
    texto = corpo or ""
    # `<body` conta tanto quanto `<html`: um corpo que abre direto no body já é
    # documento, e embrulhá-lo criaria um segundo `<body>` cujos atributos o
    # cliente descarta — o fundo e a cor do modelo sumiriam do e-mail entregue e
    # continuariam aparecendo na prévia. É a MESMA régua do front
    # (`montarDocumento` em previaEmailDados.ts), e as duas precisam bater para
    # a tela e o envio contarem a mesma história.
    if re.search(r"<(html|body)\b", texto, re.I):
        return texto
    return (
        "<!DOCTYPE html>\n"
        '<html xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light only">\n'
        '<meta name="supported-color-schemes" content="light only">\n'
        "<!--[if mso]>\n"
        "<xml><o:OfficeDocumentSettings><o:AllowPNG/>"
        "<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>\n"
        "<![endif]-->\n"
        "</head>\n"
        '<body style="margin:0;padding:0;">\n'
        f"{texto}\n"
        "</body>\n</html>"
    )


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
        # O texto simples sai do corpo ORIGINAL: tirá-lo do documento embrulhado
        # arrastaria o conteúdo do <head> para dentro da mensagem de quem lê em
        # texto puro.
        texto = re.sub(r"<[^>]+>", "", corpo)
        msg.set_content(texto, subtype="plain", charset="utf-8")
        msg.add_alternative(documento_html(corpo), subtype="html", charset="utf-8")
    else:
        msg.set_content(corpo, subtype="plain", charset="utf-8")
    if anexo_nome and anexo_bytes is not None:
        tipo, _ = mimetypes.guess_type(anexo_nome)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(anexo_bytes, maintype=maintype, subtype=subtype, filename=anexo_nome)
    return msg.as_bytes()


# ── Entrega (worker) ─────────────────────────────────────────────────────────

import os as _os
import shlex as _shlex
import time as _time

# Binário do MTA no servidor do DataStage: configuração de SERVIDOR (env do
# worker), nunca entrada de usuário. Em `lnxprd021` é o Postfix.
SENDMAIL_BIN = _os.getenv("EMAIL_SENDMAIL_BIN", "/usr/sbin/sendmail")
_BIN_RE = re.compile(r"^/[A-Za-z0-9_./\\-]+$")


def comando_sendmail(remetente: str, binario: str | None = None) -> str:
    """`<bin> -t -i -f <remetente>` — o ÚNICO comando que o e-mail executa.
    `-t` lê os destinatários do cabeçalho To:; `-f` fixa o envelope-from no
    remetente do Admin (sem ele o Postfix usa o usuário SSH: bounces vão para
    a caixa errada e um relay que policia o MAIL FROM descarta depois do rc 0).
    O remetente é o único argumento que vem de configuração: já passou pela
    allowlist EMAIL_RE (sem metacaractere de shell) e ainda vai citado."""
    b = (binario or SENDMAIL_BIN).strip()
    if not _BIN_RE.match(b) or "/../" in b:
        raise ValueError(f"EMAIL_SENDMAIL_BIN inválido: {b!r}")
    rem = validar_email(remetente)
    if not rem:
        raise ValueError("remetente inválido para o envelope (-f)")
    return f"{_shlex.quote(b)} -t -i -f {_shlex.quote(rem)}"


def enviar(client, mensagem: bytes, remetente: str, timeout: int = 60, binario: str | None = None) -> dict:
    """Entrega `mensagem` ao sendmail pelo stdin de uma sessão SSH já aberta
    (paramiko SSHClient — o do SSHHook do Airflow ou o da API). Devolve
    {exit_code, stderr, duration_ms}; quem chama decide se rc != 0 é falha.
    Se o sendmail fechar o stdin antes de ler tudo (mensagem grande recusada),
    o rc e o stderr dele são o diagnóstico — não um 'não conectou'."""
    t0 = _time.time()
    stdin, stdout, stderr = client.exec_command(comando_sendmail(remetente, binario), timeout=timeout)
    escrita_erro = ""
    try:
        stdin.write(mensagem)
        stdin.channel.shutdown_write()
    except OSError as e:  # canal fechado pelo sendmail no meio da escrita
        escrita_erro = f"sendmail fechou a entrada antes de ler a mensagem inteira ({e})"
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode(errors="replace").strip()
    if escrita_erro:
        err = (err + " | " if err else "") + escrita_erro
        if exit_code == 0:
            exit_code = -1
    return {"exit_code": exit_code, "stderr": err[:2000], "duration_ms": int((_time.time() - t0) * 1000)}


def resolver_anexo(sftp, raiz: str, nome: str, raizes_permitidas: list[str],
                   limite_mb: int, mapa: dict) -> tuple[bytes | None, str | None, dict]:
    """Lê o anexo do servidor do DataStage por SFTP, DEPOIS de trocar os
    placeholders do nome (`relatorio_{odate}.xlsx`).

    Devolve `(bytes|None, aviso|None, detalhe)`. `detalhe` sempre traz
    `{"caminho": …, "bytes": …}` para o log, mesmo quando não leu nada.

    Regra da spec: anexo ausente NÃO derruba a corrida — o e-mail sai sem ele
    com aviso (`status='sem_anexo'`). O que é recusado de propósito:
    - nome resolvido que escapa da raiz (um placeholder não pode inserir `..`
      nem `/` — `caminho_do_anexo` devolve None e nem chegamos ao SFTP);
    - caminho que NÃO é arquivo regular: um diretório ou um device em
      `sftp.open()` pendura a task ou lê lixo; `S_ISREG` no `stat` resolve
      antes de abrir (ressalva da revisão adversarial da F1);
    - arquivo maior que o limite do Admin, medido pelo `stat` ANTES de ler —
      ler para depois medir traria o arquivo inteiro para a memória do worker.
    """
    import errno as _errno
    import stat as _stat

    nome_resolvido = interpolar(str(nome or ""), mapa or {})
    caminho = caminho_do_anexo(raiz, nome_resolvido, raizes_permitidas)
    detalhe = {"caminho": caminho or f"{raiz}/{nome_resolvido}", "bytes": None}
    if not caminho:
        return None, (f"anexo recusado: '{nome_resolvido}' sai da raiz permitida "
                      f"'{raiz}' depois de resolver os placeholders"), detalhe
    try:
        info = sftp.stat(caminho)
    except OSError as e:
        # `IOError` É `OSError` no Python 3: o paramiko usa a mesma classe para
        # "não existe" e para canal caído. Só o errno separa os dois, e a
        # diferença importa — ausente é rotina (e-mail sem anexo), SFTP fora do
        # ar é problema de infraestrutura e não pode virar 'sem anexo' mudo.
        if e.errno in (_errno.ENOENT, _errno.ENOTDIR):
            return None, f"anexo não encontrado em {caminho} — e-mail enviado sem anexo", detalhe
        return None, f"anexo não pôde ser consultado em {caminho} ({type(e).__name__}: {e})", detalhe
    except Exception as e:   # noqa: BLE001
        return None, f"anexo não pôde ser consultado em {caminho} ({type(e).__name__}: {e})", detalhe
    if not _stat.S_ISREG(info.st_mode or 0):
        return None, f"anexo ignorado: {caminho} não é um arquivo (é diretório ou especial)", detalhe
    # ⚠️ A régua do cadastro é LEXICAL (não há SSH no salvar): com um link de
    # diretório dentro da raiz — `/dados/saida/corrente -> /u02/outra_area`, uso
    # comum no DataStage — o caminho passa no texto e o `stat` segue o link,
    # lendo um arquivo de FORA das pastas liberadas. O navegador de pastas já
    # recusa entrar nesse link (confere nível a nível no servidor); aqui o
    # equivalente é perguntar ao servidor o caminho real e medi-lo contra as
    # mesmas raízes. Servidor que não implemente `realpath` não bloqueia o
    # envio: aí vale o que a régua lexical já garantiu.
    try:
        real = sftp.normalize(caminho)
    except Exception:  # noqa: BLE001
        real = None
    if real and real != caminho and not caminho_do_anexo(
            posixpath.dirname(real), posixpath.basename(real), raizes_permitidas):
        detalhe["caminho"] = real
        return None, (f"anexo recusado: {caminho} aponta para {real}, fora das pastas "
                      f"liberadas — e-mail enviado sem anexo"), detalhe
    tamanho = int(info.st_size or 0)
    detalhe["bytes"] = tamanho
    teto = max(1, int(limite_mb or LIMITE_ANEXO_MB_PADRAO)) * 1024 * 1024
    if tamanho > teto:
        return None, (f"anexo maior que o limite: {caminho} tem {tamanho / 1048576:.1f} MB "
                      f"(limite {limite_mb} MB) — e-mail enviado sem anexo"), detalhe
    if tamanho == 0:
        return None, f"anexo vazio (0 byte) em {caminho} — e-mail enviado sem anexo", detalhe
    with sftp.open(caminho, "rb") as fh:
        dados = fh.read()
    detalhe["bytes"] = len(dados)
    return dados, None, detalhe
