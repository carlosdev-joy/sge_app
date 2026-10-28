# Card 3 do PIO lê a foto diária — v2.6.4

## O que muda
Só o Card 3 (Assinadas e Pagas) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD03_*`, schema `dbo`, banco DMDB41), no mesmo padrão dos Cards 1 e 2.
Número do card, lista, Resumo do Seguro, Histórico e Enviar usam a mesma foto (data + lote).
Os demais cards e a busca global seguem na carga legada (`routers/pio.py` intocado); Cards 1 e 2 não mudam.
Na lista do Card 3 não aparece "dias pendente": a proposta já está paga.

Regra da carga (do documento da frente de dados): assinatura `CO`/`SO`, `STA_PAGO='S'`, sem `CA`/`EX`,
`YEAR(DTH_VENDA)` = ano do relógio do SQL18 na hora da carga. A API não reaplica esse filtro: a foto é a
resposta.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do
   login da aplicação nas três tabelas do Card 3, colunas `QTD_REGISTROS`/`VLR_PREMIO_TOTAL` na AGG.
2. **Medir a lista**: a FAT tem ≈689 mil linhas por foto e só índice em `DTA_MOVIMENTO`. Cronometrar
   `COUNT` + página 1 e uma página profunda; se lento, pedir à frente de dados o índice
   `(DTA_MOVIMENTO, LOTE_ID, DTH_VENDA, COD_PROPOSTA, ID_FOTO)`.
3. `scripts/deploy_prod.sh`: migrations pendentes (141/142/143 se ainda não aplicadas, e a 144) → **s**;
   `config/` → **n**. A 144 só insere em `etl_versao_ferramenta`/`etl_app_config`.
4. Validar: prêmio e quantidade do card × consulta 2 do repasse na mesma data; total da lista =
   quantidade do card; Cards 1, 2 e 4–8 inalterados.

## Smoke (a–g)
a) Preflight ok. b) Card "Assinadas e Pagas" = prêmio/quantidade da consulta 2. c) Lista: total = quantidade,
paginação sem repetir linha, tempo aceitável. d) Detalhe sem "dias pendente". e) Resumo/Enviar usam o contato
da foto ("Contato não informado" quando ausente). f) Cards 1, 2, 4–8 e busca global inalterados.
g) Sem permissão/tabela: card "—", tela não quebra.

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- Quantidade = linhas da query (≈689 mil), não contratos únicos: no diagnóstico de 28/10 eram 688.952
  propostas distintas (22 combinações proposta/venda repetidas, 49 linhas a mais, preservadas).
- O período é o **ano corrente**. Na virada do ano a carga pode legitimamente voltar quase vazia e a foto vazia
  é bloqueada pela carga; enquanto isso o card segue mostrando a última foto publicada (data no tooltip).
- `SO` aparece cru no Histórico (rótulo não documentado); `CO` = "Assinada".
- Rótulo "contratos" na quantidade, como nos Cards 1 e 2 (pergunta de negócio ainda aberta).

## Pendências conhecidas
- Sem `SELECT` do login nas tabelas, o card mostra "—" (não zero).
- Numeração 140+ a reconciliar com o `develop`.
- `pio_card3.py` repete as rotas dos Cards 1 e 2; extrair fábrica comum quando os demais cards migrarem
  (agora são três cópias).
