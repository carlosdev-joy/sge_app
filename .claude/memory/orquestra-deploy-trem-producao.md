---
name: orquestra-deploy-trem-producao
description: 🏁 MARCO 2026-08-12 — o trem inteiro do Orquestra SUBIU PARA PRODUÇÃO e está funcionando; corrida de malha LIGADA (malha_corrida_ativa=1); encerra ~10 pendências de deploy que se arrastavam desde 2026-08-01
metadata: 
  node_type: memory
  type: project
  originSessionId: 952e78f2-488a-4865-83e8-88eb5dbfadc9
  modified: 2026-08-13T02:39:05.748Z
---

🏁 **MARCO: em 2026-08-12 o usuário confirmou que o trem inteiro foi para
produção e está funcionando** — o [[orquestra-sge-app]] em produção deixou de
estar defasado da `main`.

## O que subiu

**Tudo que estava mergeado e pendente**, acumulado desde a última entrega
validada em produção (2026-08-01, Supervisão DataStage F1–F7 + Caixa Seguro):

- **Corrida/ciclo de malha F1–F12** (PRs #277–#288) — ver [[orquestra-spec-corrida-malha]]
- **Malha componentes F10–F15** (PRs #250–#257) — ver [[orquestra-malha-componentes]]
- **Motor de dependências F1–F9** (retomada F2–F6) — ver [[orquestra-dependencias-pipelines]]
- **Nó Aguarde F1–F4** (PRs #231–#235) — ver [[orquestra-no-aguarde]]
- **Malha data única F1–F5 + HOLD** (PR #272→#273) — ver [[orquestra-malha-data-unica]]
- **Republicar pipelines da malha** (PR #272) — ver [[orquestra-republicar-malha]]
- **Operação no nível de etapa F1–F5** (PRs #261–#270) — ver [[orquestra-reexecucao-nivel-etapa]]
- **Ajustes de malha + inventário de DAGs** (PRs #293–#296) — ver [[orquestra-ajustes-malha-inventario]]
- **Ícones do canvas** (#237/#238) e orientação do diagrama (#249) — ver [[orquestra-icones-canvas]]
- **Grafia de `pipeline_name`** (#236) — ver [[orquestra-grafia-pipeline-name]]
- **Cópia de dados** (PRs #140–#162) — ver [[orquestra-copia-dados]]

**Migrations:** a faixa **067 até 087** (21 no total), todas aplicadas.

## ⚡ A corrida de malha está LIGADA

`malha_corrida_ativa = 1`. O ciclo abre e fecha, o ODATE é carimbado uma vez e
herdado, o card e o painel mostram progresso real. Os três pré-requisitos que a
[[orquestra-spec-corrida-malha]] listava (suíte com `ORQ_TEST_MSSQL_PASSWORD`,
`GRANT SELECT` em `etl_malha_no` para os dois logins, desvio de relógio worker ×
banco) deixaram de ser porteiros — a chave foi virada e o sistema está de pé.

## O que NÃO foi confirmado nesta sessão

Honestidade sobre o limite do que sei: o usuário confirmou **"foi para produção e
está funcionando"** e que o interruptor está em 1. Ele **não** relatou os smokes
formais item a item. Então continuam sem confirmação explícita:

- smoke §8.1 do [[orquestra-no-aguarde]] (o **passo 8** é o crítico: política
  tolerante + perna falhando = limpeza roda **E** pipeline vermelho);
- `docs/smoke-malha-componentes.md` e o smoke §7 do motor;
- as pendências de **infra** específicas da [[orquestra-copia-dados]] (rebuild da
  imagem do Airflow com bcp/ODBC, `ORQUESTRA_CONN_KEY` no `.env`, "Migrar do
  Airflow" em Admin→Conexões, `ALTER COLUMN` da tabela do job) — o deploy do
  código não resolve nenhuma delas sozinho.

Se for preciso afirmar qualquer um desses como feito, **perguntar antes** — não
deduzir do "está funcionando".

## Por que isso importa daqui para frente

Produção e `main` estão alinhadas até **`c1eb65b` (PR #300)**. A próxima entrega
parte de base limpa: o "trem" acabou. Toda memória que ainda disser "falta o
deploy" para algo desta lista está desatualizada — o marco é aqui.

Regra da casa que continua valendo: [[orquestra-dev-testa-producao-manda]].
