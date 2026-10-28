# Spec: Card 2 do PIO lê a foto diária — Orquestra
Data: 2026-10-28 · Status: rascunho (aguarda aprovação)

## 1. Visão
O Card 2 do Workflow de Busca & Vendas (**Pendentes de Pagamento**, `awaiting_payment`) hoje lê a
carga legada (`PIO_AGG` / `PIO_PROPOSTA_PEND_PGTO_DET`). A equipe de dados publicou a foto diária
do Card 2 no DMDB41 (`AGG/FAT/CTL_ORQ_CARD02_*`, carga Fabric 07:30). Esta feature faz o card, a
lista, o Resumo do Seguro e o Enviar lerem essa foto, **exatamente no padrão do Card 1** (PR #525):
mesma data+lote em número e lista, aviso de foto desatualizada, zero ≠ "não consegui ler".

Fonte: documento "CARD 2 — Propostas assinadas pendentes de pagamento" (28/10/2026), colado pelo
usuário. Padrão de referência: `docs/release-notes/pio-card1-foto.md`, `api/routers/pio_card1.py`.

## 2. Escopo
**IN:**
- `GET /pio/card2/resumo` (AGG) e `GET /pio/card2/propostas` (FAT), atrás de `tela_caixa_seguro`.
- Card "Pendentes de Pagamento" (inline e painel Workflow) com prêmio + quantidade da foto.
- Lista, Resumo do Seguro, Histórico e Enviar do Card 2 com a mesma foto (data+lote).
- Migration de versão (2.6.3) e testes (API, front puro, migration).
- Fixture de simulação para teste local, só em banco descartável.

**OUT (explícito):**
- Os outros 6 cards e a busca global: seguem no legado (`pio.py` intocado). Duas fontes até migrar o resto.
- Card 1: **nenhuma alteração de comportamento** (está em produção aguardando validação do solicitante).
- Escrita nas tabelas, pipeline Fabric, retenção, alertas e identidade operacional (são da outra frente).
- Sub-filtro por forma de pagamento / sub-status de pagamento: a foto não traz esses campos (igual ao Card 1).
- Deploy em produção e merge: só com autorização própria do usuário.
- Qualquer coisa do `develop`.

## 3. Telas (impeccable)
Sem tela nova e sem mudança de layout/ordem: o Card 2 já existe na sequência (`SEQUENCIA_WORKFLOW`).
Muda só a **fonte** do valor. Reaproveita `Card1Valor` (generalizado), a lista, `ProposalDetailDialog`,
`ProposalHistoryDialog` e o Enviar com o contexto de foto do Card 1. Estados já cobertos:
carregando `…`, indisponível `—`, zero real `0`, foto desatualizada (aviso com data), detalhe
indisponível (fato com 24 meses, agregado 36). Tokens `canvas/panel/edge/ink`, claro+escuro.
A fase de front passa por `impeccable` (critique/audit) + Playwright nos dois temas antes do backend
ser dado como fechado, e por regra não reordena nenhum objeto.

## 4. Arquitetura proposta
- Back: `api/routers/pio_card2.py` (registrar em `api/main.py`). Mesmo contrato do Card 1:
  `{disponivel, referencia, atualizacao, lote_id, desatualizado, dias_defasagem, premio_total, quantidade, grupos}`
  e página `{total, limite, offset, itens, detalhe_disponivel}`. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do
  CTL `PUBLICADO`. Quantidade = `SUM(QTD_REGISTROS)`; prêmio em `Decimal`; sem GETDATE/D-30; telefone `int`.
- **Reuso sem tocar no Card 1:** `pio_card2.py` importa os helpers puros de `pio_card1.py`
  (`_texto`, `_dinheiro`, `_telefone`, `_idade`, `_item`) e declara só `AGG/FAT/CTL` e as rotas.
  Alternativa descartada: extrair uma fábrica comum agora (mexe em código do Card 1 em validação);
  fica como débito para quando os demais cards migrarem.
- Front: `lib/card2Foto.ts` (puro, testável no node) + `lib/pioCard2.ts` (hooks react-query).
  Generalizar `Card1Valor` → componente por card e o gancho `listaDoCard`/`FotoCard1` para aceitar o
  card pela configuração, **sem mudar o resultado do Card 1** (testes do Card 1 passam sem alteração).
  Integrar em `InlineWorkflow.tsx` e `ProposalWorkflowSheet.tsx` (os dois lugares que hoje têm `STATUS_CARD1`).
- Dados: lê `dbo.AGG/FAT/CTL_ORQ_CARD02_*` (DMDB41, via `MSSQL_CONN_STR`); a aplicação nunca escreve.
- Decisões: `DIAS_PENDENTE = DATEDIFF(day, DTH_VENDA, DTA_MOVIMENTO)` (na data da foto, como no Card 1).

## 5. Modelo de dados
Sem tabela nova no Orquestra. Migration `143_versao_pio_card2_foto.sql` (idempotente, só
`etl_versao_ferramenta` + `app_version`/`app_release_name`): versão **2.6.3**, título
"Card 2 do PIO lê a foto diária". Numeração a reconciliar com o `develop` (migrate.py controla por nome).
Estrutura das tabelas (DDL do documento): 28 colunas da query + `ID_FOTO`, `DTA_MOVIMENTO`, `LOTE_ID`,
`DTH_CARGA`; collation `Latin1_General_CI_AS`; STG não é lida.

## 6. Fases
### F1 — Front com contrato simulado
- Entregável: `card2Foto.ts`, `pioCard2.ts`, `Card1Valor` generalizado, integração nas duas telas, atrás do contrato da seção 4 com mock tipado.
- Aceite: Card 2 mostra `…` / `—` / valor / aviso de foto antiga; Card 1 idêntico ao de hoje; claro+escuro+mobile sem quebra.
- Validação: `tsc -b`, eslint (zero novo vs. main), build, `dist/` por último, `impeccable` + Playwright.
- Revisão adversarial antes da PR.
### F2 — API
- Entregável: `pio_card2.py`, registro em `main.py`, testes espelhando `test_pio_card1_api.py`.
- Aceite: prêmio/quantidade = consulta 2 do repasse; total da lista = quantidade; lote não publicado nunca aparece; tabela ausente → `disponivel:false`; busca por proposta/CPF/agência/matrícula.
- Validação: pytest vs. baseline (8 falhas pré-existentes), T-SQL em banco descartável com fixture.
### F3 — Integração, versão e release notes
- Troca do mock pelo real, migration 143, `docs/release-notes/pio-card2-foto.md` (deploy/smoke/rollback), memória.
- Aceite: migration roda 2×; smoke com contrato real no Playwright; registro em `/srv/segundo-cerebro/registros/orquestra/`.
Uma única PR (≈ o tamanho da #525), `feat: Card 2 do PIO lê a foto diária`.

## 7. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Sem `SELECT` do login de produção nas 3 tabelas do Card 2 | Card mostra `—` | Preflight de leitura no deploy (como no Card 1); degrada para `—`, nunca zero |
| 2 | Somar datas ou ler lote não publicado | Venda contada 2× | Toda leitura filtra data+lote do CTL; teste cobre lote ABERTO/SUBSTITUIDO |
| 3 | Número do card muda vs. legado (33.463 linhas na foto × ~22.500 do legado) | Solicitante estranha | Explicar na release note: foto tem CO+SO, JOINs multiplicam linhas; confirmar com o solicitante antes do deploy |
| 4 | Generalizar `Card1Valor`/`listaDoCard` altera o Card 1 | Regressão em card já em produção | Testes do Card 1 sem alteração; diff do Card 1 revisado linha a linha |
| 5 | Dados pessoais (CPF, telefone, e-mail) no detalhe | LGPD | Mesma permissão `tela_caixa_seguro`, página ≤ 200 linhas, nada em log |
| 6 | Migration 143 × numeração do `develop` | Conflito na promoção | Nomes distintos; registrado na release note |

## 8. Smoke pós-deploy
a) Preflight no DMDB41: um lote PUBLICADO na data; AGG × FAT conciliam; `SELECT` do login nas 3 tabelas.
b) Card "Pendentes de Pagamento" mostra prêmio e quantidade = consulta 2 do repasse (mesma data).
c) Abrir o card: total da lista = quantidade do card; paginação sem repetir linha.
d) Foto com data ≠ hoje mostra o aviso com a data; sem foto mostra `0`/vazio explicado, não erro.
e) Resumo do Seguro e Enviar do Card 2 usam o contato da foto; "Contato não informado" quando ausente.
f) Cards 1 e 3–8 e a busca global inalterados.
g) Sem permissão/tabela: card `—`, tela não quebra.

## 9. Pendências e decisões em aberto
1. **Regra da assinatura:** o cabeçalho da query diz `'PE'`, o código usa `CO`/`SO`, e o catálogo (`pio-fonte-de-dados.md`) diz `CO`. O que é `SO` e o Card 2 pode conter propostas que o Card 3 (Assinadas e Pagas) também conta? (`STA_PAGO` separa os dois.)
2. **"Dias pendente"** no Card 2 = dias desde a venda (`DTH_VENDA`), como no Card 1? Ou desde `DTH_ALTERACAO`?
3. Como no Card 1, "Usuário" e rodapé do Resumo do Seguro saem também no Card 2? (no Card 1 saíram por pedido do RITM.)
4. O documento diz "front adiado até nova liberação"; esta spec trata o pedido de hoje como a liberação.
5. Contrato = ? (pergunta do Card 1 ainda aberta) — vale o mesmo rótulo "contratos" na quantidade?
