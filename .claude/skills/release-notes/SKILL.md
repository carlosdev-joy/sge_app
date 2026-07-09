---
description: >
  Gera release notes de versão do ORQUESTRA e sincroniza a documentação de usuário.
  Use quando o usuário pedir "release notes", "fechar versão", "changelog",
  "notas da versão", "documentar a release" ou após um conjunto de entregas merged.
argument-hint: "<versao ex: 2.4.0>"
---

# Release notes — ORQUESTRA

Modelo a seguir: `docs/release-notes/v2.2.0.md` (estrutura, tom e nível de detalhe).

## 1. Levantar o conteúdo
- Mudanças desde a última release:
  ```bash
  ls docs/release-notes/          # última versão documentada
  git log --oneline --no-merges vANTERIOR..HEAD 2>/dev/null || git log --oneline --no-merges -40
  ```
- Agrupar por tema (governança, operação, segurança, UX, correções) — não por commit.

## 2. Escrever `docs/release-notes/vX.Y.Z.md`
Estrutura do modelo:
- Cabeçalho: título temático, data, versão, compatibilidade.
- **Resumo executivo** (2-3 parágrafos) + blocos "Impacto para gestores" / "Impacto
  para analistas e engenheiros ETL".
- Seções por tema com emoji, explicando **o que muda na prática** (não o diff técnico).
- Correções relevantes com o sintoma que o usuário percebia (ex.: "cards duplicados
  no Teams") — não o nome interno do bug.
- Público: gestores e usuários, não só devs. Tom: claro, pt-BR, sem jargão de código.

## 3. Sincronizar documentação (não pule)
- `docs/MANUAL_USUARIO.md` — se alguma tela/fluxo mudou para o usuário final.
- `docs/ORQUESTRA_Funcionalidades_e_Beneficios.md` — se há funcionalidade nova ou
  benefício mensurável novo; atualizar a linha "Versão de referência" no topo.
- Versão exibida na UI (header mostra `vX.Y.Z` — procurar a constante no frontend e
  atualizar; recompilar `dist/`).

## 4. Validar e entregar
- `/revisao-pr` antes de commitar; commit no estilo do projeto; nunca push na `main`.
- Perguntar ao usuário se quer também um resumo curto para e-mail/Teams da release.
