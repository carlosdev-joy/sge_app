# Spec: Card 5 do PIO lê a foto diária — Orquestra
Data: 2026-11-02 · Status: em execução · Chamado RITM0118510 (SCTASK0120198)

## 1. Visão
O Card 5 do Workflow de Busca & Vendas (**Emitidas**, `emission_sent`; VG + AP) passa a ler a foto diária
`AGG/FAT/CTL_ORQ_CARD05_*` (DMDB41, Fabric 07:30), como os Cards 1–4. Unidade = **contrato** (`SEGMENTO` +
`NUM_SIVPF`); a foto é um estoque do ano corrente.

## 2. Escopo
**IN:** `GET /pio/card5/{resumo,propostas}`; número do card = prêmio em destaque + contratos abaixo; lista com selo
de status por situação; Histórico (situação, emissão, segmento); Resumo do Seguro: "Proposta/Certificado", sem
"Usuário"/rodapé, motivo do cancelamento por último em Dados da Venda; migration 146 (v2.6.6); testes; release note.
**OUT:** mapa do Brasil e filtros (decisão do Carlos para o Card 4, estendida ao 5 na falta de resposta);
linha do tempo do Workflow; demais cards e busca global; escrita nas tabelas; merge/deploy sem autorização.

## 3. Telas (impeccable — Operate, refinamento do incumbente)
Sem tela nova, sem reordenação. Selo da lista segue a linguagem existente (pílula sólida): azul `blue-600`/branco
(emitida), amarelo `amber-400`/grafite (cobertura suspensa — grafite porque branco sobre amarelo reprova contraste),
vermelho `red-700`/branco (cancelada); texto = situação real. Sem cor nova no sistema. Motivo do cancelamento:
`CampoInfo` de largura total, último do quadro Dados da Venda; ausência vira texto ("Não informado na origem").

## 4. Arquitetura
Back: `api/routers/pio_card5.py` (helpers de `pio_card1`/`pio_card4`). Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL
`PUBLICADO`. Resumo só pela AGG. Regra de cor única no backend (`tom_do_status`); front só mapeia tom → classe
(`seloDaProposta`). Front: `STATUS_CARD5 = "emission_sent"`, `lib/pioCard5.ts`, campo `foto.emitida`.

## 5. Dados
Sem tabela nova. Migration `146_versao_pio_card5_foto.sql` (idempotente; 2.6.6).

## 6. Riscos
Prêmio NULL ≠ zero (card mostra "—"); estoque ≠ vendas novas (release note); códigos de situação de VG não valem
em AP (teste prende); regra de cor decidida pelo usuário, restante "azul" sujeito à homologação do solicitante.
