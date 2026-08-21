"""dags/utils/chamado_derivacoes.py — o que se lê nas entrelinhas do chamado.

Porta para o produto três leituras que o painel da estação
(`ritm_geresd_ed.html`) já fazia e a tela `/chamados` não tinha:

  1. **tipo de demanda** — "Inclusão de coluna", "Extração de dados"… O
     ServiceNow tem `cat_item`, mas metade dos chamados chega com catálogo
     genérico e o assunto real só aparece no título.
  2. **categoria "dia a dia"** — a equipe já marca isso à mão nas work notes
     (`dia a dia - bug`). Era conhecimento preso no texto; aqui vira coluna.
  3. **objetos técnicos citados** — DMDB…, DM_…, TB_, VW_, PRC_. É o atalho
     para saber sobre o que o chamado fala sem abrir o chamado.

**Por que na ingestão e não na leitura.** Regex por linha a cada request faz a
tela pagar o custo em toda abertura, e — pior — faz o resultado variar
conforme a versão do código que respondeu. Derivado na ingestão, o valor é
gravado, indexável e igual para todo mundo até o próximo ciclo.

⚠️ Derivação é PALPITE ASSUMIDO, não verdade da origem. Por isso nada aqui
sobrescreve campo do ServiceNow, e o tipo desconhecido vira "Demanda técnica"
— um rótulo honesto — em vez de string vazia que a tela teria de adivinhar.
"""
from __future__ import annotations

import re

from utils.frescor_modulo import carimbar

# Ver utils/frescor_modulo.py: sem este carimbo, uma versão antiga deste
# módulo em cache no worker derivaria tudo pelo código velho, em silêncio.
carimbar(__file__)

# Ordem importa: o primeiro que casar vence. "inclusão de coluna" antes de
# "ajuste em tabela" porque um pedido de coluna nova costuma citar os dois.
TIPOS = (
    ("inclusão de coluna", "Inclusão de coluna/campo"),
    ("inclusao de coluna", "Inclusão de coluna/campo"),
    ("ajuste em tabela", "Ajuste em tabela"),
    ("enriquecimento", "Enriquecimento de dados"),
    ("extração de dados", "Extração de dados"),
    ("extracao de dados", "Extração de dados"),
    ("análise pontual", "Análise / investigação"),
    ("analise pontual", "Análise / investigação"),
    ("consulta de dados", "Consulta de dados"),
    ("atendimento auditoria", "Demanda de auditoria"),
    ("auditoria", "Demanda de auditoria"),
    ("demanda estruturante", "Demanda estruturante"),
    ("ajuste em relatório", "Ajuste em relatório"),
    ("ajuste em relatorio", "Ajuste em relatório"),
    ("dúvidas", "Esclarecimento / dúvida"),
    ("duvidas", "Esclarecimento / dúvida"),
    ("parametrização", "Parametrização"),
    ("parametrizacao", "Parametrização"),
    ("restauração", "Restauração banco/servidor"),
    ("restauracao", "Restauração banco/servidor"),
    ("processamento de arquivo", "Processamento de arquivo"),
    ("bucc", "Ajuste na BUCC"),
)

# O rótulo de quem não casou com nada. Dito, e não vazio: "não classifiquei"
# precisa aparecer no gráfico, senão o total por tipo não fecha com a fila.
TIPO_PADRAO = "Demanda técnica"

# Limites das colunas (migration 092).
TIPO_MAX = 60
CATEGORIA_MAX = 60
OBJETOS_MAX = 200

# Quantos objetos técnicos guardar por chamado. Três é o que cabe no card sem
# virar parede de texto — e o painel já usava esse corte.
OBJETOS_LIMITE = 3

# Nomenclatura dos objetos do ambiente: DMDB41..TABELA, DM_123_ALGO, TB_, VW_,
# PRC_. Sem isso o operador precisa abrir o chamado para saber do que se trata.
#
# ⚠️ Os sufixos aceitam DÍGITO, ao contrário do regex original do painel
# (`TB_[A-Z_]+`): lá, `TB_CLIENTE2` era capturado como `TB_CLIENTE` — nome de
# outra tabela, que existe. Recorte silencioso que aponta para o objeto
# errado é pior que não capturar nada.
#
# A borda à ESQUERDA é tão necessária quanto o sufixo: sem ela,
# `DBTB_VENDAS` casa `TB_VENDAS` e `ADM_123_X` casa `DM_123_X` — nomes de
# objetos que existem e não são os do texto. Mesmo defeito, outro lado.
_OBJETOS = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:DMDB\d+\.\.[A-Z_0-9]+|DM_\d+_[A-Z_0-9]+"
    r"|TB_[A-Z_0-9]+|VW_[A-Z_0-9]+|PRC_[A-Z_0-9]+)",
    re.IGNORECASE)

# "dia a dia - bug" → bug. O travessão pode ser hífen ou en-dash: quem digita
# no ServiceNow usa os dois, e aceitar só um jogaria metade das marcações no
# balde genérico.
#
# Depois do travessão vem `[^\S\n]*` — espaço em branco EXCETO quebra de
# linha. Com `\s*`, um "dia a dia -" no fim da linha faz a captura pular para
# a linha seguinte e a frase inteira do técnico vira "categoria", enchendo o
# gráfico de barras de uso único. (O `.splitlines()[0]` adiante não protegia
# disso: `.` já não casa `\n`.)
_DIAADIA_COM_CATEGORIA = re.compile(r"dia\s+a\s+dia[^\S\n]*[-–][^\S\n]*(.+)",
                                    re.IGNORECASE)
_DIAADIA_SOLTO = re.compile(r"\bdia\s+a\s+dia\b", re.IGNORECASE)

CATEGORIA_GERAL = "geral"


def tipo_demanda(titulo: str, catalogo: str = "") -> str:
    """O tipo pelo título e pelo catálogo, nessa ordem de prioridade.

    O título manda porque é onde o solicitante descreve o pedido de verdade; o
    catálogo entra como segunda chance para o caso de o título vir genérico
    ("Solicitação de dados") e o catálogo ser específico.
    """
    for fonte in ((titulo or ""), (catalogo or "")):
        texto = fonte.lower()
        for chave, rotulo in TIPOS:
            if chave in texto:
                return rotulo[:TIPO_MAX]
    return TIPO_PADRAO


def categoria_diaadia(work_notes: str) -> str:
    """A categoria que a equipe já escreve à mão nas work notes.

    Sem marcação nenhuma devolve string vazia — e isso é diferente de
    "geral": o primeiro é chamado que ninguém classificou, o segundo é
    chamado marcado como dia a dia sem categoria. Colapsar os dois inventaria
    classificação que ninguém fez.
    """
    texto = str(work_notes or "")
    achado = _DIAADIA_COM_CATEGORIA.search(texto)
    if achado:
        # `.rstrip('.')` porque a marcação costuma terminar a frase.
        categoria = achado.group(1).strip().rstrip(".").strip().lower()
        if categoria:
            return categoria[:CATEGORIA_MAX]
        # "dia a dia - ." é marcação sem categoria, não ausência de
        # marcação: devolver vazio aqui mandaria o chamado para o balde de
        # "ninguém classificou", contrariando a regra deste módulo.
    if _DIAADIA_SOLTO.search(texto):
        return CATEGORIA_GERAL
    return ""


def objetos_citados(descricao: str, limite: int = OBJETOS_LIMITE) -> str:
    """Os objetos técnicos citados, sem repetição e na ordem em que aparecem.

    Devolve string separada por vírgula (e não lista) porque o destino é uma
    coluna: o espelho é lido por SQL, e uma tabela auxiliar para três nomes
    curtos custaria mais do que resolve.
    """
    achados = _OBJETOS.findall(str(descricao or ""))
    # dict.fromkeys preserva a ordem e tira repetido — o mesmo objeto costuma
    # ser citado várias vezes no mesmo texto.
    unicos = list(dict.fromkeys(a.upper() for a in achados))[:limite]
    return ", ".join(unicos)[:OBJETOS_MAX]


def derivar(linha: dict) -> dict:
    """Acrescenta as três derivações à linha já normalizada."""
    return {
        "tipo_demanda": tipo_demanda(linha.get("titulo"), linha.get("catalogo")),
        "categoria_diaadia": categoria_diaadia(linha.get("work_notes")),
        "objetos": objetos_citados(linha.get("descricao")),
    }
