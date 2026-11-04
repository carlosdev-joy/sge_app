# Agente Terminal — F1: prévia da interface

Primeira fase da spec `docs/spec-agente-terminal.md`. **Só front, com dados simulados.**

## O que muda
- Nova interface de chat estilo terminal (`TerminalChat`, `ComandoBloco`, `ConfirmarComando`) e lógica pura em `lib/terminalComando.ts`.
- A prévia abre apenas em `/agentes?agente=terminal&simulado=1` (somente leitura por padrão; acrescente `&escrita=1` para ver o modo com confirmação de escrita). Sem esses parâmetros, a tela `/agentes` é a de sempre.
- Estados: vazio com exemplos, executando, comando de leitura com saída (corte em 40 linhas + "Mostrar tudo"), comando de escrita com card "Confirmar e executar"/"Recusar" e contagem de 2 min, comando bloqueado, comando que falhou, saída truncada.

## Limites
- **Nada é executado.** O simulador (`lib/terminalSimulado.ts`) devolve respostas fixas; não há chamada de rede.
- O agente ainda não existe no catálogo nem no RBAC (F2). Servidor, DataStage e bancos entram nas F3–F5.

## Deploy
- **Sem migration nesta fase.** A versão é registrada na F2 (primeira entrega com backend): a numeração de migrations é sequencial sem lacuna (teste `test_eoc_f3_paridade_tipos`) e as 197–200 estão reservadas pela Malha F16 em andamento, então a F1 não toma número.
- Atualizar `dist/`. Sem mudança de API, `dags/` ou dependências.
