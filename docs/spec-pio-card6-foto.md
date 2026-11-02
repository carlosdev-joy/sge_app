# Spec: Card 6 do PIO lê a foto diária — Orquestra
Data: 2026-11-02 · Status: em execução · Chamado RITM0118511

## 1. Visão
O Card 6 (**Rejeitadas**, `declined`; VG, `SIT_REGISTRO='2'`) passa a ler a foto `AGG/FAT/CTL_ORQ_CARD06_*` (DMDB41, Fabric 07:30).
Unidade = **certificado** (`NUM_SIVPF`); a FAT tem uma linha por motivo. Mesmo desenho do Card 4.

## 2. Escopo
**IN:** `GET /pio/card6/{resumo,propostas,motivos}`; prêmio em destaque + contratos abaixo; lista sem "dias" e sem "Gerenciar
Devolução"; Resumo do Seguro com "Proposta/Certificado" e motivos como última informação de Dados da Venda; Workflow da
rejeitada terminando em "Proposta Rejeitada"; Histórico (situação, motivos, declínio, quitação); migration 147 (v2.6.7); testes; release note.
**OUT:** mapa do Brasil; Workflow real nos demais cards; ações por motivo; demais cards e busca global; escrita nas tabelas; merge/deploy sem autorização.

## 3. Telas (impeccable — Operate, refinamento do incumbente)
Sem tela nova e sem reordenação. Selo "Rejeitada" e cor do card inalterados (`red-700`). "Motivos da Rejeição (n)": bloco de largura
total, último do quadro Dados da Venda; cada motivo = descrição em negrito, complemento em `text-dim` com quebras preservadas, "Motivo N ·
registrado em dd/mm/aaaa"; estados consultando/erro ("a lista não está vazia — ela é desconhecida")/vazio. Timeline: terceira etapa vermelha com ícone de X.

## 4. Arquitetura
Back `api/routers/pio_card6.py` (helpers de `pio_card1`/`pio_card4`). Resumo só pela AGG; lista `GROUP BY NUM_SIVPF` com `MIN()`; total
`COUNT(DISTINCT NUM_SIVPF)`; nunca `SUM(VLR_CONTRATO)`. Front: `STATUS_CARD6 = "declined"`, `lib/pioCard6.ts`, `foto.rejeitada`, `MotivosCard6.tsx`.

## 5. Dados
Sem tabela nova. Migration `147_versao_pio_card6_foto.sql` (idempotente; 2.6.7).

## 6. Riscos
Dupla contagem de prêmio por motivo (AGG + teste proíbe soma por linha); prêmio NULL ≠ zero; Workflow "real" sem desenho do negócio (homologar); IS por linha de motivo (`MIN`).
