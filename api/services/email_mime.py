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
# maiúsculo e pode ter dígito, `_`, `-` e `.` — o mesmo alfabeto que
# `_JOB_NAME_STRICT_RE` (api/routers/jobs.py) aceita no cadastro do nó.
# Alfabeto menor aqui deixaria um nó salvável inalcançável pelo marcador.
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)(?::([A-Za-z0-9_.\-]{1,128}))?\}")
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
    escreveu o marcador pediu aquele nó, não "qualquer um".

    ⚠️ A TELA NÃO CONFERE o nome do nó (ela não conhece o grafo a montante no
    painel): um `{tabela:CONTA}` escrito para o nó `CONTA_SANCOES` passa no save
    e sai literal no e-mail. Quem denuncia é o log da task, em runtime."""
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


def html_para_texto(corpo: str) -> str:
    """HTML → texto simples legível, para o alternativo `text/plain`.

    ⚠️ Tirar as tags com um `re.sub` só COLA o conteúdo das células: uma tabela
    de resultado virava `ProdutoQtdACIDO A3DIPIRONA1`, em que o número de uma
    linha encosta no nome da seguinte — ilegível e ambíguo para quem lê em modo
    texto, para leitor de tela e para o snippet da caixa de entrada. As
    fronteiras de bloco viram separador ANTES do strip."""
    texto = corpo or ""
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)          # comentário some inteiro
    texto = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", texto)   # e o que não é conteúdo
    texto = re.sub(r"(?i)</t[dh]\s*>", " | ", texto)              # célula → separador
    texto = re.sub(r"(?i)<br\s*/?>|</(tr|p|div|h[1-6]|li|table)\s*>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = texto.replace("&#160;", " ").replace("&nbsp;", " ")
    # `A | B | ` → `A | B`; e no máximo uma linha em branco entre blocos
    texto = "\n".join(re.sub(r"\s*\|\s*$", "", l.strip()) for l in texto.splitlines())
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


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
        texto = html_para_texto(corpo)
        msg.set_content(texto, subtype="plain", charset="utf-8")
        msg.add_alternative(documento_html(corpo), subtype="html", charset="utf-8")
    else:
        msg.set_content(corpo, subtype="plain", charset="utf-8")
    if anexo_nome and anexo_bytes is not None:
        tipo, _ = mimetypes.guess_type(anexo_nome)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(anexo_bytes, maintype=maintype, subtype=subtype, filename=anexo_nome)
    return msg.as_bytes()
