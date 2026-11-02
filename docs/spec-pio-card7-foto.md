# Spec: Card 7 do PIO lê a foto diária — Orquestra
Data: 2026-11-02 · Status: em execução · Chamado RITM0118567

## 1. Visão
O Card 7 (**Devolução de Prêmio**, `refund_scheduled`; rejeitadas VG + AP) passa a ler a foto `AGG/FAT/CTL_ORQ_CARD07_*` (DMDB41). Unidade = contrato
(VG certificado | AP bilhete). Diferente dos Cards 1–6: o clique no card **não abre lista**, abre 3 sub-cards.

## 2. Escopo (decisões do usuário em 02/11)
**IN:** `GET /pio/card7/{resumo,propostas,devolucao}`; card = valor devolvido (todos os status) + contratos; 3 sub-cards (Realizada, em Andamento, Pendente) que somam o card;
lista só após escolher um; selo com o status real; Resumo com Dados da Devolução e linha do tempo na etapa real; migration 148 (v2.6.8); testes; release note.
**OUT:** dados bancários editáveis/Salvar, Gerar Nova Venda, layout global, mapa do Brasil, Workflow real nos demais cards, e-mail/telefone (não estão na foto), motivos de declínio (idem).

## 3. Telas (impeccable — Operate, refinamento do incumbente)
Sem tela nova. Sub-cards: 3 botões sólidos (verde/âmbar/vermelho, texto branco — linguagem de `STATUS_COR`), empilhados no celular e em linha de `sm` para cima; o escolhido ganha anel;
`aria-pressed`; estados consultando/erro ("não são zero — são desconhecidos")/sem foto. O Resumo reaproveita o modal existente, com a linha do tempo de devolução já existente
(agora na etapa real) e um quadro "Dados da Devolução" no padrão dos outros (`bg-canvas`/`border-edge`); campo que a foto não traz diz "Não disponível nesta foto" em itálico.

## 4. Arquitetura
Back `api/routers/pio_card7.py`: regra dos sub-cards num único `CASE` (`_bucket`) usado na AGG e na FAT (desconhecido = pendente, logo soma sempre fecha); dados bancários só em `/devolucao`.
Front: `STATUS_CARD7`, `pioCard7.ts`, `DevolucaoSubcards.tsx`, `DevolucaoCard7.tsx`, `foto.devolucao`, `ProposalTimeline` com `refundStep`; `semLista` esconde os avisos de lista.

## 5. Dados
Sem tabela nova. Migration `148_versao_pio_card7_foto.sql` (idempotente; 2.6.8).

## 6. Riscos
Valor ≠ prêmio (release note); código de status fora do mapa (cai em Pendente; preflight lista os reais); dado bancário exposto (fora da lista, endpoint próprio, mesma permissão);
campos ausentes na foto (a tela não inventa).
