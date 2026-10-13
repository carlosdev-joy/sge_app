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
Visão geral | Montagem | Execução | Configuração | Versões
Fonte/revisão/editor/salvo (resumo curto)
Biblioteca        | Desfazer/Refazer | Organizar | Mais
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
Visão geral | Montagem | Execução | Configuração | Versões
Corrida selecionada | Histórico | Última atualização / conexão
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
**Configuração:** navegação interna Identificação, Agenda/dependências, Parâmetros, Políticas de execução, Notificações e Documentação. Um grupo ativo por vez e barra Salvar comum. Nome e contexto sempre visíveis.
**Versões:** lista, estado de confirmação e comparação. Restore abre novo draft e preserva histórico; sem botão que prometa reverter execução ativa.
**Histórico em Execução:** abre sob demanda; clique seleciona a corrida no visualizador operacional comum; filtros de data/status/versão e retorno preservados. Logs e tentativas ficam no inspector da etapa, com ampliação contextual.
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


## Referência interativa
O [protótipo de Pipeline](../prototypes/pipeline-workspace/README.md) materializa a composição e as principais interações desta proposta. Sua [verificação e capturas](../prototypes/pipeline-workspace/VALIDACAO.md) distinguem o que foi testado do que é conceitual. Validar com o usuário antes de adaptar as telas React do produto. Nenhuma integração com DEV foi realizada.


## Preservação funcional e revisão de navegação — 11/10/2026
Decisão do usuário: Montagem e Execução são abas principais. Histórico/logs integram Execução, sem uma segunda faixa de modos. O inventário dos 11 componentes, oito agendas, sessão, publicação e ações operacionais está na [matriz de preservação funcional](../matriz-paridade-pipeline.md). Essa matriz é requisito para implementação: reduzir densidade não autoriza perder campos, payloads, permissões ou funcionalidades. Integrações e campos especializados não cobertos pelo protótipo permanecem pendências explícitas.


## Estado de implementação — entrega 1 (11/10/2026)
Base `develop` `df1a81ca`; documentos `52c0c589`. Implementado com tokens e componentes existentes (`bg-panel`, `border-edge`, `text-ink`, `text-dim`, Button/Input/Select/Textarea; pares claro/escuro em toda cor de paleta):
- Casca do Pipeline: breadcrumb com domínio, título com rótulos "Ambiente da aplicação", contexto (rascunho/publicado/corrida) e "Alterações não salvas"; identificador técnico em monospace abaixo; ações frequentes no cabeçalho (sessão de rascunho na Montagem/Configuração, Executar na Execução).
- Abas `Visão geral | Montagem | Execução | Configuração | Versões`; foco visível nas abas e na navegação de grupos.
- Configuração com navegação interna (coluna de 208px no desktop, faixa rolável no móvel) e um grupo por vez; barra de status com Salvar rascunho comum; JSON em Avançado.
- Montagem com grid 160/1fr/260 (lg) e 192/1fr/320 (xl), alvo do contrato; ferramentas de importação e ordem abaixo do canvas.
- Execução sem biblioteca, toolbar de montagem ou formulário de pipeline; alternância Gráfico | Tabela e logs.

Não implementado nesta entrega: barra Salvar/Validar/Publicar unificada, painel de validação recolhível, recolher biblioteca/inspector, inspector operacional com abas, movimento/estados F5. Capturas comparativas ainda não registradas.

## Estado de implementação — F4.1 (candidato 2.19.0)
- Workspace do Pipeline sem a moldura de 1600 px do shell: margem lateral compacta `px-3 sm:px-4` (12/16 px, sempre menor que o `p-6` anterior); Visão geral, Configuração e Versões limitadas à largura útil anterior (1552 px), com cabeçalho e abas estáveis entre destinos.
- Montagem: grade 160/1fr/260 (lg), 192/1fr/320 (xl) e 216/1fr/352 (2xl); painel recolhido sai da grade. Alternadores Componentes e Propriedades na barra do canvas, com o localizador de etapa e Organizar. Biblioteca e inspector com rolagem interna no desktop. Altura do canvas `max(470px, 100dvh − 26rem)`; na Execução `max(620px, 100dvh − 21rem)`.
- Cabeçalho: Salvar rascunho, Validar rascunho e Publicar versão (primária quando permitida). Validação e publicação abaixo do canvas, recolhível, com resumo de uma linha.
- Pendentes: desfazer/refazer, inspector em subseções e modo focado (F4.2); painéis recolhíveis da Execução e inspector operacional com abas (F5); capturas comparativas com o mockup 02.

## Estado de implementação — F4.2 (candidato 2.20.0)
- Inspector com cabeçalho (nome, tipo, Expandir propriedades, Fechar), nome para exibição e subseções Configuração | Etapa | Lineage | Avançado em abas sublinhadas (`aria-pressed`, `aria-controls`). Subseção visitada fica montada e oculta; overlays dela só ativos quando visível. Marcador âmbar e texto acessível indicam alterações não aplicadas.
- Aplicar e Descartar alterações no rodapé de cada subseção, com a frase única "Aplicar inclui na Montagem desta aba; Salvar rascunho persiste e Publicar é uma ação separada."
- Desfazer/Refazer como botões de ícone (32 px) depois do título do canvas, com dica do passo e do atalho; aviso de passo desfeito ou histórico reiniciado numa linha de status sob a barra.
- Modo focado: a coluna do inspector ocupa a grade, com a mesma altura do canvas e conteúdo limitado a 1024 px; biblioteca e canvas ficam ocultos e montados. Sem modal.
- Diagnóstico mostrado no topo do inspector em vermelho com par claro/escuro.
- Pendentes: capturas comparativas com o mockup 02 e revisão no navegador real.

## Estado de implementação — F2 (candidato 2.22.0)
- **Lista**: título, uma frase de propósito e, à direita, *Lista clássica* (link discreto) e *Novo pipeline* (primária, só com edição). Busca principal com ícone. Situação em botões com `aria-pressed` e *Filtros* recolhível (projeto, domínio, limpar). Linha de status `aria-live` com o intervalo, por exemplo "51–100 de 123 · atualizando…".
- **Linhas**: no desktop (≥1024 px), a lista é uma grade de cinco colunas (Pipeline, Situação, Projeto e domínio, Atualização, ações), e cada linha herda as colunas com `subgrid`, alinhadas mesmo com ações de largura variável. Abaixo disso, a linha empilha os blocos com rótulos visíveis. O nome amigável fica em 14 px e semibold, com o identificador em monospace de 12 px quando difere. A situação usa pílulas de 12 px com ícone e par claro/escuro: verde para publicado, azul para em desenvolvimento, âmbar para em edição e neutro para inativo e ainda não publicado. Nada depende de `title` ou hover.
- **Ações**: *Continuar montagem* (primária pequena) só com rascunho e edição, *Abrir montagem* quando outra pessoa edita, e *Mais* (menu do DS, com nome acessível "Mais ações de <pipeline>"). Foco visível em links, botões e filtros.
- **Erro e vazio**: callout vermelho com o motivo do 503, *Tentar novamente* e *Usar lista clássica*. Vazio com filtros oferece *Limpar filtros*; sem nenhum pipeline, *Novo pipeline*.
- **Criação**: grade com identificação à esquerda e resumo à direita (340 px, fixo no desktop), como no mockup 04, sem as escolhas *Carga de dados* e *Importar fluxo*, que não existem no produto. O identificador sugerido fica em só leitura até *Editar identificador*. Um cartão *Fluxo em branco* explica o começo. Resumo acessível dos erros no topo do formulário, campo marcado e foco no primeiro inválido. Rodapé com *Cancelar* e *Criar e abrir montagem*.
- Verificado em Chromium com APIs sintéticas (1440 claro e escuro, 1280, 947 e 390 claro e escuro, sem overflow horizontal). Os passes visuais e a comparação lado a lado com o mockup 04 são do root.
