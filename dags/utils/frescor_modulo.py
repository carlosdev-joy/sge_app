"""dags/utils/frescor_modulo.py — acusa módulo servido de cache velho.

O problema que isto resolve tem sintoma nenhum. O arquivo da DAG (`.py` na
raiz de `dags/`) é reprocessado pelo DagBag a cada execução, então mudança
nele entra sozinha. Já `from utils.x import y` é import comum: se o módulo
está em `sys.modules` do processo do worker Celery, o import devolve a versão
EM MEMÓRIA e os forks herdam esse cache. O arquivo muda no disco e ninguém
consulta de novo.

O estrago é mudo — task VERDE, ciclo OK, efeito nenhum. Mordeu em 13/08 com a
PR #312, que mexia só em `dags/utils/`: três ciclos depois do deploy gravando
pelo código antigo, com log impecável. O `deploy.sh` passou a avisar (PR #313),
mas aviso no deploy só alcança quem estava olhando a tela naquele momento.

Aqui a checagem é feita por quem executa: cada módulo carimba o instante em
que entrou em memória, e a DAG — que sempre roda fresca — compara esse
carimbo com o `mtime` do arquivo em disco. Arquivo mais novo que o import
significa código velho rodando, e o ciclo passa a DIZER isso.

Uso, no topo de cada módulo auxiliar:

    from utils.frescor_modulo import carimbar
    carimbar(__file__)

E na DAG, antes do trabalho:

    from utils.frescor_modulo import conferir
    for aviso in conferir():
        print(aviso)

⚠️ Módulo carregado de uma versão ANTERIOR a esta guarda não tem carimbo — e
é justamente o caso que interessa. Por isso `conferir()` também acusa módulo
esperado e ausente do registro: no worker atualizado, todo módulo listado
carimba; a falta do carimbo é, ela própria, o sinal.
"""
from __future__ import annotations

import os
import time

# nome do módulo → {"arquivo", "importado_em", "mtime_no_import"}
_REGISTRO: dict[str, dict] = {}

# Módulos que DEVEM carimbar. Um nome aqui sem carimbo no registro significa
# que o worker está servindo uma versão anterior à guarda.
ESPERADOS = ("utils.servicenow_sync", "utils.chamado_derivacoes",
             "utils.triagem_ia")


def carimbar(caminho_arquivo: str) -> None:
    """Registra quando este módulo entrou em memória. Chame no import."""
    try:
        nome = _nome_do_modulo(caminho_arquivo)
        _REGISTRO[nome] = {
            "arquivo": caminho_arquivo,
            "importado_em": time.time(),
            "mtime_no_import": os.path.getmtime(caminho_arquivo),
        }
    except Exception:
        # Uma guarda de diagnóstico jamais pode derrubar o import do módulo
        # que ela protege — seria trocar um defeito mudo por um barulhento no
        # lugar errado.
        pass


def _nome_do_modulo(caminho_arquivo: str) -> str:
    base = os.path.basename(caminho_arquivo)
    return f"utils.{os.path.splitext(base)[0]}"


def conferir() -> list[str]:
    """Avisos sobre módulos desatualizados em memória. Lista vazia = tudo em dia."""
    avisos: list[str] = []
    for nome in ESPERADOS:
        marca = _REGISTRO.get(nome)
        if marca is None:
            # Sem carimbo: ou o módulo não foi importado neste processo (então
            # não há o que conferir), ou veio de uma versão anterior à guarda.
            # A segunda hipótese é a perigosa, e é a que precisa aparecer.
            import sys
            if nome in sys.modules:
                avisos.append(
                    f"[CACHE] {nome} está em memória SEM carimbo de frescor: "
                    f"o worker provavelmente serve uma versão anterior a esta. "
                    f"Reinicie o worker do Airflow.")
            continue
        try:
            mtime_atual = os.path.getmtime(marca["arquivo"])
        except OSError:
            continue
        if mtime_atual > marca["mtime_no_import"] + 1:  # 1s de folga p/ rsync
            idade = int(mtime_atual - marca["importado_em"])
            avisos.append(
                f"[CACHE] {nome} mudou no disco {idade}s DEPOIS de ter sido "
                f"carregado — este ciclo está rodando o código antigo. "
                f"Reinicie o worker do Airflow.")
    return avisos
