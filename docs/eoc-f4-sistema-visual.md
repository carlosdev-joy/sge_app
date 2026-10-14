# EOC-F4 — Contrato do sistema visual comum

Autoridade: SPEC consolidada §EOC-F4 e análise `docs/analises-ux-modulos-malha` (41ac369), `design-global/sistema-visual.md`, direção e arquitetura. A base é `src/index.css`, Tailwind e os componentes existentes; expansão de shell/Pipeline é F5. Não altera motor, rotas, RBAC, configuração de jobs ou canvas.

## Tipografia e ativos

Inter variável local, pesos 100–900, fallback system-ui; arquivos e licença OFL em `ui-react/public/fonts/`. Montserrat e os ativos ORQ preservam a identidade. Nenhum CDN/download em runtime. Raiz de 16px preserva unidades rem e zoom; conteúdo/controle 14/20px, ajuda 12/18px, título 24/32px, seção 16/24px. IDs/código conservam fonte mono do contexto. Texto longo quebra nos títulos/estados; inputs mantêm acesso ao valor completo pelo foco/seleção.

## Tokens e métricas

Canvas/panel/edge/ink/dim e action/control-border/focus são os pares existentes. Sucesso, warning, falha e informação possuem `*-ink`/`*-surface` claro/escuro; seleção usa action e não transforma estado operacional. Espaçamentos da base continuam 4/8/12/16/24/32px. Raio controle 6px, painel 8px, diálogo 12px. Transição 150ms; reduced-motion desativa movimento dos componentes novos.

| Métrica | Confortável | Compacta | Motivo |
|---|---|---|---|
| Controle normal | mínimo 40px | mínimo 32px | Legibilidade 14/20px, sem restringir texto multilinha |
| Controle pequeno | mínimo 32px | mínimo 32px | Ações de toolbar existentes, sem comprimir fonte para 12px |
| Controle grande | mínimo 44px | mínimo 44px | Ações destacadas |
| Linha Table | mínimo 44px | mínimo 36px | Cresce com conteúdo; `dense` é exceção explícita 36px |
| Grupo de campos | 16px | 12px | Separação entre campos sem margens extras no shell |
| Controle por toque | mínimo 44px | mínimo 44px | Media query pointer:coarse tem precedência sobre compacta |

A densidade é escolha local em **Perfil → Densidade da interface**, chave `orquestra-ui-density-v1` (dois valores conhecidos; inválido/storage indisponível usa confortável). Aplica antes do React para evitar salto inicial. Não armazena payload, agenda, seleção ou dados de negócio. Sincronização entre dispositivos e preferências de contexto pertencem à F21. A preferência compacta não reduz dimensões de nós nem painéis de canvas.

## Componentes e estados

Button mantém primary/secondary/danger/ghost e sm/md/lg, ref/handlers e semântica de submit do consumidor; loading preserva nome, desabilita ação e anuncia aria-busy. Input/Select/Textarea conservam props/ref/valores, possuem label persistente, help e erro associados por IDs; erro prevalece em aria-invalid sem perder descrições fornecidas pelo chamador. Read-only e disabled distinguem-se da edição.

Checkbox/Switch/Radio mantêm inputs nativos e foco visível no elemento visual. Tabs conservam callbacks e badges (neutro versus alerta), indicam destino atual com aria-current; não alegam tabpanel quando consumidores ainda são navegação. Table preserva compound API e rolagem dentro do wrapper. Modal/Sheet preservam pilha, Esc, trap e retorno de foco, aceitam títulos longos e close legível em ambos os temas. Toast mantém o contrato success/error/info e fecha pelo botão nomeado da aplicação. Autocomplete mantém busca/seleção e ganha label associado/controle comum. Badge mantém chaves/aliases e estado neutro desconhecido; nenhum estado passa a ser sucesso por ser lido ou selecionado.

Foco usa contorno de 2px com offset 2px, independente da borda neutra. Novas cores semânticas são medidas nas superfícies reais, junto de zoom 200%, nomes longos, teclado e temas. Arestas/agenda/execução não são modificadas por esta fase.

## Amostra reproduzível antes da expansão

`ui-react/examples/sistema-visual.html` carrega os componentes **reais**, com dados sintéticos e controles de tema/densidade. Servir via Vite local e abrir `/examples/sistema-visual.html`. Não é rota do produto, não usa API, não é ponto de entrada do build publicado. Exercita controles, estados, tabela, Tabs, Modal, Sheet, Toast e texto longo, sem criar job/enviar mensagem externa.

Validar em 1440/1280/947/390px, temas e densidades; zoom 200% real do viewport equivalente e checagem de tamanhos/foco. A amostra não prova conformidade global das páginas ainda não migradas: a F5 começa pela expansão de shell/Pipeline e as fases seguintes pelos demais módulos.

## Aceite do candidato 2.23.0

| Evidência | Resultado |
|---|---|
| Fonte/licença | Inter e Montserrat locais com OFL já distribuídos; nenhum novo ativo externo |
| TypeScript/build | `tsc -b` e distribuição final aprovados; amostra incluída na checagem de tipos |
| Lint | 176 ocorrências históricas; zero assinatura nova |
| Suíte | 7914 PASS, mesmos oito IDs de falha da base F3, 51 SKIP; nenhuma regressão |
| Direcionados | 202 PASS: rolagem/inputs sr-only, envio em loading e migrations idempotentes |
| Visual/teclado | 20 casos de temas/densidades em1440/1280/947/390 e720CSSpx/DPR2 (reflow equivalente a200%); sem overflow, alvos44px por toque, Modal/Sheet/Esc/retorno e persistência |
| Contraste da amostra | 32 amostras por tema: mínimo4,55:1 claro /4,83:1 escuro; foco visível em teclado; não equivale a certificação global |
| Nativo candidato sobre DEV | Fixture própria já arquivada, três nós; canvas630×584px antes/depois e em densidade compacta; perfil, temas e histórico de versões com foco legível; nenhum novo run ou comunicação externa |
| Revisão independente | Três achados corrigidos: esquema nativo herdado, foco dos overlays no header, alvo de fechar. Nenhum defeito material remanescente confirmado |

Evidências sanitizadas da rodada em `/root/orquestra-eoc-evidencias/f4/`: `suite-compare.json`, `lint-compare.json`, `rodada2/resultado.json`, `contrast.json`, `native-dev.json`, `independent-review.md`. As capturas da amostra são feitas depois do teste de reset, em densidade confortável; os valores de compacta/toque constam das medições anteriores à captura (Chromium pode normalizar pointer em full-page screenshot). `lineageIsx.ts` tem NUL pré-existente e permanece byte a byte igual; fontes alteradas não têm NUL.

Integração/publicação DEV seguem o roteiro da release2.23.0. A prova pós-deploy de SHA, versão, migration174 e assets é registrada separadamente em `dev-health.json` e `F4-concluida-DEV-2.23.0.md`; não confundir smoke do candidato com publicação concluída. Próxima expansão: EOC-F5, shell/menu/contexto e piloto Pipeline.
