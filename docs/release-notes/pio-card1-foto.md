# Card 1 do PIO lê a foto diária — v2.6.1 (RITM0117336)

## O que muda
Só o Card 1 (Pendentes de Assinatura) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD01_*`, schema `dbo`, banco DMDB41). Os outros sete cards e a
busca global seguem na carga legada (`routers/pio.py` intocado).

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT,
   `SELECT` do login da aplicação nas três tabelas, collation `Latin1_General_CI_AS`.
2. Conferir servidor/banco do `MSSQL_CONN_STR` de produção (sem expor a senha).
3. `scripts/deploy_prod.sh` (`config/` → responder **n**). A única migration é a 140 (versão
   2.6.1); ela só insere em `etl_versao_ferramenta`/`etl_app_config`.
4. Validar: prêmio e quantidade do card × consulta 2 do repasse na mesma data; total da lista
   = quantidade do card; os outros sete cards inalterados.

## Rollback
Reverter o código (API + `dist/`). As tabelas e o pipeline Fabric não são tocados — a aplicação
nunca escreve neles. A versão registrada pode ficar (é só rótulo).

## Pendências conhecidas
- Sem `SELECT` do login nas tabelas, o card mostra "—" (não zero).
- Numeração 140+ a reconciliar com o `develop`.
- Busca global ainda no legado (duas fontes até migrar os demais cards).
