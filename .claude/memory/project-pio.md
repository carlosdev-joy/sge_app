---
name: project-pio
description: "PIO — a carga que alimenta os 8 cards do Workflow em Busca & Vendas; EM PRODUÇÃO desde 2026-09-01, doc em docs/pio-fonte-de-dados.md"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8a380743-1bf5-4253-ace6-207c3d764c4b
  modified: 2026-09-02T01:08:31.105Z
---

**PIO** é a carga de propostas comerciais de seguros que dá o número dos cards do
Workflow em Busca & Vendas ([[orquestra-caixa-seguro-poc]]).

📄 **O conteúdo vive no repo:** `docs/pio-fonte-de-dados.md` — caminho do dado,
catálogo dos 8 cards, dicionário das tabelas, o de-para campo da tela × coluna, e
as consultas de conferência da carga. Não duplicar aqui; esta memória é o estado
e os gotchas. Há também uma página do de-para:
https://claude.ai/code/artifact/9f6dd8ab-e063-4104-86e0-f2799ec39fb3

## 🏁 Estado: EM PRODUÇÃO, os 8 cards com dado real (2026-09-01)

Nenhum card usa proposta de exemplo. PRs #346, #348–#354 mergeadas, deployadas e
**confirmadas funcionando pelo usuário**; as cargas dos 8 passos foram ajustadas
no servidor no mesmo dia. Migrations **101 a 104** aplicadas.

| # | Card | `COD_CARD` | Tabela DET | Fonte · período |
|---|---|---|---|---|
| 1 | Pendentes de Assinatura | `PEND_ASSIN` | `PIO_PROPOSTA_PENDENTE_DET` | TDDB48 · 30 dias |
| 2 | Pendentes de Pagamento | `PEND_PGTO` | `PIO_PROPOSTA_PEND_PGTO_DET` | TDDB48 · 30 dias |
| 3 | Assinadas e Pagas | `ASSINA_PAGA` | `PIO_PROPOSTA_ASSINA_PAGA_DET` | TDDB48 · 30 dias |
| 4 | Em Análise | `CRITICA` | `PIO_PROPOSTA_CRITICA_DET` | DMDB05 · ano |
| 5 | Emitidas | `EMITIDA` | `PIO_PROPOSTA_EMITIDA_DET` | DMDB05 · ano |
| 6 | Rejeitadas | `REJEITADA` | `PIO_PROPOSTA_REJEITADA_DET` | DMDB05 · ano |
| 7 | Devoluções de Prêmio | `DEVOL_PREMIO` | `PIO_PROPOSTA_DEVOL_PREMIO_DET` | DMDB05 · 30 dias |
| 8 | Sensibilizações | `SENSIBILIZACAO` | `PIO_PROPOSTA_SENSIBILIZACAO_DET` | DMDB05 · ano |

Volumes de 2026-09-01: 8.973 · 24.039 · 72.368 · 165 · **771.774** · 6.818.
A **Consulta de Propostas** busca em TODOS os cards (`card=TODOS`), por proposta,
CPF, agência ou matrícula.

## ⚠️ Os gotchas que continuam valendo

1. **A `PIO_AGG` tem MAIS DE UMA LINHA POR CARD.** A carga agrega por SITUAÇÃO
   dentro do card: EMITIDA veio em 4 linhas (127+715.074+44.749+11.824 =
   771.774), CRITICA em 2. **Qualquer leitura precisa agregar por `COD_CARD`** —
   um `new Map(cards.map(...))` sobrescreve a chave repetida e mostra a ÚLTIMA
   linha (o card exibiu 11.824 de 771.774, plausível e sem erro). Corrigido em
   dois lugares: `SUM`+`GROUP BY` na API e `contagemPorCard()` no front.
2. **Dois vocabulários de coluna.** Cards 1–3 (TDDB48): `COD_PROPOSTA`,
   `COD_CPF`, `NUM_MATRICULA`, `AREA_PRODUTO`, `VLR_IMP_SEGURADA`,
   `STA_SITUACAO`. Cards 4–8 (DMDB05): `NUM_PROPOSTA`, `COD_CPF_CNPJ`,
   `NUM_MATRI_VENDEDOR`, `DES_RAMO_PRODUTO`, `VLR_IS_VENDA`, `NOM_SUB_SITUACAO`,
   `NUM_IDADE` (já pronta). Traduzem: `ESQUEMA_TDDB48` / `ESQUEMA_DMDB05` em
   `api/routers/pio.py`, com apelidos iguais — é o que sustenta o `UNION ALL` das
   8 DET. O que a fonte não tem entra como `CAST(NULL AS <tipo>)`.
   Ler com o vocabulário errado dá "Invalid column name" e, como o endpoint
   degrada, **o card fica vazio sem erro na tela**.
3. **`COD_CARD` precisa de ≥ `VARCHAR(11)`**: `'ASSINA_PAGA'` tem 11 e o guia
   dizia 10. Com ANSI_WARNINGS ON a carga morre (Msg 2628); com OFF grava
   `'ASSINA_PAG'` calado e o card fica em ZERO para sempre. A migration 103
   alarga para 20.
4. **Cards 2, 3 e 7 se sobrepõem por construção.** 2 e 3 saem do mesmo
   `STA_ASSINATURA='CO'` (separa o `STA_PAGO`); o 7 são as rejeitadas COM
   movimento de cobrança, então a mesma proposta está no 6 e no 7.
5. **A API não refiltra por status** — cada DET já vem filtrada da carga.
   Repetir o filtro zera o card no dia em que a carga mudar de critério.
6. **API e `dist/` sempre JUNTOS** no deploy: o front chama `card=TODOS&modo=…`
   e lê campos que só a API nova devolve.
7. **`MAX(DTH_REFERENCIA)`, não `= hoje`** (o guia pede hoje): sem isso, um dia
   sem carga mostraria ZERO em vez do último número verdadeiro + a data velha,
   que é o que denuncia a carga parada.
8. **Card que lê a carga esconde o Select de sub-status** — ele filtra o array
   local e não a lista paginada do servidor.
9. **Três valores que a tela não pode confundir** (dois já foram o mesmo número
   com rótulos diferentes): `value` = **prêmio** (`VLR_PREMIO`; nos cards 4–8,
   `VLR_CONTRATO`) · `individualIncome` = **renda** (`VLR_RENDA_FORMAL`) ·
   `insuredAmount` = **importância segurada** (`VLR_IMP_SEGURADA`/`VLR_IS_VENDA`).
   Nos cards 4–8 ficam vazios Região (sem UF), Renda e telefone de reserva.
10. **O container `orquestra-api` do DEV roda de IMAGEM, não de volume**: código
    de `api/` só aparece com `docker compose … up -d --build orquestra-api`, o
    que reinicia o `airflow-webserver` junto — e enquanto ele sobe, **o login
    falha com 500**. Esperar `healthy` (ver [[vps-ambiente-dev-orquestra]]).

🧪 `tests/test_pio_regiao.py` **compila `regiao.ts` com `tsc --ignoreConfig` e o
exercita no `node`** — é o jeito de testar lógica de front neste repo, que não
tem test runner.

## Pendências

1. **Versionar a procedure de carga** —
   `SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.PRC_PIO_CARGA_DIARIA'))` no servidor,
   e daí para uma migration. As migrations 101–104 criam só as TABELAS, de
   propósito: o texto que roda em produção é a fonte da verdade.
2. **SQL Agent Job da carga** — aguarda o DBA (`usr_dstage_prev` não tem
   permissão no SQL Agent). Sem ele a carga não roda sozinha às 07:30.
3. ⚠️ **Performance da busca com 771 mil linhas na EMITIDA**: proposta e CPF usam
   `LIKE '%termo%'`, que não usa índice. Se ficar lento, comparar por igualdade
   quando o termo vier completo — aí os índices `_PROPOSTA` e `_CPF` entram.
4. **Backlog do guia:** gráfico de tendência pela `PIO_AGG_HIST` (carregada, sem
   tela); nome do vendedor (cruzar matrícula com
   `WORK_GEPLAC.dbo.TB_VENDA_MATRICULA_VIDA` ou `DMDB11.dbo.DM_038_FUNC_CEF`);
   sub-status dentro de `/pio/propostas`, devolvendo o filtro ao card 2;
   **`NOM_AGENCIA`** (nome da agência, cards 4–8) existe e não é exibido.
5. **`PIO_PROPOSTA_PENDENTE_AGG`** (migration 101) ficou **órfã** — ninguém lê.
   Não foi dropada porque a carga nasceu fora do repo; se o DBA confirmar que
   nada a escreve, um DROP vira migration própria.
