# Card 4 do PIO lê a foto diária — v2.6.5

## O que muda
O Card 4 (Em Análise = críticas de propostas Vida em Grupo) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD04_*`, schema `dbo`, DMDB41). Número do card, lista, Resumo, Histórico e Enviar usam
a mesma foto (data + lote). Os demais cards e a busca global seguem como estavam.

**Granularidade = certificado (`NUM_SIVPF`).** A FAT tem uma linha por mensagem de crítica; o certificado repete.
- Card: contratos = `SUM(QTD_CONTRATOS)` e prêmio = `SUM(VLR_PREMIO_TOTAL)` da AGG — cada certificado **uma vez**.
- Lista: uma linha por certificado (`GROUP BY NUM_SIVPF`); o total da lista = contratos do card.
- Histórico da proposta: Situação, nº de Críticas e Quitação (data ou "Não informada").
- Resumo do Seguro: nova seção **"Pendências (n)"** abaixo de "Dados do Segurado", com as críticas do
  certificado (`DES_MSG_CRITICA` + `DES_COMPLEMENTAR`), pela rota nova `GET /pio/card4/pendencias?certificado=`
  (só leitura). Nº da proposta em Dados da Venda; sem "Usuário" e sem rodapé.
- **Não incluído:** botões **Upload** / reenvio **Samplemed** por tipo de crítica (falta o mapa
  `COD_MSG_CRITICA → ação`, URLs e permissões) e o **mapa do Brasil** (fora do escopo por decisão do usuário).
- "Região" fica vazia nesta lista: UF/cidade da query são da **agência de cobrança**, não do segurado.

Regra da carga (D-30 em `DTINCLUS` e `DTA_OCORRENCIA`, `STA_CRITICA='7'`, `SIT_REGISTRO IN ('1','9')`, banco 104)
é da CARGA; a API não reaplica data nenhuma.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do login
   da aplicação nas três tabelas, colunas `QTD_CONTRATOS`/`QTD_CRITICAS`/`VLR_PREMIO_TOTAL` na AGG.
2. `scripts/deploy_prod.sh`: migrations pendentes (141–144 se ainda não aplicadas, e a 145) → **s**; `config/` → **n**.
3. Validar: contratos e prêmio do card × consulta 1 do repasse; total da lista = contratos; Cards 1–3 e 5–8 inalterados.

## Smoke (a–g)
a) Preflight ok. b) Card "Em Análise" = consulta 1 (foto de 29/10: 407 contratos, R$ 528.747,15). c) Lista: uma
linha por certificado, total = contratos, paginação sem repetir. d) Histórico com situação/críticas/quitação; Resumo com "Pendências" listando todas as críticas do certificado.
e) Resumo/Enviar usam o contato da foto. f) Cards 1–3, 5–8 e busca global inalterados. g) Sem permissão/tabela: "—".

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- O card hoje mostra o número do legado (`CRITICA`, DMDB05); passa a ser o da foto (SIAS, D-30). Os números vão mudar.
- `NUM_SIVPF` (= `NUM_CERTIFICADO`) é o "número da proposta"? Confirmar ou indicar outro campo.
- A query **não filtra pagamento** e o texto do chamado fala em propostas pagas: a quitação aparece no Histórico
  para auditar; falta homologar a ausência do filtro.
- Origem usa `NOLOCK` e `TOP 1` por `TIMESTAMP` nos telefones (leitura não confirmada e empate): homologar.
- D-30 sem limite superior pode abranger 31 datas de calendário.

## Pendências conhecidas
- Mapa mensagem → ação (Upload/Samplemed), mapa do Brasil e geografia comum (agência × segurado).
- Sem `SELECT` do login nas tabelas, o card mostra "—" (não zero).
- Numeração 140+ a reconciliar com o `develop`. `pio_card4.py` é o 4º router do padrão (débito: fábrica comum).
