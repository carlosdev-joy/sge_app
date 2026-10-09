# Workspace de Pipeline — F5: operação contextual

Base: develop c86de2a. F5 autorizada em 09/10/2026. F6 permanece separada.

## Escopo e ameaças

A navegação é uma preferência de piloto, nunca uma concessão de permissão. A configuração `Workspace:OperationsEnabled` habilita ações implementadas; `Workspace:NavigationPilotUsers` enumera matrículas do grupo piloto. Ambas ficam desabilitadas/vazias por padrão. O servidor calcula capabilities com permissões atuais da sessão. Só o piloto perde Etapas/Fluxos na sidebar; as rotas continuam reversíveis. Falha de capabilities mantém a navegação legada.

Fronteiras: browser não escolhe URL upstream; .NET encaminha apenas o alias de disparo fixo, com timeout, corpo/resposta limitados, sem redirects/proxy e sem log de headers. Disparo exige Bearer, três permissões de tela e acao_executar, não acao_editar. Logs exigem as mesmas telas e identidade de corrida/etapa resolvida; corpo é texto, limitado e sem cache. Conf é permitida só para o disparo, não para alterar marcadores estáticos F4. Resposta de disparo contém somente identidade/estado, sem conf.

Publicação pendente e atividade/reservas impedem novo disparo. Reprocessamento de pipeline gerido exige corrida já vinculada à versão/hash atuais; versões antigas, vínculos desconhecidos e cascata entre pipelines são recusados antes dos efeitos. A política do motor F4 permanece autoridade final em corridas concorrentes. Limites de concorrência e falhas externas entram novamente na F6; não se promete cancelamento geral de job remoto.

## Destino do inventário F1

| Função | Destino F5 |
|---|---|
| Lista, busca, criar pipeline | Pipelines e criação de rascunho |
| Criar/editar/remover os 11 tipos | Desenvolvimento: Fluxo/Etapas e propriedades do rascunho |
| Ordenar | Propriedades: ordem de execução; dependências continuam no grafo |
| Renomear | Propriedades: renomear identificador no rascunho, atualiza arestas/layout/ramos/linhas relacionadas; referência Encrypted imutável exige preservar identificador |
| Salvar fluxo | Lease/revisão/fence F3; configuração ativa intacta |
| Gerar/sincronizar DAG | Validar/publicar F4; histórico/restaurar continuam |
| Parâmetros/catálogos/vínculos | Aba Parâmetros (existentes e adicionar), configuração completa JSON do pipeline/etapa para catálogos e vínculos |
| Importar etapas em lote | Configuração recolhível: lista JSON para rascunho; sem POST ao cadastro ativo |
| Configuração/política sem movimento | Propriedades e configuração completa JSON do rascunho |
| Lineage/extração/prévias/IA | Aba Ferramentas aponta as ferramentas especializadas legadas com contexto; cadastro gerido continua protegido contra escrita direta |
| Disparo | Execuções: confirmação explícita com conf/data lógica; ação separada de publicação |
| Reprocessar/pausar/liberar/cancelar pausa | Mesmo canvas operacional e modais existentes, com corrida exata selecionada |
| Estado/logs/tentativas | Execuções e Logs dentro do workspace; seleção de corrida, etapa, tentativa e fonte Airflow |
| Inativação | Status existente preservado; remoção não se apresenta como inativação |

Configuração avançada JSON é um destino funcional explícito, não alegação de paridade visual de todos os formulários especializados. Ferramentas legadas permanecem acessíveis e têm as permissões originais. Escrever lineage ativo de pipeline gerido permanece bloqueado desde F4. Renomear etapa com parâmetros protegidos é recusado com explicação, sem mover/copy de cifra. Não oferecer função futura como botão funcionando.

## Visual e links

Extensão do sistema ORQUESTRA, tokens claro/escuro e controles existentes. Configuração fica recolhível para biblioteca/canvas/propriedades aparecerem antes. Abas e experiência preservam data, run_id e de=malha; volta à malha aceita origem estruturada, nunca URL livre. Links /jobs?pipeline e /fluxos?pipeline&modo=execucao convertem apenas para piloto; legado=1 preserva acesso especializado. Links sem pipeline encaminham à seleção da lista. Canvas operacional usa snapshot confirmado, não projeção intermediária.

## Entrega e prova

Migration estrutural idempotente 146 reserva comandos; migration idempotente 147 registra funcionalidade v2.11.0 no DEV atual. Nenhuma dependência nova: wheels/NuGet existentes. Testes de fronteira .NET/Python/JS; TypeScript, ESLint por assinatura contra base, pytest completo e NUL. Browser em lote desktop/mobile claro/escuro com fixtures sintéticas; revisão independente de código/segurança/visual antes PR. Build dist por último. Merge em develop e DEV autorizados; main/Caixa exigem autorização própria. Pacote .NET offline reconstruído sem rede e smoke de disparo/logs/reprocessamento/negativas com pipeline sintético isolado.

Reserva de comandos serializada contra publicação e outras corridas. Requests guardam SHA-256 e versão/hash, sem conf persistida. Comando sem confirmação expira em erro e não permite nova reserva para reprocessar a mesma corrida: solicite nova corrida para evitar clear externo tardio. Reconciliador usa token/estado como fencing. O motor recusa comandos expirados e múltiplas corridas ativas de pipeline gerido.
