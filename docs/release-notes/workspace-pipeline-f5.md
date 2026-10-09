# Workspace de Pipeline — F5

Execuções e logs permanecem no pipeline. A corrida selecionada acompanha o link, a troca de abas e o retorno à malha. Logs são abertos por etapa/tentativa; reprocessamento mantém prévia e pausas usam as ferramentas já existentes.

A montagem apresenta configuração recolhível, busca de etapas, importação em lote JSON, ordem e renomeação no rascunho. Referências protegidas permanecem na origem. Ferramentas especializadas legadas têm entrada contextual e continuam protegidas contra escrita direta de configuração gerida.

## Deploy DEV

- Aplicar migrations idempotentes 146 (comandos) e 147 (versão funcional v2.11.0 no DEV v2.10.0).
- Atualizar dist, API e imagem .NET; sem dependências Python/NuGet novas.
- Overlay workspace: WORKSPACE_OPERATIONS_ENABLED=true e WORKSPACE_NAVIGATION_PILOT_USERS com lista explícita de matrículas do piloto. Lista vazia conserva menus Etapas/Fluxos para todos. Nunca habilitar produção implicitamente.
- Preservar flags/credenciais/permissões SQL F4; nenhum grant de escrita ativa para .NET.
- Recarregar nginx após recriar API para atualizar resolução do upstream; reiniciar apenas serviços alterados.
- Smoke com fixture sintética: disparo/conf/idempotência, leitura de corrida, log/tentativa, reprocessar versão corrente, negar antiga/pendente/sem permissão, menus/links piloto versus usuário fora do piloto.

## Limites

Não há cancelamento geral de job remoto. Cancelar pausa não significa encerrar execução. Renomear etapa com parâmetro Encrypted exige preservar o identificador até migrar a referência na origem. Configuração completa usa JSON, sem alegar equivalência visual dos formulários especializados. Piloto, concorrência/desempenho medidos e validação final ficam na F6. DataStage/dados reais dependem da Caixa. Main/produção permanecem separados.

Reserva de comandos serializada contra publicação e outras corridas. Requests guardam SHA-256 e versão/hash, sem conf persistida. Comando sem confirmação expira em erro e não permite nova reserva para reprocessar a mesma corrida: solicite nova corrida para evitar clear externo tardio. Reconciliador usa token/estado como fencing. O motor recusa comandos expirados e múltiplas corridas ativas de pipeline gerido.
