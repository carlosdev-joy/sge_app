# Spec: Card 3 do PIO lê a foto diária — Orquestra
Data: 2026-10-28 · Status: em execução (pedido "segue processo do card 3"; mesmo padrão dos Cards 1 e 2)

## 1. Visão
O Card 3 do Workflow de Busca & Vendas (**Assinadas e Pagas**, `paid`) hoje lê a carga legada
(`ASSINA_PAGA`). A equipe de dados publicou a foto diária (`AGG/FAT/CTL_ORQ_CARD03_*`, DMDB41,
Fabric 07:30). O card, a lista, o Resumo, o Histórico e o Enviar passam a ler essa foto, igual aos
Cards 1 (PR #525) e 2 (PR #528): mesma data+lote em número e lista, zero ≠ "não consegui ler".

Fonte: documento "CARD 3 — Propostas assinadas e pagas" (28/10/2026) colado pelo usuário.

## 2. Escopo
**IN:** `GET /pio/card3/resumo` (AGG) e `/pio/card3/propostas` (FAT, paginada); card inline e painel
Workflow com prêmio + quantidade da foto; lista/Resumo/Histórico/Enviar com a mesma foto;
migration de versão 2.6.4; testes; release note.
**OUT:** os demais 5 cards e a busca global (legado, `pio.py` intocado); Cards 1 e 2 sem mudança de
comportamento; escrita nas tabelas, pipeline, retenção, alertas (frente de dados); sub-filtro de
pagamento; deploy em produção e merge (autorização própria); qualquer coisa do `develop`.

## 3. Telas (impeccable)
Sem tela nova e sem mudança de ordem/layout. Muda só a fonte do valor do card "Assinadas e Pagas".
Reaproveita `Card1Valor`, a lista e os diálogos com o contexto genérico `foto`. Diferença de
conteúdo: a proposta já está **paga**, então não existe "dias pendente" — a lista não mostra o
"⏱️ N dias" no Card 3 (`daysInPending = 0`). Estados: `…`, `—`, zero real, detalhe fora da retenção.
Tokens `canvas/panel/edge/ink`, claro+escuro, sem cor nova.

## 4. Arquitetura
- Back: `api/routers/pio_card3.py` (cópia do padrão do Card 2, tabelas `*_ORQ_CARD03_*`), registrado
  em `api/main.py`. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; quantidade =
  `SUM(QTD_REGISTROS)`; **não reaplica `YEAR(GETDATE())`** sobre foto histórica; não soma datas.
- Front: `STATUS_CARD3 = "paid"` em `card1Foto.ts`; `lib/pioCard3.ts` (hooks); `InlineWorkflow` e
  `ProposalWorkflowSheet` escolhem resumo/foto por status (mapa, no lugar da terceira cadeia de ternários).
- Decisão: continuar sem fábrica comum (Card 1 em validação); débito registrado.

## 5. Modelo de dados
Sem tabela nova no Orquestra. Migration `144_versao_pio_card3_foto.sql` (idempotente; só versão
2.6.4 + `app_version`/`app_release_name`).

## 6. Fases (uma PR, `feat: Card 3 do PIO lê a foto diária`)
F1 front (contrato simulado, Playwright claro/escuro) → F2 API + testes → F3 migration, release note,
registro. Validação: pytest vs. 8 falhas pré-existentes, `tsc -b`, eslint, build, `dist/` por último,
revisão adversarial antes da PR.

## 7. Riscos
| # | Risco | Mitigação |
|---|-------|-----------|
| 1 | Volume ≈ 689 mil linhas/foto: `ORDER BY DTH_VENDA, COD_PROPOSTA, ID_FOTO` e busca livre (`LIKE`) varrem a FAT inteira do dia; páginas profundas custam mais (a FAT só tem índice em `DTA_MOVIMENTO`) | Sempre filtra data+lote; página ≤ 200; registrar na release note e pedir à frente de dados índice `(DTA_MOVIMENTO, LOTE_ID, DTH_VENDA, COD_PROPOSTA, ID_FOTO)`; medir no DMDB41 antes do deploy |
| 2 | Sem `SELECT` do login nas 3 tabelas | Card mostra `—`, nunca zero; preflight |
| 3 | Virada do ano: a query volta a poucas linhas (e foto vazia é bloqueada pela carga) | Não vira zero falso: sem foto nova o card mostra a última publicada, com a data no tooltip |
| 4 | Dados pessoais (CPF, telefone, e-mail) no detalhe | Mesma permissão `tela_caixa_seguro`, página ≤ 200, nada em log |
| 5 | "contratos" × linhas (688.952 propostas distintas em 689.001 linhas; 22 combinações repetidas) | Quantidade = linhas, dito na release note |

## 8. Smoke pós-deploy
a) Preflight no DMDB41 (um lote PUBLICADO; AGG × FAT conciliam; `SELECT` do login). b) Card "Assinadas
e Pagas" = prêmio (≈ R$ 411,9 mi) e quantidade (≈ 689 mil) da consulta 2 na mesma data. c) Lista: total
= quantidade; paginação sem repetir; tempo de resposta aceitável. d) Detalhe sem "dias pendente".
e) Resumo/Enviar usam o contato da foto. f) Cards 1, 2 e 4–8 e a busca global inalterados. g) Sem
permissão/tabela: `—`.

## 9. Pendências
Rótulo do `SO`; "contrato" × linha; índice na FAT; alerta de falha e identidade operacional (dados).
