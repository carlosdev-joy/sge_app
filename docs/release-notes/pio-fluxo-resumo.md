# Resumo do Seguro mostra o fluxo da proposta — v2.6.10

Ajuste pedido pelo Carlos em 02/11/2026 (sobre os cards 1–8 do PIO).

## O que muda
A linha do tempo do **Resumo do Seguro** passa a mostrar **todas as etapas até a do card selecionado**, como o fluxo real da proposta: as etapas anteriores aparecem
**concluídas (sucesso)** e a etapa do card, em destaque. Exemplo no Card 4 (Em Análise): Pendente de Assinatura ✓ → Pendente de Pagamento ✓ → Assinada e Paga ✓ → **Em Análise**.

| Card | Fluxo mostrado |
|---|---|
| 1 Pendentes de Assinatura | Pendente de Assinatura |
| 2 Pendentes de Pagamento | + Pendente de Pagamento |
| 3 Assinadas e Pagas | + Assinada e Paga |
| 4 Em Análise | + Em Análise |
| 5 Emitidas | + Emitida |
| 6 Rejeitadas | …Em Análise → **Rejeitada** (não passa por Emitida) |
| 7 Devolução de Prêmio | …Em Análise → Rejeitada → **Devolução** |
| 8 Sensibilizações | …Emitida → **Sensibilização** (acompanha propostas emitidas) |

- A **etapa atual** traz o estado real do card: Card 5 mostra a situação (Integrada, Cobertura Suspensa, **Cancelada** — em vermelho, com "X"); Card 7, o sub-card (Devolução Realizada,
  em Andamento, Pendente); Card 8, o último movimento ("Sensibilização · Enviada"); Card 4, a situação ("Em Análise · Em Crítica").
- A regra mora num só lugar (`lib/fluxoProposta.ts`) e vale para todos os cards; o Resumo tem um único caminho. Status fora dos 8 cards (`pending_dps`, `refund_pending`, usados no
  Acompanhamento) seguem no fluxo antigo.
- Layout: o círculo fica acima do traço (o check não é cortado); no celular o fluxo longo **abre na etapa atual** e rola na horizontal para ver o histórico.
- Substitui os fluxos específicos dos Cards 6, 7 e 8 (Rejeitada, etapas da devolução, Movimento × Proposta): a situação de cada um segue visível na etapa atual e nos quadros
  "Dados da Devolução" e "Dados da Sensibilização".

## Premissas a homologar com o solicitante
- O fluxo é **inferido da ordem da operação** (`SEQUENCIA_WORKFLOW`) e de dois desvios (rejeitada sem Emitida; devolução depois da rejeição): a foto de cada card traz o estado
  atual, **não o histórico** — as etapas anteriores são as que a proposta teria cumprido para chegar ao card, não eventos lidos da origem. Contratos AP e certificados que não
  passaram por todas as etapas também mostram o caminho inteiro.
- Cards 5 e 8: Sensibilização aparece depois de Emitida; Devolução, depois de Rejeitada.

## Deploy (produção — exige autorização própria)
`scripts/deploy_prod.sh`: migration 150 → **s**; `config/` → **n**; só front (`dist/`) e migration de versão. Sem mudança de API, tabela ou carga.

## Smoke
Abrir o Resumo de uma proposta em cada card: etapas anteriores verdes com check, atual em destaque com o estado real; no celular, a etapa atual visível ao abrir e o histórico ao deslizar;
Acompanhamento (fluxo antigo) inalterado.

## Rollback
Reverter o código (`dist/`).
