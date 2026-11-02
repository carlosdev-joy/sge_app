# Ajustes do Card 7 e do Workflow — v2.6.12

Pedido do Carlos em 03/11/2026.

## O que muda
- **Card 7 (Devolução de Prêmio):** nos registros dos sub-cards **verde (Devolução Realizada)** e **laranja (Devolução em Andamento)** o botão **"Gerenciar Devolução" sai**. Ele continua
  só no **vermelho (Devolução Pendente)**, que é onde há dados bancários a tratar. O selo, o Resumo do Seguro e os demais cards não mudam.
- **Tela "Gerenciamento de Devolução":** o botão **"Programar Devolução"** passa a se chamar **"Salvar Dados Bancários"** (o texto durante o processamento continua "Processando...").
- **Workflow da tela principal:** passa a **abrir por padrão**, já mostrando os **8 cards** ao acessar a tela. A barra "Workflow" ainda recolhe/expande, se o usuário quiser; para
  deixá-lo fixo e sem a barra basta remover o botão de alternar (decisão a confirmar).

## Atenção
O diálogo "Gerenciamento de Devolução" é uma **simulação anterior a esta entrega**: ao clicar, espera 2 segundos e mostra "Dados bancários registrados — a devolução foi programada com sucesso",
**sem gravar nada**. Com o novo nome ("Salvar Dados Bancários") a expectativa de que os dados sejam salvos fica maior: **enquanto não houver gravação real, o botão não persiste os dados bancários**.
Definir o destino da escrita (e permissão/auditoria) antes de liberar o uso (era a parte "editável + Salvar" que ficou fora da entrega do Card 7).

## Deploy (produção — exige autorização própria)
`scripts/deploy_prod.sh`: migration 152 → **s**; `config/` → **n**; só `dist/` e migration de versão. Sem mudança de API, tabela ou carga.

## Smoke
Card 7: Realizada e em Andamento sem o botão nos registros; Pendente com "Gerenciar Devolução" → o diálogo mostra "Salvar Dados Bancários". Ao entrar em Busca & Vendas o Workflow já está aberto com os 8 cards.

## Rollback
Reverter o código (`dist/`).
