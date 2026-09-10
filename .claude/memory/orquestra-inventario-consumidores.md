---
name: orquestra-inventario-consumidores
description: "Tela Inventário de Consumidores do Orquestra (PR #149, main): endpoints → views/procs do BUCC, com seed do incidente NUM_CPF_CNPJ de 2026-07-02"
metadata: 
  node_type: memory
  type: project
  originSessionId: 37110f94-a212-4226-818b-0a3933cf5eb7
---

Tela **Inventário de Consumidores** no Orquestra ([[orquestra-sge-app]]): cadastro de quais endpoints/serviços consomem quais views/procs de um banco (caso motivador: **BUCC**), para alterações de schema serem feitas primeiro nos consumidores e por último no banco. Mesclada na main em 2026-07-02 (PR #149): migration 055 (`etl_inventario_endpoint` + `etl_inventario_objeto`, RBAC `tela_inventario` p/ admin/desenvolvedor), router `api/routers/inventario.py`, página `/inventario` (grupo Governança & Dados), docs em `docs/inventario-consumidores-bucc.md`.

**Why:** Incidente de 2026-07-02 — restauração do backup do BUCC (com DBA); dúvida sobre o formato de `NUM_CPF_CNPJ`: ficou **VARCHAR preservando zeros à esquerda** (PF 11 dígitos, PJ 14), porque o GI devolve os dados conforme a TIPAGEM do SELECT (numérico perderia os zeros). Seed da migration registra: endpoint `GBE_ConsultaContratosCelularEmailIREndereco_SF` (GI/Salesforce) → 6 views `VW_*_GENESYS`/`VW_CONTRATO_IMPOSTO_RENDA` pendentes de validar campo CNPJ + recompilação; `GBE_ConsultaContratos` (Salesforce); processo Genesys do Jordan → `VW_CLIENTES_EMAIL_TELEFONE_CVP`.

**How to apply:** Pendências: (1) deploy manual em produção (migration 055 + rebuild não necessário para esta tela); (2) rótulo amigável de `tela_inventario` na tela de perfis do Admin ficou de fora (Admin.tsx estava reservado pela branch de conexões) — adicionar num PR futuro; (3) alimentar o inventário com os demais endpoints do GI conforme o time confirmar (padrão do incidente: perguntar "qual view/proc o endpoint consulta?"). Relacionado: [[orquestra-copia-dados]].
