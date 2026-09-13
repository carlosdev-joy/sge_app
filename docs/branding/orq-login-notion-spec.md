Fonte: https://app.notion.com/p/3da9f9fc3e22819a8102edfa2efd27af?pvs=204
Capturada em 2026-09-13. Referência consolidada fornecida pelo usuário.

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3da9f9fc3e22819a8102edfa2efd27af as of 2026-09-13T18:42:42.867Z:
<page url="https://app.notion.com/p/3da9f9fc3e22819a8102edfa2efd27af" icon="🔐">
<ancestor-path>
<parent-page url="https://app.notion.com/p/3da9f9fc3e2281f791ffc01651b286a7" title="Orquestra — Identidade Visual e Login (equipe de agentes de IA)"/>
<ancestor-2-page url="https://app.notion.com/p/3da9f9fc3e2281b4a15efb16beb473e9" title="Orquestra"/>
<ancestor-3-page url="https://app.notion.com/p/3da9f9fc3e2281188c7ff4b3067b3731" title="Especificações"/>
</ancestor-path>
<properties>
{"title":"Especificação Final — Login ORQ (Visual aprovado + correções técnicas)"}
</properties>
<iconMetadata>{"type":"emoji","emoji":"🔐"}</iconMetadata>
<content>
<callout icon="✅" color="blue_bg">
	**Documento final para implementação.** A referência visual é a tela ORQ já aprovada. O desenvolvedor não deve redesenhar a experiência; deve aplicar os ajustes visuais descritos aqui e consolidar as correções técnicas levantadas na análise e no QA.
</callout>
## 1. Decisão de produto e escopo
O login mantém a estrutura em duas colunas. O painel esquerdo apresenta a plataforma; o painel direito prioriza autenticação rápida. A marca principal passa a ser **ORQ**. Não voltar para “Gestão de Pipelines”.
Assinatura institucional: **Plataforma de Orquestração de Dados, Processos e Inteligência** — sem ponto final quando usada como assinatura de marca.
A tela deve representar o ORQ atual: Pipelines, Chamados, Lineage, Desenvolvimento/ETL, Integrações e IA. A análise anterior constatou que os bullets antigos já não representavam o produto atual.
## 2. Visual aprovado — preservar
- Manter a composição visual já desenvolvida: painel navy à esquerda, formulário claro à direita, logo ORQ colorido, cinco pilares e onda tecnológica inferior.
- Proporção desktop de referência: **48% branding / 52% login**.
- Aumentar a composição do logo aproximadamente **5% a 10%**, preservando proporções e adicionando respiro abaixo.
- Logo é o primeiro elemento da hierarquia visual do painel.
- Ícones dos cinco pilares devem usar a mesma biblioteca, bounding box e `strokeWidth` (referência: 20px, 1.75–2).
- Onda inferior puramente decorativa, com opacidade de referência **0.40** e faixa recomendada 0.25–0.50; nunca competir com conteúdo.
- Manter azul vivo como cor da ação principal.
- Não introduzir animações pesadas, canvas ou WebGL; ambiente pode ser air-gapped.
### Variantes de marca
- **Login/institucional:** símbolo colorido + ORQ.
- **Header/nav escuro:** versão de alto contraste — ORQ branco e símbolo branco/ciano/azul-claro; evitar azul-marinho/violeta escuro sobre o header azul.
- **Fundo claro:** símbolo colorido + ORQ navy.
- **Favicon/sidebar recolhida:** símbolo isolado, validado em 16–32px.
- CAIXA e ORQ permanecem identidades separadas; não incorporar CAIXA ao símbolo ORQ.
## 3. Comportamentos existentes que não podem regredir
Preservar após validar no código atual:
- `autoFocus` na matrícula;
- `autoComplete` dos campos para gerenciadores de senha;
- aviso de Caps Lock via `getModifierState`;
- estado de loading no botão;
- fallback do logo institucional;
- fluxo pós-login baseado no RBAC existente, **sem assumir destinos específicos até validar ****`firstVisiblePath`**.
O QA encontrou divergência entre a documentação anterior e o comportamento real de `firstVisiblePath`; portanto, não alterar roteamento pós-login como efeito colateral deste trabalho.
## 4. Correção prioritária — tratamento do 401 no login
Existe um defeito estrutural no fluxo analisado: o cliente HTTP global intercepta 401 e chama expiração de sessão antes de o login receber o erro contextual. Na própria tela de login isso pode recarregar `/login`, perder a matrícula digitada e impedir a mensagem útil ao usuário.
### Implementação requerida
Criar um caminho dedicado de autenticação, por exemplo `apiLogin()` em `lib/api.ts`, que:
- reutilize o shaping de erro necessário;
- **não execute ****`expirarSessao()`**** para o 401 originado pela tentativa de login**;
- preserve `apiFetch` global para as demais telas, evitando regressão nas chamadas autenticadas;
- devolva ao Login status/erro suficiente para mensagem contextual;
- trate separadamente falhas HTTP e exceções de transporte/timeout.
Não editar o interceptador global de forma que altere silenciosamente o comportamento das demais telas.
## 5. Mensagens de autenticação
A UI deve diferenciar causas quando o backend/cliente conseguir identificá-las:
<table fit-page-width="true" header-row="true">
<tr>
<td>Condição</td>
<td>Mensagem</td>
</tr>
<tr>
<td>401</td>
<td>**Matrícula ou senha incorreta.** Use a mesma senha da sua rede corporativa</td>
</tr>
<tr>
<td>403</td>
<td>**Sua matrícula não tem acesso liberado.** Abra um chamado para a Engenharia de Dados</td>
</tr>
<tr>
<td>502</td>
<td>**Serviço de autenticação indisponível.** Não é a sua senha — tente em alguns minutos</td>
</tr>
<tr>
<td>500</td>
<td>**Não foi possível abrir sua sessão.** O problema é do sistema, não da sua senha</td>
</tr>
<tr>
<td>422 / validação</td>
<td>**Preencha matrícula e senha.**</td>
</tr>
<tr>
<td>Rede/transporte</td>
<td>**Não foi possível conectar ao ORQ.** Verifique sua conexão corporativa</td>
</tr>
</table>
**Regra de segurança:** o 401 deve usar sempre a mesma mensagem, independentemente de a matrícula existir ou não. Não revelar existência de usuário por mensagem, status visual ou mudança de foco.
O QA observou que timeout, DNS e conexão recusada podem não virar 502. Portanto, a implementação deve ter fallback explícito para exceções de transporte e não depender somente do status HTTP.
## 6. Validação dos campos
- Usar `<form onSubmit={...}>`; botão principal `type="submit"`.
- Enter em matrícula ou senha deve submeter normalmente; não criar listener global.
- Matrícula: validar também valor composto apenas por espaços antes da requisição. É permitido normalizar/trimar **somente a matrícula** conforme contrato atual.
- **Não aplicar ****`trim()`**** na senha**: espaços podem fazer parte da credencial e o backend atual os preserva.
- Senha inicia oculta.
- Toggle Eye/EyeOff deve ser `<button type="button">`, com `aria-label` alternando entre “Mostrar senha” e “Ocultar senha”.
- Ao submeter, considerar voltar a senha para estado oculto.
- Durante loading, desabilitar submit e impedir múltiplas requisições sem alterar a largura do botão.
## 7. Acessibilidade
- Labels associadas com `htmlFor` e inputs com `id`.
- Erro textual, nunca apenas cor.
- Container de erro com `role="alert"` e política única de `aria-live`; adotar **`polite`**** como padrão**, salvo validação de acessibilidade que justifique `assertive`.
- Focus visível e navegação integral por teclado.
- Não remover `outline` sem substituição acessível.
- Ordem lógica: Matrícula → Senha → Mostrar/Ocultar → Entrar.
- Validar contraste real dos controles. **Não assumir que ****`border-edge`**** atende 3:1**: o QA calculou contraste insuficiente para a borda proposta em claro e escuro. Definir/usar token de borda de input que passe no gate acessível nos dois temas.
## 8. Sistema de design e tema
A implementação atual do login deve deixar de usar cores arbitrárias quando já houver tokens semânticos equivalentes.
Preferir tokens do projeto para canvas, painel, borda, texto e cores CVP/ORQ, evitando hex literais espalhados no JSX. Porém, a migração não pode ser mecânica: cada token aplicado a input/foco/borda precisa passar contraste.
Adicionar/reusar alternador de tema usando a infraestrutura existente em `lib/theme.ts`, sem criar um segundo estado global de tema. Evitar flash branco no acesso de usuários que usam modo escuro.
## 9. Mobile e responsividade
- Desktop: duas colunas, aproximadamente 48/52.
- Tablet: manter duas colunas enquanto houver largura útil.
- Mobile: uma coluna, sem overflow horizontal.
- Não esconder completamente identidade/proposta do produto em mobile.
- Usar uma **faixa compacta de marca associada ao formulário** e preservar ORQ; os pilares podem ser condensados.
- Não assumir que o login atual está totalmente sem marca em mobile: a análise encontrou um bloco móvel existente. A correção é preservar melhor a proposta de valor, não duplicar branding.
- Testar reflow em **320 CSS px** e 360px.
## 10. Itens deliberadamente fora do escopo
Não adicionar sem backend/configuração correspondente:
- “Esqueci minha senha” — a autenticação usa credencial de rede/Airflow; recuperação não pertence ao ORQ;
- “Lembrar de mim” — TTL é controlado pelo sistema;
- SSO/MFA fictício;
- cadastro/autosserviço;
- link hardcoded de ServiceNow — a URL está em configuração administrativa e não há contrato público confirmado para expô-la;
- animações pesadas ou dependências externas/CDN.
A frase “fale com a Engenharia de Dados” não deve virar link inventado. Se houver um canal real já exposto pela configuração da aplicação, reutilizá-lo; caso contrário, manter orientação textual até existir contrato técnico.
## 11. Versão e informações de suporte
A análise apontou ausência de versão na tela. Exibir versão apenas por fonte pública e mínima apropriada para login. **Não reutilizar cegamente ****`/versao`**** se ele expõe changelog ou conteúdo interno em excesso**; o QA identificou esse risco. Se necessário, criar/usar resposta mínima segura (ex.: número da versão) conforme padrão do backend.
O texto “Pressione Enter para entrar” é dispensável tecnicamente e pode ser removido para reduzir ruído, já que o comportamento deve ser nativo do `<form>`.
## 12. Critérios de aceite
- [ ] Visual permanece aderente à tela ORQ aprovada; não houve redesign não solicitado.
- [ ] Logo e cinco pilares permanecem presentes no desktop.
- [ ] Proporção 48/52 aplicada ou ajustada apenas por necessidade responsiva documentada.
- [ ] Ícones possuem peso visual consistente e onda não compete com o conteúdo.
- [ ] Variante correta do logo é usada conforme fundo.
- [ ] `autoFocus`, `autoComplete`, Caps Lock e loading existentes não regrediram.
- [ ] 401 na tentativa de login não dispara reload/expiração global da própria tela.
- [ ] Matrícula digitada não é perdida após credencial inválida.
- [ ] 401 não permite enumeração de matrícula.
- [ ] 403, 5xx e falha de transporte têm tratamento distinto quando identificáveis.
- [ ] Matrícula vazia ou só com espaços não dispara requisição.
- [ ] Senha não sofre `trim()`.
- [ ] Eye/EyeOff usa `type="button"` e não submete o form.
- [ ] Erros são anunciados de forma acessível.
- [ ] Inputs/focus/bordas passam contraste nos temas claro e escuro.
- [ ] Tema reutiliza `lib/theme.ts` e não cria estado paralelo.
- [ ] Mobile preserva identidade, funciona em 320 CSS px e não possui overflow horizontal.
- [ ] Roteamento pós-login mantém o comportamento existente salvo mudança explicitamente aprovada e testada.
- [ ] Nenhuma dependência externa/CDN foi introduzida.
- [ ] Nenhum link ou integração inexistente foi inventado.
- [ ] Não houve alteração indevida na autenticação das outras telas.
## 13. Plano de implementação para o desenvolvedor
1. Ler `Login.tsx`, `lib/api.ts`, `lib/theme.ts`, `lib/nav.ts`, router e tokens atuais antes de alterar código.
2. Registrar o comportamento atual de login, 401, 403, falha de transporte e redirect pós-login.
3. Implementar primeiro o caminho dedicado de login/erro sem alterar `apiFetch` global.
4. Aplicar a tela visual já aprovada sobre tokens do projeto.
5. Implementar validação, acessibilidade, toggle de senha e tema.
6. Validar mobile e contraste.
7. Executar lint, typecheck/build e testes existentes.
8. Adicionar testes focados para autenticação e regressão quando a estrutura do projeto permitir.
9. Revisar o diff garantindo que não houve mudança incidental em autorização/RBAC.
10. Entregar relatório final com arquivos alterados, decisões divergentes, testes executados e evidência visual.
## 14. Evidências mínimas de teste
O desenvolvedor deve demonstrar, no mínimo:
- login válido;
- credencial inválida sem reload e sem perder matrícula;
- 403 quando reproduzível;
- 500/502 e falha de transporte com mocks/testes quando não for seguro provocar em ambiente;
- matrícula vazia e composta apenas por espaços;
- senha contendo espaços preservada;
- Caps Lock;
- toggle de senha sem submit acidental;
- Enter para login;
- loading sem duplo submit;
- tema claro/escuro sem flash indevido;
- teclado/focus/erro anunciado;
- 320px, 360px e desktop;
- usuário com diferentes permissões para confirmar que o redirect/RBAC não regrediu.
<callout icon="⚠️" color="yellow_bg">
	**Ponto de controle:** a revisão QA anterior reprovou o pacote porque havia requisitos contraditórios. Este documento resolve as contradições conhecidas e deve ser tratado como a referência consolidada. Se o código atual divergir de alguma premissa, o desenvolvedor deve preservar segurança/comportamento existente, documentar a divergência e solicitar validação antes de mudar contrato de autenticação, autorização ou RBAC.
</callout>
## 15. Entrega esperada
Ao final, retornar: resumo das alterações, arquivos modificados, dependências adicionadas (se houver), testes/validações executados, screenshots do resultado e qualquer ponto que ainda exija validação manual.
</content>
</page>
