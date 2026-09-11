# 📨 E-mail: prévia na tela, modelos institucionais e seletor de anexo

**Compatibilidade:** Apache Airflow 2.x | SQL Server | servidor de e-mail do próprio DataStage — nenhuma conta nova
**Migrations:** **112** (`112_email_modelos.sql`, F2) — deploy.sh etapa 6c, responder **s**
**Spec:** `docs/spec-email-modelos-e-navegacao.md` (F1 = #393 · F2 = #394 · F3 = #395 · F4 = esta PR)
**Manual:** `docs/MANUAL_USUARIO.md` §3.5-A (modelo, prévia e seletor de anexo), §4.10 (Admin: catálogo e padronização), §4.6 (deploy) e §5 (FAQ)
**Depende de:** a migration **111** e o canal de e-mail já configurados (`docs/release-notes/email.md`)

---

## 📋 Resumo

A notificação por e-mail (release anterior) entregou o canal. Esta trata de
**como as pessoas escrevem o aviso** — e tira delas o trabalho de escrever HTML.

Três coisas mudam no painel do nó de e-mail:

1. **Prévia na tela.** Vê-se a mensagem enquanto se escreve, alternando entre os
   marcadores e valores de exemplo.
2. **O corpo vira uma escolha.** Uma lista com os modelos do catálogo mais a
   opção *Corpo livre*. O nó novo já nasce no modelo padrão.
3. **O anexo se escolhe navegando.** Clica na pastinha, desce da pasta liberada
   até onde o arquivo está, clica nele — pasta e nome preenchidos de uma vez.

E uma no Admin: **Admin › E-mail › Modelos**, onde se mantém o layout
institucional, com a prévia ao lado do editor.

> **A decisão que atravessa as fases:** o nó guarda só o **id** do modelo, e o
> corpo é lido do banco **no envio**. Corrigir o layout no Admin vale para todos
> os fluxos que usam aquele modelo, já na corrida seguinte — sem republicar DAG
> e sem reabrir nó.

## 🔍 Como funciona

1. **`dbo.etl_email_modelo`** (migration 112) guarda os modelos: nome único,
   descrição, assunto sugerido, corpo, `html`, `ativo` e `padrao`. A migration
   **semeia** o modelo institucional já marcado como padrão.
2. O nó grava `modelo_id` dentro de `notify_json` — a mesma coluna de sempre.
   Nó gravado antes desta versão **não tem a chave**: entra como *Corpo livre* e
   envia exatamente o que enviava.
3. Na corrida, o `EmailOperator` lê o modelo pelo id e usa o corpo dele. A
   leitura **não filtra por `ativo`**, de propósito: desativar tira da lista de
   escolha sem quebrar quem já usa.
4. A chave `email_exigir_modelo` (em `etl_app_config`) é o endurecimento
   opcional: ligada, *Corpo livre* some da lista, e só continua visível para o
   nó que **já estava** nele — que segue salvando como está. Quem já escolheu um
   modelo perde o caminho de volta pela tela. Sem a migration 112 a chave não
   vale: sem catálogo não haveria modelo para escolher, e o nó novo ficaria
   insalvável.
5. `GET /email/anexo/listar` navega pelas pastas do anexo por SFTP, reusando
   `preparar_pasta`/`listar_pasta` dos Utilitários — mesma defesa contra escape
   de raiz, mesma auditoria. O que muda é de onde vêm as raízes
   (`email_anexo_raizes`) e a permissão (quem edita pipeline).

> **A prévia é um `<iframe>` isolado**, sem `allow-scripts` e sem
> `allow-same-origin` — o primeiro do produto. HTML de terceiro renderizado na
> tela de quem é administrador não pode executar nada nem enxergar a sessão.

## ⚠️ O defeito que não repetimos

O catálogo de cards do Teams, que já existe no produto, **degrada em silêncio**:
template apagado ou desativado faz o envio cair para a mensagem embutida, e o
aviso sai com a cara errada sem ninguém saber. Aqui:

- **apagar modelo em uso é recusado**, e a resposta nomeia os fluxos;
- **desativar** é o gesto de tirar de circulação: some da lista de escolha e
  quem já usa continua enviando;
- **modelo que sumiu faz a etapa falhar**, dizendo qual é. Chegar nesse estado
  significa que alguém apagou direto no banco — é erro, não rotina.

## 🚀 Deploy

Ordem sugerida, com o `./deploy.sh`:

| Etapa | Resposta | Por quê |
|---|---|---|
| `api/` | **s** | catálogo, régua do nó e a rota de navegação do anexo |
| `dist/` (front) | **s** | prévia, seção Modelos e o seletor de arquivo |
| `dags/` | **s** | `dags/utils/email_operator.py` e `email_envio.py` mudaram |
| **reiniciar o worker** | **obrigatório** | o worker **cacheia `dags/utils/`**: sem o restart a task fica verde rodando o código antigo, ignorando o modelo escolhido |
| `config/` | **n** | o `nginx.conf` de produção está à frente do repo |
| Migrations (**6c**) | **s** | aplica a **112** (tabela, chave e a semente do modelo institucional) |

**Nada a republicar.** Nó existente segue igual; quem escolher um modelo passa a
ler o layout do banco desde a primeira corrida.

## ✅ Conferência pós-deploy

Feita com um pipeline de teste, sem tocar em fluxo de produção. Os passos (g),
(h) e (i) mexem em configuração **global** (o catálogo e o interruptor): siga-os
até o fim, incluindo o que manda desfazer.

a) **Admin › E-mail › Modelos** abre e mostra *Aviso de fim de carga* como
   **padrão**. Se disser "aplique a migration 112", a etapa 6c não rodou.
b) Abrir o modelo: o corpo carrega e a **prévia aparece ao lado**. Fechar sem
   salvar.
c) Num pipeline de teste, arrastar um nó de **E-mail**: ele já nasce com o
   modelo padrão escolhido, e a prévia mostra o layout institucional.
d) Marcar **Anexar um arquivo do servidor** › **Navegar…**: a janela abre nas
   pastas de Admin › E-mail. Descer uma pasta e **clicar num arquivo** — pasta e
   nome são preenchidos. Se o nome tiver data, aparece a oferta de trocar por
   `{odate}`.
e) Salvar o fluxo, **publicar** e rodar. O e-mail chega com o layout do modelo e
   com o anexo.
f) ⭐ **A prova do vínculo vivo:** editar o corpo do modelo no Admin (trocar uma
   palavra do rodapé) e rodar a corrida de novo **sem republicar**. O texto novo
   tem de aparecer.
g) Tentar **excluir** o modelo, que está em uso pelo fluxo de teste: a exclusão
   é recusada nomeando o fluxo.
h) **Desativar** o modelo: ele some da lista de escolha do nó, e a corrida
   seguinte do fluxo que já o usa **continua enviando** igual.
   ⚠️ **Reative o modelo em seguida.** Enquanto o único modelo do catálogo
   estiver inativo, a lista de escolha fica vazia: todo nó novo volta a nascer
   em *Corpo livre* e os nós que já o usam passam a exibir o aviso de "fora da
   lista de escolha". Confira que a estrela de padrão voltou.
i) *(opcional, só se a padronização for a política escolhida)* Com o modelo
   **ativo** de novo, ligar **exigir modelo do catálogo**: um nó **novo** deixa
   de oferecer *Corpo livre* e abre em "Selecione um modelo…". Um nó que já
   rodava em corpo livre — se houver algum — continua salvando como está.
   Desligar depois, se a decisão ainda não estiver tomada.

## 🧯 Reversão

**O gesto mais barato quase nunca é reverter.** Desligar a padronização, ou
desativar um modelo, resolve na tela e na hora, sem mexer em pipeline nenhum.
Se a reversão for mesmo necessária, ela tem de ser **completa** — e tem um
efeito colateral que precisa ser conhecido antes:

- **Voltar só o `dist/` e a imagem da API NÃO faz o e-mail voltar ao corpo do
  nó.** Quem monta a mensagem é o **worker**: o `EmailOperator` continua lendo
  `modelo_id` e usando o corpo do catálogo. Para o layout antigo voltar é
  preciso restaurar também `dags/utils/` **e reiniciar o worker** — é o mesmo
  cache de `dags/utils/` do roteiro de deploy.
- **O texto do nó nunca foi apagado**: ele é gravado mesmo com um modelo
  escolhido, então voltar para *Corpo livre* (na tela ou por reversão)
  reencontra o que a pessoa havia escrito.
- ⚠️ **A reversão quebra o salvar de quem usa anexo em subpasta.** A versão
  anterior exige que a pasta do anexo seja **exatamente** uma das raízes
  liberadas; os nós que apontam para uma subpasta (o que o seletor da F3
  permite) passam a devolver 422 ao salvar o fluxo. O **envio** continua
  funcionando — só a edição é recusada. Antes de reverter, ou corrija esses nós
  para uma raiz exata, ou aceite que eles ficam sem poder ser editados até a
  volta da versão nova.
- **Migration 112**: não precisa reverter. A tabela e a chave ficam inertes sem
  o código que as lê.

## 📌 Fica registrado

- **Ficar sem padrão ativo** — por exclusão (quando não está em uso) ou por
  simples desativação — faz os nós novos voltarem a nascer em corpo livre, sem
  aviso; e, se era o único modelo, a lista de escolha fica vazia.
- As **raízes de anexo do e-mail** não passam pela lista de pastas proibidas dos
  Utilitários: `/etc` pode ser cadastrada em Admin › E-mail. A navegação é
  barrada pela conferência no servidor, mas o envio leria o arquivo — vale
  conferir a lista de pastas ao configurar.
- `acao_editar` passa a permitir **listar pastas por SFTP** (só as do e-mail),
  sem exigir `tela_utilitarios`.
