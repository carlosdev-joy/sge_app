# Especificação Header ORQ — fonte recebida

Fonte: https://app.notion.com/p/3da9f9fc3e2281d1a138d4365eabff51
Captura: 2026-09-13. Baseline exigido: e09fc76.

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3da9f9fc3e2281d1a138d4365eabff51 as of 2026-09-13T20:50:36.669Z:
<page url="https://app.notion.com/p/3da9f9fc3e2281d1a138d4365eabff51" icon="🧭">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3da9f9fc3e2281f791ffc01651b286a7" title="Orquestra — Identidade Visual e Login (equipe de agentes de IA)"/>
<ancestor-2-page url="https://app.notion.com/p/3da9f9fc3e2281b4a15efb16beb473e9" title="Orquestra"/>
<ancestor-3-page url="https://app.notion.com/p/3da9f9fc3e2281188c7ff4b3067b3731" title="Especificações"/>
</ancestor-path>
<properties>
{"title":"Especificação Final — Header ORQ (Visual aprovado + validação técnica do sge_app)"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🧭"}</iconMetadata>
<content>
<callout icon="✅" color="blue_bg">
	**Baseline confirmado em ****`main`****.** Esta especificação foi atualizada após o merge da PR #407. A `main` atual está no commit `e09fc76e8451c47a6049acd46e7d589acc43a2b8`. A PR #406 entregou a identidade ORQ e o login acessível; a PR #407 complementou o login para janelas de menor altura e corrigiu clipping/overflow responsivo. Todo esse conjunto passa a ser **pré-requisito**, não escopo deste trabalho. A implementação do header deve partir exatamente dessa `main`.
</callout>
## 1. Objetivo
Consolidar o header operacional do ORQ usando a identidade que já entrou na `main`, corrigindo apenas o que ainda está pendente no header e componentes diretamente associados.
**Não redesenhar o login. Não recriar assets. Não reimplementar ****`Logo.tsx`**** do zero.**
Resultado visual desejado no desktop:
**CAIXA \| ORQ vX.Y / Página atual**                     **Busca \| Tema \| Notificações \| Perfil**
O header deve continuar fino, corporativo e operacional.
## 2. Baseline real da `main` — já entregue
As PRs #406 e #407 já consolidaram:
- marca principal **ORQ**;
- assinatura `Plataforma de Orquestração de Dados, Processos e Inteligência`;
- assets oficiais em `/images/orq/`;
- `Logo.tsx` compartilhado com variantes `white`, `brand` e `header`;
- `logo-name.png` e `logo-orbital.png`;
- favicon ORQ;
- fontes locais;
- tokens de branding/interação;
- variante de logo específica para o header;
- login acessível e responsivo;
- `apiLogin` isolado;
- endpoint público mínimo `/versao/publica` usado apenas no login;
- `usePublicVersion()`;
- contraste do header registrado como evidência da entrega;
- responsividade do login também por **altura útil**, não apenas largura;
- compactação progressiva do login abaixo de 850px e 680px de altura em desktop/tablet;
- em mobile baixo, priorização de marca, formulário e ação principal;
- correção da coluna mobile para `minmax(0, 1fr)`, evitando clipping por largura intrínseca;
- regressão Playwright específica para alturas e viewports reduzidos, incluindo 320×568, 360×640, 390×664, 667×375 e 800×300.
Portanto, nenhum desses itens deve voltar a ser tratado como problema a resolver nesta feature. Em especial, **não alterar ****`Login.css`**** para acomodar o header**: as regras responsivas de altura da PR #407 são baseline e devem permanecer intactas.
## 3. Arquitetura atual do header
O shell oficial continua:
`AppShellV2` → `HeaderV2` + `Sidebar` + conteúdo
O header está decomposto em:
- `ui-react/src/components/layout/header/HeaderV2.tsx`
- `ui-react/src/components/layout/header/Brand.tsx`
- `ui-react/src/components/layout/header/HeaderControls.tsx`
- `ui-react/src/components/layout/header/NotificationsBell.tsx`
- `ui-react/src/components/layout/header/ProfileDropdown.tsx`
- `ui-react/src/components/layout/header/ChangelogModal.tsx`
- `ui-react/src/components/layout/Logo.tsx`
Dependências compartilhadas relevantes:
- `ui-react/src/lib/nav.ts`
- `ui-react/src/lib/theme.ts`
- `ui-react/src/lib/version.ts`
- `ui-react/src/index.css`
- `ui-react/src/components/layout/AppShellV2.tsx`
Essa decomposição deve ser preservada.
## 4. Branding — o que já está correto
`Logo.tsx` na `main` já define:
- nome principal `ORQ`;
- assinatura institucional correta;
- assets oficiais fornecidos;
- `showText` para wordmark/símbolo isolado;
- `showSubtitle` opt-in;
- variante `header`.
O CSS atual também já possui `.orq-logo-header` para garantir contraste no fundo azul.
**Decisão:** preservar essa implementação. O header deve consumir `<Logo variant="header" ... />`; não criar um segundo SVG, segundo wordmark ou nova regra de branding.
## 5. `Brand.tsx` — principal ajuste estrutural
Estado atual:
- logo institucional CVP/CAIXA;
- `Logo variant="header" iconSize={28}`;
- versão via `useAppVersion()`;
- toda a composição está dentro de `<a href="/">`.
### 5.1 Composição final
Desktop/tablet, quando houver espaço:
**\[CAIXA\] \| \[ORQ\] vX.Y**
Depois, fora do componente Brand:
**/ Página atual**
Regras:
- CAIXA e ORQ continuam identidades independentes;
- inserir divisor vertical discreto entre CAIXA e ORQ;
- não exibir slogan no header;
- não exibir “Gestão de Pipelines”;
- versão é informação secundária;
- preservar fallback da marca institucional `/branding/logo-cvp.png` → `/images/logo-cvp.svg`.
### 5.2 Navegação SPA
Trocar `<a href="/">` por `Link` do `react-router-dom` para evitar reload completo e preservar o estado do shell.
Destino permanece `/`.
Não alterar `firstVisiblePath`, RBAC ou o comportamento do `HomeRedirect`.
### 5.3 Acessibilidade da marca
O link deve ter nome acessível explícito, por exemplo `aria-label="Ir para o início do ORQ"`.
Evitar depender apenas de `title`.
## 6. `HeaderV2.tsx` — preservar estrutura, refinar implementação
O código atual já faz corretamente:
- `<header>` semântico;
- hambúrguer apenas em mobile;
- marca à esquerda;
- título da página derivado do `NAV`;
- controles globais à direita;
- filete laranja institucional;
- altura de 52px + filete de 4px.
Tudo isso permanece.
### 6.1 Fundo
O gradiente atual é:
`#1A5FA8 → #0F4C88 → #0D3D6B`
Essas mesmas cores já existem como tokens `cvp.blue`, `cvp.mid` e `cvp.blued` no Tailwind.
**Correção:** remover a duplicação de hex inline e usar a fonte de design já existente, sem alterar visualmente o gradiente aprovado.
O header é superfície fixa escura, portanto `text-white/*` continua correto conforme `docs/ui-temas-cores.md`.
### 6.2 Filete laranja
Preservar exatamente o papel visual atual. Referência: 4px.
Não aumentar a altura total do header.
## 7. Título da página / breadcrumb leve
`HeaderV2` já usa `NAV.find(...)` com rota exata ou prefixo.
Preservar `NAV` como fonte única. Não criar uma segunda tabela global de nomes.
Desktop:
**ORQ vX / Utilitários**
Regras:
- separador `/` discreto;
- label com contraste alto;
- truncar quando faltar espaço;
- título some antes da marca e dos controles essenciais em viewport estreito;
- breadcrumb é apresentação, nunca autorização.
### Rotas internas de Caixa Seguro
O item raiz de `NAV` cobre `/caixa-seguro/*` como `Busca & Vendas`. Não ampliar o escopo desta feature para reconstruir a taxonomia interna. Se houver necessidade futura de título específico para subrota, tratar em spec própria ou mapa explícito pequeno, sem mexer no RBAC.
## 8. `HeaderControls.tsx` — preservar comportamento
O componente atual já concentra:
- Command Palette;
- `Ctrl+K` / `Cmd+K`;
- tema;
- notificações;
- perfil;
- logout.
Não duplicar essas responsabilidades no `HeaderV2`.
### 8.1 Command Palette
Preservar listener global atual.
Ajustes:
- adicionar `type="button"`;
- adicionar `aria-label="Abrir busca global"`;
- manter `title` como ajuda complementar;
- manter botão visual oculto em viewport pequena, sem desativar o atalho de teclado.
### 8.2 Tema
Preservar `getTheme()` e `toggleTheme()` de `lib/theme.ts`.
Adicionar `type="button"` ao trigger.
Não criar novo estado persistente de tema.
### 8.3 Logout
Preservar exatamente o contrato atual:
1. POST `/auth/logout` best-effort;
2. `logout()` do store;
3. saída para `/login`.
A troca para navegação SPA **não é obrigatória no logout** nesta feature, porque o reload após encerrar sessão é comportamento aceitável e isola estado autenticado.
## 9. Notificações — comportamento preservado, acessibilidade corrigida
O componente atual já implementa:
- polling de notificações e comunicados a cada 30s;
- refresh ao focar janela;
- contador agregado;
- marcação de visto/lido;
- toast de itens novos;
- banner de comunicado;
- navegação por link quando aplicável.
**Não alterar endpoints, polling, regras de leitura, confirmação ou toast.**
### Correções necessárias
- trigger do sino: `type="button"`;
- `aria-haspopup` apropriado;
- label dinâmica, por exemplo `Notificações, 3 não lidas`;
- manter `aria-expanded`;
- fechar dropdown por `Escape`;
- devolver foco ao trigger quando fechado via teclado;
- “Marcar todas como lidas” deve ser `type="button"`;
- itens acionáveis do feed não podem depender apenas de `div onClick`: usar `button`/`Link` ou implementar semântica e teclado equivalentes;
- itens sem ação podem permanecer conteúdo estático;
- não alterar a regra de confirmação de comunicados durante essa refatoração.
### Banner de comunicado
Não transformar o banner em um projeto de modal completo nesta feature. Corrigir somente regressões diretamente encontradas durante a alteração do header. Qualquer revisão extensa de focus trap/modal fica fora do escopo.
## 10. Perfil — corrigir branding residual e teclado
O dropdown atual preserva dados de usuário e histórico de versão, mas ainda contém branding antigo em texto.
### Correções obrigatórias
- trocar `ORQUESTRA v{appVersion}` por **`ORQ v{appVersion}`**;
- trigger com `type="button"`;
- `aria-haspopup`;
- nome acessível explícito;
- manter `aria-expanded`;
- fechar por `Escape`;
- devolver foco ao trigger após fechamento por teclado;
- botões “versão/changelog” e “Sair” com `type="button"`.
Não alterar:
- cálculo de iniciais;
- dados de matrícula/e-mail/perfil/área;
- mapeamento de perfil;
- lógica de logout;
- autorização/RBAC.
## 11. `ChangelogModal.tsx` — branding residual e acessibilidade mínima
A `main` ainda mostra:
**ORQUESTRA — Gestão de Pipelines**
Isso conflita com a identidade já entregue.
Trocar por:
**ORQ — Plataforma de Orquestração de Dados, Processos e Inteligência**
ou, se o espaço visual ficar melhor:
**ORQ**
com a assinatura institucional em linha secundária.
Preservar consulta autenticada a `/versao`; esse modal precisa do histórico completo.
### Acessibilidade mínima
- botão X com `type="button"` e `aria-label="Fechar histórico de versões"`;
- botão “Fechar” com `type="button"`;
- preservar Escape já existente;
- adicionar semântica de diálogo (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`) sem reescrever todo o modal.
Focus trap completo pode ser tratado separadamente se a infraestrutura atual não oferecer componente reutilizável.
## 12. Versão — decisão corrigida após o merge do login
Existem agora **duas fontes com responsabilidades diferentes**:
### Login público
`usePublicVersion()` → `/versao/publica`
Retorna somente o número e não expõe histórico.
### Área autenticada / header
`useAppVersion()` → `/versao`
Mantém histórico e calcula a maior versão numericamente; header, perfil e changelog compartilham a query `['versao']`.
**Decisão:** não migrar o header para `/versao/publica`. O header está dentro de `PrivateRoute` e deve continuar usando `useAppVersion()` para permanecer sincronizado com o changelog autenticado.
O fallback `1.0` atual permanece, salvo decisão separada de produto.
## 13. Responsividade — corrigida para a realidade do componente
A versão anterior da spec sugeria simplesmente manter marca completa no mobile. Isso não é suficiente porque `Brand` atual inclui CVP + ORQ + versão e pode disputar espaço com quatro controles.
### Desktop ≥ md
Exibir:
**CAIXA \| ORQ vX / Página atual** + controles completos
### Faixa intermediária
Ordem de degradação:
1. ocultar botão visual da busca (atalho continua);
2. ocultar breadcrumb/título;
3. ocultar nome textual do usuário, mantendo avatar;
4. somente depois compactar branding institucional.
### Mobile 320/360
Obrigatório não ter overflow horizontal.
Prioridades funcionais:
1. hambúrguer;
2. identificação ORQ reconhecível;
3. notificações;
4. perfil;
5. tema.
A marca CAIXA pode ser ocultada ou reduzida **somente no mobile** se necessário para atender 320px; ORQ não pode desaparecer.
A versão pode ser ocultada no menor breakpoint se necessário. O número continua disponível no perfil/changelog.
Não reduzir alvos de toque a ponto de comprometer usabilidade.
## 14. Dimensões e interação
Manter:
- corpo do header: 52px;
- filete: 4px;
- sem segunda linha;
- sem slogan.
Para controles por ícone, buscar área clicável mínima prática de aproximadamente 36px; em mobile, preferir 40px quando couber.
O tamanho visual do ícone pode continuar 15–20px.
## 15. Design system
Preservar a regra do repositório:
- `bg-canvas`, `bg-panel`, `border-edge`, `text-ink`, `text-dim` para superfícies que acompanham tema;
- header e perfil podem usar branco sobre gradiente azul porque são superfícies fixas escuras documentadas;
- notificações continuam usando `bg-panel/border-edge/text-ink`;
- evitar novos hex literais;
- não alterar tokens do login apenas para implementar o header.
Os tokens e regras `.orq-logo-*` que entraram na PR #406 e as regras responsivas de altura/clipping do login consolidadas pela PR #407 são baseline e não devem ser removidos ou enfraquecidos.
## 16. `AppShellV2` e Sidebar — fora do escopo
`AppShellV2` já resolve:
- drawer mobile;
- fechamento ao navegar;
- contenção de overflow;
- full bleed de Caixa Seguro.
Não modificar esse comportamento para implementar o header.
A Sidebar será tratada separadamente. Não aproveitar esta PR para reordenar menus ou mudar grupos.
## 17. RBAC e navegação — fora do escopo
Não alterar:
- `NAV`;
- `NAV_GROUPS`;
- `canAccess`;
- `firstVisiblePath`;
- `RequirePerm`;
- `HomeRedirect`;
- permissões do backend.
Os merges #406 e #407 preservaram deliberadamente esse comportamento. O header não é motivo para reabrir a decisão.
## 18. Escopo técnico esperado
Arquivos prováveis:
- `ui-react/src/components/layout/header/Brand.tsx`
- `ui-react/src/components/layout/header/HeaderV2.tsx`
- `ui-react/src/components/layout/header/HeaderControls.tsx`
- `ui-react/src/components/layout/header/NotificationsBell.tsx`
- `ui-react/src/components/layout/header/ProfileDropdown.tsx`
- `ui-react/src/components/layout/header/ChangelogModal.tsx`
- testes/harness específicos do header
- documentação da entrega
- `ui-react/dist/*` por último
`Logo.tsx` e `index.css` **não são alterações obrigatórias**: já contêm a identidade nova. Só modificar se um defeito concreto do header exigir, com justificativa e teste.
Não há necessidade prevista de:
- backend;
- migration;
- nova dependência;
- novo asset;
- alteração no login;
- alteração de autenticação.
## 19. Fases de implementação
### F1 — Brand + Header
- `Link` SPA no Brand;
- divisor CAIXA \| ORQ;
- responsividade do branding;
- gradiente usando fonte de design existente;
- preservar 52px + 4px;
- validar breadcrumb.
### F2 — Controles globais e acessibilidade
- tipos de botão;
- ARIA da busca/tema;
- Escape e foco em notificações/perfil;
- itens acionáveis do feed acessíveis por teclado;
- branding ORQ no perfil.
### F3 — Changelog + regressão
- branding ORQ no modal;
- semântica mínima de diálogo;
- testes do conjunto;
- screenshots desktop/mobile;
- revisão adversarial;
- build/dist.
</content>
</page>
