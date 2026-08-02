# 🔗 Nó Aguarde — ponto de encontro entre pernas paralelas

**Compatibilidade:** Apache Airflow 2.x | SQL Server
**Migration:** 068
**Spec:** `docs/spec-no-aguarde.md`

---

## 📋 Resumo

Fluxos com etapas em paralelo agora podem ter um **ponto de encontro**: um nó que
segura o fluxo até que todas as pernas ligadas a ele terminem, e só então libera o
que vem depois.

O caso que motivou a feature: dois processos rodam ao mesmo tempo usando os
**mesmos arquivos de trabalho**, e a remoção desses arquivos só é segura quando os
dois acabaram. Apagar antes corrompe quem ainda está lendo.

```
   ┌── Carga_Clientes ──┐
───┤                    ├── ▮ Aguarde ── Limpa_Arquivos
   └── Carga_Contratos ─┘
```

> **Impacto para engenheiros ETL:** deixa de ser necessário serializar etapas que
> poderiam rodar em paralelo só para garantir a ordem da limpeza.
>
> **Impacto para a operação:** a limpeza de arquivos temporários pode rodar mesmo
> quando uma das pernas falha — sem que isso esconda a falha do pipeline.

---

## 🎯 A decisão que importa: o que fazer quando uma perna falha

Cada nó Aguarde tem uma política, escolhida no painel:

| Política | Comportamento | Quando usar |
|---|---|---|
| **Só seguir se todas derem certo** (padrão) | Se qualquer perna falhar, o que vem depois não roda | O passo seguinte depende do resultado das pernas |
| **Seguir assim que todas terminarem, mesmo com falha** | Libera o passo seguinte deu certo ou não | O passo seguinte é **limpeza** |

⚠️ **A segunda opção não deixa o pipeline verde.** A etapa que falhou continua
marcada como falha, o alerta de erro sai normalmente e o pipeline termina em erro.
A única coisa que muda é que o passo seguinte ao Aguarde roda assim mesmo.

Essa garantia é estrutural, não uma promessa: o registro de conclusão de cada perna
continua ligado direto ao fechamento do pipeline, sem o Aguarde no meio — e há teste
automatizado travando esse desenho.

---

## 🖥 Na tela

No editor de fluxo, o **Aguarde** aparece no grupo *Fluxo* da paleta, ao lado de SQL,
Decisão e Notificação. Ele é desenhado como uma **barra vertical** atravessada no
caminho — a leitura visual de "aqui as pernas se encontram".

- **Ele espera só quem está ligado nele.** O que não tiver uma linha chegando ao
  Aguarde não é esperado.
- **Prender as pontas soltas** — botão no painel que liga ao Aguarde tudo que está
  solto no fluxo, de uma vez. As ligações ficam desenhadas no canvas; a barreira
  nunca vira dependência invisível.
- A política aparece no próprio card do nó, sem precisar abrir o painel.

**Avisos de montagem** (anel âmbar no nó):
- Aguarde **sem nenhuma etapa ligada** — o fluxo não salva
- Aguarde **com uma etapa só** — salva com aviso: não junta nada
- Aguarde **sem nada na saída** — salva com aviso: não segura ninguém

---

## 🚀 Deploy

⚠️ **A ordem importa:**

1. Aplicar a **migration 068** (etapa 6c do `deploy.sh`)
2. Subir API + front
3. **REGERAR as DAGs** — o gerador mudou, mas as DAGs já geradas **não mudam
   sozinhas**. Sem este passo, nada acontece.
4. Validar em **um pipeline de teste** antes da malha inteira

**Rollback:** remover o nó do fluxo e regerar a DAG. A coluna `aguarde_json` pode
ficar — é inerte para quem não usa o nó.

---

## 🧪 Qualidade

- **73 testes novos** entre as três fases
- Matriz de **12 combinações** (3 políticas × com/sem decisão × com/sem notificação)
  que compila **e importa** a DAG gerada — pega erro de carga que a análise
  sintática não vê
- **Teste-âncora** travando o invariante de que a política tolerante não esconde
  falha de pipeline
- Pipelines **sem** o nó Aguarde geram DAG idêntica à anterior
