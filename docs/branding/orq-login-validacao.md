# Login ORQ — entrega da especificação final

Referência: [Especificação Final — Login ORQ no Notion](https://app.notion.com/p/3da9f9fc3e22819a8102edfa2efd27af).
Captura integral em `orq-login-notion-spec.md`. Este documento consolida os ajustes
sobre o visual aprovado e substitui as observações técnicas anteriores de `orq-login.md`.

## Resultado

- Duas colunas em 48/52, logo aumentado de 110 para 120px (+9,1%) e assinatura sem ponto.
- Cinco pilares no desktop, Lucide 20px/stroke 1.8; onda decorativa com opacidade .40.
- Mobile com marca/assinatura compactas e nomes dos cinco pilares; descrições condensadas
  e onda omitida no mobile para priorizar o formulário. Reflow em 320 e 360px.
- Logo original colorido no login e variante branca sobre o header, sem fundir CAIXA e ORQ.
  Fallback institucional CVP mantido; símbolo isolado inspecionado em 16/32px.
- Matrícula com autofocus/autocomplete; senha com autocomplete, Caps Lock e toggle acessível.
- Validação local impede matrícula vazia/só espaços; somente matrícula recebe trim.
- Senha volta a ficar oculta ao submeter. Ref síncrona impede duplicação da requisição.
- Erro textual `role=alert`, `aria-live=polite`, descrições vinculadas aos inputs;
  ordem de teclado Matrícula → Senha → Toggle → Entrar, foco visível.
- Tema usa `lib/theme.ts`; bootstrap mínimo anterior ao bundle lê a mesma chave `theme`.
- Botão continua azul vivo nos dois temas. Tokens de borda/foco medidos, não apenas presumidos.

## Autenticação e segurança

`apiLogin` usa fetch dedicado para `/auth/login`, sem token antigo nem expiração global.
401 mantém o documento, matrícula e senha digitados, com mensagem fixa independente do
`detail` recebido. 403, 422, 500, 502/503/504 e transporte têm mensagens contextuais.
Timeout de 30s, cancelamento via AbortController e falha de leitura do corpo são tratados;
resposta inválida é recusada. A UI não exibe mensagens internas do backend.

`apiFetch` e `apiFetchBruto` não foram alterados: nas demais telas, 401 continua expirando
a sessão. Não foram modificados backend de autenticação, autorização nem `firstVisiblePath`.

Divergência documentada: a ordem real de NAV determina [] → `/dashboard`, permissão
`tela_utilitarios` → `/utilitarios`, apenas `tela_chamados` → `/avisos` (rota anterior
sem permissão específica). Esses destinos foram preservados e comprovados no navegador.

O novo `GET /versao/publica` retorna somente `{versao: número-ou-null}`; seleciona só a
coluna de versão, permite apenas versão numérica e usa a maior versão numérica como o
header. Nunca entrega changelog, autor ou configuração. Sem dados/banco indisponível,
retorna null e o login omite o número; não inventa uma versão. O login não chama `/versao`
nem `/config`. Esse endpoint é adicional e não altera as rotas existentes.

## Arquivos relevantes

- `ui-react/src/lib/api.ts`: transporte dedicado e mensagens de login.
- `ui-react/src/lib/publicVersion.ts`, `api/routers/infra.py`: versão pública mínima.
- `ui-react/src/pages/Login.tsx`, `Login.css`: formulário, validação, tema e composição.
- `ui-react/src/index.css`, `ui-react/index.html`: tokens, variantes de logo e bootstrap do tema.
- `ui-react/src/components/layout/Logo.tsx`, `header/Brand.tsx`: assinatura e contraste.
- `tests/js/login_api_harness.cjs`, `tests/test_login_orq.py`: regressão e endpoint mínimo.
- `scripts/smoke_orq_login.py`: evidências reproduzíveis com API simulada.
- `ui-react/dist/`: build regenerado. Logos/fontes/fundo locais da primeira entrega preservados.

Dependências adicionadas nesta correção: **nenhuma**. Sem CDN, migration, wheel ou links inventados.

## Validação

- `npm run build` / `tsc -b`: passou. Aviso de tamanho de bundle já existente.
- ESLint: 193 apontamentos, baseline 195; zero novos por arquivo/regra/mensagem/severidade.
- Pytest completo: **5405 passed, 8 failed, 50 skipped**. Baseline: **5398/8/50**;
  mesmas oito falhas identificadas, sete novos testes passando.
- Harness executa `api.ts` real: falha na versão anterior sem apiLogin; passa na atual.
  Demonstra isolamento do 401 de login e preservação do interceptador global.
- Revisão adversarial independente: **APROVADO**, nenhum defeito confirmado.
- Chromium: 320/360/768/1440px, claro/escuro, sem overflow; proporção 48/52;
  bootstrap escuro antes do bundle, persistência de tema, versão sem histórico,
  ordem de foco, validação, toggle, senha com espaços, loading sem duplo submit,
  401 sem reload, 403/422/500/502/rede, sucesso e três conjuntos de permissões.
- Bordas renderizadas: **3,91:1 claro**, **6,17:1 escuro**; foco também acima de 3:1.
- `git diff --check` e inspeção de bytes NUL nos fontes alterados.

### Evidências visuais

- [Desktop claro](screenshots/login-claro.png)
- [Desktop escuro](screenshots/login-escuro.png)
- [Mobile 320px](screenshots/login-mobile-320.png)
- [Mobile 360px escuro](screenshots/login-mobile-360-escuro.png)
- [Mensagem de erro](screenshots/login-erro.png)
- [Header com contraste](screenshots/header-contraste.png)
- [Símbolo em 16 e 32px](screenshots/simbolo-16-32.png)

As capturas/testes usam contas, respostas e versão fictícias. Não foram usadas credenciais
reais nem provocadas falhas reais no serviço corporativo.

## Deploy e validação manual

Frontend + API para disponibilizar `/versao/publica`. Sem migration/configuração.
No DEV, a API usa imagem Docker: rebuild/recriar o serviço e reiniciar o nginx de UI
para atualizar a resolução do IP da API. O build do frontend é servido por volume.

Antes de produção: validar uma credencial corporativa real, gerenciador de senhas e
anúncio com leitor de tela da organização. Testes automatizados verificam os atributos
e a interação, mas não substituem esse aceite assistivo. Deploy/merge seguem o fluxo
de autorização do projeto; nenhum ajuste foi enviado à produção nesta etapa.
