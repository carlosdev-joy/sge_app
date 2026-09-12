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
    if isinstance(texto, str) and len(texto) > LIMITE_CELULA:
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
