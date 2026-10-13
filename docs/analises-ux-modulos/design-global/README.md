# Design premium e fácil de usar — proposta global

Data: 12/10/2026. Abrange toda a ferramenta, além de Pipeline/Malha. É uma proposta de design para leitura/revisão, sem código de produto alterado. O usuário solicitou explicitamente refinamento visual, tipografia, menus, espaçamento, tipos de objeto e unificação global.

**Direção recomendada:** um ambiente de trabalho de orquestração, sóbrio e preciso, em que o desenho e o diagnóstico são protagonistas. A qualidade vem da hierarquia, consistência e previsibilidade das ações. Premium significa cuidado nos detalhes e menor esforço para compreender a ferramenta.

Leia [direção e diagnóstico visual](direcao-e-percepcao-visual.md), [sistema visual e componentes](sistema-visual.md), [arquitetura e adoção global](arquitetura-e-adocao-global.md) e [pranchas conceituais](pranchas/README.md).

## Decisão de direção

| Abordagem | Benefício | Limite |
|---|---|---|
| Refinar cada tela isoladamente | Menor mudança inicial | Mantém inconsistências entre módulos e multiplica exceções |
| Sistema global com adoção progressiva — recomendado | Unifica linguagem, componentes e interação; permite migrar por jornadas | Requer inventário e critérios comuns antes de disseminar alterações |
| Substituição completa do frontend | Liberdade ampla | Alto risco de perder contratos, campos e operação; sem justificativa neste estudo |

A proposta adota o sistema global sobre React/componentes atuais. Antes de qualquer implementação, reconciliar com a SPEC e aprovar o design e suas fases conforme o processo do repositório. Não instalar bibliotecas, trocar fontes ou reorganizar menus em produção a partir destas pranchas.

## Como o agente deve usar

1. Entender a hierarquia e os tokens, não copiar dimensões sem testar conteúdo real.
2. Classificar cada alteração como global, específica do módulo ou novo requisito funcional.
3. Inventariar os usos dos componentes/tokens no código e verificar o DEV real.
4. Propor uma especificação de adoção que preserve contratos, RBAC, atalhos, nomes e estados existentes.
5. Demonstrar as jornadas com conteúdo longo e estados vazio/erro/espera em claro e escuro; só depois implementar.

As pranchas são desenhos de comunicação, com dados fictícios. Não são screenshots do produto atual, UI final aprovada, protótipo funcional ou evidência de capacidade implementada.
