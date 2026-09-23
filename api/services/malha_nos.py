"""
api/services/malha_nos.py — expansão dos nós especiais da malha, vista da API
(F10, desenho docs/malha-componentes-desenho.md §3.2).

PORT PURO de dags/utils/malha_nos.py — **o canônico é o de dags/**: quem mudar
a regra muda lá primeiro e espelha aqui. A cópia existe pelo mesmo motivo de
api/services/data_referencia.py e api/services/dependencias.py: api/ e dags/
são árvores de deploy separadas (o container da API não embarca dags/), e um
import cruzado quebraria no primeiro deploy parcial. A PARIDADE é garantida por
teste (tests/test_malha_nos_expandir.py): a matriz de expansão dos dois módulos
tem de ser IDÊNTICA — divergir faz a suíte falhar antes de chegar em produção.

Usado pelo GET do detalhe da malha (o `upstream` por nó que o front consome sem
reimplementar a expansão) e, na F11, pelo compilador do Aguarde. Módulo PURO:
sem banco, sem FastAPI — este port não tem SQL, então o GOTCHA do placeholder
(? em api/, %s em dags/) não se aplica aqui; vale a paridade semântica.
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
