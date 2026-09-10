---
name: orquestra-republicar-malha
description: "Botão \"Republicar pipelines\" da tela Malha — regera as DAGs de todos os membros para os vínculos desenhados valerem; PR #272, migration 080; ✅ EM PRODUÇÃO desde 2026-08-12"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80c9c0f8-d96b-4823-bfbd-f3a91475f9ad
  modified: 2026-08-13T02:40:33.317Z
---

Gesto novo do [[orquestra-sge-app]]: com a malha aberta (modo Montagem), o
botão **Republicar pipelines** regera as DAGs de TODOS os membros ATIVOS, para
que os vínculos desenhados (aresta, Aguarde, agendamento do Início) passem a
valer no Airflow. Nasce de [[orquestra-malha-componentes]] — desenhar grava a
dependência na hora, mas a DAG publicada continua a ANTERIOR até ser regerada.

🏁 **PR #272 MERGEADA na main (2026-08-04, merge b2d3bbd)** — 11 commits,
34 arquivos: carrega também a linha de progresso do canvas e as F1–F5 da
[[orquestra-malha-data-unica]]. ✅ **EM PRODUÇÃO desde 2026-08-12** — ver
[[orquestra-deploy-trem-producao]].

## Desenho (nenhum executor novo)
`POST /malhas/{m}/republicar` (dry_run no body, perm `acao_executar`): marca os
membros ativos como pendentes e dispara **UMA** execução da `etl_dag_factory`,
que passou a aceitar **lista de alvos** em `conf["pipelines"]` + `escopo_rotulo`
— mesma semântica do `conf["pipeline_name"]` do botão por pipeline. Membro
INATIVO não entra (a SP filtra `active=1`) e vem em `ignorados` com motivo.
Migration **080**: `modo_verificacao` em `etl_dag_pendente` — depois do run o
reconciliador confere cada membro no Airflow sem notificar sucesso.

## ⚠️ O defeito que só a EXECUÇÃO mostrou (dev)
Primeira versão disparava a factory sem lista: o run ficou **FAILED** mesmo
tendo gerado os 3 membros, porque um pipeline **de fora da malha** (pendente e
sem etapas) entrou no lote da `sp_etl_pipelines_pendentes_criar`, que é
**GLOBAL**. Gesto certo aparecendo vermelho na tela de Publicação. Com a lista,
pendência de terceiro vira **aviso**. **Lição: a SP de pendentes é global — todo
gesto que dispara a factory carrega o lote inteiro junto, e o escopo do run
precisa ser dito no conf para o log não mentir.**

## Achados da revisão adversarial (5, todos fechados)
1. **Import error sem gating** — DAG que o Airflow não importa deixa a versão
   ANTERIOR ativa; a factory zerava o carimbo e a tela dizia "publicado e em
   dia", mudo. → fila de verificação pós-run + carimbo REACESO no erro.
2. **Deploy de `api/` sem `dags/`** (o deploy.sh pergunta separado) faria o
   botão virar **no-op VERDE**: factory antiga ignora `conf["pipelines"]` e
   fecha SUCCESS com lote vazio. → a API volta a marcar `dag_criada=0` (com
   desfazer se o disparo falhar). **Lição: contrato novo entre as árvores
   `api/` e `dags/` precisa funcionar com a árvore velha do outro lado.**
3. **`dag_criada=0` durante o run** era lido como "nunca publicado" (badge e
   fila mentindo) → a existência da DAG passou a vir do **Airflow**; chip e
   contador usam só o carimbo da 073.
4. **Aresta desenhada DURANTE a publicação** não deixava carimbo (o
   `WHERE dag_criada = 1` de `_ligar_dag_config_pendente` falhava) → dependência
   sumia da DAG em silêncio. → `OR EXISTS` na fila do reconciliador.
5. Lote vazio fechava SUCCESS sem cobrar os alvos pedidos.

## Deploy — foi no MESMO trem (2026-08-12, feito)
Ver [[orquestra-dependencias-pipelines]]: migrations **067 + 070–080** (12) na
etapa 6c + **dags/ + api/ + front juntos**. Conferência da 080:
`COL_LENGTH('dbo.etl_dag_pendente','modo_verificacao')` não-NULL.
Smoke §5b em `docs/smoke-malha-componentes.md`.
⏳ **Não reproduzido ao vivo** (só teste unitário): DAG com erro de CARGA →
notificação de erro + chip ⟳ voltando a acender.

## Validação
pytest **1931 passed** (baseline 1899; +32), mesmas 5 falhas pré-existentes;
tsc/eslint limpos; dist rebuildada. Cenários EXECUTADOS no dev (factory
despausada só para o teste e repausada; fixtures SMOKE_F12 restauradas):
vínculo novo → carimbo acende → republicar → run SUCCESS com escopo
`Malha SMOKE_F12 (3 pipeline(s))` → `schedule=None # dependente` no arquivo →
carimbos zerados; membro inativo em `ignorados`; fila com `modo_verificacao=1`
e ZERO notificações de sucesso.
