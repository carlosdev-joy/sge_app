# Header ORQ Navy — especificação recebida

Fonte: https://app.notion.com/p/3da9f9fc3e22816fa9c1f5ece718cd4a
Baseline: main39555e6, após merge PR410. Histórico F1/F2/F3 preservado.

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3da9f9fc3e22816fa9c1f5ece718cd4a as of 2026-09-13T22:13:37.057Z:
<page url="https://app.notion.com/p/3da9f9fc3e22816fa9c1f5ece718cd4a" icon="🎨">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3da9f9fc3e2281f791ffc01651b286a7" title="Orquestra — Identidade Visual e Login (equipe de agentes de IA)"/>
<ancestor-2-page url="https://app.notion.com/p/3da9f9fc3e2281b4a15efb16beb473e9" title="Orquestra"/>
<ancestor-3-page url="https://app.notion.com/p/3da9f9fc3e2281188c7ff4b3067b3731" title="Especificações"/>
</ancestor-path>
<properties>
{"title":"Especificação — Header ORQ Navy (evolução visual pós-F1/F2/F3)"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🎨"}</iconMetadata>
<content>
<callout icon="🎨" color="blue_bg">
	**Nova especificação independente.** Esta mudança não reabre F1/F2/F3 do header. A F1 já foi mergeada na PR #408, a F2 foi mergeada na PR #409 e a F3 está em PR própria (#410). Esta spec trata somente da evolução visual da cor do header após a conclusão dessas fases.
</callout>
## 1. Objetivo
Substituir o gradiente azul institucional legado do header por uma superfície **ORQ Navy**, alinhada à identidade visual já utilizada no painel esquerdo do login.
Objetivo visual:
- aumentar consistência entre Login e aplicação autenticada;
- reforçar ORQ como produto principal;
- reduzir aparência de header legado/CVP sem remover a identificação institucional da CAIXA;
- preservar toda a composição, responsividade e acessibilidade já entregues nas fases F1/F2/F3.
## 2. Baseline técnico
A implementação deve partir da `main` após as fases do header concluídas.
Histórico relevante:
- PR #406 — identidade ORQ + login acessível;
- PR #407 — responsividade do login em janelas baixas;
- PR #408 — Header F1: marca, composição responsiva e gradiente baseado nos tokens CVP;
- PR #409 — Header F2: controles, teclado, foco, notificações e perfil;
- PR #410 — Header F3: changelog/branding/acessibilidade; executar esta spec somente depois que a F3 estiver concluída/mergeada ou rebased sobre ela.
Não desenvolver esta alteração em paralelo modificando os mesmos blocos da F3 sem rebasing explícito.
## 3. Estado atual
A F1 adotou um gradiente derivado dos tokens CVP existentes, preservando a aparência azul institucional.
Isso foi correto para a fase de consolidação estrutural, mas não representa a decisão visual posterior de aproximar o shell autenticado da nova identidade ORQ.
O token já existente da identidade ORQ é:
`--brand-navy: 4 20 60`
Equivalente visual aproximado:
`#04143C`
Esse token já é utilizado no login e deve ser a referência primária desta mudança.
## 4. Decisão visual
### Fundo do header
Trocar o gradiente azul atual por **ORQ Navy sólido**, usando o token existente:
`background: rgb(var(--brand-navy))`
Não criar nova cor hex apenas para o header.
Não usar `cvp.blue`, `cvp.mid` ou `cvp.blued` como fundo principal após esta alteração.
### Por que sólido
A identidade do login usa o navy como superfície institucional principal. O fundo sólido:
- cria continuidade visual direta entre login e aplicação;
- melhora a leitura da marca e dos controles;
- reduz ruído visual;
- diferencia melhor ORQ da navegação antiga;
- evita criar um segundo gradiente sem necessidade.
Se durante validação visual for demonstrado que o sólido cria perda de hierarquia, qualquer variação deverá reutilizar tokens ORQ existentes e ser documentada antes do merge. Não criar gradiente arbitrário.
## 5. Elementos que permanecem
Preservar integralmente:
- altura do header em 52px;
- filete laranja inferior de 4px;
- composição CAIXA \| ORQ vX / Página;
- variante `header` do logo ORQ;
- título derivado de `NAV`;
- botão hambúrguer mobile;
- busca global;
- alternância de tema;
- notificações;
- perfil;
- responsividade entregue na F1;
- acessibilidade entregue na F2;
- changelog e semântica da F3;
- navegação SPA do Brand;
- RBAC;
- sidebar;
- login.
Esta spec **não é um redesign do header**. É uma mudança de superfície/cor com validação de contraste.
## 6. Logo ORQ no navy
Usar a variante já existente:
`<Logo variant="header" ... />`
Não criar novo asset e não reconstruir o logo.
Como o fundo ficará mais escuro que o gradiente atual, validar novamente:
- legibilidade do símbolo;
- ORQ branco;
- versão;
- divisor;
- título da página;
- ícones dos controles.
A implementação atual de `.orq-logo-header` deve ser preservada salvo defeito visual comprovado.
## 7. Marca CAIXA/CVP
A marca institucional permanece no header conforme regras responsivas da F1.
Não alterar asset, fallback ou tamanho nesta spec, salvo ajuste mínimo de contraste necessário e comprovado.
No mobile, continuam valendo as prioridades definidas anteriormente: ORQ não pode desaparecer e CAIXA pode compactar/ocultar conforme breakpoint já implementado.
## 8. Filete laranja
Preservar o filete laranja atual.
Ele passa a funcionar como acento institucional entre a superfície ORQ Navy e o conteúdo da aplicação.
Não aumentar espessura nem saturação nesta feature.
## 9. Tema claro/escuro
O header continua sendo uma **superfície fixa escura**, independente do tema da página.
Portanto:
- ORQ Navy deve ser o mesmo em light e dark mode;
- não criar `html.dark` específico para mudar a cor do header;
- dropdowns e conteúdo continuam seguindo seus próprios tokens de tema;
- alternância de tema não pode alterar o fundo do header.
## 10. Contraste
Executar validação de contraste após a troca.
Itens mínimos:
- texto principal branco sobre ORQ Navy;
- texto secundário/versão;
- divisor CAIXA \| ORQ;
- breadcrumb/título;
- busca global;
- ícone de tema;
- sino;
- contador de notificações;
- avatar/nome do perfil;
- estados hover/focus.
Não reduzir opacidade de elementos ao ponto de perder os requisitos de contraste existentes.
## 11. Hover e focus
Não aproveitar a troca de cor para redesenhar todos os estados.
Preservar estados existentes e ajustar somente se houver perda de contraste sobre o novo navy.
Preferir branco/transparência e tokens já existentes.
Não introduzir novos hex arbitrários.
## 12. Responsividade
Todos os breakpoints e regras de degradação da F1 permanecem.
Validar pelo menos:
- 1440px;
- 1280px;
- 1024px;
- 768px;
- 360px;
- 320px.
A mudança de cor não pode provocar alteração de largura, wrapping, altura ou ordem dos controles.
## 13. Escopo de código esperado
Alteração principal esperada:
- `ui-react/src/components/layout/header/HeaderV2.tsx`
Possível ajuste de estilo/token compartilhado apenas se necessário:
- `ui-react/src/index.css`
Testes/smokes/documentação:
- smoke visual/responsivo do header;
- evidência de contraste;
- `ui-react/dist/*` por último.
Não há necessidade prevista de alterar:
- `Logo.tsx`;
- `Brand.tsx`;
- `HeaderControls.tsx`;
- `NotificationsBell.tsx`;
- `ProfileDropdown.tsx`;
- `ChangelogModal.tsx`;
- `AppShellV2.tsx`;
- `nav.ts`;
- `theme.ts`;
- backend;
- login.
Se algum desses arquivos precisar mudar, documentar a razão antes do merge.
## 14. Critérios de aceite visual
- [ ] Header utiliza ORQ Navy como fundo principal.
- [ ] Cor vem de `--brand-navy`, sem novo hex duplicado.
- [ ] Gradiente CVP não permanece como fundo dominante.
- [ ] Filete laranja continua presente com 4px.
- [ ] CAIXA \| ORQ continuam legíveis e separados.
- [ ] Logo ORQ mantém alto contraste.
- [ ] Breadcrumb/título continua legível.
- [ ] Busca, tema, notificações e perfil mantêm leitura adequada.
- [ ] Light e dark mode usam o mesmo navy no header.
- [ ] Não há alteração de altura ou wrapping.
- [ ] Não há overflow em 320/360px.
## 15. Critérios de aceite técnico
- [ ] Nenhuma mudança de RBAC.
- [ ] Nenhuma mudança de navegação.
- [ ] Nenhuma mudança em polling/notificações.
- [ ] Nenhuma mudança em autenticação/logout.
- [ ] Nenhuma mudança no login.
- [ ] F1/F2/F3 continuam passando seus smokes/regressões.
- [ ] Build TypeScript/Vite aprovado.
- [ ] ESLint sem novos achados em relação ao baseline.
- [ ] Testes existentes sem nova regressão.
- [ ] Capturas desktop/mobile conferidas.
- [ ] Contraste documentado.
- [ ] `dist/` regenerada por último conforme padrão do projeto.
## 16. Ordem recomendada
1. Aguardar/concluir F3 (#410) para evitar conflito desnecessário.
2. Criar branch própria a partir da `main` atualizada.
3. Trocar somente a superfície do header para `rgb(var(--brand-navy))`.
4. Executar smokes F1/F2/F3.
5. Validar contraste e screenshots em light/dark.
6. Validar 320/360/768/1024/1440.
7. Rodar build, lint e suíte aplicável.
8. Fazer revisão adversarial.
9. Gerar `dist/` por último.
10. Abrir PR independente, sem misturar outras melhorias de shell.
<callout icon="⚠️" color="yellow_bg">
	**Importante:** a PR #408 já entregou e validou a F1. Esta nova decisão visual não deve ser aplicada alterando retrospectivamente a documentação ou o histórico da F1. Ela deve entrar como uma evolução independente, com PR e evidências próprias.
</callout>
## 17. Resultado esperado
Antes:
**header azul CVP em gradiente**
Depois:
**header ORQ Navy (#04143C via ****`--brand-navy`****) + filete laranja + identidade CAIXA \| ORQ preservada**
O resultado deve visualmente conectar a tela de login ao ambiente autenticado sem alterar o comportamento operacional do header.
</content>
</page>
