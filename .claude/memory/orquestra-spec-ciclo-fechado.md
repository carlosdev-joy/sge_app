---
name: orquestra-spec-ciclo-fechado
description: "Spec APROVADA docs/spec-malha-operar-ciclo-fechado.md (PR #302) — reavaliar/concluir ciclo de malha já fechado; ✅ F0 MERGEADA (PR #303); nasce do caso Carga_Vida #4 (12/08); F1 em execução"
metadata: 
  node_type: memory
  type: project
  originSessionId: 952e78f2-488a-4865-83e8-88eb5dbfadc9
  modified: 2026-08-13T13:46:56.817Z
---

Spec em `docs/spec-malha-operar-ciclo-fechado.md`, **APROVADA pelo usuário em
2026-08-13** (PR #302 mergeada). Pedido: *"fechar a malha quando executada após
correções de falhas"*. Ver [[orquestra-sge-app]].

## Estado das fases

✅ **F0 MERGEADA (PR #303) e EM PRODUÇÃO (deploy 2026-08-13)** — os dois defeitos
vivos, mais duas correções que a revisão exigiu. Suíte 3168 (baseline 3157),
tsc 0, eslint no baseline. ⚠️ **Smoke não confirmado item a item**: é
observacional (não se provoca falha em produção) — o que prova a F0 viva é o
PRÓXIMO ciclo que fechar em FALHA emitir `MALHA_DESFECHO_FALHA` e **não** emitir
`MALHA_CONCLUIDA` do nó Fim.

🚧 **F1 em execução** — reavaliar o ciclo. F2–F5 a seguir.

## ⚠️ O caso que provou tudo (Carga_Vida, ciclo #4 de 2026-08-12)

Linha do tempo REAL do banco de produção — vale mais que a spec inteira:
01:10 ciclo abre · 04:30 `3RECEBIMENTO`+`6SINISTRO` partem · 04:45 **falham** →
`PREDECESSOR_FALHOU` em `PEPS`/`COBERTURA` · **07:13 a guardiã fecha FALHA** ·
09:52 e 11:10 os pais concluem **SUCESSO** · 11:10 `COBERTURA` conclui SUCESSO ·
22:51 `PEPS` conclui SUCESSO · 23:00 o nó Fim anuncia **"ciclo concluído"**.

**Os 4 pipelines terminaram em SUCESSO, nenhum com `substituida_em`.** O verde
já existia no banco; só o veredito ficou congelado — sentenciado 16h antes do
fim real do trabalho. **O pedido não era carimbar sucesso: era poder reavaliar.**

## 🐛 Dois defeitos VIVOS em produção (achados no levantamento)

1. **O nó Fim anuncia conclusão sobre ciclo fechado em FALHA.** A guarda "não
   anunciar com membro vivo" está inteira dentro de `if aberta is not None:`
   (`guardia.py:1496`) — ciclo fechado ⇒ `corrida_aberta` devolve None ⇒ guarda
   não roda. E numa malha **com nó Fim** o observador é a **ÚNICA** fonte do
   evento (`tipo = "MALHA_CONCLUIDA" if corrida["no_fim"] is None else None`,
   `guardia.py:1328`): a única fonte é justamente a sem guarda. Vai ao Teams
   como ✅ *"Nada a fazer — a malha terminou o ciclo."*
2. **O fechamento em FALHA é MUDO** (`so_se_primeira_falha=True`,
   `guardia.py:1075`): alerta já emitido ⇒ desfecho sem evento. Por isso a linha
   do tempo do ciclo #4 só tem o "fim" verde das 23:00.

## A causa raiz do fecho prematuro

`_quiescencia_liberada` adia o fecho **só** quando `liberado()` aprova alguma
linha `AGUARDANDO` — isto é, que vai partir **agora**. A guardiã distingue "vai
partir" de "não vai partir", mas **não conhece "pode partir se alguém
consertar"** — e falha de predecessor é o estado mais reexecutável que existe.

## Por que nenhum caminho existente resolvia

- **Finalização Manual** só alcança linha `EXECUTANDO`/`RUNNING` (404 sem alvo) e
  declaradamente não fecha corrida ("Fechar é da guardiã, sempre — Decisão 19").
- **`POST .../encerrar`** fecha com desfecho FIXO `CANCELADA` e **recusa 422
  ciclo já fechado**.
- **Rerun com cascata** é o ÚNICO que reabre ciclo, mas atrás de `if cascata:`
  **e** `if n > 0:` — e `n = marcar_substituidas(info["com_corrida"])`.
  ⚠️ **Dependente que `nao_partiu` não tem corrida a aposentar ⇒ `n = 0` ⇒ o
  efeito nunca roda.** A condição que bloqueia o conserto é a MESMA que causou a
  falha. Ver [[orquestra-spec-corrida-malha]].
- `mc.fechar_corrida(...,'CONCLUIDA')` tem **1 chamador de produção** (a
  guardiã) e `SQL_FECHAR` exige `fechada_em IS NULL`: **não existe transição
  terminal→terminal no produto**. A spec preserva isso (reavaliar passa por
  ABERTA).

## Decisões do usuário (2026-08-13)

1. Investigar o fecho prematuro — **sim**, vira a F3.
2. Permissão **`acao_executar`** (mesmo nível de disparar) — ⚠️ **diverge da
   #301, que propõe `acao_admin`; as duas precisam de resposta coerente**.
3. Janela: **até a virada do ciclo seguinte**, recusa nominal depois.
4. Teto vencido: **estender na reabertura** — sem isso, reabrir ciclo com teto
   vencido deixa a guardiã fechar **`EXPIRADA`**, que NÃO está em `REABREM` e é
   fim de linha irreversível.

## Fases

**F0** falso verde do Fim + desfecho que se anuncia + portão que fala (é
correção de defeito vivo, não feature — precede até a #301) · **F1** reavaliar
(reusa `reabrir_corrida`+`descartar_desfecho`, estende teto) · **F2** prévia
honesta + adoção das linhas órfãs · **F3** carência da guardiã (a causa raiz;
fase de risco) · **F4** concluir manualmente com desfecho próprio
`CONCLUIDA_MANUAL` (exceção) · **F5** manual/smoke/aceitação.

## Lições da F0 (pagas em 2 rodadas de revisão adversarial)

- ⚠️ **Guarda posta em laço compartilhado atinge quem não devia.** A guarda do
  nó Fim ficou antes do `if obs["tipo"] == "notificacao"` e emudeceu também o
  aviso — cujo contrato ("os P ∈ U que alimento concluíram") continua VERDADEIRO
  num ciclo que deu errado por outro ramo. Agravante: a cláusula **desiste**, não
  adia → apagaria aviso legítimo para sempre.
- ⚠️ **Leitura que degrada larga torna guarda nova INERTE.** `corrida_aberta` e
  `corrida_da_data` devolviam `None` tanto para "não existe" quanto para "não
  consegui ler" — e `None` fazia a guarda não rodar. Conserto: parâmetro
  `sentinela_erro` (default preserva chamadores) + `ERRO_LEITURA`, o padrão que
  `_quiescencia_liberada` já usava. **Quando criar guarda, verificar as DUAS
  leituras que alimentam a decisão** — o revisor achou a gêmea uma linha acima.
- ⚠️ **Tipo de evento novo precisa de rótulo E cor no front**, senão chega cru
  (`MALHA_DESFECHO_FALHA`) em cinza de informativo. `ROTULO_EVENTO_CORRIDA` +
  `estiloEvento` em `components/malhas/statusExecucao.ts`.
- ⚠️ **Comentário entre `case`s empilhados dispara `no-fallthrough`** no eslint —
  pôr o comentário acima do grupo.
- ⚠️ **`git add -u` não pega bundle novo da dist** (nasce untracked): commitaria
  o `index.html` novo + a remoção do antigo e deixaria o novo de fora → **tela
  branca** após o deploy. Usar `git add -A` e conferir que o bundle referenciado
  no `index.html` está no índice.
- ✅ **Teste que reprova a própria mudança é sinal bom**:
  `test_interruptor_desligado_deixa_o_rerun_exatamente_como_antes` estava certo —
  com o interruptor em 0 a feature não existe no ambiente, e avisar seria ruído.
- ✅ **Dublê que devolve o que o chamador pediu prova o argumento, não só o
  efeito**: `lambda ..., sentinela_erro=None: sentinela_erro` falha se o chamador
  esquecer de passar o sentinela.
- A paridade das duas árvores passou a comparar **assinaturas** (`inspect`), não
  só nomes — a F0 criou o primeiro parâmetro opcional capaz de divergir, e o port
  da API não tem chamador que denuncie.

## GOTCHAs que a spec paga

- **Linha nascida depois do fecho fica com `malha_execucao_id` NULL**
  (`_dona_do_odate` só aceita dono de ciclo ABERTO) — no ciclo #4 são 3 das 5.
- **Contadores NÃO delatam o carimbo**: `SQL_ESTADO` de ciclo fechado não tem
  teto superior (`malha_corrida.py:1454-1457`) mas a lista do painel tem
  (`_ESCOPO_PAINEL_FECHADA`) → cabeçalho tende a "13 de 13" sob chip vermelho.
- **`fechada_por LIKE 'manual:%'` não discrimina gesto humano**: `EXPIRADA` e
  `ABORTADA` já gravam esse prefixo em fechamentos automáticos.
- **Status novo em `etl_pipeline_execucao` é PIOR**: a 067 não tem CHECK — entra
  em silêncio e todo leitor que compara `='SUCESSO'` ignora a linha.
- **Carimbar SUCESSO na linha É soltar a cadeia** (`liberado()` e
  `_rede_seguranca` só olham status/data) — por isso ficou fora do escopo.
- **`duration_seconds` de relógio envenena p50/SLA por 90 dias** — a Finalização
  Manual já faz isso (`finalizacao.py:313`).
- Achado colateral: **`GET /audit` sem autenticação** (`infra.py:199-203`).

Ver [[orquestra-spec-malha-reset-forca]] (§9 da spec: separadas, contrato
compartilhado, #301 primeiro), [[orquestra-modos-de-falso-verde]],
[[orquestra-deploy-trem-producao]].
