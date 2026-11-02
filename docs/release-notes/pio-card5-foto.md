# Card 5 do PIO lê a foto diária — v2.6.6

Chamado **RITM0118510 / SCTASK0120198** (Card 05, prazo 06/11/2026).

## O que muda
O Card 5 (**Emitidas**, Vida em Grupo + Acidentes Pessoais) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD05_*`, schema `dbo`, DMDB41). Número do card, lista, Resumo, Histórico e Enviar usam
a mesma foto (data + lote). Os demais cards e a busca global seguem como estavam.

- **Card:** prêmio em destaque (`SUM(VLR_PREMIO_TOTAL)` da AGG) e, abaixo em fonte menor, a quantidade de
  contratos (`SUM(QTD_CONTRATOS)`). Sem nenhum prêmio informado o card mostra "—" (desconhecido, não zero).
- **Lista:** um contrato por linha (chave `SEGMENTO` + `NUM_SIVPF`); total da lista = contratos do card.
- **Selo de status** (cor por situação; o texto é a situação real do contrato):
  azul = emitida (Integrada, Integrada Proposta Nova/Migrada, Aceita…, Ativo), **amarelo = Cobertura Suspensa**,
  **vermelho = Cancelada** (VG `4`, AP `2`). A regra mora num só lugar: `tom_do_status` em `pio_card5.py`.
- **Resumo do Seguro:** "Proposta/Certificado" em Dados da Venda; sem "Usuário" e sem rodapé (como nos Cards 1–4);
  contrato **inativo** (`SIT_CONTRATO='Inativo'`) mostra "Motivo do Cancelamento" como **última** informação de
  Dados da Venda ("Não informado na origem" quando a fonte não registrou).
- **Histórico:** Situação, Emissão e Segmento.
- **Fora do escopo:** mapa do Brasil com filtros Região/Estado/Cidade (mesma decisão do Card 4).
- "Região" fica vazia: UF/cidade são da **agência de cobrança**, não do segurado.

⚠️ A foto é um **estoque do ano corrente** (vendas desde 01/01), não "vendas novas do dia". Fotos de dias
diferentes nunca se somam. O ano corrente é regra da CARGA; a API não reaplica data nenhuma.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do login da
   aplicação nas três tabelas, colunas `QTD_CONTRATOS`/`QTD_PREMIOS_INFORMADOS`/`VLR_PREMIO_TOTAL` na AGG e
   `DES_COD_SIT_CONTRATO`/`SIT_CONTRATO`/`MOT_CANCELAMENTO` na FAT.
2. `scripts/deploy_prod.sh`: migrations pendentes (141–145 se ainda não aplicadas, e a 146) → **s**; `config/` → **n**.
3. Validar: contratos e prêmio do card × consulta de validação da carga; total da lista = contratos; Cards 1–4 e
   6–8 inalterados.

## Smoke (a–h)
a) Preflight ok. b) Card "Emitidas" = prêmio/contratos da foto (02/11: 814.968 contratos, R$ 492.469.590,63).
c) Lista: total = contratos, paginação sem repetir. d) Selo azul/amarelo/vermelho conforme a situação.
e) Contrato cancelado: motivo por último em Dados da Venda. f) Histórico e Enviar com o contato da foto.
g) Cards 1–4, 6–8 e busca global inalterados. h) Sem permissão/tabela: "—".

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- Regra de cor: "emitida" = Integrada ou Cobertura Suspensa (decisão do Carlos em 02/11); Cancelada vermelho,
  Cobertura Suspensa amarelo, o restante azul. As situações "Aceita – Aguard. Emissão/Pagamento 1ª Parcela" e
  "Aguardando Proposta Física" também aparecem azuis (não há instrução diferente no chamado).
- `NUM_SIVPF` é certificado (VG) ou apólice (AP); rótulo "Proposta/Certificado" — não há número de proposta distinto.
- Produto AP 8521: 109.159 registros com prêmio zero na origem — preservados, não estimados.
- 14 emissões anteriores à venda preservadas. `NOLOCK` e `TOP 1` sem desempate na origem (BILHETE): homologar.
- A linha do tempo do Resumo do Seguro não foi alterada (o chamado não pede para o Card 5).

## Pendências conhecidas
- Mapa do Brasil e geografia comum (agência × segurado). Alertas/identidade de serviço e CU(s) do pipeline.
- Numeração 140+ a reconciliar com o `develop`. `pio_card5.py` é o 5º router do padrão (débito: fábrica comum).
