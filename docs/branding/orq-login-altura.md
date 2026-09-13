# Login ORQ em janelas baixas

A captura do usuário mostrou o cartão ultrapassando a altura útil do navegador.
O smoke reproduziu a regressão em 1580×730 antes da correção.

O layout considera altura além de largura: até 850 px compacta logo, margens e
onda decorativa; até 680 px em duas colunas preserva os cinco títulos sem suas
descrições. No celular até 740 px prioriza logo, posicionamento e formulário,
ocultando capacidades e instrução introdutória. Controles mantêm seus tamanhos.
A coluna mobile usa `minmax(0, 1fr)` para evitar corte lateral por largura
intrínseca. Alturas extremas e mensagens adicionais continuam roláveis.

Validação: build TypeScript/Vite; ESLint com 193 ocorrências antes/depois;
pytest com 5405 aprovados, 50 ignorados e as mesmas 8 falhas preexistentes.
Smoke de autenticação existente e `scripts/smoke_orq_login_height.py` com
1580×730, 1366×650, 1024×600, 768×600, 390×664, 360×640, 320×568,
667×375 e 800×300 em ambos os temas. Campos/botão cabem sem rolar nos
cenários usuais; teclado, Caps Lock e erro são exercitados também nos extremos.
Viewports reduzidos cobrem espaço equivalente ao zoom; não simulam teclado
virtual de um aparelho físico. Revisão adversarial aprovada.

Deploy: somente frontend, `ui-react/dist` versionado; sem migration/dependência.
Validação manual sugerida: abrir login na janela habitual, reduzir altura,
conferir matrícula/senha/Entrar, alternar tema e conferir navegação com Tab.
