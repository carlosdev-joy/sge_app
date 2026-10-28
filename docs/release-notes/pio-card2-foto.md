# Card 2 do PIO lê a foto diária — v2.6.3

## O que muda
Só o Card 2 (Pendentes de Pagamento) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD02_*`, schema `dbo`, banco DMDB41), no mesmo padrão do Card 1.
Número do card, lista, Resumo do Seguro, Histórico e Enviar usam a mesma foto (data + lote).
Os demais cards e a busca global seguem na carga legada (`routers/pio.py` intocado); o Card 1
não muda de comportamento.

Regra da carga (confirmada pelo solicitante): assinatura `CO`/`SO`, `STA_PAGO='N'`, sem `CA`/`EX`,
venda nos últimos 30 dias; "dias pendente" = dias desde `DTH_VENDA` na data da foto.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT,
   `SELECT` do login da aplicação nas três tabelas do Card 2, collation `Latin1_General_CI_AS`.
2. `scripts/deploy_prod.sh`: migrations pendentes (141/142 da #527, se ainda não aplicadas, e a 143)
   → responder **s**; `config/` → **n**. A 143 só insere em `etl_versao_ferramenta`/`etl_app_config`.
3. Validar: prêmio e quantidade do card × consulta 2 do repasse na mesma data; total da lista =
   quantidade do card; Card 1 e os demais inalterados.

## Smoke (a–g)
a) Preflight ok. b) Card "Pendentes de Pagamento" = prêmio/quantidade da consulta 2. c) Lista: total =
quantidade, paginação sem repetir linha. d) Foto de outro dia: só o tooltip informa a data; sem foto: "—"
com tooltip. e) Resumo/Enviar usam o contato da foto ("Contato não informado" quando ausente).
f) Card 1 e cards 3–8 inalterados. g) Sem permissão/tabela: card "—", tela não quebra.

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- A quantidade da foto (≈33,4 mil linhas) é maior que a do legado (≈22,5 mil): a foto inclui `CO` e `SO`,
  e os JOINs da query podem multiplicar linhas (3 combinações proposta/venda repetidas no diagnóstico).
  `SUM(QTD_REGISTROS)` conta linhas, não propostas distintas.
- O código `SO` aparece cru no Histórico (rótulo não documentado); `CO` = "Assinada".
- Quantidade rotulada "contratos", como no Card 1 (pergunta de negócio do Card 1 ainda aberta).

## Pendências conhecidas
- Sem `SELECT` do login nas tabelas, o card mostra "—" (não zero).
- Numeração 140+ a reconciliar com o `develop`.
- `pio_card2.py` repete as duas rotas do `pio_card1.py` (helpers compartilhados); extrair fábrica comum
  quando os demais cards migrarem.
