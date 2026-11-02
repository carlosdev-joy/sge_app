# Spec: Card 8 do PIO lê a foto diária — Orquestra
Data: 2026-11-02 · Status: em execução · Chamado RITM0118664

## 1. Visão
O Card 8 (**Sensibilizações**, `sensitization_monitoring`; último movimento de propostas Vida, VG + AP) passa a ler a foto `AGG/FAT/CTL_ORQ_CARD08_*` (DMDB41). Unidade =
**identificação** (empresa + nº), não a proposta. Foto de ~6,5 milhões de linhas; FAT só D-2 (política de 02/11).

## 2. Escopo (decisões do usuário em 02/11)
**IN:** `GET /pio/card8/{resumo,propostas}`; card = valor + identificações; lista sem dias, selo com o status real, ordem por identificação; botão "Sensibilizar"
(habilita pela equivalência declarada; clique só avisa); Resumo com valor, movimento encaminhado e data de envio; Workflow com os dois estados reais; política D-2;
migration 149 (v2.6.9); testes; release note.
**OUT:** mapa do Brasil, layout global, Workflow real nos demais cards, envio real do movimento, filtros, busca, dados do segurado (não estão na foto).

## 3. Telas (impeccable — Operate, refinamento do incumbente)
Sem tela nova. Selo da lista = pílula sólida no azul do card com o status real; "Sensibilizar" = `Button` primário pequeno, desabilitado com dica quando já corresponde.
Resumo: quadro "Dados da Sensibilização" no padrão dos outros (`bg-canvas`/`border-edge`, 3 colunas), nota em itálico sobre o que a foto não traz. Workflow: duas etapas
(Movimento → Proposta) — a segunda verde quando o movimento já a confirma, laranja quando difere. Sem cor nova.

## 4. Arquitetura
Back `api/routers/pio_card8.py`: total da lista e do card pela AGG; lista pelo índice único; detalhe só se a foto é ≥ D-2 e o lote tem linhas na FAT; `_legivel` trata NULL e NUL;
`EQUIVALENTES` + `pode_sensibilizar` numa só regra. Front: `STATUS_CARD8`, `pioCard8.ts`, `foto.sensibilizacao`, `SensibilizacaoCard8.tsx`, `ProposalTimeline` com `passos`,
`ListaPio.ordem`.

## 5. Dados
Sem tabela nova. Migration `149_versao_pio_card8_foto.sql` (idempotente; 2.6.9).

## 6. Riscos
6,5 M de linhas (nenhum COUNT/ORDER BY por data na FAT); detalhe expirado ≠ zero; status NULL/NUL nunca como rótulo vazio; equivalência do botão a homologar; clique sem integração
não pode fingir sucesso; valor ≠ prêmio pago.
