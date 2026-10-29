# Spec: Card 4 do PIO lê a foto diária — Orquestra
Data: 2026-10-29 · Status: em execução (pedido "agora vamos fazer o card 4")

## 1. Visão
O Card 4 do Workflow de Busca & Vendas (**Em Análise**, `in_analysis`; críticas de propostas Vida em
Grupo) hoje lê a carga legada (`CRITICA`). A frente de dados publicou a foto diária
`AGG/FAT/CTL_ORQ_CARD04_*` (DMDB41, Fabric 07:30). Card, lista, Resumo, Histórico e Enviar passam a
ler essa foto. **Diferença dos Cards 1–3:** a granularidade é o **certificado** (`NUM_SIVPF`), não a
linha: a FAT guarda uma linha por mensagem de crítica e o mesmo certificado repete.

## 2. Escopo
**IN:** `GET /pio/card4/resumo` (AGG: contratos, prêmio sem repetição, nº de críticas) e
`/pio/card4/propostas` (FAT **agrupada por certificado**, paginada) e `/pio/card4/pendencias`
(críticas de um certificado — consulta 5 do repasse); card inline/painel e lista com a foto;
Histórico mostra situação, nº de críticas e quitação; **seção "Pendências" no Resumo do Seguro**, abaixo
de "Dados do Segurado" (liberada pelo usuário em 29/10, com o pedido do solicitante: certificado uma vez
na lista, críticas em lista com `DES_MSG_CRITICA` e `DES_COMPLEMENTAR`); Nº da proposta em Dados da
Venda, sem "Usuário" e sem rodapé (como nos Cards 1–3); migration 145 (v2.6.5); testes; release note.
**OUT:** **mapa do Brasil** e filtros Região/Estado/Cidade (o usuário os tirou do escopo, 29/10);
botões por tipo de crítica (**Upload** só em pendência documental; **reenvio Samplemed** para DPS): exigem
o mapa `COD_MSG_CRITICA → ação`, URLs e permissões, que o negócio não definiu — nada é inferido do texto;
demais cards e busca global; escrita nas tabelas; deploy/merge sem autorização própria.

## 3. Telas (impeccable)
Sem tela nova e sem reordenação; um bloco novo no diálogo existente. Muda a fonte do valor do card "Em Análise". Lista: uma linha por
certificado (nunca por mensagem), mesmo cartão dos outros. Histórico (foto): Situação (`Em Crítica`/
`Aguardando Proposta Física`), Críticas (n) e Quitação (data ou "Não informada"), no lugar de
Assinatura/Pagamento (que a fonte não tem). "Região" fica vazia no Card 4: UF/cidade da query são da
**agência de cobrança**, não do segurado (semântica diferente dos Cards 1–3). Seção "Pendências (n)" no mesmo padrão de "Dados do Segurado" (título azul centrado, painel
`bg-canvas`/`border-edge`): uma linha por crítica — ícone âmbar (par claro/escuro), descrição em negrito,
complemento em `text-dim` com quebras de linha preservadas, "Crítica N · registrada em dd/mm/aaaa".
Estados: consultando, erro ("a lista não está vazia — ela é desconhecida"), vazio, lista. Validada no
Playwright (claro/escuro, desktop/390 px). Sem cor nova.

## 4. Arquitetura
- Back: `api/routers/pio_card4.py`. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem
  GETDATE/D-30. Resumo: `SUM(QTD_CONTRATOS)` (aditiva), `SUM(VLR_PREMIO_TOTAL)` (já uma vez por
  certificado), `SUM(QTD_CRITICAS)`. Lista: `GROUP BY NUM_SIVPF` com `MIN()` nas colunas (a carga já
  provou unicidade de prêmio e das 13 dimensões); total = `COUNT(DISTINCT NUM_SIVPF)` = quantidade do card.
  Nunca soma `VLR_CONTRATO` por linha. Nº da proposta = `NUM_SIVPF` (equivalência a homologar).
  CPF/CNPJ numérico volta formatado com zeros à esquerda (11 se PF, 14 se PJ).
- Front: `STATUS_CARD4 = "in_analysis"`, `lib/pioCard4.ts`, mapa de status nos dois componentes;
  campos opcionais `criticas/subSituacao/quitacao` no item/foto.
- Reuso dos helpers de `pio_card1` e `_filtro_da_busca` com mapa de colunas do Card 4.

## 5. Dados
Sem tabela nova. Migration `145_versao_pio_card4_foto.sql` (idempotente; versão 2.6.5).

## 6. Fases (uma PR): front com contrato simulado → API + testes → migration/release note → QA adversarial.

## 7. Riscos
| # | Risco | Mitigação |
|---|-------|-----------|
| 1 | Somar prêmio/linhas por mensagem (dupla contagem) | Lista agrupada; resumo só pela AGG; teste prende `COUNT(DISTINCT)` e proíbe `SUM(VLR_CONTRATO)` |
| 2 | Sem `SELECT` do login nas 3 tabelas / nomes de coluna | `—`, nunca zero; preflight |
| 3 | "Em Análise" na produção hoje conta o legado (CRITICA, DMDB05); número muda | Release note; confirmar com solicitante |
| 4 | Query sem filtro de pagamento, texto do chamado cita "pagas" | Mostrar quitação; homologar |
| 5 | `NOLOCK`/`TOP 1` de telefone na origem (leitura suja/empate) | Fora da API; homologar com solicitante |
| 6 | Dados pessoais (CPF/CNPJ, telefone, e-mail) | Mesma permissão `tela_caixa_seguro`, página ≤ 200, nada em log |

## 8. Smoke
a) Preflight (um lote PUBLICADO; AGG × FAT conciliam; `SELECT` do login). b) Card = contratos e prêmio da
consulta 1 (ex.: 407 / R$ 528.747,15 na foto de 29/10). c) Lista: total = contratos, 1 linha por
certificado, paginação sem repetir. d) Histórico: situação/críticas/quitação. e) Resumo/Enviar usam contato
da foto. f) Cards 1–3 e 5–8 e busca global inalterados. g) Sem permissão/tabela: `—`.

## 9. Pendências
`NUM_SIVPF` = nº de proposta?; filtro de pagamento; mapa de mensagens → ação (Upload/Samplemed, URLs,
permissões); mapa do Brasil e geografia comum (agência × segurado); nome do estado "Em Análise" × "crítica".
