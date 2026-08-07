"""api/services/msg_texto.py — port das funções de TEXTO do card do Teams.

Gêmeo puro de `dags/utils/ds_teams.py` (087): interpolação de placeholders e a
precedência entre o que está escrito no nó e o que veio do modelo do catálogo.

Por que um port e não um import: `dags/` e `api/` são árvores separadas em
runtime (a API não tem o `dags/` no path, e o worker não tem o `api/`), e o
repo já resolve isso do mesmo jeito em `dependencias.py` e `malha_corrida.py` —
módulos gêmeos com teste de paridade. Aqui a paridade é ainda mais barata de
manter: **nenhuma destas funções toca o banco**, então o gêmeo é idêntico byte
a byte, sem a diferença de placeholder (`%s` × `?`) que separa os outros dois.

⚠️ O motivo de existir é a PRÉVIA da tela. Ela precisa renderizar pela mesma
regra do envio — uma prévia que monta o texto por outro caminho é uma promessa
que o Teams não cumpre, e o operador descobriria às 3h, com o card errado já
entregue.
"""
from __future__ import annotations

#: Os nomes que o editor oferece. `{ciclo}` é o rótulo humano da Decisão 74
#: ("ciclo de 04/08"), nunca o id.
PLACEHOLDERS_MALHA = ("malha", "data", "pipelines", "ciclo", "quantidade")


def interpolar(texto, mapa: dict) -> str:
    """Troca `{chave}` pelos valores do mapa.

    Placeholder DESCONHECIDO fica intacto de propósito: quem escreveu `{jobs}`
    achando que existe precisa ver `{jobs}` na prévia para descobrir o engano —
    apagá-lo silenciosamente entregaria uma frase com um buraco onde deveria
    haver informação. `None` vira string vazia (o valor existe e está vazio, que
    é diferente de não existir).
    """
    saida = str(texto or "")
    for chave, valor in (mapa or {}).items():
        saida = saida.replace("{" + str(chave) + "}", "" if valor is None else str(valor))
    return saida


def texto_da_notificacao(config: dict, template: dict | None, mapa: dict) -> tuple:
    """`(titulo, corpo)` já interpolados, na precedência do nó de Etapas.

    A mensagem escrita NO NÓ vence o corpo do modelo — o modelo é ponto de
    partida, não camisa de força, e quem ajustou o texto para uma malha
    específica não pode ver o ajuste sumir porque alguém editou o modelo
    compartilhado. Título segue a mesma regra.

    Sem nó, sem modelo e sem texto, devolve `(None, None)` e o chamador mantém
    a frase automática de sempre: configurar é opcional, e malha nenhuma fica
    muda por não ter sido configurada.
    """
    cfg = config or {}
    tpl = template or {}
    titulo = (str(cfg.get("titulo") or "").strip()
              or str(tpl.get("titulo") or "").strip())
    corpo = (str(cfg.get("mensagem") or "").strip()
             or str(tpl.get("corpo") or "").strip())
    return (interpolar(titulo, mapa) if titulo else None,
            interpolar(corpo, mapa) if corpo else None)


def contexto_exemplo(malha: str, membros) -> dict:
    """O mapa da PRÉVIA, com os membros REAIS da malha.

    Nomes inventados esconderiam justamente o caso que quebra: a malha de 40
    membros cujo `{pipelines}` estoura o limite da coluna de detalhe. O corte em
    10 é o mesmo que a guardiã aplica na emissão de verdade
    (`contexto_da_notificacao`) — se a prévia cortasse noutro ponto, ela
    mostraria uma frase que o Teams não recebe.

    A DATA é a de exemplo, e só ela: na emissão real vem do ciclo, e aqui não há
    ciclo nenhum para consultar. É o único valor da prévia que não é o de
    produção, e a tela diz isso ao lado.
    """
    nomes = [str(m) for m in (membros or [])]
    resumo = ", ".join(nomes[:10])
    if len(nomes) > 10:
        resumo += f" (+{len(nomes) - 10})"
    return {"malha": malha, "data": "2026-08-04", "pipelines": resumo,
            "quantidade": len(nomes), "ciclo": "ciclo de 04/08"}
