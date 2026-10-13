# Sistema visual global proposto

Parâmetros abaixo são candidatos de design; não tokens já implementados. Valores finais exigem validação visual com conteúdo real, zoom e temas. Reutilizar a base de `ui-react/src/index.css`, `tailwind.config.js` e `docs/ui-temas-cores.md`.

## Tipografia

No SHA auditado, corpo usa system-ui; Montserrat e Inter têm declarações locais de @font-face para identidade ORQ. A proposta preserva a marca e unifica o conteúdo operacional com uma família já distribuída. Recomendação: experimentar Inter local no conteúdo e controles, com system-ui como fallback. Essa é uma escolha de continuidade com os ativos existentes, não necessidade de adicionar fonte externa. Confirmar arquivos/licença e métricas antes de alterar globalmente.

| Papel | Tamanho / linha candidatos | Peso | Aplicação |
|---|---|---|---|
| Título de página | 24 / 32px | 600 | Um por tela; nomes muito longos quebram linha |
| Título de seção/painel | 16 / 24px | 600 | Configuração, propriedades, diagnóstico |
| Conteúdo e controles | 14 / 20px | 400/500 | Forms, tabelas, menus e tarefas |
| Ajuda/metadados | 12 / 18px | 400 | Informação secundária; nada essencial depende de texto diminuto |
| Valor/KPI principal | 28 / 36px | 600 | Somente quando o número orienta decisão |
| Código/log | 13 / 20px | 400 | Família monoespaçada local/sistema, editor ampliável |

Usar sentence case; evitar rótulos longos em caixa alta. Limitar linhas de ajuda a cerca de60–80 caracteres. Usar tabular-nums em duração, horários e contadores. Truncamento tem tooltip/acesso ao texto completo; ID técnico pode ser copiado e nome pode quebrar. Não reduzir tudo para12px para caber mais.

## Superfícies, marca e estado

| Papel | Claro atual | Escuro atual | Diretriz |
|---|---|---|---|
| Canvas | #F8FAFC | #0F1117 | Área de trabalho/fundo |
| Panel | #FFFFFF | #1A1D27 | Navegação, formulários, inspector |
| Edge | #E2E8F0 | #2A2D3A | Separação; borda neutra não substitui foco |
| Ink | #1E293B | #E2E8F0 | Texto principal |
| Dim | #64748B | #94A3B8 | Secundário; validar contra superfície real |

Esses cinco pares foram conferidos na fonte; tokens action/focus/control-border e marca também já existem. Aproveitar seus valores vigentes em vez de inventar azuis isolados. Todos os novos tokens precisam de par claro/escuro e função definida.

Seleção usa borda/foco de ação e indicação textual. Sucesso, falha, aviso e execução usam ícone+texto+cor, com preenchimentos suaves. Neutro não significa sucesso. “Aguardando recurso”, “Aguardando dependência” e “Agendado” têm textos distintos; estado deve vir do motor. Não codificar onze tipos apenas por onze cores.

## Espaçamento e densidade

Escala candidata:4,8,12,16,24,32px. Ícone16–20px; raio de controle6px, painel8px, modal12px. Bordas1px; sombra apenas para elevação real (menu, modal), não em todas as caixas.

| Elemento | Confortável | Compacto | Regra |
|---|---|---|---|
| Controle | 40px altura | 32px em desktop | Conteúdo/ações essenciais não encolhem abaixo do legível |
| Linha de tabela | 44px | 36px | Conteúdo de múltiplas linhas expande |
| Espaço entre campos | 16px | 12px | Grupo semântico separado por24px |
| Margem de página | 24px | 16px em viewport reduzido | Evitar margem repetida em shells aninhados |
| Cabeçalho global | alvo56px | igual | Sem múltiplas barras redundantes |
| Biblioteca | alvo240px | recolhível | Redimensionável dentro de limites testados |
| Inspector | alvo360px | alvo320px | Conteúdo pode exigir ampliação; não ocultar campos |

São dimensões de partida das pranchas. Densidade é preferência global de apresentação; não deve reduzir alvos de toque. Nas interfaces por toque, projetar alvos de44px como meta interna. Medir contraste, foco e ampliação na validação; não declarar conformidade a partir destes números.

## Menus e ações

Uma navegação global para destinos e uma navegação contextual para o objeto. Sidebar recolhível mantém rótulo acessível; grupo expandido não exige abrir um submenu para toda ação frequente. O usuário deve reconhecer Pipeline e Malha antes de seus detalhes técnicos.

Menus de overflow guardam ações ocasionais. Salvar/publicar/investigar necessários à jornada não desaparecem todos atrás de reticências. Ações indisponíveis mostram motivo quando ajudam a decidir; permissões sensíveis não são descobertas por tentativa. Perigo exige linguagem explícita e tratamento compatível com a reversibilidade/contrato real.

## Tipos de objeto no desenho

| Objeto | Representação candidata | Informação mínima |
|---|---|---|
| Pipeline em uma malha | Contêiner com ícone de fluxo e limite distinto | Nome, referência/versão, estado da instância quando operacional |
| Etapa executável | Retângulo sóbrio, ícone do tipo, cabeçalho uniforme | Nome, tipo técnico, resumo curto e estado quando aplicável |
| Decisão | Nó com marca visual de decisão; portas rotuladas | Expressão resumida, Sim/Não/casos/default sem alterar ordem |
| Aguarde | Nó de junção com ícone de sincronização | Política de liberação e dependências |
| Notificação/E-mail | Mesmo modelo básico, ícone de comunicação | Tipo/canal, sem expor destinatários sensíveis |
| Referência reutilizada | Ícone e metadado de referência | Origem e versão; não parecer cópia local |
| Execução | Faixa/estado no mesmo nó, sem trocar identidade | Corrida, estado e duração/contexto |

Preservar DataStage, Python, Shell, Stored Proc, REST, SQL, Decisão, Aguarde, Valida Arquivo, Notificação e E-mail. Ícones/categorias ajudam a leitura; não substituem tipos, schemas, saídas e formulários. Pipeline/Malha não devem virar novos tipos de etapa por decoração.

Arestas dirigidas com rota previsível; rótulos perto da origem para ramos. Diferenciar seleção de estado. Pan/zoom/fit minimap quando necessário, busca e alternativa por lista/teclado. Rearrange só altera layout quando esse é seu contrato. Usar agregação em malhas grandes, sem fingir que dependências ocultas desapareceram.

## Componentes a uniformizar globalmente

Button, Input, Select/Autocomplete, Tabs, Table, Badge, Banner, Hint, DropdownMenu, Modal, Sheet, Toast, Skeleton, Empty/Error State e Focus Ring. Os correspondentes existentes em `src/components/ui/` são ponto de partida. Variantes devem ter finalidade (primário/secundário/perigo; confortável/compacto), não nomes de páginas.

Formulário: label persistente, ajuda abaixo, erro junto ao campo, resumo acessível para múltiplos erros; avançado recolhível com aviso quando contém valor configurado. Tabela: cabeçalho consistente, filtros próximos, status legível, ações alinhadas, colunas opcionais/redimensionáveis conforme contratos. Modal curto para confirmação; Sheet para configuração contextual; tela própria para edição longa. Não transformar todos os fluxos em modais.

Loading preserva estrutura sem inventar dados; vazio diferencia ausência de itens de filtro sem resultado; erro permite tentar novamente e voltar; stale/offline mostra atualização/fonte; read-only identifica modo e motivo; dirty identifica mudança pendente; seleção e foco têm estados diferentes. Toast não é único lugar de informar falha relevante.

## Movimento e acessibilidade

Transições curtas de120–180ms como candidato, sem deslocar foco ou esconder o resultado da ação. Indicador de execução só para execução confirmada; respeitar reduced-motion e evitar movimento contínuo em dezenas de nós. Não usar pulso para telemetria indisponível.

Validar teclado completo, foco visível, leitura de rótulos, ordem de tabulação, contraste nos dois temas, zoom200%, nomes longos, tradução, modal/escape e alternativa ao drag. Conteúdo operacional importante não pode depender apenas de hover, cor, animação ou ícone.
