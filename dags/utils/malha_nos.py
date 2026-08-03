"""
dags/utils/malha_nos.py — expansão dos nós especiais da malha (F10, desenho
docs/malha-componentes-desenho.md §3.2).

O Aguarde é JUNÇÃO PURA: em runtime ele NÃO existe — ele compila para linhas
normais da 067 (etl_pipeline_dependencia). Este módulo é a ÚNICA autoridade da
expansão: dado o desenho (nós + arestas de nó), responde

  • por nó: `upstream` (todos os pipelines alcançáveis para TRÁS através de
    arestas, expandindo nós intermediários transitivamente por BFS — o
    aguarde→aguarde do §2.1) e `saidas_pipeline` (os pipelines ligados
    diretamente na saída do nó);
  • o conjunto compilado da malha: {(dependente, predecessor, no_id), ...} —
    para cada Aguarde, cada saída-pipeline D depende de cada P ∈ upstream
    (a explosão N×M do §3.1, assinada com o id do nó).

Consumidores: o compilador da API (F11 — via o PORT api/services/malha_nos.py,
com teste de PARIDADE no precedente de data_referencia/dependencias) e a
guardiã (F14 — importa ESTE módulo direto, paridade por identidade de objeto,
como a F4 fez). O GET do detalhe da malha devolve o upstream calculado AQUI —
o front NUNCA reimplementa a expansão (uma autoridade só, a regra que salvou o
texto do ciclo na F8).

Módulo PURO: zero banco, zero Airflow. Testável sozinho. A GRAMÁTICA (§2.1)
não é validada aqui — é responsabilidade da API no gesto; este módulo apenas
expande o desenho que receber, sem travar em entrada malformada (ciclo entre
nós não faz o BFS pendurar: `visitados` é global à busca).
"""
from __future__ import annotations


def expandir(nos, arestas) -> dict:
    """Expande o desenho dos nós de uma malha.

    Entrada:
      nos     — iterável de dicts {"id": int, "tipo": str}
                (tipo: 'inicio' | 'aguarde' | 'notificacao' | 'fim')
      arestas — iterável de dicts com as chaves da etl_malha_aresta:
                {"origem_no" | "origem_pipeline", "destino_no" | "destino_pipeline"}
                (chave ausente conta como None — cada ponta é nó XOR pipeline)

    Saída:
      {"nos": {id: {"upstream": set[str], "saidas_pipeline": set[str]}},
       "dependencias": {(dependente, predecessor, no_id), ...}}

    Regras (§3.2): upstream expande nó→nó por BFS (aguardes encadeados somam o
    upstream transitivo); nó fora do grafo = sets vazios; SÓ Aguardes produzem
    dependências compiladas — Início planta agendamento (F13) e Notificação/Fim
    são observadores da guardiã (F14), nenhum deles vira linha na 067.

    Comparação de pipelines é pela grafia recebida — quem chama canoniza ANTES
    (regra da PR #236: a API grava sempre a grafia registrada em etl_pipeline).
    """
    # Índices do grafo: entradas e saídas por nó.
    entradas: dict = {}     # no_id -> [aresta, ...] (arestas com destino_no == id)
    saidas_pipe: dict = {}  # no_id -> set[pipeline] (saídas diretas para pipeline)
    for a in arestas:
        dno = a.get("destino_no")
        if dno is not None:
            entradas.setdefault(dno, []).append(a)
        ono = a.get("origem_no")
        if ono is not None and a.get("destino_pipeline") is not None:
            saidas_pipe.setdefault(ono, set()).add(a["destino_pipeline"])

    def _upstream(no_id) -> set:
        """Pipelines alcançáveis para trás a partir do nó, através de nós.

        BFS com `visitados` global à busca: ciclo entre nós (entrada malformada
        — a API recusa no gesto) não pendura, e diamante não re-expande.
        """
        vistos, fila, pipes = set(), [no_id], set()
        while fila:
            atual = fila.pop(0)
            if atual in vistos:
                continue
            vistos.add(atual)
            for aresta in entradas.get(atual, ()):
                if aresta.get("origem_pipeline") is not None:
                    pipes.add(aresta["origem_pipeline"])
                elif aresta.get("origem_no") is not None:
                    fila.append(aresta["origem_no"])
        return pipes

    resultado_nos: dict = {}
    dependencias: set = set()
    for no in nos:
        no_id = no["id"]
        up = _upstream(no_id)
        sp = set(saidas_pipe.get(no_id, ()))
        resultado_nos[no_id] = {"upstream": up, "saidas_pipeline": sp}
        # Só o Aguarde compila: N entradas × M saídas viram N×M linhas da 067,
        # cada uma assinada com o id do nó (proveniência — Decisão 1).
        if (no.get("tipo") or "").strip().lower() == "aguarde":
            for dependente in sp:
                for predecessor in up:
                    dependencias.add((dependente, predecessor, no_id))
    return {"nos": resultado_nos, "dependencias": dependencias}
