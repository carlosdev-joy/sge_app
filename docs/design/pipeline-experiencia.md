# Contrato de experiência visual — Pipeline ORQUESTRA
Data:2026-10-11 · Estado: proposta detalhada para revisão
Complementa [spec-ux-pipeline-profissional.md](../spec-ux-pipeline-profissional.md). Referências aprovadas em [mockups/pipeline-workspace](../mockups/pipeline-workspace/README.md).

## Autoridade e objetivo
Os mockups01/02/04 definem a composição desejada. Este documento transforma essa referência em hierarquia, comportamento e aceite. Tokens/controles existentes fornecem a implementação clara/escura; a proposta organiza responsabilidades e não cria nova marca.
Quando a documentação anterior descreve apenas “preservar a interface incumbente”, esta proposta explicita a reorganização solicitada pelo usuário. Durante revisão, nenhuma regra nova é apresentada como já implementada.
O futuro DESIGN.md pode apontar para este contrato, tokens existentes e demais superfícies. Um arquivo global de design não substitui especificação por tarefa/tela.

## Casca e identidade
- Marca ORQ/ORQUESTRA e elementos corporativos aprovados permanecem. Navegação lateral tem hierarquia discreta; ação primária não compete com cabeçalhos de seção.
- No Pipeline, breadcrumb, nome amigável, identificador técnico copiável e contexto. Uma linha principal e uma linha auxiliar, sem repetir estado em três blocos.
- Nomear “Ambiente da aplicação: Desenvolvimento” e “Destino: PROD/DEV/HML” quando ambos são necessários. Não oferecer seletor de produção com aparência de simples tema.
- Rascunho: revisão, salvo/alterações locais e usuário que edita. Execução: corrida, data e versão executada. Permissões não são derivadas desses rótulos.
- Botões frequentes fixos na região de ações; secundários no menu Mais. Ações negadas não aparecem como atalhos utilizáveis; leitura permanece acessível conforme autorização.
- Perfil de experiência permanece ajuste pessoal de entrada/prioridade, discreto, sem competir com fonte/versão. A mudança não concede capacidade.
- Não remover destinos globais de outros módulos nesta fase. Publicação global é histórico técnico da fábrica; publicação de versão ocorre no Pipeline.

## Tipografia, superfície e densidade
Fontes atuais já incluem Inter/Montserrat localmente; corpo global usa system-ui. Proposta: Inter no workspace e controles, fallback system-ui; preservar tratamento da marca. Sem download remoto. Testar métricas/compatibilidade antes de aplicar em casca global.
Escala: título24px/600; seção16px/600; conteúdo/controles14px; metadado12px. Evitar texto9–10px para status e ações essenciais. Identificador/comando usa monospace apenas onde ajuda.
Grade de espaçamento4/8/12/16/24px; campo principal mínimo36px, alvos de interação pelo menos24×24px ou espaçamento equivalente, foco visível. Mobile usa44px para controles de toque frequentes.
Reutilizar tokens semânticos de ui-react/src/index.css e tailwind.config.js:
| Token | Claro | Escuro |
|---|---|---|
|canvas|rgb(248,250,252)|rgb(15,17,23)|
|panel|rgb(255,255,255)|rgb(26,29,39)|
|edge|rgb(226,232,240)|rgb(42,45,58)|
|ink|rgb(30,41,59)|rgb(226,232,240)|
|dim|rgb(100,116,139)|rgb(148,163,184)|
Ação usa --action/--action-strong/--control-focus existentes. Estados operacionais usam contrato compartilhado atual; medir contraste em ambos os temas, corrigindo o token comum quando necessário. Não copiar hexadecimal isolado por tela.
Bordas leves e grupos por função. Não transformar todo campo num cartão, nem acrescentar sombras/gradientes sem função. Contraste de texto normal alvo4,5:1; componentes/ícones funcionais3:1.

## Composição desktop: Montagem
Em1440×960 e1280×800, sem depender de zoom do navegador:
```text
Casca
Breadcrumb | nome/contexto                 Salvar | Validar | Publicar
Visão geral | Fluxo | Execuções | Configuração | Versões
Fonte/revisão/editor/salvo (resumo curto)
Biblioteca        | Montagem / Execução | Desfazer/Refazer | Organizar
recolhível        | Canvas dominante                    | Inspector
                  |                                     | da etapa
                  | Validação recolhível                | selecionada
```
Biblioteca alvo192–224px; inspector320–360px; canvas recebe largura restante. Permitir recolher ambos e modo focado; dimensionar por largura disponível, sem prometer3colunas quando o canvas fica inutilizável.
Em tela desktop, identidade, abas, ações e parte utilizável do canvas devem estar presentes sem rolar por formulários de governança. Altura deriva do viewport e da casca; rolagem interna de biblioteca/inspector; sem overflow-hidden que corte menus/sticky.
Painel inferior fechado ocupa uma linha de resumo; aberto usa altura limitada com rolagem própria. Erros/avisos por severidade; clique seleciona etapa/campo. Publicação em progresso permanece legível mesmo recolhido.
Nó horizontal compacto (alvo176–208px), ícone do tipo, nome amigável, tipo e estado quando em execução. Nome pode quebrar em duas linhas; identificador completo no inspector/cópia, sem reduzir fonte essencial.
Arestas ortogonais, direção legível, nomes de saídas de decisão. Seleção tem destaque distinto do estado de sucesso/falha; selecionar um nó verde não remove a indicação de sucesso.
Minimap e zoom acessíveis; zoom não muda ao atualizar estado. Início/Fim meramente visuais só se identificados como marcadores: nunca criar etapas executáveis ou sucesso fictício.

## Inspector de Montagem
Sem seleção: orientação curta e contexto do rascunho. Não ocupar painel com cadastro completo.
Com seleção: nome/tipo, configuração principal, conexões, parâmetros/vínculos, políticas de etapa e Lineage em subseções. Formulários dos11tipos preservam campos desconhecidos e dados atuais.
Operações normais no inspector; campos extensos podem abrir modo focado da mesma área. Modal para confirmação destrutiva, segredo protegido e importação excepcional. Evitar modal dentro de modal.
Aplicar incorpora edição local ao draft; Salvar persiste a revisão; Publicar confirma nova versão pelo processo existente. Explicar essa distinção uma vez no lugar da ação.
Remover e JSON em ações avançadas, não competindo com configurar. Desfazer/refazer oferece ação somente para alterações locais elegíveis.

## Composição desktop: Execução
```text
Nome | corrida | data | versão              Executar | Mais
Fluxo [Execução]      Última atualização / conexão
Resumo curto de estado e contagens confiáveis
Canvas operacional dominante                Inspector
                                            Resumo / Tentativas / Logs
Visão alternativa: tabela | histórico       Ações autorizadas
```
Sem biblioteca editável, sem toolbar de montagem e sem formulário de pipeline. Selecionar etapa abre investigação na direita; abrir log conserva gráfico/run/etapa/tentativa e pode expandir painel.
Estado da corrida tem rótulo e ícone; “Solicitado”, “Em fila” e “Executando” são diferentes. Botão recebido não significa que o motor começou.
Não mostrar simultaneamente gráfico e tabela completa das mesmas etapas. Tabela é alternativa para busca/triagem, com mesma seleção e corrida.
Reprocessar não se confunde com executar tudo. Explicar escopo antes da confirmação; respeitar limitações de versão/cascata atuais.

## Movimento e confiabilidade
- Running confirmado: indicador discreto no nó e rótulo Executando; ciclo suave1,5–2s, sem deslocar layout. Sucesso é check/verde sem pulsação.
- Ramo pulado/estado desconhecido não recebe animação de execução. Histórico encerrado não pulsa como atividade atual.
- Transição de cor curta150–200ms; novo estado acessível por texto/ícone. Não usar animação para fabricar progresso.
- Dados indisponíveis: manter último estado com carimbo e aviso; suspender indicador de atividade atual até revalidar. Preservar semântica histórica do status.
- prefers-reduced-motion: sem pulso/movimento; ícone/texto sustentam a mesma informação.
- Não anunciar cada polling em leitor de tela; anunciar mudança relevante da etapa selecionada/publicação via região acessível.
- Origem/frescor aparecem no resumo; logs escapados como texto. Mensagens resumidas primeiro; detalhe técnico/copiar sob demanda.

## Demais telas do Pipeline
**Lista:** busca principal, filtros adicionais recolhíveis, uma linha por Pipeline, nome amigável/técnico, estado, responsável, editor e atualização. Entrar pelo nome; ações secundárias em menu. Rascunho novo deve ser localizável sem histórico do navegador.
**Criação:** identificação essencial à esquerda e resumo útil à direita (referência04); nenhuma lista extensa de política/agendamento antes de começar.
**Visão geral:** finalidade, dono, versão e relações. Resumo de configuração com Editar configuração. Não replicar controles da aba Configuração.
**Configuração:** navegação interna Identificação, Agenda/dependências, Parâmetros, Execução, Notificações e Documentação. Um grupo ativo por vez e barra Salvar comum. Nome e contexto sempre visíveis.
**Versões:** lista, estado de confirmação e comparação. Restore abre novo draft e preserva histórico; sem botão que prometa reverter execução ativa.
**Execuções:** histórico filtrável; clique abre visualizador operacional comum; filtros de data/status/versão e retorno preservados.
**Ferramentas:** conteúdo atual vira ajuda contextual/ações apropriadas. Sem aba inteira que apenas encaminha a outras abas.

## Responsividade, teclado e erro
947px: biblioteca em drawer e inspector adaptável; não empilhar biblioteca inteira antes do canvas. 390px: canvas focado, botões para biblioteca/inspector e detalhes em área acessível; sem overflow horizontal do documento.
Abas possuem contexto acessível e rolagem local se necessário. Dropdown respeita viewport; ações não desaparecem sob teclado virtual.
Seleção/localizador oferece alternativa ao drag; controles zoom e foco não exigem mouse. Delete só remove seleção do gráfico fora de input/textarea; confirma remoção conforme regra atual.
Escape fecha painel/modal adequado, foco retorna ao gatilho; Tab não se perde. Erro de campo associado ao rótulo. Indisponibilidade oferece tentar novamente sem perder trabalho.
Nenhuma mudança de UI dá autorização de publicação/execução; backend controla capacidades.

## Aceite visual e de tarefas
Para cada tela/estado, evidência corresponde à mesma largura/tema e fixture. Comparar com referência01/02/04 e registrar diferença intencional por limitação real, nunca aprovar só por semelhança de cores.
Verificar: criar→retomar, iniciar edição→configurar→salvar, montar→validar erro→corrigir, publicar→confirmar versão, solicitar execução→acompanhar, falhar→investigar tentativa/log, consulta por outro usuário, conflito/reconexão.
Medir sucesso da tarefa, tempo, retornos desnecessários e dúvidas com representantes dos três públicos; ausência de representante é pendência explícita, não sucesso presumido.
Capturas obrigatórias: montagem vazia/populada/seleção/diagnóstico, configuração, publicação pendente/erro, execução running/success/failure/skipped/fonte indisponível, inspector/log, lista com draft, versões.
Simulações testam estados/UI; execução real própria testa integração. Cada registro identifica qual tipo de evidência é.
