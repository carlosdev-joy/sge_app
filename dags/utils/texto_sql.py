"""dags/utils/texto_sql.py — cortar texto pelo limite REAL da coluna.

`NVARCHAR(n)` conta unidades UTF-16, não caracteres Python: emoji fora do BMP
(🙂, 🔥) ocupa DUAS. Um `texto[:60]` passa no teste, cabe na cabeça de quem
escreveu e estoura no banco com Msg 8152 — no meio de um ciclo, derrubando a
gravação da tabela inteira naquele lote.

Este módulo existe porque a regra já tinha sido escrita uma vez, dentro de
`servicenow_sync`, e mesmo assim os cortes seguintes voltaram a usar `[:n]`.
Regra que mora em um lugar só não é reinventada errada no lugar seguinte.

⚠️ Não importa NADA de outros módulos de utils: `chamado_derivacoes` e
`servicenow_sync` importam daqui, e uma seta de volta fecharia o ciclo.
"""
from __future__ import annotations


def unidades_utf16(texto: str) -> int:
    """Quantas unidades NVARCHAR o texto ocupa."""
    return len((texto or "").encode("utf-16-le")) // 2


def cortar(texto, limite: int) -> str:
    """Corta no limite da coluna, COM reticência e sem partir um emoji.

    A reticência é obrigatória: truncar calado já mordeu neste repo (PR #161),
    e o leitor precisa saber que o texto continua no ServiceNow.
    """
    t = (texto or "").strip()
    if unidades_utf16(t) <= limite:
        return t
    alvo = limite - 1          # a reticência ocupa 1 unidade
    saida, total = [], 0
    # Iterar por caractere (code point) garante que um par substituto nunca é
    # cortado ao meio — o que geraria texto inválido no banco.
    for ch in t:
        custo = unidades_utf16(ch)
        if total + custo > alvo:
            break
        saida.append(ch)
        total += custo
    return "".join(saida) + "…"
