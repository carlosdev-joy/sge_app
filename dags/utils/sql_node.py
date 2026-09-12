"""Nó SQL do fluxo: o resultado do SELECT em formato publicável no XCom.

Até aqui o nó SQL devolvia só o **valor escalar** (1ª coluna da 1ª linha), que a
Decisão `valor_sql` a jusante lê pelo `return_value`. Este módulo acrescenta a
TABELA — colunas e linhas — para que o nó de e-mail a jusante possa mostrar o
resultado da consulta dentro do aviso (F4/F5 da spec
docs/spec-email-tabela-sql-e-ajustes.md).

⚠️ **O escalar não muda.** Ele continua sendo o `return_value` da task, byte a
byte: toda Decisão `valor_sql` já publicada lê aquele XCom, e mexer no retorno
quebraria fluxos em produção sem aviso. A tabela vai numa CHAVE PRÓPRIA.

⚠️ **O corte acontece AQUI, na origem.** Um SELECT sem filtro pode devolver
centenas de milhares de linhas; carregar isso na memória do worker para depois
jogar fora na montagem do e-mail seria caro e arriscado. O cursor é lido até um
teto, o que passa disso nunca chega a virar objeto Python.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal

# Quanto do resultado vira e-mail. 50 × 15 é o que se lê num aviso sem rolar a
# mensagem inteira; acima disso o relatório é um arquivo, não um corpo de e-mail.
LIMITE_LINHAS = 50
LIMITE_COLUNAS = 15
# Teto de LEITURA: quantas linhas o cursor entrega para sabermos o total. Acima
# disto o aviso passa a dizer "mais de 1.000" em vez de um número exato — a
# alternativa seria um COUNT(*) extra na origem, caro e fora do que a fase pede.
TETO_LEITURA = 1000
# Uma célula gigante (VARCHAR(MAX) com um JSON dentro, por exemplo) entupiria o
# XCom e o corpo do e-mail. O corte é por caractere, com reticências.
LIMITE_CELULA = 200


def valor_publicavel(v):
    """Valor do banco → algo que o XCom serializa e o e-mail sabe mostrar.

    `None` continua `None` (quem renderiza decide como mostrar a ausência).
    Data, hora e decimal viram texto — o JSON do XCom não os carrega — e bytes
    viram um rótulo, porque binário no corpo de um e-mail não ajuda ninguém."""
    if v is None or isinstance(v, (bool, int, float, str)):
        texto = v
    elif isinstance(v, _decimal.Decimal):
        texto = str(v)
    elif isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        texto = v.isoformat(sep=" ") if isinstance(v, _dt.datetime) else v.isoformat()
    elif isinstance(v, (bytes, bytearray, memoryview)):
        texto = f"<{len(bytes(v))} bytes>"
    else:
        texto = str(v)
    if isinstance(texto, str):
        # Quebra de linha DENTRO da célula destrói o alinhamento da versão em
        # texto (a tabela vira degrau) e não acrescenta nada no HTML, onde a
        # célula já quebra sozinha.
        texto = " ".join(texto.split())
        if len(texto) > LIMITE_CELULA:
            return texto[:LIMITE_CELULA - 1] + "…"
    return texto


def ler_resultado(cursor):
    """Cursor JÁ executado → ``(escalar_cru, tabela)``, numa leitura só.

    ⚠️ O **escalar sai CRU**, exatamente como `fetchone()[0]` devolveria: é ele
    que vira o `return_value` da task, e a Decisão `valor_sql` o compara com
    régua tipada (texto/data/número). Passá-lo pela conversão da tabela mudaria
    silenciosamente o valor — uma data viraria texto ISO, um decimal viraria
    string e um texto longo seria cortado em 200 caracteres — e fluxos em
    produção passariam a decidir diferente sem ninguém mexer neles.

    ⚠️ E as duas coisas vêm da MESMA leitura: ler o cursor duas vezes daria
    resultados diferentes num SELECT sem ORDER BY, e o fluxo decidiria por um
    valor que o e-mail não mostra."""
    tabela = montar_tabela(cursor)
    return tabela.pop("_escalar", None), tabela


def montar_tabela(cursor) -> dict:
    """Cursor JÁ executado → dicionário publicável no XCom.

    Devolve:
      - ``columns``   nomes das colunas (até ``LIMITE_COLUNAS``);
      - ``rows``      linhas (até ``LIMITE_LINHAS``), já em valores publicáveis;
      - ``total``     quantas linhas foram LIDAS (no máximo ``TETO_LEITURA``);
      - ``truncado``  ficou linha de fora do que é mostrado;
      - ``havia_mais`` o teto de leitura foi atingido, então ``total`` é um piso
        e não o número exato;
      - ``colunas_ocultas`` quantas colunas ficaram de fora.

    Cursor sem `description` (um SELECT que não devolve conjunto) vira tabela
    vazia em vez de erro: o nó SQL existe para alimentar a Decisão, e a tabela é
    um extra que nunca pode derrubar a task."""
    descricao = getattr(cursor, "description", None) or []
    todas_colunas = [str(d[0]) for d in descricao]
    colunas = todas_colunas[:LIMITE_COLUNAS]
    if not colunas:
        return {"columns": [], "rows": [], "total": 0, "truncado": False,
                "havia_mais": False, "colunas_ocultas": 0, "_escalar": None}

    lidas = cursor.fetchmany(TETO_LEITURA) or []
    # `fetchmany` pode devolver mais do que o pedido? Não — mas pode devolver
    # menos e ainda haver linhas; o teto atingido é o sinal de "havia mais".
    havia_mais = len(lidas) >= TETO_LEITURA
    linhas = [[valor_publicavel(c) for c in linha[:LIMITE_COLUNAS]]
              for linha in lidas[:LIMITE_LINHAS]]
    return {
        "columns": colunas,
        "rows": linhas,
        "total": len(lidas),
        "truncado": len(lidas) > len(linhas),
        "havia_mais": havia_mais,
        "colunas_ocultas": max(0, len(todas_colunas) - len(colunas)),
        # CRU de propósito — ver `ler_resultado`. Sai do dicionário antes de ir
        # para o XCom, para não haver duas versões do mesmo valor circulando.
        "_escalar": (lidas[0][0] if lidas and len(lidas[0]) else None),
    }


def resumo_para_log(tabela: dict) -> str:
    """Uma linha para o log da task — é por ela que o smoke confere se o
    recurso está ativo no worker (e não rodando código velho em cache)."""
    t = tabela or {}
    total = t.get("total", 0)
    partes = [f"{len(t.get('rows') or [])} linha(s) publicada(s)",
              f"{len(t.get('columns') or [])} coluna(s)"]
    if t.get("havia_mais"):
        partes.append(f"mais de {total} lidas")
    elif t.get("truncado"):
        partes.append(f"de {total} lidas")
    if t.get("colunas_ocultas"):
        partes.append(f"{t['colunas_ocultas']} coluna(s) fora")
    return ", ".join(partes)


# ── render para o corpo do e-mail (F5) ──────────────────────────────────────
# Paleta e medidas do modelo institucional (migration 112/113), para a tabela
# não parecer colada de outro lugar.
_BORDA = "#E2E8F0"
_CABECALHO = "#F8FAFC"
_TINTA = "#1E293B"
_TINTA_FRACA = "#64748B"


def _celula(valor) -> str:
    """Texto da célula, já ESCAPADO.

    ⚠️ Este é o primeiro lugar do e-mail onde entra dado de fora — tudo mais
    (pipeline, status, datas) é gerado pelo próprio produto. Uma descrição com
    `<b>` ou um `&` de razão social quebraria o layout do aviso; um `</table>`
    quebraria o resto da mensagem."""
    from html import escape

    if valor is None or valor == "":
        return f'<span style="color:{_TINTA_FRACA};">—</span>'
    return escape(str(valor), quote=False)


def tabela_html(tabela: dict) -> str:
    """Tabela do nó SQL → HTML para o corpo do e-mail.

    Sem colunas (nó que não rodou, SELECT sem conjunto) devolve um aviso
    discreto em vez de nada: uma linha em branco no meio do aviso faria o leitor
    achar que a mensagem veio quebrada."""
    t = tabela or {}
    colunas = t.get("columns") or []
    linhas = t.get("rows") or []
    if not colunas:
        return (f'<div style="color:{_TINTA_FRACA};font-size:12px;">'
                "(sem resultado)</div>")

    th = "".join(
        f'<th align="left" style="padding:8px 12px;border-bottom:1px solid {_BORDA};'
        f'color:{_TINTA_FRACA};font-size:11px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.5px;">{_celula(c)}</th>'
        for c in colunas)

    corpo = []
    for i, linha in enumerate(linhas):
        fundo = f' bgcolor="{_CABECALHO}"' if i % 2 else ""
        tds = "".join(
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDA};'
            f'color:{_TINTA};font-size:13px;">{_celula(v)}</td>' for v in linha)
        corpo.append(f"<tr{fundo}>{tds}</tr>")
    if not linhas:
        corpo.append(
            f'<tr><td colspan="{len(colunas)}" style="padding:10px 12px;'
            f'color:{_TINTA_FRACA};font-size:12px;">A consulta não devolveu linhas.</td></tr>')

    rodape = ""
    aviso = _aviso_de_corte(t)
    if aviso:
        rodape = (f'<tr><td colspan="{len(colunas)}" style="padding:8px 12px;'
                  f'color:{_TINTA_FRACA};font-size:11px;">{aviso}</td></tr>')

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;border:1px solid {_BORDA};border-radius:8px;'
        'border-collapse:collapse;font-family:Segoe UI,Helvetica,Arial,sans-serif;">'
        f'<tr bgcolor="{_CABECALHO}">{th}</tr>'
        + "".join(corpo) + rodape + "</table>")


def _aviso_de_corte(t: dict) -> str:
    """A frase que diz o que ficou de fora — e que NUNCA afirma um total que não
    foi contado: acima do teto de leitura o número é um piso, e o texto diz
    "mais de", em vez de mentir um número exato."""
    mostradas, total = len(t.get("rows") or []), t.get("total", 0)
    partes = []
    if t.get("havia_mais"):
        # Milhar com ponto, explícito: `:n` depende do locale do processo, e o
        # worker roda sem locale definido — sairia "1000" aqui e "1.000" na
        # prévia da tela, com o teste cruzado acusando a diferença.
        milhar = f"{total:,}".replace(",", ".")
        partes.append(f"mostrando {mostradas} de mais de {milhar} linhas")
    elif t.get("truncado"):
        partes.append(f"mostrando {mostradas} de {total} linhas")
    if t.get("colunas_ocultas"):
        n = t["colunas_ocultas"]
        partes.append(f"{n} coluna não cabe no aviso" if n == 1
                      else f"{n} colunas não cabem no aviso")
    return " · ".join(partes)


def tabela_texto(tabela: dict) -> str:
    """A mesma tabela em TEXTO, para corpo que não é HTML.

    O nó aceita "Corpo livre" em texto simples: mandar markup para lá encheria
    o aviso de `<td style=…>`.

    ⚠️ NÃO é esta versão que vai para o alternativo `text/plain` de um corpo
    HTML — lá quem trabalha é `html_para_texto` (email_envio.py), que transforma
    as fronteiras de célula e de linha em separadores antes de tirar as tags."""
    t = tabela or {}
    colunas = t.get("columns") or []
    linhas = t.get("rows") or []
    if not colunas:
        return "(sem resultado)"
    if not linhas:
        return " | ".join(str(c) for c in colunas) + "\n(a consulta não devolveu linhas)"

    matriz = [[str(c) for c in colunas]]
    matriz += [["—" if v is None or v == "" else str(v) for v in linha] for linha in linhas]
    larguras = [max(len(l[i]) for l in matriz) for i in range(len(colunas))]
    saida = [" | ".join(c.ljust(larguras[i]) for i, c in enumerate(linha)).rstrip()
             for linha in matriz]
    saida.insert(1, "-+-".join("-" * w for w in larguras))
    aviso = _aviso_de_corte(t)
    if aviso:
        saida.append(f"({aviso})")
    return "\n".join(saida)


def resumo_curto(tabela: dict) -> str:
    """Para o ASSUNTO, onde uma tabela não cabe: `3 linhas × 2 colunas`.

    Sem isto, `{tabela}` no assunto colocaria markup (ou um bloco de texto com
    quebras de linha) num cabeçalho de e-mail — e a régua do assunto recusa
    quebra de linha, fazendo a etapa falhar depois de resolver os marcadores."""
    t = tabela or {}
    colunas = t.get("columns") or []
    if not colunas:
        return "(sem resultado)"
    linhas = len(t.get("rows") or [])
    total = t.get("total", linhas)
    quantas = f"mais de {total}" if t.get("havia_mais") else str(total)
    return (f"{quantas} linha{'s' if total != 1 else ''} × "
            f"{len(colunas)} coluna{'s' if len(colunas) != 1 else ''}")
