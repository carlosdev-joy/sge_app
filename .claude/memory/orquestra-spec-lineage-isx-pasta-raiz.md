---
name: orquestra-spec-lineage-isx-pasta-raiz
description: "Spec de correção do lineage ISX: jobs fora de Jobs/ (busca pela raiz do projeto + pasta informada); docs/spec-lineage-isx-pasta-raiz.md; 📋 RASCUNHO 2026-09-08 aguardando aprovação; documento de origem no sshd-amostra do DEV (sem senhas, mas com host real — não entra no repo)"
metadata:
  type: project
  originSessionId: 627a18b0-5a47-44d0-b15e-ca31a4caf9a1
  modified: 2026-09-08T14:22:27.340Z
---

Pedido do usuário em 2026-09-08 ("precisamos agora fazer algumas correções para importar
o isx corretamente segue a spec"): documento `/dados/bi/2026-09-08-lineage-isx-bfs-raiz-alternativa.md`
no `sshd-amostra` do DEV (lido por `docker exec … cat`, NÃO copiado para o repo). Origem:
o primeiro job pedido em produção (projeto BI_CVP) mora numa pasta irmã de `Jobs/` e a
busca em largura do engine começa fixa em `Jobs/` → "não encontrado".

Spec da casa em `docs/spec-lineage-isx-pasta-raiz.md` (2 fases: F1 engine/API/DAG/
harness/smoke; F2 tela + docs). **Aguarda aprovação** antes de codar.

## O que o documento NÃO viu (validado contra o código)
- `validar_pasta` exige `Jobs` como 1º componente (isx_engine.py:172) e é usada pelo
  path rápido (`api_id_de`), pelo istool (`caminhos_istool`) e pela pasta conhecida → só
  mudar o BFS deixaria 422 logo depois de achar; o "workaround por SQL" do documento
  (§6, `UPDATE ds_folder_path`/`INSERT status='pendente'`) NÃO funciona hoje.
- Tetos encadeados: `LOCALIZAR_MAX_S` 30 ↔ router `_TETO_LOCALIZAR_S` 35 ↔
  `_TETO_EXTRAIR_S` 60 (busca + export no mesmo teto) ↔ DAG `TIMEOUT_JOB_S` 90 ↔ textos
  do front ("até 60 s", `POR_STATUS[504]`).
- `ui/js/app.js` não existe: o front é `components/governanca/isx/*` (F4).
- 504 do executor perde o `meta` (pasta achada) — o `e.meta` só cobre `ISXError`.

## Desenho proposto
BFS pela raiz com `Jobs` PRIMEIRO na fila; `pasta_inicial`; `ds_folder_path` no corpo
do extrair e na query do localizar (validado por `validar_pasta` sem `Jobs`, ≤ 500);
pasta informada errada → busca só na subárvore do 1º componente → 404 "abaixo de";
teto por situação (65 s com pasta, 125 s buscando); busca em etapa própria no router
para o 504 do export ainda persistir a pasta; DAG 150 s; campo "Pasta no DataStage" em
`PainelJobIsx` só sem pasta conhecida; harness DEV com raiz de `BI_VIDA` + `JobForaDeJobs`
em `BU02 - Base Amostra\Sub`; smoke item n.

Ver [[orquestra-spec-lineage-isx]].
