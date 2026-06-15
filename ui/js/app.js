/* ══ Ícones SVG inline — sem dependências externas (compatível air-gap/Docker) ══ */
const ICONS = {
  edit:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  trash:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>`,
  disable: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`,
  play:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
  refresh: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
  gear:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  graph:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`,
  check:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  detail:  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  history: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.95L1 10"/><polyline points="12 7 12 12 15 15"/></svg>`,
  link:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
  rerun:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>`,
};

let authHeader = null;

/* ── Sessão ORQUESTRA (token opaco; sobrevive ao F5) ──────────────────────────
   - POST /auth/login devolve token + dados do usuário (perfil, permissões, nome)
   - O token (NUNCA a senha) fica no localStorage em ORQ_SESSION_KEY
   - No F5, restoreSession() valida o token via GET /me e religa a aplicação   */
const ORQ_SESSION_KEY = 'orq_session';
let __orqToken = null;

window.__userPerfil = 'consulta';
window.__userPerms  = [];

/** Header de autenticação para a API ORQUESTRA: Bearer (sessão) > Basic. */
function _orqAuthHeader() {
  if (__orqToken)  return { Authorization: 'Bearer ' + __orqToken };
  if (authHeader)  return { Authorization: authHeader };
  return {};
}

function _saveSession(token, ttlHours) {
  try {
    localStorage.setItem(ORQ_SESSION_KEY, JSON.stringify({
      token, exp: Date.now() + (ttlHours || 12) * 3600 * 1000 }));
  } catch(e) {}
}
function _loadSession() {
  try {
    const s = JSON.parse(localStorage.getItem(ORQ_SESSION_KEY) || 'null');
    if (s && s.token && s.exp > Date.now()) return s;
  } catch(e) {}
  return null;
}
function _clearSession() {
  __orqToken = null;
  try { localStorage.removeItem(ORQ_SESSION_KEY); } catch(e) {}
}

/** Aplica os dados do usuário (de /auth/login ou GET /me) nos globals e na UI. */
function _applyUserInfo(u) {
  window.__currentUser = u.matricula || '';
  window.__userPerfil  = u.perfil || 'consulta';
  window.__userPerms   = u.permissoes || [];
  window.__displayName = [u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || u.matricula;
  const who = $('who');
  if (who) who.textContent = u.primeiro_nome || u.matricula || '';
}

function _hasPerm(p) { return (window.__userPerms || []).includes(p); }

/** Esconde abas que o perfil não pode ver. */
function _applyPermVisibility() {
  const mapa = {
    'tab-dashboard':  'tela_dashboard',  'tab-pipelines': 'tela_pipelines',
    'tab-jobs':       'tela_jobs',       'tab-logs':      'tela_logs',
    'tab-ds-monitor': 'tela_ds_monitor', 'tab-governanca':'tela_governanca',
    'tab-malha':      'tela_malha',      'tab-admin':     'tela_admin',
  };
  Object.entries(mapa).forEach(([id, perm]) => {
    const el = $(id);
    if (el) el.classList.toggle('hidden', !_hasPerm(perm));
  });
}

/** Restaura a sessão após F5: valida o token e religa a aplicação. */
async function restoreSession() {
  const s = _loadSession();
  if (!s) return false;
  try {
    const r = await fetch(ORQUESTRA_API + '/me', { headers: { Authorization: 'Bearer ' + s.token } });
    if (!r.ok) { _clearSession(); return false; }
    __orqToken = s.token;
    _applyUserInfo(await r.json());
    // Header da service account para as chamadas diretas ao Airflow
    try {
      const ra = await fetch(ORQUESTRA_API + '/auth/airflow-header',
        { headers: { Authorization: 'Bearer ' + __orqToken } });
      if (ra.ok) { const da = await ra.json(); authHeader = da.header || null; }
    } catch(e) {}
    $('loginScreen').classList.add('hidden');
    $('appScreen').classList.remove('hidden');
    _postLoginInit();
    // Sessão válida: a UI React (/v2) é a principal. Só permanecemos na UI legada
    // quando há um deep-link explícito para uma tela ainda não migrada
    // (ex.: /?tab=ds-monitor). Caso contrário, redireciona para o /v2.
    const tab = new URLSearchParams(window.location.search).get('tab');
    const legacyOnly = { 'ds-monitor': 'tab-ds-monitor' };
    if (tab && legacyOnly[tab]) {
      const btn = $(legacyOnly[tab]);
      if (btn) btn.click();
    } else {
      window.location.href = '/v2/';
      return true;
    }
    return true;
  } catch(e) { return false; }
}

// ── Auth sistêmico (service account para chamadas de leitura) ─────────────────
let __sysAuth = null;

/** Retorna o auth do usuário sistêmico se disponível, senão o do usuário logado. */
function _sysAuth() { return __sysAuth || authHeader; }

/** Modos que ESCREVEM dados — usam authHeader do usuário logado. */
const _WRITE_MODES = new Set([
  'save_tag','save_owner','save_job_type','delete_job_type',
  'save_version','delete_version','save_pipeline','delete_pipeline',
]);

/**
 * Carrega credenciais do usuário sistêmico a partir da Variable 'ORQUESTRA_SYSTEM_AUTH'.
 * O valor deve ser um Basic auth header: "Basic base64(user:pass)".
 * Qualquer usuário Airflow (inclusive Viewer) pode ler Variables.
 */
async function _initSystemAuth() {
  try {
    const r = await fetch('/api/v1/variables/ORQUESTRA_SYSTEM_AUTH',
      { headers: { Authorization: authHeader } });
    if (r.ok) {
      const v = await r.json();
      if (v && v.value) {
        __sysAuth = v.value.trim();
        console.log('[ORQ] Auth sistêmico carregado.');
      }
    }
  } catch(e) {
    console.warn('[ORQ] Auth sistêmico não disponível — usando auth do usuário:', e.message);
  }
}

/**
 * Detecta se o usuário logado é somente-visualizador (Viewer no Airflow).
 * Estratégia: GET /api/v1/pools requer role Op ou superior.
 *   - 200 → usuário tem Op/Admin → editor
 *   - 403 → usuário é Viewer → modo somente-leitura
 * Funciona com autenticação LDAP sem precisar de credencial Admin.
 */
async function _detectViewerRole() {
  try {
    const r = await fetch('/api/v1/pools?limit=1', { headers: { Authorization: authHeader } });
    if (r.status === 403) {
      window.__isViewer = true;
      document.body.classList.add('viewer-mode');
      console.log('[ORQ] Modo visualizador ativado para', window.__currentUser);
    } else {
      window.__isViewer = false;
      console.log('[ORQ] Usuário editor confirmado para', window.__currentUser);
    }
  } catch(e) {
    console.warn('[ORQ] Detecção de role falhou (assumindo editor):', e.message);
    window.__isViewer = false;
  }
}
// ─────────────────────────────────────────────────────────────────────────────

let jobMode = 'manual';
let pipelineStatus = 1;
const $ = (id) => document.getElementById(id);
function _escHtml(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Links para UI do Airflow (usado nos modais de erro/timeout)
const AIRFLOW_UI_BASE = 'https://airflow.caixavidaeprevidencia.intranet/';
const AIRFLOW_UI = AIRFLOW_UI_BASE.replace(/\/$/, '');

/* ══ ORQUESTRA — DAG Factory + Logs (Spec Alterações index.html v1.0) ══ */
const DAG_FACTORY_ID = 'etl_dag_factory';
const LOGS_DAG_ID = 'etl_job_execution_query';
let logsCurrentOffset = 0;
const LOGS_LIMIT = 30;

/* ══ Validações (Pipelines) ══ */
const IDENT_RE = /^[A-Z0-9_]+$/;

function setFieldInvalidById(inputId, errId, message) {
  const inp = $(inputId);
  const err = $(errId);
  if (inp && inp.closest) {
    const field = inp.closest('.field');
    if (field) field.classList.add('invalid');
  }
  if (err) {
    err.textContent = message || '';
    err.style.display = message ? 'block' : 'none';
  }
}

function clearFieldInvalidById(inputId, errId) {
  const inp = $(inputId);
  const err = $(errId);
  if (inp && inp.closest) {
    const field = inp.closest('.field');
    if (field) field.classList.remove('invalid');
  }
  if (err) {
    err.textContent = '';
    err.style.display = 'none';
  }
}

function validateIdentField(inputId, errId, label, required) {
  const inp = $(inputId);
  if (!inp) return true;
  const v = (inp.value || '').trim().toUpperCase();
  inp.value = v;
  if (!v) {
    if (required) {
      setFieldInvalidById(inputId, errId, (label || 'Campo') + ' obrigatório. Use apenas letras, números e "_" (sem espaços).');
      return false;
    }
    clearFieldInvalidById(inputId, errId);
    return true;
  }
  if (!IDENT_RE.test(v)) {
    setFieldInvalidById(inputId, errId, (label || 'Campo') + ' inválido. Use apenas letras, números e "_" (sem espaços).');
    return false;
  }
  clearFieldInvalidById(inputId, errId);
  return true;
}

function validateTagDraft() {
  const inp = $('tag-input');
  if (!inp) return true;
  const v = (inp.value || '').trim().toUpperCase();
  inp.value = v;
  // rascunho (antes do Enter) não precisa ser obrigatório
  if (!v) { clearFieldInvalidById('tag-input', 'err-tags'); return true; }
  if (!IDENT_RE.test(v)) { setFieldInvalidById('tag-input', 'err-tags', 'Tag inválida. Use apenas letras, números e "_" (sem espaços).'); return false; }
  clearFieldInvalidById('tag-input', 'err-tags');
  return true;
}

async function waitDagRun(dagId, runId, maxSec) {
  const end = Date.now() + (maxSec * 1000);
  while (Date.now() < end) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const r = await fetch('/api/v1/dags/' + dagId + '/dagRuns/' + runId, { headers: { 'Authorization': _sysAuth() } });
      if (r.status === 401) { sair(); return 'failed'; }
      if (!r.ok) return 'failed';
      const d = await r.json();
      if (d.state === 'success' || d.state === 'failed') return d.state;
    } catch(_) {
      return 'failed';
    }
  }
  return 'failed'; // timeout
}

async function gerarDAG(idx) {
  const list = window.__pipelines || [];
  const p = list[idx];
  if (!p) return;
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }

  const btn = document.getElementById('dag-btn-' + idx);
  const isRegen = !!p.dag_criada;
  const labelDefault = isRegen ? '↺ Regenerar' : '⚙ Gerar DAG';

  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Gerando...';
  }

  try {
    const runId = 'orquestra_ui_' + Date.now();
    const r = await fetch('/api/v1/dags/' + DAG_FACTORY_ID + '/dagRuns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ dag_run_id: runId, conf: { pipeline_name: p.pipeline_name } })
    });
    if (r.status === 401) { sair(); return; }
    if (!r.ok) {
      showToast('Erro ao disparar factory: ' + await r.text(), true);
      if (btn) { btn.disabled = false; btn.textContent = labelDefault; }
      return;
    }
    const data = await r.json();
    showToast('Factory disparada para "' + p.pipeline_name + '" — aguardando...', false);
    const state = await waitDagRun(DAG_FACTORY_ID, data.dag_run_id || data.run_id, 60);
    if (state === 'success') {
      showToast('DAG gerada: ' + p.pipeline_name, false);
      p.dag_criada = 1;
      if (btn) {
        btn.disabled = false;
        btn.className = 'btn-dag-ok btn-sm';
        btn.title = 'DAG já criada — clique para regenerar após mudanças';
        btn.textContent = '↺ Regenerar';
      }
    } else {
      showToast('Falha ao gerar DAG. Verifique os logs no Airflow.', true);
      if (btn) { btn.disabled = false; btn.textContent = labelDefault; }
    }
  } catch(e) {
    showToast('Erro: ' + (e && e.message ? e.message : e), true);
    if (btn) { btn.disabled = false; btn.textContent = labelDefault; }
  }
}

// Drill-down do Dashboard: abre aba Logs filtrado por FAILED de hoje
function _drillDownFalhas() {
  const falhaCount = parseInt(($('kpi-falha') || {}).textContent || '0', 10);
  if (!falhaCount) { showToast('Sem falhas hoje.', false); return; }
  switchPage('page-logs', $('tab-logs'));
  const today = new Date().toISOString().slice(0, 10);
  if ($('lf-status'))    $('lf-status').value   = 'FAILED';
  if ($('lf-date-from')) $('lf-date-from').value = today;
  // Limpar outros filtros
  ['lf-project','lf-pipeline','lf-datetime-from','lf-execution-id','lf-period'].forEach(id => { if ($(id)) $(id).value = ''; });
  setTimeout(() => loadLogs(0), 50);
}

function clearLogsFilters() {
  ['lf-project','lf-pipeline','lf-status','lf-date-from','lf-datetime-from','lf-execution-id','lf-period'].forEach(id => { if ($(id)) $(id).value = ''; });
  const area = $('logs-table-area');
  if (area) area.innerHTML =
    '<div class="empty-state">' +
      '<span class="es-icon">≣</span>' +
      '<p class="es-title">Nenhum log carregado</p>' +
      '<p class="es-sub">Use os filtros acima e clique em Buscar logs.</p>' +
    '</div>';
  if ($('logs-status')) $('logs-status').textContent = '';
  logsCurrentOffset = 0;
}

function logsSwitchTab(which) {
  const tabs = { exec: $('log-tab-exec'), factory: $('log-tab-factory') };
  const panels = { exec: $('log-panel-exec'), factory: $('log-panel-factory') };
  for (const k of Object.keys(tabs)) {
    if (tabs[k])   tabs[k].classList.toggle('active', k === which);
    if (panels[k]) panels[k].style.display = (k === which) ? '' : 'none';
  }
  if (which === 'factory') loadFactoryRuns();
}

const FACTORY_STATE_BADGE = {
  success: '<span class="badge badge-success">✓ Concluída</span>',
  failed:  '<span class="badge badge-failed">✕ Com erro</span>',
  running: '<span class="badge badge-running">… Em execução</span>',
  queued:  '<span class="badge">⏳ Aguardando</span>',
};

async function loadFactoryRuns() {
  const st = $('factory-status'), area = $('factory-table-area');
  if (st) st.textContent = 'Carregando execuções da factory...';
  try {
    const r = await fetch(ORQUESTRA_API + '/factory/runs?limit=20');
    if (!r.ok) { if (st) st.textContent = 'Erro ' + r.status + ' ao consultar o Airflow.'; return; }
    const data = (await r.json()).data || [];
    if (!data.length) {
      area.innerHTML = '<div class="empty-state"><span class="es-icon">♻</span><p class="es-title">Nenhuma regeneração encontrada</p></div>';
      if (st) st.textContent = '';
      return;
    }
    const fmtDt = (s) => s ? new Date(s).toLocaleString('pt-BR') : '—';
    const rows = data.map((run, i) => {
      const estado = (run.estado || '').toLowerCase();
      const badge = FACTORY_STATE_BADGE[estado] || ('<span class="badge">' + (run.estado || '—') + '</span>');
      const geradasTxt = run.geradas > 0
        ? '<span style="color:var(--green);font-weight:600">' + run.geradas + ' gerada(s)</span>'
        : '<span style="color:var(--muted)">—</span>';
      const errosTxt = run.erros > 0
        ? ' <span style="color:var(--red);font-weight:600">' + run.erros + ' erro(s)</span>'
        : '';
      return '<tr style="cursor:pointer" onclick="toggleFactoryDetail(' + i + ', \'' + encodeURIComponent(run.dag_run_id) + '\')">' +
        '<td style="font-size:12px;white-space:nowrap">' + (run.iniciado_em || '—') + '</td>' +
        '<td>' + badge + '</td>' +
        '<td style="font-size:12px">' + (run.escopo || '—') + '</td>' +
        '<td style="text-align:center">' + geradasTxt + errosTxt + '</td>' +
        '<td style="font-size:11px;color:var(--muted);white-space:nowrap">' + (run.finalizado_em || '—') + '</td>' +
      '</tr>' +
      '<tr id="factory-detail-' + i + '" style="display:none"><td colspan="5" style="background:var(--bg);padding:1rem">' +
        '<div id="factory-detail-body-' + i + '" style="font-size:12px;color:var(--muted)">…</div></td></tr>';
    }).join('');
    area.innerHTML = '<div class="query-table-wrap"><table class="query-table">' +
      '<thead><tr><th>Início</th><th>Situação</th><th>O que foi regenerado</th><th>Resultado</th><th>Concluído em</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';
    if (st) st.textContent = data.length + ' execução(ões). Clique numa linha para ver as etapas.';
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + (e.message || e);
  }
}

const FACTORY_STEP_STYLE = {
  reset:  { icon: '🔄', color: 'var(--cvp-blue)', label: 'Preparação' },
  gerada: { icon: '📝', color: 'var(--green)',    label: 'Arquivo gerado' },
  banco:  { icon: '💾', color: 'var(--green)',    label: 'Cadastro atualizado' },
  vazio:  { icon: '⚠️', color: 'var(--orange)',   label: 'Atenção' },
  resumo: { icon: '🏁', color: 'var(--cvp-blue)', label: 'Resultado final' },
  erro:   { icon: '❌', color: 'var(--red)',      label: 'Erro' },
  info:   { icon: 'ℹ️', color: 'var(--muted)',    label: 'Informação' },
};

async function toggleFactoryDetail(i, encodedRunId) {
  const row = $('factory-detail-' + i);
  if (!row) return;
  if (row.style.display !== 'none') { row.style.display = 'none'; return; }
  row.style.display = '';
  const body = $('factory-detail-body-' + i);
  body.textContent = 'Buscando log no Airflow...';
  try {
    const r = await fetch(ORQUESTRA_API + '/factory/runs/' + encodedRunId + '/log?raw=true');
    if (!r.ok) {
      const t = await r.text();
      body.innerHTML = '<span style="color:var(--red)">Erro ' + r.status + ': ' + t.slice(0, 200) + '</span>';
      return;
    }
    const d = await r.json();
    let html = '';
    if (d.steps && d.steps.length) {
      html += '<div style="display:flex;flex-direction:column;gap:.4rem;margin-bottom:.75rem">';
      for (const s of d.steps) {
        const sty = FACTORY_STEP_STYLE[s.tipo] || FACTORY_STEP_STYLE.info;
        html += '<div style="display:flex;gap:.5rem;align-items:flex-start">' +
          '<span>' + sty.icon + '</span>' +
          '<span style="font-size:11px;font-weight:600;min-width:80px;color:' + sty.color + '">' + sty.label + '</span>' +
          '<span style="font-size:12px;color:var(--text)">' + s.msg + '</span></div>';
      }
      html += '</div>';
    } else {
      html += '<div style="color:var(--orange);margin-bottom:.75rem">Nenhuma etapa [FACTORY] encontrada no log — a task pode ter falhado antes de iniciar.</div>';
    }
    if (d.erros_lista && d.erros_lista.length) {
      html += '<div style="background:rgba(220,38,38,.06);border:1px solid rgba(220,38,38,.3);border-radius:8px;padding:.6rem;margin-bottom:.75rem">' +
        '<div style="font-weight:600;color:var(--red);margin-bottom:.3rem">Erros detectados</div>' +
        d.erros_lista.map(e => '<div style="font-family:monospace;font-size:11px">' + e + '</div>').join('') + '</div>';
    }
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = '<span style="color:var(--red)">Erro: ' + (e.message || e) + '</span>';
  }
}

async function loadLogs(offset) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  logsCurrentOffset = (offset !== undefined ? offset : logsCurrentOffset) || 0;

  const conf = { offset: logsCurrentOffset, limit: LOGS_LIMIT };
  const fproj = $('lf-project') ? $('lf-project').value : '';
  const fpip  = $('lf-pipeline') ? $('lf-pipeline').value.trim() : '';
  const fstat = $('lf-status') ? $('lf-status').value : '';
  const fdf     = $('lf-date-from')     ? $('lf-date-from').value     : '';
  const fdtFrom = $('lf-datetime-from') ? $('lf-datetime-from').value : '';
  const fexec = $('lf-execution-id') ? $('lf-execution-id').value.trim() : '';
  if (fproj) conf.filter_project = fproj;
  if (fpip)  conf.filter_pipeline = fpip;
  if (fstat) conf.filter_status = fstat;
  // fdtFrom agora é um número de horas (ex: "24") quando vem de filtro rápido
  // filter_hours_back = backend calcula: WHERE start_time >= DATEADD(hour, -N, GETDATE())
  if (fdtFrom && !isNaN(parseInt(fdtFrom, 10))) {
    conf.filter_hours_back = parseInt(fdtFrom, 10);  // ex: 24
    // Manter filter_date_from como data (sem hora) para compatibilidade
    if (fdf) conf.filter_date_from = fdf;
  } else if (fdf) {
    conf.filter_date_from = fdf;   // data manual: "2026-06-03" (sem hora)
  }
  if (fexec) conf.filter_execution_id = fexec;

  const btn = $('btn-logs-query'), btnTxt = $('btn-logs-txt'), st = $('logs-status'), area = $('logs-table-area');
  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = 'Buscando...';
  if (st) st.textContent = 'Consultando API...';

  try {
    const params = new URLSearchParams();
    params.set('offset', conf.offset || 0);
    params.set('limit',  conf.limit  || LOGS_LIMIT);
    if (conf.filter_project)      params.set('filter_project',      conf.filter_project);
    if (conf.filter_pipeline)     params.set('filter_pipeline',     conf.filter_pipeline);
    if (conf.filter_status)       params.set('filter_status',       conf.filter_status);
    if (conf.filter_hours_back)   params.set('filter_hours_back',   conf.filter_hours_back);
    if (conf.filter_date_from)    params.set('filter_date_from',    conf.filter_date_from);
    if (conf.filter_execution_id) params.set('filter_execution_id', conf.filter_execution_id);

    if (st) st.textContent = 'Carregando dados...';
    const r = await fetch(ORQUESTRA_API + '/execucoes?' + params.toString());
    if (r.status === 401) { sair(); return; }
    if (!r.ok) { if (st) st.textContent = 'Erro API: ' + r.status; return; }

    const payload = await r.json();
    try { window.__lastLogsPayload = payload; } catch(e) {}
    renderLogsTable(payload, area, st);
  } catch(err) {
    if (st) st.textContent = 'Erro de conexão: ' + (err && err.message ? err.message : err);
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Buscar logs';
  }
}

function renderLogsTable(result, area, statusEl) {
  if (!area) return;
  const _rawRows = (result && (result.data || result.rows)) || [];
  const st_l = window.__sortState['logs'];
  const rows = st_l ? _sortData(_rawRows, st_l.col, st_l.dir) : _rawRows;
  const total = (result && result.total) || 0;
  const offset = (result && (result.offset || 0)) || 0;
  const limit = (result && (result.limit || LOGS_LIMIT)) || LOGS_LIMIT;
  const pages = (result && (result.pages || 0)) || 0;

  const from = total ? (offset + 1) : 0;
  const to = total ? Math.min(offset + limit, total) : 0;
  if (statusEl) statusEl.textContent = total ? ('Exibindo ' + from + '–' + to + ' de ' + total + ' execução(ões)') : 'Nenhum resultado';

  const statusPill = (s) => {
    const v = (s || '').toUpperCase();
    if (v === 'SUCCESS') return '<span class="log-pill success">✓ SUCCESS</span>';
    if (v === 'FAILED')  return '<span class="log-pill failed">✕ FAILED</span>';
    if (v === 'WARNING') return '<span class="log-pill warning">! WARNING</span>';
    if (v === 'RUNNING') return '<span class="log-pill running">… RUNNING</span>';
    return '<span class="log-pill running">… ' + (v || 'DESCONHECIDO') + '</span>';
  };

  const fmtDur = (sec) => {
    if (sec === null || sec === undefined || sec === '') return '—';
    const n = parseInt(sec, 10);
    if (isNaN(n)) return '—';
    if (n < 60) return n + 's';
    const m = Math.floor(n / 60);
    const s = n % 60;
    return m + 'm ' + s + 's';
  };

  const fmtDt16 = (v) => v ? String(v).slice(0, 16) : '—';

  if (!rows.length) {
    area.innerHTML =
      '<div class="empty-state">' +
        '<span class="es-icon">≣</span>' +
        '<p class="es-title">Nenhum log encontrado</p>' +
        '<p class="es-sub">Ajuste os filtros e tente novamente.</p>' +
      '</div>';
    return;
  }

  const body = rows.map(r => {
    const falha = parseInt(r.jobs_falha || 0, 10);
    const warn  = parseInt(r.jobs_warning || 0, 10);
    let fw = '—';
    if (falha > 0) fw = '<span class="log-pill failed">✕ ' + falha + '</span>';
    else if (warn > 0) fw = '<span class="log-pill warning">! ' + warn + '</span>';

    // Importante: os parâmetros do onclick precisam estar entre aspas simples,
    // senão o HTML quebra (ex.: onclick="openLogDetail("abc","def")").
    const ex = String(r.execution_id || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    const pip = String(r.pipeline || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    // Acknowledge: badge se já assumido, botão se FAILED sem ack
    let ackHtml = '';
    if (r.status_geral === 'FAILED') {
      if (r.ack_by) {
        const ackLabel = r.display_name ? r.display_name + ' (' + r.ack_by + ')' : r.ack_by;
        ackHtml = '<span style="font-size:10px;color:var(--muted);white-space:nowrap" title="Assumido em ' + (r.ack_at || '') + '">👁 ' + _escHtml(ackLabel) + '</span>';
      } else if (!window.__isViewer) {
        ackHtml = '<button class="btn-ghost btn-sm" style="font-size:10px;padding:.15rem .4rem" ' +
          'onclick="_ackFailure(\'' + ex + '\',\'' + pip + '\',this)" ' +
          'title="Assumir investigação desta falha — sinaliza ao time que alguém já está olhando">👁 Assumir</button>';
      }
    }
    return '<tr>' +
      '<td style="font-weight:500;white-space:nowrap">' + (r.pipeline || '—') + '</td>' +
      '<td><span class="tag-pill">' + (r.project || '—') + '</span></td>' +
      '<td style="white-space:nowrap">' + statusPill(r.status_geral) + (ackHtml ? '<br>' + ackHtml : '') + '</td>' +
      '<td style="white-space:nowrap">' + fmtDt16(r.inicio) + '</td>' +
      '<td style="white-space:nowrap">' + fmtDt16(r.fim) + '</td>' +
      '<td style="white-space:nowrap">' + fmtDur(r.duracao_total_segundos) + '</td>' +
      '<td style="text-align:center">' + (r.total_jobs ?? '—') + '</td>' +
      '<td style="text-align:center">' + fw + '</td>' +
      '<td style="font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace;font-size:11px;color:var(--muted)">' + (r.execution_id || '—') + '</td>' +
      '<td class="col-actions"><div class="row-actions">' +
        '<button class="btn-ver-jobs" onclick="openLogDetail(\'' + ex + '\',\'' + pip + '\')" title="Ver jobs desta execução">' + ICONS.detail + '</button>' +
        (!window.__isViewer ? '<button class="act-btn act-rerun" onclick="reexecutarDoPipelineLog(\'' + pip + '\')" title="Reexecutar este pipeline agora">' + ICONS.rerun + '</button>' : '') +
      '</div></td>' +
    '</tr>';
  }).join('');

  const _lHdr = (label, col) =>
    '<th style="cursor:pointer;user-select:none;white-space:nowrap" ' +
    'data-sort-table="logs" data-sort-col="' + col + '">' +
    label + _sortIcon('logs', col) + '</th>';

  area.innerHTML =
    '<div class="query-table-wrap"><table class="query-table"><thead><tr>' +
    _lHdr('Pipeline','pipeline') + _lHdr('Projeto','project') +
    _lHdr('Status','status_geral') + _lHdr('Início','inicio') +
    _lHdr('Fim','fim') + _lHdr('Duração','duracao_total_segundos') +
    '<th>Jobs</th><th>Falha/Aviso</th><th>Execution ID</th><th class="col-actions">Ações</th>' +
    '</tr></thead><tbody>' + body + '</tbody></table></div>' +
    (pages > 1 ? renderPagination(offset, limit, total, pages, 'loadLogs') : '');
}

function openLogDetail(executionId, pipeline) {
  if (!executionId) { showToast('Execution ID inválido.', true); return; }
  $('ld-title').textContent = 'Detalhe da execução';
  $('ld-sub').textContent = 'Execution ID: ' + executionId + (pipeline ? (' · Pipeline: ' + pipeline) : '');
  $('ld-status').textContent = 'Carregando...';
  $('ld-table-area').innerHTML = '<div class="empty-state"><span class="es-icon">≣</span><p class="es-title">Carregando...</p><p class="es-sub">Aguarde o retorno do Airflow.</p></div>';
  $('logDetailModal').classList.add('open');
  loadLogDetail(executionId, pipeline);
}

function closeLogDetail() {
  $('logDetailModal').classList.remove('open');
}

async function loadLogDetail(executionId, pipeline) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }

  $('ld-status').textContent = 'Consultando API...';
  try {
    const params = new URLSearchParams();
    params.set('detail_mode', 'true');
    params.set('offset', 0);
    params.set('limit', 200);
    params.set('filter_execution_id', executionId);
    if (pipeline) params.set('filter_pipeline', pipeline);

    // Buscar jobs, duração média, runbook e tempos de fila DS em paralelo
    const [r, rMedia, rPip, rDs] = await Promise.all([
      fetch(ORQUESTRA_API + '/execucoes?' + params.toString()),
      pipeline
        ? fetch(ORQUESTRA_API + '/execucoes/duracao-media?pipeline=' + encodeURIComponent(pipeline) + '&limit=30')
        : Promise.resolve(null),
      pipeline
        ? fetch(ORQUESTRA_API + '/pipelines?filter_name=' + encodeURIComponent(pipeline) + '&limit=1')
        : Promise.resolve(null),
      fetch(ORQUESTRA_API + '/datastage/log?execution_id=' + encodeURIComponent(executionId) + '&limit=100').catch(() => null),
    ]);

    if (r.status === 401) { sair(); return; }
    if (!r.ok) { $('ld-status').textContent = 'Erro API: ' + r.status; return; }

    const payload  = await r.json();
    let avgData = {}, runbook = '';
    if (rMedia && rMedia.ok) {
      try { avgData = (await rMedia.json()).data || {}; } catch(_) {}
    }
    if (rPip && rPip.ok) {
      try {
        const pd = await rPip.json();
        const rec = (pd.data || []).find(p => p.pipeline_name === pipeline) || (pd.data || [])[0];
        runbook = (rec && rec.runbook_md) || '';
      } catch(_) {}
    }
    // Mapa job_name → queued_seconds (tempo em fila WM DataStage)
    let queuedMap = {};
    if (rDs && rDs.ok) {
      try {
        for (const lg of ((await rDs.json()).logs || [])) {
          if (lg.queued_seconds !== null && lg.queued_seconds !== undefined) {
            queuedMap[lg.job_name] = lg.queued_seconds;
          }
        }
      } catch(_) {}
    }
    payload._avgData   = avgData;
    payload._pipeline  = pipeline || '';
    payload._runbook   = runbook;
    payload._queuedMap = queuedMap;
    renderLogDetailTable(payload);
  } catch (e) {
    $('ld-status').textContent = 'Erro: ' + (e && e.message ? e.message : e);
  }
}

function renderLogDetailTable(result) {
  const area = $('ld-table-area');
  if (!area) return;

  const rows = (result && result.data) || [];
  if (!rows.length) {
    $('ld-status').textContent = 'Nenhum job encontrado para esta execução.';
    area.innerHTML =
      '<div class="empty-state">' +
        '<span class="es-icon">⬡</span>' +
        '<p class="es-title">Nenhum job encontrado</p>' +
        '<p class="es-sub">Sem registros para esta execução.</p>' +
      '</div>';
    return;
  }

  $('ld-status').textContent = 'Exibindo ' + rows.length + ' job(s)';

  const statusPill = (s) => {
    const v = (s || '').toUpperCase();
    if (v === 'SUCCESS') return '<span class="log-pill success">✓ SUCCESS</span>';
    if (v === 'FAILED')  return '<span class="log-pill failed">✕ FAILED</span>';
    if (v === 'WARNING') return '<span class="log-pill warning">! WARNING</span>';
    if (v === 'RUNNING') return '<span class="log-pill running">… RUNNING</span>';
    return '<span class="log-pill running">… ' + (v || '—') + '</span>';
  };
  const fmtDur = (sec) => {
    if (sec === null || sec === undefined || sec === '') return '—';
    const n = parseInt(sec, 10);
    if (isNaN(n)) return '—';
    if (n < 60) return n + 's';
    return Math.floor(n / 60) + 'm ' + (n % 60) + 's';
  };
  const fmtDt16 = (v) => v ? String(v).slice(0, 16) : '—';

  const escAttr = (s) => String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const logName = (p) => {
    if (!p) return '—';
    const s = String(p);
    const parts = s.split(/[\\/]/);
    return parts[parts.length - 1] || '—';
  };

  // Pipeline/execution_id ficam no escopo para o botão de log
  const detPipeline    = (result && result._pipeline) || (result && result.filters && result.filters.pipeline) || '';
  const detExecutionId = (result && result.filters && result.filters.execution_id) || '';
  const avgData        = (result && result._avgData) || {};
  const queuedMap      = (result && result._queuedMap) || {};

  // Tempo em fila WM: badge azul ao lado da duração
  const fmtFila = (jobName) => {
    const q = queuedMap[jobName];
    if (q === null || q === undefined || q <= 0) return '';
    return ' <span style="font-size:10px;color:var(--cvp-blue);font-weight:600" ' +
      'title="Tempo aguardando na fila do Workload Management DataStage antes de iniciar">⏳ fila ' + fmtDur(q) + '</span>';
  };

  // Desvio de duração vs histórico
  const fmtDesvio = (jobName, sec) => {
    const info = avgData[jobName];
    if (!info || !info.avg || sec === null || sec === undefined) return '';
    const pct = Math.round(((sec - info.avg) / info.avg) * 100);
    if (Math.abs(pct) < 10) return '';  // variação < 10% — não exibir
    const color = pct > 30 ? '#dc2626' : pct > 0 ? '#d97706' : '#16a34a';
    const arrow = pct > 0 ? '▲' : '▼';
    return ' <span style="font-size:10px;color:' + color + ';font-weight:600" title="Média: ' + fmtDur(info.avg) + '">' + arrow + ' ' + Math.abs(pct) + '%</span>';
  };

  const body = rows.map(r => {
    const jobTitle  = escAttr(r.job_name || '');
    const taskId    = escAttr(r.task_id  || r.job_name || '');
    const pipEsc    = escAttr(r.pipeline || detPipeline);
    const execEsc   = escAttr(r.execution_id || detExecutionId);
    const logBtnCls = r.status === 'FAILED' || r.status === 'WARNING'
      ? 'btn-ghost btn-log-job btn-log-job--err'
      : 'btn-ghost btn-log-job';
    const rerunBtn = (!window.__isViewer && r.status === 'FAILED')
      ? '<button class="btn-ghost btn-sm" style="font-size:11px;padding:.2rem .5rem;color:var(--green)" ' +
          'onclick="_rerunFromTask(\'' + pipEsc + '\',\'' + execEsc + '\',\'' + taskId + '\',this)" ' +
          'title="Reexecutar a partir deste job (e downstream)">' +
          '🔁 Rerun' +
        '</button>'
      : '';
    return '<tr>' +
      '<td style="font-weight:500;white-space:nowrap;max-width:280px;overflow:hidden;text-overflow:ellipsis" title="' + jobTitle + '">' + (r.job_name || '—') + '</td>' +
      '<td style="white-space:nowrap">' + statusPill(r.status) + '</td>' +
      '<td style="white-space:nowrap;font-size:12px">' + fmtDt16(r.inicio) + '</td>' +
      '<td style="white-space:nowrap;font-size:12px">' + fmtDt16(r.fim) + '</td>' +
      '<td style="white-space:nowrap;font-size:12px">' + fmtDur(r.duration_seconds) + fmtDesvio(r.job_name, r.duration_seconds) + fmtFila(r.job_name) + '</td>' +
      '<td style="white-space:nowrap;display:flex;gap:4px;flex-wrap:wrap">' +
        '<button class="' + logBtnCls + '" ' +
          'onclick="_showAirflowJobLog(\'' + pipEsc + '\',\'' + execEsc + '\',\'' + taskId + '\')" ' +
          'title="Ver log do Airflow para este job">' +
          '📋 Log' +
        '</button>' +
        '<button class="btn-ghost btn-sm" style="font-size:11px;padding:.2rem .5rem" ' +
          'onclick="_showDsLog(\'' + execEsc + '\',\'' + jobTitle + '\')" ' +
          'title="Ver log DataStage (etl_ds_job_log)">' +
          '⬡ DS Log' +
        '</button>' +
        rerunBtn +
      '</td>' +
    '</tr>';
  }).join('');

  // Runbook: exibir quando houver job com falha e o pipeline tiver instruções cadastradas
  const hasFailed  = rows.some(r => r.status === 'FAILED');
  const runbookBox = (hasFailed && result._runbook)
    ? '<div style="margin-bottom:.75rem;padding:.6rem .8rem;border:1px solid rgba(220,38,38,.35);border-left:4px solid var(--red);border-radius:8px;background:rgba(220,38,38,.05)">' +
        '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--red);margin-bottom:.3rem">📖 Runbook — em caso de falha</div>' +
        '<div style="font-size:12px;white-space:pre-wrap;line-height:1.5">' + _escHtml(result._runbook) + '</div>' +
      '</div>'
    : '';

  // Mini-grafo: cadeia visual dos jobs na ordem de execução
  const NODE_COLORS = { SUCCESS: 'var(--green)', FAILED: 'var(--red)', WARNING: 'var(--cvp-orange)', RUNNING: 'var(--cvp-blue)' };
  const sortedRows = rows.slice().sort((a, b) => String(a.inicio || '').localeCompare(String(b.inicio || '')));
  const miniGraph = sortedRows.length > 1
    ? '<div style="display:flex;align-items:center;gap:0;overflow-x:auto;padding:.6rem .4rem;margin-bottom:.75rem;background:var(--bg);border:1px solid var(--border);border-radius:10px">' +
      sortedRows.map((r2, idx) => {
        const c = NODE_COLORS[(r2.status || '').toUpperCase()] || 'var(--muted)';
        const shortName = String(r2.job_name || '').length > 22 ? String(r2.job_name).slice(0, 20) + '…' : (r2.job_name || '—');
        const node = '<div style="display:flex;flex-direction:column;align-items:center;min-width:90px;flex-shrink:0" title="' + escAttr(r2.job_name) + ' — ' + (r2.status || '') + '">' +
          '<div style="width:14px;height:14px;border-radius:50%;background:' + c + ';box-shadow:0 0 0 3px color-mix(in srgb, ' + c + ' 25%, transparent)"></div>' +
          '<div style="font-size:9px;margin-top:4px;color:var(--muted);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + shortName + '</div>' +
        '</div>';
        const arrow = idx < sortedRows.length - 1
          ? '<div style="flex-shrink:0;color:var(--border);font-size:14px;margin:0 2px;padding-bottom:14px">→</div>'
          : '';
        return node + arrow;
      }).join('') +
      '</div>'
    : '';

  area.innerHTML =
    runbookBox +
    miniGraph +
    '<div class="query-table-wrap">' +
      '<table class="query-table"><thead><tr>' +
        '<th>Job</th><th>Status</th><th>Início</th><th>Fim</th><th>Duração</th><th>Ações</th>' +
      '</tr></thead><tbody>' + body + '</tbody></table>' +
    '</div>';
}

/* ══ DS LOG MODAL ══ */
async function _showDsLog(executionId, jobName) {
  const modal = $('dsLogModal');
  $('dsl-title').textContent = 'Log DataStage — ' + (jobName || '');
  $('dsl-sub').textContent = 'Execution ID: ' + (executionId || '');
  $('dsl-status').textContent = 'Carregando...';
  $('dsl-body').innerHTML = '';
  modal.classList.add('open');

  try {
    const params = new URLSearchParams();
    if (executionId) params.set('execution_id', executionId);
    if (jobName)     params.set('job_name', jobName);
    const r = await fetch(ORQUESTRA_API + '/datastage/log?' + params.toString(), {
      headers: authHeader ? { Authorization: authHeader } : {},
    });
    if (!r.ok) {
      $('dsl-status').textContent = 'Erro API: ' + r.status;
      $('dsl-body').innerHTML = '<p style="color:var(--danger)">Não foi possível carregar o log DataStage.</p>';
      return;
    }
    const data = await r.json();
    const rows = data.logs || data.data || data.rows || (Array.isArray(data) ? data : []);
    if (!rows.length) {
      $('dsl-status').textContent = 'Nenhum registro encontrado.';
      $('dsl-body').innerHTML = '<div class="empty-state"><span class="es-icon">⬡</span><p class="es-title">Sem log DataStage</p><p class="es-sub">Este job pode não ter sido executado pelo DataStageOperator.</p></div>';
      return;
    }
    const row = rows[0];
    $('dsl-status').textContent = 'Registro encontrado — wave ' + (row.wave_number ?? '—');

    const pill = (s) => {
      const v = (s || '').toUpperCase();
      if (v === 'SUCCESS') return '<span class="log-pill success">✓ SUCCESS</span>';
      if (v === 'ABORTED' || v === 'FAILED') return '<span class="log-pill failed">✕ ' + v + '</span>';
      if (v === 'WARNING') return '<span class="log-pill warning">! WARNING</span>';
      return '<span class="log-pill running">… ' + (v || '—') + '</span>';
    };

    let childHtml = '';
    try {
      const cj = typeof row.child_jobs === 'string' ? JSON.parse(row.child_jobs || '[]') : (row.child_jobs || []);
      if (cj.length) {
        childHtml = '<div class="section-sep" style="margin:.75rem 0 .4rem">JOBS FILHOS (' + cj.length + ')</div>' +
          '<table class="query-table" style="font-size:12px"><thead><tr><th>Job</th><th>Status</th><th>Código</th></tr></thead><tbody>' +
          cj.map(c => '<tr><td>' + (c.name || '—') + '</td><td>' + pill(c.status) + '</td><td>' + (c.status_code ?? '—') + '</td></tr>').join('') +
          '</tbody></table>';
      }
    } catch (_) {}

    const logLines = (row.log_summary || '').slice(0, 4000);

    // Cabeçalho de timing DataStage
    const dsStart = row.ds_start_time || '';
    const dsEnd   = row.ds_end_time   ? String(row.ds_end_time).slice(0, 19).replace('T', ' ') : '';
    let durationStr = '—';
    if (dsEnd && dsStart) {
      try {
        // ds_start_time vem no formato do dsjob: "Wed Jun 11 03:45:12 2025"
        const tEnd = new Date(dsEnd.replace(' ', 'T') + 'Z');
        const tStt = new Date(dsStart);
        if (!isNaN(tEnd) && !isNaN(tStt)) {
          const diff = Math.round((tEnd - tStt) / 1000);
          durationStr = diff < 60 ? diff + 's' : Math.floor(diff/60) + 'm ' + (diff%60) + 's';
        }
      } catch(_) {}
    }

    const timingHtml = (dsStart || dsEnd) ?
      '<div style="background:var(--surface2);border-radius:8px;padding:.6rem 1rem;margin-bottom:.9rem;display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem .75rem;font-size:12px">' +
        '<div><div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px">Início DataStage</div>' +
          '<strong>' + (dsStart || '—') + '</strong></div>' +
        '<div><div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px">Fim DataStage</div>' +
          '<strong>' + (dsEnd || '—') + '</strong></div>' +
        '<div><div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px">Duração</div>' +
          '<strong>' + durationStr + '</strong></div>' +
      '</div>' : '';

    $('dsl-body').innerHTML =
      timingHtml +
      '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem .75rem;font-size:12px;margin-bottom:.75rem">' +
        '<div><span style="color:var(--muted)">Status DS:</span> ' + pill(row.status) + '</div>' +
        '<div><span style="color:var(--muted)">Wave:</span> ' + (row.wave_number ?? '—') + '</div>' +
        '<div><span style="color:var(--muted)">PID:</span> ' + (row.pid || '—') + '</div>' +
        '<div><span style="color:var(--muted)">Projeto:</span> ' + (row.project || '—') + '</div>' +
        '<div><span style="color:var(--muted)">Pipeline:</span> ' + (row.pipeline_name || '—') + '</div>' +
        '<div><span style="color:var(--muted)">Atualizado:</span> ' + (row.updated_at ? String(row.updated_at).slice(0,16) : '—') + '</div>' +
      '</div>' +
      childHtml +
      (logLines ? '<div class="section-sep" style="margin:.75rem 0 .4rem">LOG SUMMARY</div>' +
        '<pre style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:.75rem;font-size:11px;max-height:280px;overflow:auto;white-space:pre-wrap;word-break:break-all">' +
        logLines.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') +
        '</pre>' : '');

  } catch (e) {
    $('dsl-status').textContent = 'Erro: ' + (e && e.message ? e.message : e);
  }
}

/* ══ LINEAGE DSX v1 ══ */
const LINEAGE_DSX_DAG = 'etl_lineage_extract_dsx';
let _dsxLineageData = [];
let _dsxTargetJobId = null;
let _dsxCtx = null; // { project_name, job_name, dsx_file }

// De-para client-side (fallback para preview antes do JOIN do banco)
const STAGE_TYPE_LABELS = {
  'Banco de Dados (ODBC)': 'Banco de Dados ODBC',
  'ODBCConnectorPX': 'Banco de Dados ODBC',
  'Arquivo DataSet (.ds/.dx)': 'DataSet (arquivo DS)',
  'DataSetStage': 'DataSet (arquivo DS)',
  'PxDataSet': 'DataSet (arquivo DS)',
  'SequentialFile': 'Arquivo sequencial',
  'PxSequentialFile': 'Arquivo sequencial',
  'PxSort': 'Ordenação',
  'PxRemDup': 'Remover duplicatas',
  'PxFunnel': 'Funil (consolidação)',
  'PxLookup': 'Lookup (enriquecimento)',
  'PxAggregator': 'Agregador',
  'PxJoin': 'Join',
  'PxMerge': 'Merge',
  'PxFilter': 'Filtro',
  'PxModify': 'Modificar registro',
  'CTransformerStage': 'Transformação customizada',
  'TransformerStage': 'Transformação',
  'PxSwitch': 'Desvio condicional',
  'PxPivot': 'Pivotamento',
  'PxSurrogateKeyGen': 'Gerador chave surrogate',
  'PxChangeCapture': 'Captura de alterações',
  'PxPeek': 'Peek (debug)',
  'RowGenerator': 'Gerador de linhas (teste)',
  'ColumnGenerator': 'Gerador de colunas (teste)',
};
function getTypeLabel(stageTypeRaw) {
  return STAGE_TYPE_LABELS[stageTypeRaw] || stageTypeRaw || 'Tipo desconhecido';
}

function _inferProjectFromPipeline(pipelineName) {
  const p = (pipelineName || '').toUpperCase().trim();
  return ['BI_CVP','BI_VIDA','BI_PREVIDENCIA','BI_PRESTAMISTA'].find(x => p.startsWith(x)) || '';
}

function _tryGetProjectFromJobsList(pipelineName) {
  const list = window.__jobs || [];
  const j = list.find(x => x && x.pipeline_name === pipelineName && x.project_name);
  return j ? j.project_name : null;
}

function _tryGetProjectFromPipelinesCache(pipelineName) {
  const list = window.__pipelines || [];
  const p = list.find(x => x && x.pipeline_name === pipelineName && x.project_name);
  return p ? p.project_name : null;
}

function _nowSql() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2,'0');
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

function openLineageDSXPreview() {
  const m = $('lineageDSXPreviewModal');
  if (!m) return;
  // Reposicionar no final do body garante stacking order correto
  // independente de qual modal foi aberto primeiro
  document.body.appendChild(m);
  m.classList.add('open');
}
function closeLineageDSXPreview() { $('lineageDSXPreviewModal').classList.remove('open'); }

async function loadLineageDSX(jobId) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }

  const pipelineName = $('job_pipeline_name') ? $('job_pipeline_name').value.trim() : '';
  const j = jobsBdata.find(x => x.id === jobId);
  if (!j) { showToast('Job inválido.', true); return; }
  if (!pipelineName) { showToast('Informe o pipeline antes de extrair.', true); return; }
  if (!j.name || !j.name.trim()) { showToast('Informe o nome do job antes de extrair.', true); return; }
  if ((j.type || '') !== 'datastage') { showToast('Extrair do DSX está disponível somente para jobs DataStage.', true); return; }

  // Prioridade: project salvo no ctx (vem de etl_pipeline_job_query com project_name)
  // Fallback: inferir pelo nome do pipeline (retrocompatibilidade)
  const projectName = (window.__lineageTableCtx && window.__lineageTableCtx.project)
    ? window.__lineageTableCtx.project
    : _inferProjectFromPipeline(pipelineName);
  if (!projectName) {
    showToast('Projeto não encontrado para este job. Contate o administrador para verificar o campo project_name no cadastro do pipeline.', true);
    return;
  }

  _dsxTargetJobId = jobId;
  _dsxCtx = { project_name: projectName, job_name: j.name.trim(), dsx_file: projectName + '.dsx' };

  // UI do modal
  $('dsx-prev-title').textContent = 'Prévia — Linhagem DSX';
  $('dsx-prev-sub').textContent = projectName + ' / ' + j.name.trim();
  $('dsx-prev-status').textContent = 'Buscando no arquivo .dsx...';
  $('dsx-prev-table').innerHTML = '';
  $('btn-apply-dsx').disabled = true;
  openLineageDSXPreview();

  const btn = $('btn-dsx-extract');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Extraindo...'; }

  try {
    const r = await fetch(ORQUESTRA_API + '/lineage/extract-dsx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({ project_name: projectName, job_name: j.name.trim() }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      $('dsx-prev-status').textContent = 'Erro: ' + (err.detail || ('HTTP ' + r.status));
      return;
    }
    const payload = await r.json();
    showLineageDSXPreview(payload);
  } catch (e) {
    $('dsx-prev-status').textContent = 'Erro: ' + (e && e.message ? e.message : e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⬡ Extrair linhagem do DSX'; }
  }
}

function showLineageDSXPreview(payload) {
  const dados = (payload && payload.dados) || [];
  _dsxLineageData = dados;
  if (payload && payload.dsx_file) _dsxCtx.dsx_file = payload.dsx_file;

  $('dsx-prev-status').textContent = dados.length + ' ponto(s) de contato encontrado(s). Revise e clique em Aplicar.';
  if (!dados.length) {
    $('dsx-prev-table').innerHTML = '<p style="font-size:12px;color:var(--muted)">Nenhum dado extraído.</p>';
    $('btn-apply-dsx').disabled = true;
    return;
  }
  $('btn-apply-dsx').disabled = false;

  const dirColors = {
    origem:        { bg:'#E6F1FB', color:'#0C447C', label:'Origem' },
    destino:       { bg:'#EAF3DE', color:'#27500A', label:'Destino' },
    transformacao: { bg:'#EEEDFE', color:'#3C3489', label:'Transformação' },
  };

  const rows = dados.map(d => {
    const dir = d.direction || 'transformacao';
    const c = dirColors[dir] || dirColors.transformacao;
    const cat = (d.type_category || (dir === 'transformacao' ? 'transformacao' : '—'));
    const typeLabel = d.type_label || getTypeLabel(d.stage_type_raw) || d.object_type || '—';
    const stage = d.stage_name || d.object_name || '—';
    const detail =
      d.file_path
        ? _fileBasename(d.file_path)
        : (d.database_name && d.object_name)
          ? (d.database_name + '.' + d.object_name)
          : (d.object_name || '—');

    return '<tr>' +
      '<td style="white-space:nowrap"><span style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:' + c.bg + ';color:' + c.color + ';font-size:11px;font-weight:700">' + c.label + '</span></td>' +
      '<td style="white-space:nowrap">' + (cat || '—') + '</td>' +
      '<td style="white-space:nowrap">' + (typeLabel || '—') + '</td>' +
      '<td>' + (stage || '—') + '</td>' +
      '<td style="font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace;font-size:11px">' + (detail || '—') + '</td>' +
    '</tr>';
  }).join('');

  $('dsx-prev-table').innerHTML =
    '<div class="query-table-wrap"><table class="query-table"><thead><tr>' +
      '<th>Direção</th><th>Categoria</th><th>Tipo (label)</th><th>Stage</th><th>Tabela / Arquivo / Path</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table></div>';
}

function applyLineageDSX() {
  if (!_dsxTargetJobId) return;
  const j = jobsBdata.find(x => x.id === _dsxTargetJobId);
  if (!j) return;

  const now = _nowSql();
  const dsxFile = (_dsxCtx && _dsxCtx.dsx_file) ? _dsxCtx.dsx_file : null;

  // Suporta formato novo (d.direction) e legado (d['Direção'])
  const _getDir = d => (d.direction || d['Direção'] || '').toLowerCase();
  const origens = _dsxLineageData.filter(d => _getDir(d).startsWith('orig'));
  const destinos = _dsxLineageData.filter(d => _getDir(d).startsWith('dest'));
  const transfs  = _dsxLineageData.filter(d => {
    const dir = _getDir(d);
    return !dir.startsWith('orig') && !dir.startsWith('dest');
  });

  const toObj = (x) => ({
    t: x.object_type || x['Tipo de Objeto']
      || (x.type_category === 'arquivo' ? 'Arquivo'
        : x.type_category === 'transformacao' ? 'Transformação' : 'Tabela'),
    n: (x.object_name || x.stage_name || x['Nome do Objeto'] || '').toString(),
    stage_name:      x.stage_name      || x['Nome do Objeto']  || null,
    stage_type_raw:  x.stage_type_raw  || x['Tipo de Objeto']  || null,
    database_name:   x.database_name   || null,
    sql_expression:  x.sql_expression  || x['Tabela / Arquivo'] || null,
    file_path:       x.file_path       || null,
    dsx_source_file: dsxFile,
    extracted_at:    now,
    extraction_method: 'dsx_auto',
  });

  j.origens = origens.map(toObj);
  j.destinos = destinos.map(toObj);
  j.transformacoes = transfs.map(toObj);

  if (!j.origens.length) j.origens = [{ t: 'Tabela', n: '' }];
  if (!j.destinos.length) j.destinos = [{ t: 'Tabela', n: '' }];

  renderModalBody();
  renderJobLinesB();
  closeLineageDSXPreview();
  showToast('Linhagem extraída do DSX aplicada — revise e salve.', false);
}

/* ══ DASHBOARD v2 ══ */
const ORQUESTRA_API = '/orquestra';

function setTodayIfEmptyDate(id) {
  const el = $(id);
  if (!el) return;
  if (el.value) return;
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  el.value = d.getFullYear() + '-' + mm + '-' + dd;
}

function escJsSingle(str) {
  return String(str || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

/* ── Accordion de grupos por projeto no dash-pipelines ── */
function pipGroupToggle(headerRow) {
  const gid = headerRow.dataset.gid;
  if (!gid) return;
  const toggleEl = headerRow.querySelector('.pipe-group-toggle');
  const isOpen = toggleEl && toggleEl.classList.contains('open');
  const tbody = headerRow.closest('tbody');
  if (!tbody) return;
  const childRows = tbody.querySelectorAll('tr[data-group="' + gid + '"]');
  childRows.forEach(r => {
    if (isOpen) { r.classList.add('collapsed'); }
    else        { r.classList.remove('collapsed'); }
  });
  if (toggleEl) toggleEl.classList.toggle('open', !isOpen);
  // persiste estado
  const LS_KEY = 'orq_pipe_groups_collapsed';
  let state = {};
  try { state = JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch(e) {}
  state[gid] = isOpen; // true = colapsado
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch(e) {}
}

function fmtHMS(sec) {
  const n = parseInt(sec || 0, 10);
  if (!n || isNaN(n)) return '—';
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  const s = n % 60;
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

/* ══ BUSCA GLOBAL (Ctrl+K) ══ */
let _ckPipelines = null;   // cache de pipelines para a busca
let _ckSelIdx = 0;

const CK_PAGES = [
  { label: '◫ Ir para Dashboard',  act: () => { $('tab-dashboard').click(); } },
  { label: '≡ Ir para Pipelines',  act: () => { $('tab-pipelines').click(); } },
  { label: '⬡ Ir para Jobs',       act: () => { $('tab-jobs').click(); } },
  { label: '≣ Ir para Logs',       act: () => { $('tab-logs').click(); } },
  { label: '♻ Regenerações de DAG', act: () => { $('tab-logs').click(); setTimeout(() => logsSwitchTab('factory'), 150); } },
  { label: '⬡ Ir para DS Monitor', act: () => { $('tab-ds-monitor').click(); } },
  { label: '◈ Ir para Governança', act: () => { $('tab-governanca').click(); } },
];

function ckOpen() {
  let ov = $('ck-overlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'ck-overlay';
    ov.style = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9000;display:flex;align-items:flex-start;justify-content:center;padding-top:12vh';
    ov.innerHTML =
      '<div style="background:var(--card);border:1px solid var(--border);border-radius:14px;width:560px;max-width:92vw;box-shadow:0 18px 60px rgba(0,0,0,.35);overflow:hidden">' +
        '<input id="ck-input" type="text" placeholder="Buscar pipeline ou ação...  (Esc fecha)" ' +
          'style="width:100%;border:0;outline:0;background:transparent;padding:1rem 1.2rem;font-size:15px;color:var(--text)" ' +
          'oninput="ckRender()" onkeydown="ckKeydown(event)" />' +
        '<div id="ck-results" style="max-height:46vh;overflow-y:auto;border-top:1px solid var(--border)"></div>' +
      '</div>';
    ov.addEventListener('click', (e) => { if (e.target === ov) ckClose(); });
    document.body.appendChild(ov);
  }
  ov.style.display = 'flex';
  _ckSelIdx = 0;
  const inp = $('ck-input');
  inp.value = '';
  setTimeout(() => inp.focus(), 30);
  ckRender();
  // Carrega pipelines em background na primeira abertura
  if (_ckPipelines === null) {
    _ckPipelines = [];
    fetch(ORQUESTRA_API + '/pipelines?limit=500')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) { _ckPipelines = d.data || []; ckRender(); } })
      .catch(() => {});
  }
}

function ckClose() {
  const ov = $('ck-overlay');
  if (ov) ov.style.display = 'none';
}

function ckItems() {
  const q = ($('ck-input') ? $('ck-input').value : '').trim().toLowerCase();
  const items = [];
  for (const p of CK_PAGES) {
    if (!q || p.label.toLowerCase().includes(q)) items.push({ label: p.label, sub: 'Navegação', act: p.act });
  }
  if (q && _ckPipelines && _ckPipelines.length) {
    for (const p of _ckPipelines) {
      const nm = p.pipeline_name || '';
      if (nm.toLowerCase().includes(q)) {
        items.push({
          label: '≡ ' + nm,
          sub: (p.project_name || '') + (p.active ? ' · ativo' : ' · inativo'),
          act: () => {
            $('tab-pipelines').click();
            setTimeout(() => { const f = $('qf-name'); if (f) { f.value = nm; } loadQuery(0); }, 200);
          },
        });
        if (items.length > 25) break;
      }
    }
  }
  return items.slice(0, 25);
}

function ckRender() {
  const res = $('ck-results');
  if (!res) return;
  const items = ckItems();
  if (_ckSelIdx >= items.length) _ckSelIdx = Math.max(0, items.length - 1);
  res.innerHTML = items.length
    ? items.map((it, i) =>
        '<div onclick="ckExec(' + i + ')" onmouseenter="_ckSelIdx=' + i + ';ckHighlight()" data-ck-idx="' + i + '" ' +
          'style="padding:.6rem 1.2rem;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:1rem' +
          (i === _ckSelIdx ? ';background:color-mix(in srgb, var(--cvp-blue) 12%, transparent)' : '') + '">' +
          '<span style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + it.label + '</span>' +
          '<span style="font-size:10px;color:var(--muted);white-space:nowrap">' + (it.sub || '') + '</span>' +
        '</div>').join('')
    : '<div style="padding:1rem 1.2rem;font-size:12px;color:var(--muted)">Nada encontrado.</div>';
}

function ckHighlight() {
  const res = $('ck-results');
  if (!res) return;
  res.querySelectorAll('[data-ck-idx]').forEach(el => {
    const i = parseInt(el.getAttribute('data-ck-idx'), 10);
    el.style.background = (i === _ckSelIdx) ? 'color-mix(in srgb, var(--cvp-blue) 12%, transparent)' : '';
  });
}

function ckExec(i) {
  const items = ckItems();
  if (items[i]) { ckClose(); items[i].act(); }
}

function ckKeydown(ev) {
  if (ev.key === 'Escape') { ckClose(); return; }
  const items = ckItems();
  if (ev.key === 'ArrowDown') { ev.preventDefault(); _ckSelIdx = Math.min(items.length - 1, _ckSelIdx + 1); ckHighlight(); }
  else if (ev.key === 'ArrowUp') { ev.preventDefault(); _ckSelIdx = Math.max(0, _ckSelIdx - 1); ckHighlight(); }
  else if (ev.key === 'Enter') { ev.preventDefault(); ckExec(_ckSelIdx); }
}

document.addEventListener('keydown', (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
    ev.preventDefault();
    ckOpen();
  }
});

/* ══ GANTT DO DIA ══ */
const GANTT_COLORS = { SUCCESS: 'var(--green)', FAILED: 'var(--red)', WARNING: 'var(--cvp-orange)', RUNNING: 'var(--cvp-blue)' };

async function loadDashGantt() {
  const box = $('dash-gantt');
  if (!box) return;
  try {
    const proj    = $('df-project') ? $('df-project').value.trim() : '';
    const dateRef = $('df-date')    ? $('df-date').value.trim()    : '';
    const params  = new URLSearchParams();
    if (proj)    params.set('filter_project', proj);
    if (dateRef) params.set('date_ref', dateRef);
    const r = await fetch(ORQUESTRA_API + '/dashboard/gantt?' + params.toString());
    if (!r.ok) { box.innerHTML = '<p style="font-size:12px;color:var(--muted)">Erro ao carregar linha do tempo (' + r.status + ')</p>'; return; }
    const data = (await r.json()).data || [];
    if ($('gantt-count')) $('gantt-count').textContent = '(' + data.length + ')';
    if (!data.length) {
      box.innerHTML = '<p style="font-size:12px;color:var(--muted)">Nenhuma execução no dia.</p>';
      return;
    }
    // Janela: min(início) → max(fim)
    const toMs = (s) => s ? new Date(String(s).replace(' ', 'T')).getTime() : null;
    let tMin = Infinity, tMax = -Infinity;
    for (const d of data) {
      const a = toMs(d.inicio), b = toMs(d.fim) || Date.now();
      if (a) tMin = Math.min(tMin, a);
      if (b) tMax = Math.max(tMax, b);
    }
    if (!isFinite(tMin) || tMax <= tMin) { box.innerHTML = ''; return; }
    const span = tMax - tMin;
    const fmtH = (ms) => new Date(ms).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

    // Régua de horas (4 marcos)
    let ruler = '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin:0 0 .3rem 180px">';
    for (let i = 0; i <= 4; i++) ruler += '<span>' + fmtH(tMin + span * i / 4) + '</span>';
    ruler += '</div>';

    const rows = data.map(d => {
      const a = toMs(d.inicio), b = toMs(d.fim) || Date.now();
      const left  = Math.max(0, (a - tMin) / span * 100);
      const width = Math.max(0.8, (b - a) / span * 100);
      const color = GANTT_COLORS[d.status] || 'var(--muted)';
      const durMin = Math.round((b - a) / 60000);
      const durTxt = durMin >= 60 ? Math.floor(durMin/60) + 'h' + (durMin%60 ? (durMin%60) + 'min' : '') : durMin + 'min';
      const crit = d.criticidade === 'ALTA' ? ' 🔺' : '';
      return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;cursor:pointer" ' +
        'onclick="openLogDetail(decodeURIComponent(\'' + encodeURIComponent(d.execution_id) + '\'),decodeURIComponent(\'' + encodeURIComponent(d.pipeline) + '\'))" ' +
        'title="' + d.pipeline + ' — ' + d.status + ' — ' + d.inicio + ' → ' + (d.fim || 'agora') + ' (' + durTxt + ')">' +
        '<div style="width:172px;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right" title="' + d.pipeline + '">' + d.pipeline + crit + '</div>' +
        '<div style="flex:1;position:relative;height:16px;background:var(--bg);border-radius:4px">' +
          '<div style="position:absolute;left:' + left + '%;width:' + width + '%;height:100%;background:' + color + ';border-radius:4px;opacity:.85"></div>' +
        '</div>' +
        '<div style="width:52px;font-size:10px;color:var(--muted);white-space:nowrap">' + durTxt + '</div>' +
      '</div>';
    }).join('');

    box.innerHTML = ruler + '<div style="max-height:320px;overflow-y:auto;padding-right:4px">' + rows + '</div>';
  } catch(e) {
    box.innerHTML = '<p style="font-size:12px;color:var(--muted)">Erro: ' + (e.message || e) + '</p>';
  }
}

async function loadDashboard() {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  setTodayIfEmptyDate('df-date');

  const st = $('dash-status');
  const btn = $('btn-dash');
  const btnTxt = $('btn-dash-txt');
  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = 'Atualizando...';
  if (st) st.textContent = 'Consultando dashboard...';

  try {
    const proj    = $('df-project') ? $('df-project').value.trim() : '';
    const dateRef = $('df-date')    ? $('df-date').value.trim()    : '';
    const params  = new URLSearchParams();
    if (proj)    params.set('filter_project', proj);
    if (dateRef) params.set('date_ref', dateRef);

    const url = ORQUESTRA_API + '/dashboard' + (params.toString() ? '?' + params.toString() : '');
    const r = await fetch(url);
    if (!r.ok) { if (st) st.textContent = 'Erro API: ' + r.status; return; }

    const payload = await r.json();
    renderDashboard(payload);
    if (st) st.textContent = '';
    _updateDashLastUpdated();
    window.__lastDashPayload = payload;
    _updateFailureBadge(_extractFailuresFromDash(payload));
  } catch (e) {
    if (st) st.textContent = 'Erro: ' + (e && e.message ? e.message : e);
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Atualizar';
  }
}

function renderDashboard(result) {
  const dateRef = (result && result.date_ref) || '';
  if ($('dash-date-label')) $('dash-date-label').textContent = dateRef ? ('Data: ' + dateRef) : '';

  const k = (result && result.kpis) || {};
  const total = k.total_execucoes ?? 0;
  const falha = k.total_falha ?? 0;
  const warn = k.total_warning ?? 0;
  const dur = k.duracao_media_segundos ?? 0;
  const taxa = (k.taxa_sucesso_pct !== undefined && k.taxa_sucesso_pct !== null) ? k.taxa_sucesso_pct : 0;

  $('kpi-total').textContent = String(total);
  $('kpi-total-sub').textContent = (k.filter_project ? 'Projeto: ' + k.filter_project : 'Todos os projetos');
  $('kpi-taxa').textContent = String(taxa).replace('.', ',') + '%';
  $('kpi-taxa-sub').textContent = (k.total_sucesso ?? 0) + ' sucesso(s)';
  $('kpi-falha').textContent = String(falha);
  $('kpi-falha-sub').textContent = falha ? 'Atenção: falhas hoje' : 'Sem falhas hoje';
  $('kpi-dur').textContent = fmtHMS(dur);

  const runningNow = ((result && result.executando_agora) || []).length;
  $('kpi-running').textContent = String(runningNow);

  // Espera em fila WM DataStage
  const filaMedia = k.fila_media_segundos ?? 0;
  const filaJobs  = k.fila_jobs ?? 0;
  if ($('kpi-fila')) {
    $('kpi-fila').textContent = filaJobs ? fmtHMS(filaMedia) : '—';
    $('kpi-fila-sub').textContent = filaJobs
      ? filaJobs + ' job(s) · pico ' + fmtHMS(k.fila_max_segundos ?? 0)
      : 'sem espera registrada hoje';
  }

  // Gantt do dia (não-bloqueante)
  loadDashGantt();

  // Badges por projeto
  const proj = (k.por_projeto || []);
  const pb = $('dash-projetos');
  if (pb) {
    pb.innerHTML = proj.length
      ? proj.map(p => {
          const cls = p.falhas > 0 ? 'fail' : (p.warnings > 0 ? 'warn' : 'ok');
          return '<span class="proj-badge ' + cls + '">' + (p.project || '—') +
            '<span style="opacity:.7;font-weight:400">·</span>' + (p.execucoes ?? 0) + '</span>';
        }).join('')
      : '<span style="font-size:12px;color:var(--muted)">Nenhum dado por projeto.</span>';
  }

  // Alertas performance
  const alertas = (result && result.alertas_perf) || [];
  $('dash-alerta-count').textContent = alertas.length ? ('(' + alertas.length + ')') : '(0)';
  const da = $('dash-alertas');
  if (da) {
    da.innerHTML = alertas.length ? alertas.map(a => {
      const h = parseInt(a.alerta_horas || 3, 10);
      const cls = h >= 12 ? 'alerta-12h' : (h >= 6 ? 'alerta-6h' : 'alerta-3h');
      const badge = h >= 12 ? '12h+' : (h >= 6 ? '6h+' : '3h+');
      return '<div class="alerta-row ' + cls + '">' +
        '<span class="alerta-badge" style="border-color:currentColor">' + badge + '</span>' +
        '<span style="font-weight:500;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (a.pipeline || '—') + '</span>' +
        '<span style="margin-left:auto;opacity:.9">' + (a.elapsed_seconds ? fmtHMS(a.elapsed_seconds) : '—') + '</span>' +
      '</div>';
    }).join('') : '<p style="font-size:12px;color:var(--muted);margin:0">Sem alertas no momento.</p>';
  }

  // Executando agora
  const rn = (result && result.executando_agora) || [];
  $('dash-running-count').textContent = rn.length ? ('(' + rn.length + ')') : '(0)';
  const ra = $('dash-running-area');
  if (ra) {
    ra.innerHTML = rn.length ? rn.map(x => {
      const ex = escJsSingle(x.execution_id);
      const pip = escJsSingle(x.pipeline);
      return '<div class="running-row">' +
        '<span style="font-weight:500;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (x.pipeline || '—') + '</span>' +
        '<span class="tag-pill">' + (x.project || '—') + '</span>' +
        '<span style="margin-left:auto;color:var(--muted)">' + fmtHMS(x.elapsed_seconds) + '</span>' +
        '<button class="btn-ver-jobs" onclick="openLogDetail(\'' + ex + '\',\'' + pip + '\')" title="Ver jobs desta execução" style="margin-left:.4rem">' + ICONS.detail + '</button>' +
      '</div>';
    }).join('') : '<p style="font-size:12px;color:var(--muted);margin:0">Nenhum pipeline em execução.</p>';
  }

  // Status por pipeline (última execução)
  const ps = (result && result.pipeline_status) || [];
  $('dash-pipe-count').textContent = ps.length ? ('(' + ps.length + ')') : '(0)';

  // KPI falhas críticas
  const critFails = ps.filter(p =>
    (p.criticidade || '').toUpperCase() === 'ALTA' &&
    (p.ultimo_status || '').toUpperCase() === 'FAILED'
  ).length;
  const critCard = $('kpi-crit-card');
  const critVal  = $('kpi-crit');
  const critSub  = $('kpi-crit-sub');
  if (critVal) critVal.textContent = String(critFails);
  if (critSub) critSub.textContent = critFails > 0 ? '⚠ Atenção imediata!' : 'Nenhuma no momento';
  if (critCard) critCard.classList.toggle('has-alert', critFails > 0);

  const dp = $('dash-pipelines');
  if (dp) {
    const pill = (s) => {
      const v = (s || '').toUpperCase();
      if (v === 'SUCCESS') return '<span class="log-pill success">✓ SUCCESS</span>';
      if (v === 'FAILED')  return '<span class="log-pill failed">✕ FAILED</span>';
      if (v === 'WARNING') return '<span class="log-pill warning">! WARNING</span>';
      if (v === 'RUNNING') return '<span class="log-pill running">… RUNNING</span>';
      return '<span class="log-pill running">… ' + (v || '—') + '</span>';
    };
    const critBadge = (c) => {
      const v = (c || '').toUpperCase();
      if (v === 'ALTA')  return '<span class="crit-badge crit-alta">▲ ALTA</span>';
      if (v === 'MEDIA') return '<span class="crit-badge crit-media">◆ MÉDIA</span>';
      if (v === 'BAIXA') return '<span class="crit-badge crit-baixa">▼ BAIXA</span>';
      return '<span class="crit-badge" style="opacity:.35">—</span>';
    };

    if (!ps.length) {
      dp.innerHTML = '<p style="font-size:12px;color:var(--muted);margin:0">Sem dados.</p>';
    } else {
      // ── Lê estado persistido no localStorage ──
      const LS_KEY = 'orq_pipe_groups_collapsed';
      let collapsed = {};
      try { collapsed = JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch(e) {}

      // ── Agrupa por project ──
      const groups = {};
      ps.forEach(p => {
        const proj = p.project || '(sem projeto)';
        if (!groups[proj]) groups[proj] = [];
        groups[proj].push(p);
      });

      // ── Calcula resumo do grupo ──
      const groupSummary = (items) => {
        let ok=0, fail=0, warn=0, run=0;
        let topCrit = ''; // ALTA > MEDIA > BAIXA
        const critRank = {ALTA:3, MEDIA:2, BAIXA:1};
        items.forEach(p => {
          const st = (p.ultimo_status||'').toUpperCase();
          if (st === 'SUCCESS') ok++;
          else if (st === 'FAILED') fail++;
          else if (st === 'WARNING') warn++;
          else if (st === 'RUNNING') run++;
          const cr = (p.criticidade||'').toUpperCase();
          if ((critRank[cr]||0) > (critRank[topCrit]||0)) topCrit = cr;
        });
        let badges = '';
        if (ok)   badges += '<span class="log-pill success" style="font-size:10px;padding:1px 6px">✓ '+ok+'</span>';
        if (fail) badges += '<span class="log-pill failed"  style="font-size:10px;padding:1px 6px">✕ '+fail+'</span>';
        if (warn) badges += '<span class="log-pill warning" style="font-size:10px;padding:1px 6px">! '+warn+'</span>';
        if (run)  badges += '<span class="log-pill running" style="font-size:10px;padding:1px 6px">… '+run+'</span>';
        return { badges, topCrit, hasFail: fail > 0, hasRun: run > 0 };
      };

      // ── Monta HTML ──
      let rows = '';
      Object.entries(groups).sort((a,b) => a[0].localeCompare(b[0])).forEach(([proj, items]) => {
        const gid = 'pg_' + proj.replace(/[^a-zA-Z0-9]/g,'_');
        const isOpen = collapsed[gid] !== true; // aberto por padrão
        const { badges, topCrit } = groupSummary(items);
        const toggleIcon = '<span class="toggle-icon">▶</span>';
        rows += '<tr class="pipe-group-header" data-gid="'+gid+'" onclick="pipGroupToggle(this)">' +
          '<td colspan="8">' +
            '<span class="pipe-group-toggle'+(isOpen?' open':'')+'">' +
              toggleIcon +
              '<span class="pipe-group-name">'+proj+'</span>' +
              '<span class="pipe-group-count">('+items.length+')</span>' +
            '</span>' +
            '<span class="pipe-group-summary">'+badges+'</span>' +
            '<span style="margin-left:.5rem">'+critBadge(topCrit)+'</span>' +
          '</td>' +
        '</tr>';

        items.forEach(p => {
          const ex = escJsSingle(p.execution_id);
          const pip = escJsSingle(p.pipeline);
          const isCritFail = (p.criticidade||'').toUpperCase()==='ALTA' && (p.ultimo_status||'').toUpperCase()==='FAILED';
          rows += '<tr class="pipe-group-rows'+(isOpen?'':' collapsed')+' '+(isCritFail?'pipe-row-crit-fail':'')+'" data-group="'+gid+'">' +
            '<td style="font-weight:500;white-space:nowrap;padding-left:1.6rem">' + (p.pipeline || '—') + '</td>' +
            '<td>' + critBadge(p.criticidade) + '</td>' +
            '<td style="white-space:nowrap">' + pill(p.ultimo_status) + '</td>' +
            '<td style="white-space:nowrap">' + (p.ultimo_inicio ? String(p.ultimo_inicio).slice(0,16) : '—') + '</td>' +
            '<td style="white-space:nowrap">' + fmtHMS(p.duracao_segundos) + '</td>' +
            '<td style="text-align:center">' + (p.total_jobs ?? '—') + '</td>' +
            '<td></td>' +
            '<td style="white-space:nowrap"><button class="btn-ver-jobs" onclick="event.stopPropagation();openLogDetail(\''+ex+'\',\''+pip+'\')" title="Ver jobs desta execução">'+ICONS.detail+'</button></td>' +
          '</tr>';
        });
      });

      dp.innerHTML = '<div class="query-table-wrap"><table class="query-table"><thead><tr>' +
        '<th>Pipeline</th><th>Crit.</th><th>Status</th><th>Último início</th><th>Duração</th><th>Jobs</th><th></th><th>Ações</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table></div>';
    }
  }

  // Últimas falhas
  const ff = (result && result.ultimas_falhas) || [];
  $('dash-fail-count').textContent = ff.length ? ('(' + ff.length + ')') : '(0)';
  const df = $('dash-falhas');
  if (df) {
    df.innerHTML = ff.length ? ff.map(f => {
      const ex = escJsSingle(f.execution_id);
      const pip = escJsSingle(f.pipeline);
      return '<div class="failure-row">' +
        '<span class="log-pill failed">✕</span>' +
        '<div class="fr-body">' +
          '<div class="fr-name">' + (f.job_name || '—') + '</div>' +
          '<div class="fr-meta">' + (f.pipeline || '—') + ' · ' + (f.project || '—') + (f.inicio ? (' · ' + String(f.inicio).slice(0,16)) : '') + '</div>' +
        '</div>' +
        '<button class="btn-ver-jobs" onclick="openLogDetail(\'' + ex + '\',\'' + pip + '\')" title="Ver jobs desta execução" style="margin-left:auto">' + ICONS.detail + '</button>' +
      '</div>';
    }).join('') : '<p style="font-size:12px;color:var(--muted);margin:0">Sem falhas recentes.</p>';
  }
}

/* ══ GOVERNANÇA v1 ══ */
const LINEAGE_QUERY_DAG = 'etl_lineage_query';
let _govData = null; // cache do resultado da DAG
let _govMode = 'job';

async function loadGovernanca() {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const pipeline = $('gov-pipeline') ? $('gov-pipeline').value.trim() : '';
  if (!pipeline) { showToast('Informe o nome do pipeline.', true); return; }

  const btn = $('btn-gov'), bt = $('btn-gov-txt'), st = $('gov-status');
  if (btn) btn.disabled = true;
  if (bt) bt.textContent = 'Carregando...';
  if (st) st.textContent = 'Consultando lineage...';

  try {
    const r = await fetch(ORQUESTRA_API + '/lineage?pipeline_name=' + encodeURIComponent(pipeline));
    if (r.status === 401) { sair(); return; }
    if (!r.ok) { if (st) st.textContent = 'Erro API ' + r.status; return; }

    _govData = await r.json();
    const jobs = (_govData && _govData.jobs) || [];
    if (st) st.textContent = 'Lineage de ' + jobs.length + ' job(s) carregado.';

    // Preencher seletor de jobs
    const sel = $('gov-job-select');
    if (sel) {
      sel.innerHTML = '<option value="">Selecione o job...</option>';
      jobs.forEach(j => {
        const o = document.createElement('option');
        o.value = j.job_name;
        o.textContent = '#' + j.execution_order + ' ' + j.job_name;
        sel.appendChild(o);
      });
    }

    const modeRow = $('gov-mode-row');
    if (modeRow) modeRow.style.display = '';
    setGovMode('job');
  } catch (e) {
    if (st) st.textContent = 'Erro: ' + (e && e.message ? e.message : e);
  } finally {
    if (btn) btn.disabled = false;
    if (bt) bt.textContent = 'Carregar lineage';
  }
}

function clearGovernanca() {
  if ($('gov-pipeline')) $('gov-pipeline').value = '';
  if ($('gov-status')) $('gov-status').textContent = '';
  const modeRow = $('gov-mode-row'); if (modeRow) modeRow.style.display = 'none';
  const jsel = $('gov-job-selector'); if (jsel) jsel.style.display = 'none';
  const sel = $('gov-job-select'); if (sel) sel.innerHTML = '<option value="">Selecione o job...</option>';
  const vis = $('gov-visual');
  if (vis) vis.innerHTML =
    '<div class="empty-state">' +
      '<span class="es-icon">◈</span>' +
      '<p class="es-title">Informe o pipeline e carregue o lineage</p>' +
      '<p class="es-sub">O diagrama aparecerá aqui.</p>' +
    '</div>';
  _govData = null;
  _govMode = 'job';
}

function setGovMode(mode) {
  _govMode = mode;
  $('gov-btn-job').classList.toggle('active', mode === 'job');
  $('gov-btn-pipe').classList.toggle('active', mode === 'pipeline');
  const jsel = $('gov-job-selector');
  if (jsel) jsel.style.display = mode === 'job' ? '' : 'none';
  if (mode === 'job') renderLineageJob();
  if (mode === 'pipeline') renderLineagePipeline();
}

function _fileBasename(p) {
  if (!p) return p;
  return p.replace(/\\/g, '/').split('/').filter(Boolean).pop() || p;
}

function _lineageNode(label, sublabel, dbName, cls) {
  return '<div class="ls-node"><div class="ls-node-box ' + cls + '">' +
    '<span style="font-size:12px;font-weight:500">' + (label || '—') + '</span>' +
    (sublabel ? '<span class="ls-node-label">' + sublabel + '</span>' : '') +
    (dbName ? '<span class="ls-node-db">' + dbName + '</span>' : '') +
  '</div></div>';
}

// Cria e mostra o popover de drill-down ao clicar em +
function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _lsDetailPopover(btn, content, title) {
  const allItems = (content || '').toString().split('\n').map(s => s.trim()).filter(Boolean);
  const overlay  = document.getElementById('ls-modal-overlay');
  const titleEl  = document.getElementById('ls-modal-title');
  const countEl  = document.getElementById('ls-modal-count');
  const searchEl = document.getElementById('ls-modal-search');
  const listEl   = document.getElementById('ls-modal-list');

  titleEl.textContent = title || 'Detalhes';
  countEl.textContent = allItems.length + ' ' + (title && title.toLowerCase().includes('campo') ? 'campos' : 'itens');
  searchEl.value = '';

  listEl.innerHTML = allItems.length
    ? allItems.map(item => '<li class="ls-mitem">' + _escHtml(item) + '</li>').join('')
    : '<li class="ls-mitem" style="color:var(--muted)">—</li>';

  const liItems = listEl.querySelectorAll('.ls-mitem');

  searchEl.oninput = function() {
    const q = searchEl.value.toLowerCase();
    let vis = 0;
    liItems.forEach(li => {
      const match = !q || li.textContent.toLowerCase().includes(q);
      li.hidden = !match;
      if (match) vis++;
    });
    const noun = title && title.toLowerCase().includes('campo') ? 'campos' : 'itens';
    countEl.textContent = q ? (vis + ' de ' + allItems.length + ' ' + noun) : (allItems.length + ' ' + noun);
  };

  overlay.classList.add('open');
  if (allItems.length > 8) setTimeout(() => searchEl.focus(), 50);
}

// Fecha modal ao clicar no overlay fora do box
document.addEventListener('click', function(e) {
  const overlay = document.getElementById('ls-modal-overlay');
  if (overlay && overlay.classList.contains('open') && e.target === overlay)
    overlay.classList.remove('open');
});
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const overlay = document.getElementById('ls-modal-overlay');
    if (overlay) overlay.classList.remove('open');
  }
});


// Delegação de eventos para botões "+" da Governança
// (evita quebra de HTML por aspas no onclick inline com JSON.stringify)
document.addEventListener('click', function(e) {
  const btn = e.target && e.target.closest ? e.target.closest('.ls-detail-btn') : null;
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  const enc = btn.getAttribute('data-ls-content') || '';
  let content = '';
  try { content = decodeURIComponent(enc); } catch(_) { content = enc; }
  const title = btn.getAttribute('data-ls-title') || 'Detalhes';
  _lsDetailPopover(btn, content, title);
});

function renderLineageJob() {
  const vis = $('gov-visual');
  if (!vis || !_govData) return;
  const sel = $('gov-job-select');
  const jobName = sel ? sel.value : '';
  if (!jobName) {
    vis.innerHTML = '<div class="empty-state"><span class="es-icon">◎</span><p class="es-title">Selecione um job</p></div>';
    return;
  }

  const job = (_govData.jobs || []).find(j => j.job_name === jobName);
  if (!job) {
    vis.innerHTML = '<div class="empty-state"><p class="es-title">Job não encontrado.</p></div>';
    return;
  }

  const ori = job.origens || [];
  const trf = job.transformacoes || [];
  const dst = job.destinos || [];
  if (!ori.length && !dst.length && !trf.length) {
    vis.innerHTML =
      '<div class="empty-state">' +
        '<span class="es-icon">◎</span>' +
        '<p class="es-title">Sem lineage cadastrado para este job</p>' +
        '<p class="es-sub">Cadastre origens e destinos na tela de Jobs.</p>' +
      '</div>';
    return;
  }

  vis.innerHTML = _lineageJobDiagramHtml(job);
}

// Diagrama de lineage de um job (origens → [transformações] → job → destinos).
// Reutilizado pela Governança (renderLineageJob) e pelo modal de lineage da tela de Jobs.
function _lineageJobDiagramHtml(job) {
  const ori = job.origens || [];
  const trf = job.transformacoes || [];
  const dst = job.destinos || [];

  const mk = (o, cls) => {
    const isTransf = cls === 'transf';
    const isFile   = !isTransf && !!o.file_path;
    const isDb     = !isTransf && !isFile && (!!o.database_name || !!(o.object_type || '').toLowerCase().includes('odbc') || !!(o.object_type || '').toLowerCase().includes('banco'));

    // Label principal = stage_name sempre
    const label = o.stage_name || o.object_name || '—';

    // Linha de tipo simplificada + detalhe em negrito
    let detailLine = '';
    if (isFile) {
      detailLine = 'Arquivo' + (o.file_path ? ': <strong>' + _fileBasename(o.file_path) + '</strong>' : '');
    } else if (isDb) {
      detailLine = 'ODBC' + (o.database_name ? ': <strong>' + o.database_name + '</strong>' : '');
    } else {
      const typeBase = o.type_label || o.object_type || '';
      if (typeBase) detailLine = typeBase;
    }

    // Botão SQL — só para banco, quando há sql_expression
    const sqlStr = (!isFile && o.sql_expression) ? String(o.sql_expression).trim() : '';
    const btnHtml = sqlStr
      ? ('<button class="ls-detail-btn" ' +
          'title="Ver SQL / tabelas" ' +
          'data-ls-title="SQL / Tabelas" ' +
          'data-ls-content="' + encodeURIComponent(sqlStr) + '">+</button>')
      : '';

    // Botão colunas — banco e arquivo
    const cols = Array.isArray(o.columns) ? o.columns : [];
    const colsHtml = cols.length
      ? ('<button class="ls-detail-btn" ' +
          'title="Ver campos utilizados" ' +
          'data-ls-title="Campos utilizados (' + cols.length + ')" ' +
          'data-ls-content="' + encodeURIComponent(cols.join('\n')) + '" ' +
          'style="background:rgba(243,146,0,.12);border-color:var(--cvp-orange);color:#b45309">⊞</button>')
      : '';

    return '<div class="ls-node"><div class="ls-node-box ' + cls + '">' +
      '<div style="display:flex;align-items:center;justify-content:center;gap:4px">' +
        '<span style="font-size:12px;font-weight:500">' + label + '</span>' +
        btnHtml +
        colsHtml +
      '</div>' +
      (detailLine ? '<span class="ls-node-label">' + detailLine + '</span>' : '') +
    '</div></div>';
  };

  const oriH = ori.map(o => mk(o, 'origem')).join('<div style="height:8px"></div>');
  const trfH = trf.map(o => mk(o, 'transf')).join('<div style="height:8px"></div>');
  const dstH = dst.map(d => mk(d, 'destino')).join('<div style="height:8px"></div>');
  const jobH = _lineageNode(job.job_name, 'Job #' + job.execution_order, job.job_type, 'job');

  const hasTrans = trf.length > 0;
  return '<div class="lineage-svg-wrap">' +
      '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">' +
        '<div style="display:flex;flex-direction:column;gap:8px">' + (oriH || '<i style="font-size:12px;color:var(--muted)">Sem origens</i>') + '</div>' +
        '<div class="ls-arrow">→</div>' +
        (hasTrans
          ? ('<div style="display:flex;flex-direction:column;gap:8px">' + (trfH || '<i style="font-size:12px;color:var(--muted)">Sem transformações</i>') + '</div>' +
             '<div class="ls-arrow">→</div>')
          : ''
        ) +
        jobH +
        '<div class="ls-arrow">→</div>' +
        '<div style="display:flex;flex-direction:column;gap:8px">' + (dstH || '<i style="font-size:12px;color:var(--muted)">Sem destinos</i>') + '</div>' +
      '</div>' +
    '</div>';
}

function renderLineagePipeline() {
  const vis = $('gov-visual');
  if (!vis || !_govData) return;
  const jobs = (_govData.jobs) || [];
  if (!jobs.length) {
    vis.innerHTML = '<div class="empty-state"><p class="es-title">Nenhum job encontrado.</p></div>';
    return;
  }

  const mkMini = (o, cls) => {
    const lbl   = o.stage_name || o.object_name || '?';
    const isFile = !!o.file_path;
    const sub   = isFile
      ? ('Arquivo: <strong>' + _fileBasename(o.file_path) + '</strong>')
      : (o.database_name ? ('ODBC: <strong>' + o.database_name + '</strong>') : (o.object_type || ''));
    const cols  = Array.isArray(o.columns) ? o.columns : [];
    const chip  = cols.length
      ? ('<button class="ls-detail-btn" style="background:rgba(243,146,0,.12);border-color:var(--cvp-orange);color:#b45309" ' +
         'data-ls-title="Campos (' + cols.length + ')" data-ls-content="' + encodeURIComponent(cols.join('\n')) + '">⊞</button>')
      : '';
    return '<div class="ls-node"><div class="ls-node-box ' + cls + '" style="min-width:120px;max-width:200px">' +
      '<div style="display:flex;align-items:center;gap:4px;justify-content:center">' +
        '<span style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + lbl + '">' + lbl + '</span>' +
        chip +
      '</div>' +
      (sub ? '<span class="ls-node-label" style="font-size:9px">' + sub + '</span>' : '') +
    '</div></div>';
  };

  const stepsHtml = jobs.map((job, idx) => {
    const ori = (job.origens || []).map(o => mkMini(o, 'origem')).join('');
    const dst = (job.destinos || []).map(d => mkMini(d, 'destino')).join('');

    const connector = idx < jobs.length - 1 ? '<div class="pf-connector"></div>' : '';
    return '<div>' +
      '<div class="pf-step">' +
        '<div class="pf-order">' + job.execution_order + '</div>' +
        (ori
          ? '<div style="display:flex;flex-direction:column;gap:4px">' + ori + '</div><div class="ls-arrow" style="font-size:14px">→</div>'
          : '<span style="font-size:11px;color:var(--muted);margin:0 6px">sem origens →</span>'
        ) +
        '<div class="ls-node"><div class="ls-node-box job" style="min-width:140px">' +
          '<span style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block" title="' + job.job_name + '">' + job.job_name + '</span>' +
          '<span class="ls-node-label">Job #' + job.execution_order + ' · ' + (job.job_type || '') + '</span>' +
        '</div></div>' +
        (dst
          ? '<div class="ls-arrow" style="font-size:14px">→</div><div style="display:flex;flex-direction:column;gap:4px">' + dst + '</div>'
          : '<span style="font-size:11px;color:var(--muted);margin:0 6px">→ sem destinos</span>'
        ) +
      '</div>' +
      connector +
    '</div>';
  }).join('');

  vis.innerHTML = '<div class="lineage-svg-wrap" style="overflow-x:auto"><div class="pipeline-flow">' + stepsHtml + '</div></div>';
}

function _linToRowB(o) {
  // Converte item do GET /lineage para o formato de linha do modal ({t, n, ...extras})
  return {
    t: o.object_type || 'Tabela', n: o.object_name || '',
    stage_name: o.stage_name || null, stage_type_raw: o.stage_type_raw || null,
    database_name: o.database_name || null, sql_expression: o.sql_expression || null,
    file_path: o.file_path || null, dsx_source_file: o.dsx_source_file || null,
    extracted_at: o.extracted_at || null, extraction_method: o.extraction_method || null,
    columns: Array.isArray(o.columns) ? o.columns : null,
  };
}

async function openJobLineageFromTable(idx) {
  const list = window.__jobs || [];
  const j = list[idx];
  if (!j) return;

  // Prepara jobsBdata com apenas este job
  jobsBdata = [];
  jbLineId  = 0;
  addJobLineB({
    job_name:        j.job_name,
    execution_order: j.execution_order,
    job_type:        j.job_type || 'datastage',
    job_command:     j.job_command || null,
  });

  // Garante que pipeline está preenchido (necessário para DSX + save)
  if ($('job_pipeline_name') && j.pipeline_name) {
    $('job_pipeline_name').value = j.pipeline_name;
  }

  // Guarda contexto: ao fechar o modal, salva automaticamente
  // project_name vem do resultado da DAG etl_pipeline_job_query (campo adicionado no Fix do backend)
  // Fallback: tenta inferir do nome do pipeline para retrocompatibilidade
  const project = j.project_name || _inferProjectFromPipeline(j.pipeline_name) || null;
  window.__lineageTableCtx = { pipeline: j.pipeline_name, project: project, source: 'jobEdit' };

  openLineageModal(jobsBdata[0].id);

  // Carrega a lineage já cadastrada no banco para permitir editar/excluir
  try {
    const r = await fetch(ORQUESTRA_API + '/lineage?pipeline_name=' + encodeURIComponent(j.pipeline_name));
    if (r.ok) {
      const data = await r.json();
      const dbJob = ((data && data.jobs) || []).find(x => x.job_name === j.job_name);
      const jb = jobsBdata[0];
      if (dbJob && jb) {
        if ((dbJob.origens  || []).length) jb.origens  = dbJob.origens.map(_linToRowB);
        if ((dbJob.destinos || []).length) jb.destinos = dbJob.destinos.map(_linToRowB);
        jb.transformacoes = (dbJob.transformacoes || []).map(_linToRowB);
        renderModalBody();
      }
    }
  } catch(_) { /* sem lineage prévia — segue com linhas vazias */ }

  // Snapshot para detectar se houve alteração ao fechar
  if (window.__lineageTableCtx) {
    window.__lineageTableCtx.orig = JSON.stringify(collectJobRows());
  }
}

/* ══ NOME DO USUÁRIO (intranet CVP) ══ */
const USER_NAME_API = 'https://servicosaondev.caixavidaeprevidencia.intranet/api/AssistenteOnline/AssistenteOnline_UsuarioLoginAd';

async function fetchUserFirstName() {
  // Busca o nome do usuário logado via Windows Authentication.
  // O endpoint usa a sessão Windows do navegador (Kerberos/NTLM) — igual ao acesso direto pela URL.
  // NÃO enviar Authorization header — isso abre o dialog de senha do Chrome.
  // credentials:'include' replica o comportamento do browser ao acessar a URL diretamente.
  try {
    const r = await fetch(USER_NAME_API, {
      method: 'GET',
      credentials: 'include',   // envia a sessão Windows do usuário atual
      headers: { 'Accept': 'application/json' },
    });
    if (!r.ok) return null;
    const data = await r.json();
    if (data && data.sucesso && data.data && data.data.dataUsuario && data.data.dataUsuario.desNome) {
      const fullName = String(data.data.dataUsuario.desNome).trim();
      window.__displayName = fullName;   // guarda nome completo para uso no ack
      return fullName.split(' ')[0] || fullName;
    }
    if (data && data.data && data.data.idt_usuario) {
      return String(data.data.idt_usuario).split(' ')[0];
    }
  } catch(e) { /* silencioso — mantém matrícula no header */ }
  return null;
}


/* ══ SPRINT 1: Regenerar DAG, Toggle Airflow, Execução Manual ══ */

// Deriva o dag_id do Airflow a partir do pipeline_name
// Preserva o case exato para corresponder ao dag_id registrado no Airflow
function _pipelineToDagId(pipelineName) {
  return (pipelineName || '');
}

// F3 — Ativar ou pausar uma DAG no Airflow via REST API
async function _toggleDagAirflow(pipelineName, isActive) {
  const dagId = _pipelineToDagId(pipelineName);
  if (!dagId) return;
  try {
    const r = await fetch('/api/v1/dags/' + dagId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ is_paused: !isActive }),
    });
    if (r.status === 404) {
      // DAG ainda não foi criada no Airflow — silencioso
      console.log('[ORQ] DAG não encontrada no Airflow para toggle:', dagId);
      return;
    }
    if (r.ok) {
      showToast(isActive ? 'DAG ativada no Airflow ✓' : 'DAG pausada no Airflow ✓', false);
    }
  } catch(e) {
    console.warn('[ORQ] Não foi possível atualizar status da DAG no Airflow:', e);
  }
}

// F2 — Perguntar se quer regenerar a DAG após uma alteração
async function _offerRegenDag(pipelineName) {
  if (!pipelineName) return;
  const ok = await showConfirm(
    'Pipeline "' + pipelineName + '" salvo com sucesso.\n\nDeseja regenerar a DAG no Airflow agora para aplicar as mudanças?',
    'Regenerar DAG?'
  );
  if (!ok) return;
  const idx = (window.__pipelines || []).findIndex(p => p.pipeline_name === pipelineName);
  const btn = idx >= 0 ? document.getElementById('dag-btn-' + idx) : null;
  if (btn) {
    btn.click();  // reutiliza o botão Gerar/Regenerar existente
  } else {
    // Dispara direto sem precisar do índice
    const runId = 'orquestra_regen_' + Date.now();
    try {
      const r = await fetch('/api/v1/dags/' + DAG_FACTORY_ID + '/dagRuns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
        body: JSON.stringify({ dag_run_id: runId, conf: { pipeline_name: pipelineName } }),
      });
      if (r.ok) {
        showToast('DAG factory disparada para "' + pipelineName + '"', false);
      }
    } catch(e) { showToast('Erro ao disparar factory: ' + e.message, true); }
  }
}

// F4 — Executar pipeline manualmente agora
async function executarPipelineAgora(idx) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const list = window.__pipelines || [];
  const p = list[idx];
  if (!p) return;

  const dagId = _pipelineToDagId(p.pipeline_name);

  const ok = await showConfirm(
    'Executar o pipeline "' + p.pipeline_name + '" agora, fora do agendamento?\n\nUma execução manual será disparada imediatamente no Airflow.',
    '▶ Executar agora'
  );
  if (!ok) return;

  const btn = document.getElementById('exec-btn-' + idx);
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

  try {
    const runId = 'manual_orq_' + Date.now();
    const r = await fetch('/api/v1/dags/' + dagId + '/dagRuns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ dag_run_id: runId, conf: {} }),
    });
    if (r.status === 401) { sair(); return; }
    if (r.status === 404) {
      showToast('DAG "' + dagId + '" não encontrada. Gere o DAG primeiro.', true);
      return;
    }
    if (r.status === 409) {
      showToast('Já existe uma execução ativa para este pipeline.', true);
      return;
    }
    if (!r.ok) {
      showToast('Erro ao executar: ' + r.status, true);
      return;
    }
    const data = await r.json();
    const rid = data.dag_run_id || data.run_id;
    showToast('Pipeline "' + p.pipeline_name + '" disparado! (' + rid + ')', false);

    // Abrir a execução no Airflow Grid após 1s
    setTimeout(() => {
      const airflowUrl = AIRFLOW_UI + '/dags/' + dagId + '/grid';
      const ok2 = window.open(airflowUrl, '_blank');
      if (!ok2) showToast('Popup bloqueado — acesse ' + airflowUrl, false);
    }, 1200);

  } catch(e) {
    showToast('Erro de conexão: ' + (e.message || e), true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '▶'; }
  }
}


// Reexecutar a partir de um job específico com falha (e downstream)
async function _rerunFromTask(pipeline, executionId, taskId, btn) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  if (!pipeline || !taskId) { showToast('Dados insuficientes para reexecutar.', true); return; }

  const ok = await showConfirm(
    'Reexecutar o pipeline "' + pipeline + '" a partir do job "' + taskId + '"?\n\nEste job e todos os jobs posteriores serão limpos e reexecutados.',
    '🔁 Reexecutar a partir daqui'
  );
  if (!ok) return;

  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const r = await fetch(ORQUESTRA_API + '/execucoes/rerun', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({ pipeline_name: pipeline, execution_id: executionId, task_id: taskId }),
    });
    if (r.status === 401) { sair(); return; }
    if (!r.ok) {
      const txt = await r.text().catch(() => r.status);
      showToast('Erro ao reexecutar: ' + txt, true);
      if (btn) { btn.disabled = false; btn.textContent = '🔁 Rerun'; }
      return;
    }
    const data = await r.json();
    showToast('🔁 Reexecução disparada! ' + data.tasks_cleared + ' task(s) limpas — ' + (data.dag_run_id || ''), false);
    if (btn) { btn.textContent = '✓ Disparado'; }
  } catch(e) {
    showToast('Erro de conexão: ' + (e.message || e), true);
    if (btn) { btn.disabled = false; btn.textContent = '🔁 Rerun'; }
  }
}

// Acknowledge de falha — operador assume o incidente e notifica o Teams
async function _ackFailure(executionId, pipeline, btn) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const user        = window.__currentUser || '';
  const displayName = window.__displayName || user;
  if (!user) { showToast('Usuário não identificado.', true); return; }

  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const r = await fetch(ORQUESTRA_API + '/execucoes/ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({
        execution_id: executionId,
        pipeline:     pipeline,
        user:         user,
        display_name: displayName,
      }),
    });
    if (r.status === 401) { sair(); return; }
    if (!r.ok) {
      const txt = await r.text().catch(() => r.status);
      showToast('Erro ao assumir: ' + txt, true);
      if (btn) { btn.disabled = false; btn.textContent = '👁 Assumir'; }
      return;
    }
    const data = await r.json();
    const label = data.display_name || data.ack_by || user;
    showToast('👁 Falha assumida por ' + label, false);
    if (btn) {
      const span = document.createElement('span');
      span.style.cssText = 'font-size:10px;color:var(--muted);white-space:nowrap';
      span.title = 'Assumido em ' + (data.ack_at || '');
      span.textContent = '👁 ' + label;
      btn.replaceWith(span);
    }
  } catch(e) {
    showToast('Erro de conexão: ' + (e.message || e), true);
    if (btn) { btn.disabled = false; btn.textContent = '👁 Assumir'; }
  }
}

// F5 — Reexecutar pipeline direto da tela de Logs (sem trocar de tela)
async function reexecutarDoPipelineLog(pipelineName) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  if (!pipelineName) { showToast('Pipeline não identificado.', true); return; }

  const dagId = _pipelineToDagId(pipelineName);

  const ok = await showConfirm(
    'Reexecutar o pipeline "' + pipelineName + '" agora, fora do agendamento?\n\nUma execução manual será disparada imediatamente no Airflow.',
    '↺ Reexecutar'
  );
  if (!ok) return;

  try {
    const runId = 'manual_orq_' + Date.now();
    const r = await fetch('/api/v1/dags/' + dagId + '/dagRuns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ dag_run_id: runId, conf: {} }),
    });
    if (r.status === 401) { sair(); return; }
    if (r.status === 404) {
      showToast('DAG "' + dagId + '" não encontrada no Airflow. Verifique se a DAG foi gerada.', true);
      return;
    }
    if (r.status === 409) {
      showToast('Já existe uma execução ativa para "' + pipelineName + '". Aguarde a conclusão.', true);
      return;
    }
    if (!r.ok) {
      const txt = await r.text().catch(() => r.status);
      showToast('Erro ao reexecutar: ' + txt, true);
      return;
    }
    const data = await r.json();
    const rid = data.dag_run_id || data.run_id;
    showToast('↺ Pipeline "' + pipelineName + '" disparado! (' + rid + ')', false);
  } catch(e) {
    showToast('Erro de conexão: ' + (e.message || e), true);
  }
}

// F4 — Executar pipeline a partir da aba Jobs
async function executarPipelineDoJob() {
  const pipeline = $('job_pipeline_name') ? $('job_pipeline_name').value.trim() : '';
  if (!pipeline) { showToast('Informe o pipeline antes de executar.', true); return; }
  const dagId = _pipelineToDagId(pipeline);
  const ok = await showConfirm(
    'Executar o pipeline "' + pipeline + '" agora, fora do agendamento?',
    '▶ Executar agora'
  );
  if (!ok) return;
  const btn = $('btn-exec-pipeline');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const runId = 'manual_orq_' + Date.now();
    const r = await fetch('/api/v1/dags/' + dagId + '/dagRuns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ dag_run_id: runId, conf: {} }),
    });
    if (r.status === 404) { showToast('DAG não encontrada. Gere o DAG primeiro.', true); return; }
    if (r.status === 409) { showToast('Já existe uma execução ativa.', true); return; }
    if (!r.ok) { showToast('Erro ao executar: ' + r.status, true); return; }
    const data = await r.json();
    showToast('Pipeline "' + pipeline + '" disparado! (' + (data.dag_run_id || data.run_id) + ')', false);
    setTimeout(() => { window.open(AIRFLOW_UI + '/dags/' + dagId + '/grid', '_blank'); }, 1200);
  } catch(e) {
    showToast('Erro: ' + (e.message || e), true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '▶ Executar agora'; }
  }
}


/* ══ APP CONFIG — parâmetros carregados do banco ══════════════════ */
const APP_CONFIG_DAG = 'etl_app_config_query';
window.__appConfig = {
  dashboard_refresh_interval_sec: 60,
  failure_badge_refresh_sec: 300,
  failure_badge_hours_lookback: 24,
  app_version: '2.1.0',
  app_release_name: 'Sprint 1 — Junho/2026',
  pipeline_query_limit: 20,
  jobs_query_limit: 50,
  logs_query_limit: 30,
};

async function loadAppConfig() {
  try {
    const r = await fetch(ORQUESTRA_API + '/config');
    if (!r.ok) return;
    const cfg = await r.json();
    if (cfg && typeof cfg === 'object') {
      window.__appConfig = { ...window.__appConfig, ...cfg };
      console.log('[ORQ] App config carregado:', window.__appConfig);
      _renderVersionBadge();
    }
  } catch(e) {
    console.warn('[ORQ] Config não carregado, usando defaults:', e.message);
  }
}

/* ══ PIPELINE / PROJECT LIST ══════════════════════════════════════ */
const CATALOGO_DAG = 'etl_catalogo_query';
let _pipeListLoaded = false;

async function loadPipelineList() {
  if (_pipeListLoaded || !authHeader) return;
  _pipeListLoaded = true;
  try {
    const r = await fetch(ORQUESTRA_API + '/catalogo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'list_pipelines' }),
    });
    if (!r.ok) return;
    const data = await r.json();
    const names = (data && data.pipelines) || [];
    const dl = $('gov-pipeline-list');
    if (dl && names.length) {
      dl.innerHTML = names.map(n => `<option value="${_escHtml(n)}">`).join('');
    }
  } catch(_) {}
}

async function loadProjectList() {
  const sel = $('p-project');
  if (!sel || !authHeader) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/catalogo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'list_projects' }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const projects = data.projects || [];
    if (projects.length) {
      sel.innerHTML = '<option value="">Selecione…</option>' +
        projects.map(p => `<option value="${_escHtml(p.project_name)}">${_escHtml(p.project_name)}</option>`).join('');
    } else { throw new Error('empty'); }
  } catch(_) {
    sel.innerHTML = '<option value="">Selecione…</option><option value="BI_CVP">BI_CVP</option><option value="BI_VIDA">BI_VIDA</option><option value="BI_PRESTAMISTA">BI_PRESTAMISTA</option><option value="BI_PREVIDENCIA">BI_PREVIDENCIA</option>';
  }
}

/* ══ VERSÃO — badge no header ════════════════════════════════════ */
function _renderVersionBadge() {
  const el = $('orq-version-badge');
  if (!el) return;
  const v   = window.__appConfig.app_version     || '—';
  const rel = window.__appConfig.app_release_name || '';
  el.textContent = 'v' + v;
  el.title = 'ORQUESTRA v' + v + (rel ? ' · ' + rel : '');
}

/* ══ GOVERNANÇA — tab switch ══════════════════════════════════════ */
function govTabSwitch(tab) {
  ['lineage','catalogo'].forEach(t => {
    const panel = $('gov-panel-' + t);
    const btn   = $('gov-tab-' + t);
    if (panel) panel.style.display = t === tab ? '' : 'none';
    if (btn)   btn.classList.toggle('active', t === tab);
  });
  if (tab === 'catalogo') catMainTab('overview');
}

/* ══ CATÁLOGO DE DADOS — redesign ═══════════════════════════════ */
let _catSearchType  = 'tabela';
let _rankType       = 'tabela';
let _browseData     = null; // cache for explore/list tab
let _catMainTab     = 'overview';

// ── Tab switching ─────────────────────────────────────────────────
function catMainTab(tab) {
  _catMainTab = tab;
  ['overview','explore','list','pipelines'].forEach(t => {
    const btn = $('ctab-' + t), panel = $('cpanel-' + t);
    if (btn)   btn.classList.toggle('active', t === tab);
    if (panel) panel.style.display = t === tab ? '' : 'none';
  });
  if (tab === 'overview' && !_overviewLoaded) catOverviewLoad();
  if ((tab === 'explore' || tab === 'list') && !_browseData) catBrowseLoad();
}

// ── Overview ──────────────────────────────────────────────────────
let _overviewLoaded = false;

async function catOverviewLoad() {
  _overviewLoaded = true;
  const kpiEl = $('cat-kpis'), popEl = $('cat-popular'), alertEl = $('cat-alerts');

  const payload = await _catTrigger({ mode: 'overview' }, '');
  if (!payload) return;

  // KPI strip
  const kpis = [
    { label: 'Objetos', value: payload.total_assets || 0, icon: '◫', color: 'var(--cvp-blue)' },
    { label: 'Pipelines', value: payload.total_pipelines || 0, icon: '◎', color: 'var(--cvp-blue)' },
    { label: 'Com owner', value: (payload.total_with_owner || 0) + ' / ' + (payload.total_pipelines || 0), icon: '👤', color: '#16a34a' },
    { label: 'PII', value: (payload.classification_counts || {}).pii || 0, icon: '🔴', color: '#dc2626', onclick: "catMainTab('explore');document.querySelector('[name=f-class][value=PII]').checked=true;catExploreFilter()" },
    { label: 'Regulado', value: (payload.classification_counts || {}).regulado || 0, icon: '🟣', color: '#7c3aed', onclick: "catMainTab('explore');document.querySelector('[name=f-class][value=Regulado]').checked=true;catExploreFilter()" },
    { label: 'Confidencial', value: (payload.classification_counts || {}).confidencial || 0, icon: '🟠', color: '#ea580c', onclick: "catMainTab('explore');document.querySelector('[name=f-class][value=Confidencial]').checked=true;catExploreFilter()" },
  ];
  if (kpiEl) kpiEl.innerHTML = kpis.map(k =>
    `<div onclick="${k.onclick || ''}" style="border:1px solid var(--border);border-radius:10px;padding:.65rem .85rem;cursor:${k.onclick?'pointer':'default'};transition:box-shadow .15s" onmouseenter="this.style.boxShadow='0 2px 8px rgba(0,0,0,.1)'" onmouseleave="this.style.boxShadow=''">
      <div style="font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.2rem">${k.icon} ${k.label}</div>
      <div style="font-size:20px;font-weight:700;color:${k.color}">${k.value}</div>
    </div>`
  ).join('');

  // Popular assets
  const tops = payload.top_assets || [];
  if (popEl) popEl.innerHTML = tops.length ? tops.map(a =>
    `<div onclick="catAssetDetail('${_escHtml((a.database_name ? a.database_name + '.' : '') + a.asset_name)}','${a.asset_type}','${_escHtml(a.asset_name)}','${_escHtml(a.database_name||'')}')"
      style="border:1px solid var(--border);border-radius:8px;padding:.55rem .75rem;cursor:pointer;transition:all .15s"
      onmouseenter="this.style.background='rgba(0,92,169,.05)'" onmouseleave="this.style.background=''">
      <div style="font-size:11px;font-weight:600;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_escHtml(a.asset_name)}">${_escHtml(a.asset_name)}</div>
      <div style="font-size:10px;color:var(--muted);display:flex;justify-content:space-between;margin-top:2px">
        <span>${a.asset_type === 'arquivo' ? '◈ Arquivo' : '◫ ' + (a.database_name || 'ODBC')}</span>
        <span style="font-weight:600;color:var(--cvp-blue)">${a.pipeline_count} pipeline(s)</span>
      </div>
    </div>`
  ).join('') : '<div style="font-size:12px;color:var(--muted)">Nenhum dado encontrado.</div>';

  // Recently viewed
  _catRenderRecent();

  // Alerts
  const alerts = payload.alerts || [];
  if (alertEl) alertEl.innerHTML = alerts.length ? alerts.map(a =>
    `<div style="font-size:11px;padding:.3rem .5rem;border-left:3px solid ${a.type.includes('pii') ? '#dc2626' : '#d97706'};margin-bottom:.3rem;color:var(--text)">${a.message}</div>`
  ).join('') : '<div style="font-size:11px;color:var(--muted)">Nenhum alerta.</div>';
}

// ── Recently viewed (localStorage) ───────────────────────────────
function _catRecentPush(name, type, dbName) {
  try {
    let list = JSON.parse(localStorage.getItem('orq_cat_recent') || '[]');
    list = list.filter(x => x.name !== name || x.type !== type);
    list.unshift({ name, type, dbName: dbName || '', ts: Date.now() });
    if (list.length > 8) list = list.slice(0, 8);
    localStorage.setItem('orq_cat_recent', JSON.stringify(list));
  } catch(_) {}
}

function _catRenderRecent() {
  const el = $('cat-recent');
  if (!el) return;
  try {
    const list = JSON.parse(localStorage.getItem('orq_cat_recent') || '[]');
    el.innerHTML = list.length ? list.map(x =>
      `<div onclick="catAssetDetail('${_escHtml((x.dbName?x.dbName+'.':'')+x.name)}','${x.type}','${_escHtml(x.name)}','${_escHtml(x.dbName||'')}')"
        style="font-size:11px;padding:.25rem .5rem;border-radius:6px;cursor:pointer;display:flex;align-items:center;gap:.4rem;margin-bottom:2px"
        onmouseenter="this.style.background='rgba(0,92,169,.06)'" onmouseleave="this.style.background=''">
        <span style="color:var(--muted)">${x.type === 'arquivo' ? '◈' : '◫'}</span>
        <span style="font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_escHtml(x.name)}">${_escHtml(x.name)}</span>
        ${x.dbName ? `<span style="font-size:10px;color:var(--muted);flex-shrink:0">${_escHtml(x.dbName)}</span>` : ''}
      </div>`
    ).join('') : '<div style="font-size:11px;color:var(--muted)">—</div>';
  } catch(_) {}
}

// ── Browse / Explore ──────────────────────────────────────────────
async function catBrowseLoad() {
  $('cat-explore-status') && ($('cat-explore-status').textContent = 'Carregando…');
  $('cat-list-status')    && ($('cat-list-status').textContent    = 'Carregando…');

  const payload = await _catTrigger({ mode: 'browse', top_n: 200 }, '');
  if (!payload) return;
  _browseData = payload;

  // Populate database facet select
  const dbSel = $('f-database');
  if (dbSel) {
    const dbs = (payload.facets && payload.facets.databases) || [];
    dbSel.innerHTML = '<option value="">Todos</option>' + dbs.map(d => `<option>${_escHtml(d)}</option>`).join('');
  }

  catExploreFilter();
  catListFilter();
}

function catExploreFilter() {
  if (!_browseData) { catBrowseLoad(); return; }
  const typeVal  = document.querySelector('[name=f-type]:checked')?.value || '';
  const classVal = document.querySelector('[name=f-class]:checked')?.value || '';
  const dbVal    = ($('f-database') || {}).value || '';
  const q        = (($('f-search') || {}).value || '').toLowerCase();

  const assets = (_browseData.assets || []).filter(a =>
    (!typeVal  || a.asset_type === typeVal) &&
    (!dbVal    || a.database_name === dbVal) &&
    (!q        || a.asset_name.toLowerCase().includes(q))
  );

  const st = $('cat-explore-status');
  if (st) st.textContent = assets.length + ' objeto(s)';

  const grid = $('cat-explore-grid');
  if (!grid) return;
  grid.innerHTML = assets.length ? assets.map(a =>
    `<div onclick="catAssetDetail('${_escHtml((a.database_name?a.database_name+'.':'')+a.asset_name)}','${a.asset_type}','${_escHtml(a.asset_name)}','${_escHtml(a.database_name||'')}')"
      style="border:1px solid var(--border);border-radius:8px;padding:.55rem .75rem;cursor:pointer;transition:all .15s"
      onmouseenter="this.style.background='rgba(0,92,169,.05)'" onmouseleave="this.style.background=''">
      <div style="font-size:11px;font-weight:600;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_escHtml(a.asset_name)}">${_escHtml(a.asset_name)}</div>
      <div style="font-size:10px;color:var(--muted);display:flex;justify-content:space-between;margin-top:3px">
        <span>${a.asset_type === 'arquivo' ? '◈ Arquivo' : '◫ ' + (a.database_name || 'ODBC')}</span>
        <span style="font-weight:600">${a.pipeline_count}p</span>
      </div>
    </div>`
  ).join('') : '<div style="font-size:12px;color:var(--muted);padding:.5rem">Nenhum objeto encontrado.</div>';
}

let _listAssets = [];
function catListFilter() {
  if (!_browseData) return;
  const q    = (($('list-search') || {}).value || '').toLowerCase();
  const type = ($('list-type') || {}).value || '';
  _listAssets = (_browseData.assets || []).filter(a =>
    (!q    || a.asset_name.toLowerCase().includes(q)) &&
    (!type || a.asset_type === type)
  );
  catListSort();
}

function catListSort() {
  const sort = ($('list-sort') || {}).value || 'pipeline_count';
  _listAssets.sort((a, b) => {
    if (sort === 'asset_name') return a.asset_name.localeCompare(b.asset_name);
    return (b[sort] || 0) - (a[sort] || 0);
  });
  _catRenderList();
}

function _catRenderList() {
  const st = $('cat-list-status');
  if (st) st.textContent = _listAssets.length + ' objeto(s)';
  const body = $('cat-list-body');
  if (!body) return;
  body.innerHTML = _listAssets.map(a =>
    `<div onclick="catAssetDetail('${_escHtml((a.database_name?a.database_name+'.':'')+a.asset_name)}','${a.asset_type}','${_escHtml(a.asset_name)}','${_escHtml(a.database_name||'')}')"
      style="display:grid;grid-template-columns:1fr 80px 120px 60px 60px 80px;gap:8px;padding:.4rem .75rem;border-bottom:1px solid var(--border);font-size:12px;cursor:pointer;transition:background .1s"
      onmouseenter="this.style.background='rgba(0,92,169,.04)'" onmouseleave="this.style.background=''">
      <span style="font-family:monospace;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${_escHtml(a.asset_name)}">${_escHtml(a.asset_name)}</span>
      <span style="font-size:10px;color:var(--muted)">${a.asset_type === 'arquivo' ? '◈ Arq' : '◫ Tab'}</span>
      <span style="font-size:10px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_escHtml(a.database_name || (a.asset_type === 'arquivo' ? a.asset_name : ''))}</span>
      <span style="text-align:center;font-size:11px;color:#185FA5;font-weight:600">${a.as_origem || 0}</span>
      <span style="text-align:center;font-size:11px;color:#27500A;font-weight:600">${a.as_destino || 0}</span>
      <span style="text-align:center;font-size:12px;font-weight:700">${a.pipeline_count || 0}</span>
    </div>`
  ).join('') || '<div style="padding:.75rem;font-size:12px;color:var(--muted)">Nenhum resultado.</div>';
}

function _catExportListCSV() {
  if (!_listAssets.length) { showToast('Nenhum dado para exportar.', true); return; }
  const rows = [['objeto','tipo','banco','como_origem','como_destino','pipelines']];
  _listAssets.forEach(a => rows.push([a.asset_name, a.asset_type, a.database_name||'', a.as_origem||0, a.as_destino||0, a.pipeline_count||0]));
  const csv = rows.map(r => r.map(v => '"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n');
  const link = document.createElement('a');
  link.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  link.download = 'catalogo_objetos_' + new Date().toISOString().slice(0,10) + '.csv';
  link.click();
}

// ── Asset Detail Modal ────────────────────────────────────────────
async function catAssetDetail(objectKey, assetType, assetName, dbName) {
  _catRecentPush(assetName, assetType, dbName);
  _catRenderRecent();

  // Open modal immediately with loading state
  const overlay = $('ls-modal-overlay');
  const titleEl = $('ls-modal-title');
  const countEl = $('ls-modal-count');
  const searchEl = $('ls-modal-search');
  const listEl  = $('ls-modal-list');
  if (!overlay) return;

  if (titleEl) titleEl.textContent = assetName;
  if (countEl) countEl.textContent = assetType === 'arquivo' ? '◈ Arquivo' : '◫ ' + (dbName || 'Tabela');
  if (searchEl) searchEl.style.display = 'none';
  if (listEl) listEl.innerHTML = '<li style="padding:.75rem 1rem;font-size:12px;color:var(--muted)">⏳ Carregando detalhes…</li>';
  overlay.classList.add('open');

  const payload = await _catTrigger({ mode: 'asset_detail', asset_name: assetName, asset_type: assetType, database_name: dbName || '' }, '');
  if (!payload || !overlay.classList.contains('open')) return;

  const readers  = payload.pipelines_origem  || [];
  const writers  = payload.pipelines_destino || [];
  const columns  = payload.columns  || [];
  const tags     = payload.tags     || [];
  const sqlExpr  = payload.sql_expression || '';

  const tagChips = tags.map(t => `<span class="tag-pill gov-tag-${t.toLowerCase()}">${t}</span>`).join(' ');

  const pipeRow = (p, dir) => {
    const dirColor = dir === 'origem' ? '#185FA5' : '#27500A';
    const dirLabel = dir === 'origem' ? '← lê' : '→ grava';
    const cols = (() => { try { return JSON.parse(p.columns_json || '[]'); } catch(_) { return []; } })();
    return `<div style="display:flex;align-items:center;gap:.5rem;padding:.3rem .5rem;border-radius:6px;margin-bottom:3px"
      onmouseenter="this.style.background='rgba(0,92,169,.05)'" onmouseleave="this.style.background=''">
      <span style="font-size:10px;font-weight:700;color:${dirColor};min-width:40px">${dirLabel}</span>
      <span style="font-family:monospace;font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_escHtml(p.pipeline_name)}</span>
      <span style="font-size:10px;color:var(--muted)">#${p.execution_order}</span>
      ${cols.length ? `<button class="ls-detail-btn" style="background:rgba(243,146,0,.12);border-color:var(--cvp-orange);color:#b45309;font-size:9px"
        onclick="event.stopPropagation();_lsDetailPopover(this,'${encodeURIComponent(cols.join('\\n'))}','Campos (${cols.length})')">⊞</button>` : ''}
      <button onclick="event.stopPropagation();_catGoLineage('${_escHtml(p.pipeline_name)}')"
        style="font-size:9px;padding:1px 6px;border-radius:4px;border:1px solid var(--cvp-blue);background:none;color:var(--cvp-blue);cursor:pointer">→</button>
    </div>`;
  };

  const section = (title, content) =>
    `<div style="margin-bottom:.75rem">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:.35rem;padding:.3rem .5rem;background:rgba(128,128,128,.06);border-radius:4px">${title}</div>
      ${content}
    </div>`;

  if (searchEl) searchEl.style.display = 'none';
  if (listEl) listEl.innerHTML =
    // Classification + meta
    (tags.length ? section('Classificação', `<div style="padding:.2rem .5rem">${tagChips}</div>`) : '') +
    // Pipelines que leem
    (readers.length ? section(`← Lido por (${readers.length} pipeline${readers.length>1?'s':''})`,
      `<div style="padding:0 .25rem">${readers.map(p => pipeRow(p, 'origem')).join('')}</div>`) : '') +
    // Pipelines que gravam
    (writers.length ? section(`→ Gravado por (${writers.length} pipeline${writers.length>1?'s':''})`,
      `<div style="padding:0 .25rem">${writers.map(p => pipeRow(p, 'destino')).join('')}</div>`) : '') +
    // Colunas
    (columns.length ? section(`Colunas (${columns.length})`,
      `<div style="padding:.2rem .5rem;display:flex;flex-wrap:wrap;gap:4px">${
        columns.map(c => `<span style="font-family:monospace;font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(0,92,169,.07);color:var(--cvp-blue)">${_escHtml(c)}</span>`).join('')
      }</div>`) : '') +
    // SQL
    (sqlExpr ? section('SQL / Tabelas referenciadas',
      `<pre style="font-size:10px;background:rgba(128,128,128,.07);border-radius:6px;padding:.5rem .75rem;overflow-x:auto;margin:.2rem .5rem;white-space:pre-wrap;word-break:break-all">${_escHtml(sqlExpr)}</pre>`) : '') +
    // Nenhum dado
    (!readers.length && !writers.length ? '<li style="padding:.75rem 1rem;font-size:12px;color:var(--muted)">Nenhuma linhagem encontrada para este objeto.</li>' : '');
}

// ── Busca universal (overview search bar) ─────────────────────────
function catSmartDetect(val) {
  const hint = $('cat-uni-hint') || $('cat-smart-hint');
  if (!hint || !val) { if (hint) hint.textContent = ''; return; }
  if (/\.(ds|dx|csv|txt|seq|dat)$/i.test(val) || /^(ds_|seq_|file:|arquivo:)/i.test(val)) {
    hint.innerHTML = '◈ Detectado como <strong>arquivo</strong>';
  } else {
    hint.innerHTML = '◫ Detectado como <strong>tabela/banco</strong>';
  }
}

function catUnifiedSearch() {
  const val = (($('cat-uni-search') || {}).value || '').trim();
  if (!val) return;
  // Switch to Pipelines tab and run the appropriate search
  catMainTab('pipelines');
  if (/\.(ds|dx|csv|txt|seq|dat)$/i.test(val) || /^(ds_|seq_|file:|arquivo:)/i.test(val)) {
    _catSearchType = 'arquivo';
    catSwitchTab('arquivo');
    if ($('cat-file-name')) $('cat-file-name').value = val.toUpperCase();
  } else {
    _catSearchType = 'tabela';
    catSwitchTab('tabela');
    if ($('cat-object-name')) $('cat-object-name').value = val.toUpperCase();
  }
  catalogoSearch();
}

// ── Deep-link: catálogo → lineage ─────────────────────────────────
function _catGoLineage(pipelineName) {
  govTabSwitch('lineage');
  if ($('gov-pipeline')) $('gov-pipeline').value = pipelineName;
  loadGovernanca();
}

// ── Expandir / recolher todos os cards de resultado ───────────────
function _catExpandAll(open) {
  document.querySelectorAll('.cat-pipeline-card').forEach(card => {
    const body = card.querySelector('div + div');
    const arr  = card.querySelector('.cat-arrow');
    if (body) body.style.display = open ? '' : 'none';
    if (arr)  arr.textContent    = open ? '▲' : '▼';
  });
}

// ── Export CSV ────────────────────────────────────────────────────
function _catExportCSV() {
  const payload = window.__catPayload;
  if (!payload || !payload.pipelines) { showToast('Nenhum resultado para exportar.', true); return; }
  const rows = [['pipeline','project','domain','active','job','direction','object','database','file_path','campos']];
  (payload.pipelines || []).forEach(p => {
    (p.jobs || []).forEach(j => {
      rows.push([
        p.pipeline_name, p.project_name, p.domain, p.active ? 'Ativo' : 'Inativo',
        j.job_name, j.direction, j.object_name || '', j.database_name || '',
        j.file_path || '', (Array.isArray(j.columns) ? j.columns.join('; ') : ''),
      ]);
    });
  });
  const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g,'""') + '"').join(',')).join('\r\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'catalogo_' + (payload.term || 'export') + '_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}

// ── Saúde do pipeline via Airflow API ────────────────────────────
async function _pipelineHealthLoad(idx, pipelineName) {
  const el = document.getElementById('health-' + idx);
  if (!el || !authHeader) return;
  try {
    const dagId = pipelineName.toLowerCase().replace(/[^a-z0-9_]/g, '_');
    const r = await fetch(
      '/api/v1/dags/' + encodeURIComponent(dagId) + '/dagRuns?limit=1&order_by=-start_date',
      { headers: { 'Authorization': _sysAuth() } }
    );
    if (!r.ok) { el.textContent = ''; return; }
    const data = await r.json();
    const runs = data.dag_runs || [];
    if (!runs.length) { el.textContent = ''; return; }
    const last = runs[0];
    const state = last.state;
    const date  = last.start_date ? last.start_date.slice(0,10) : '';
    const cfg = {
      success: { icon: '✔', color: '#16a34a' },
      failed:  { icon: '✘', color: '#dc2626' },
      running: { icon: '↻', color: '#d97706' },
    };
    const c = cfg[state] || { icon: '○', color: 'var(--muted)' };
    el.innerHTML = `<span style="color:${c.color};font-weight:600">${c.icon} ${state}</span> <span style="color:var(--muted)">${date}</span>`;
  } catch(_) { el.textContent = ''; }
}

// ── Histórico de importações ──────────────────────────────────────
async function _catHistory(pipelineName) {
  try {
    const payload = await _catTrigger({ mode: 'pipeline_history', pipeline_name: pipelineName }, '');
    if (!payload || !payload.history) { showToast('Sem histórico para este pipeline.'); return; }
    const rows = payload.history;
    const content = rows.map(r =>
      (r.imported_at || '').slice(0,16) + ' · ' + (r.status || '') +
      (r.reviewed_by ? ' · aprovado por ' + r.reviewed_by : '') +
      (r.obs ? ' · ' + r.obs : '')
    ).join('\n');
    _lsDetailPopover(document.body, content || 'Sem registros.', 'Histórico: ' + pipelineName);
  } catch(_) { showToast('Erro ao carregar histórico.', true); }
}

// ── Linhagem completa de arquivo (quem escreve e quem lê) ────────
async function _fileLineage(fileName) {
  try {
    const payload = await _catTrigger({ mode: 'file_lineage', file_name: fileName }, '');
    if (!payload) return;
    const writers = (payload.writers || []).map(p => '✍ ' + p.pipeline_name + ' (Job: ' + p.job_name + ')');
    const readers = (payload.readers || []).map(p => '👁 ' + p.pipeline_name + ' (Job: ' + p.job_name + ')');
    const content = [
      writers.length ? '── GRAVA ──\n' + writers.join('\n') : '',
      readers.length ? '── LÊ ──\n' + readers.join('\n') : '',
    ].filter(Boolean).join('\n\n') || 'Nenhum pipeline encontrado.';
    _lsDetailPopover(document.body, content, 'Linhagem do arquivo: ' + fileName);
  } catch(_) { showToast('Erro ao carregar linhagem do arquivo.', true); }
}

function catSwitchTab(type) {
  _catSearchType = type;
  ['tabela','arquivo'].forEach(t => {
    const btn = $('cat-tab-' + t);
    const fld = $('cat-fields-' + t);
    if (btn) btn.classList.toggle('active', t === type);
    if (fld) fld.style.display = t === type ? 'grid' : 'none';
  });
}

function rankSwitchTab(type) {
  _rankType = type;
  ['tabela','arquivo'].forEach(t => {
    const btn = $('rank-tab-' + t);
    if (btn) btn.classList.toggle('active', t === type);
  });
}

async function _catTrigger(conf, statusMsg) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return null; }
  // Operações de escrita usam auth do usuário logado; leituras usam auth sistêmico
  const _auth = _WRITE_MODES.has(conf.mode || '') ? authHeader : _sysAuth();
  const st = $('cat-status');
  if (st) { st.textContent = statusMsg; st.style.color = 'var(--muted)'; }

  const r = await fetch(ORQUESTRA_API + '/catalogo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(conf),
  });
  if (r.status === 401) { sair(); return null; }
  if (!r.ok) {
    let errMsg = 'HTTP ' + r.status;
    try {
      const errBody = await r.json();
      if (errBody && errBody.detail) errMsg = (typeof errBody.detail === 'string') ? errBody.detail : JSON.stringify(errBody.detail);
    } catch(_) {}
    if (st) { st.textContent = 'Erro: ' + errMsg; st.style.color = 'var(--red)'; }
    showToast('Catálogo: ' + errMsg, true);
    return null;
  }
  return await r.json();
}

function _catShowColumns(evt, encodedJson) {
  evt.stopPropagation();
  let cols = [];
  try { cols = JSON.parse(decodeURIComponent(encodedJson)); } catch(_) {}
  _lsDetailPopover(evt.target, cols.join('\n'), 'Campos utilizados (' + cols.length + ')');
}

function _catDirBadge(dir) {
  const cfg = {
    origem:       { label: 'Origem',       bg: 'rgba(24,95,165,.12)', color: '#185FA5', border: 'rgba(24,95,165,.3)' },
    destino:      { label: 'Destino',      bg: 'rgba(39,80,10,.12)',  color: '#27500A', border: 'rgba(39,80,10,.3)'  },
    transformacao:{ label: 'Transformação',bg: 'rgba(60,52,137,.12)', color: '#3C3489', border: 'rgba(60,52,137,.3)' },
  };
  const c = cfg[dir] || { label: dir, bg: 'var(--bg)', color: 'var(--muted)', border: 'var(--border)' };
  return `<span style="font-size:10px;font-weight:600;padding:1px 7px;border-radius:999px;
    background:${c.bg};color:${c.color};border:1px solid ${c.border};white-space:nowrap">${c.label}</span>`;
}

function _catActiveChip(active) {
  return active
    ? '<span style="font-size:10px;font-weight:600;padding:1px 7px;border-radius:999px;background:rgba(34,197,94,.12);color:#15803d;border:1px solid rgba(34,197,94,.3)">Ativo</span>'
    : '<span style="font-size:10px;font-weight:600;padding:1px 7px;border-radius:999px;background:rgba(156,163,175,.12);color:var(--muted);border:1px solid var(--border)">Inativo</span>';
}

function _renderCatResults(payload, impactoMode) {
  const el = $('cat-results');
  const st = $('cat-status');
  if (!el) return;

  const pipelines = payload.pipelines || [];
  const total     = payload.total_pipelines || 0;
  const occ       = payload.total_ocorrencias || 0;
  const term      = payload.term || '';

  if (st) {
    const modeLabel = impactoMode ? '⚡ Análise de impacto' : 'Busca';
    st.style.color = 'var(--muted)';
    st.textContent = total
      ? `${modeLabel}: "${term}" — ${total} pipeline(s) · ${occ} ocorrência(s)`
      : `${modeLabel}: "${term}" — nenhum resultado encontrado.`;
  }

  if (!pipelines.length) {
    el.innerHTML =
      '<div class="empty-state" style="padding:1.5rem">' +
        '<span class="es-icon" style="font-size:28px">◫</span>' +
        '<p class="es-title">Nenhum pipeline encontrado</p>' +
        '<p class="es-sub">Tente um termo diferente ou verifique se o lineage foi importado.</p>' +
      '</div>';
    return;
  }

  // Banner de impacto upstream/downstream
  let impactBanner = '';
  if (impactoMode) {
    const leitores = pipelines.filter(p => (p.jobs||[]).some(j => j.direction === 'origem')).length;
    const gravadores = pipelines.filter(p => (p.jobs||[]).some(j => j.direction === 'destino')).length;
    impactBanner = `<div style="display:flex;gap:.75rem;margin-bottom:.85rem;flex-wrap:wrap">
      ${leitores > 0 ? `<div style="display:flex;align-items:center;gap:.4rem;padding:.4rem .85rem;border-radius:8px;background:rgba(243,146,0,.1);border:1px solid rgba(243,146,0,.3)">
        <span style="font-size:13px;font-weight:700;color:#b45309">${leitores}</span>
        <span style="font-size:11px;color:#b45309">pipeline(s) <strong>leem</strong> como origem →</span>
      </div>` : ''}
      ${gravadores > 0 ? `<div style="display:flex;align-items:center;gap:.4rem;padding:.4rem .85rem;border-radius:8px;background:rgba(24,95,165,.1);border:1px solid rgba(24,95,165,.3)">
        <span style="font-size:13px;font-weight:700;color:#185FA5">${gravadores}</span>
        <span style="font-size:11px;color:#185FA5">pipeline(s) <strong>gravam</strong> como destino →</span>
      </div>` : ''}
    </div>`;
  }

  // Toolbar: expandir/recolher + export CSV
  const toolbar = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem;gap:.5rem;flex-wrap:wrap">
    <div style="display:flex;gap:6px">
      <button class="btn btn-outline btn-sm" style="font-size:11px" onclick="_catExpandAll(true)">▼ Expandir todos</button>
      <button class="btn btn-outline btn-sm" style="font-size:11px" onclick="_catExpandAll(false)">▲ Recolher todos</button>
    </div>
    <button class="btn btn-outline btn-sm" style="font-size:11px" onclick="_catExportCSV()">⬇ Exportar CSV</button>
  </div>`;

  // Guarda dados para export
  window.__catPayload = payload;

  el.innerHTML = impactBanner + toolbar + pipelines.map((p, pi) => {
    const jobRows = (p.jobs || []).map(j => {
      const cols = Array.isArray(j.columns) ? j.columns : [];
      const colsChip = cols.length
        ? `<span style="font-size:10px;font-weight:600;padding:1px 6px;border-radius:999px;
            background:rgba(243,146,0,.12);color:#b45309;border:1px solid rgba(243,146,0,.35);
            cursor:pointer;white-space:nowrap" onclick="event.stopPropagation();_catShowColumns(event,'${encodeURIComponent(JSON.stringify(cols))}')">⊞ ${cols.length} campo(s)</span>`
        : '';
      const hasFile = !!(j.file_path);
      const objKey  = hasFile ? j.file_path : ((j.database_name ? j.database_name + '.' : '') + (j.object_name || ''));
      const fileLineageBtn = hasFile
        ? `<button onclick="event.stopPropagation();_fileLineage('${(j.file_path||'').replace(/'/g,"\\'")}')"
            style="font-size:10px;padding:1px 6px;border-radius:4px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;white-space:nowrap"
            title="Ver quem lê e quem grava este arquivo">⇄ Linhagem</button>` : '';
      const detail  = hasFile
        ? `<span style="font-size:11px;color:var(--text);font-family:monospace">${j.file_path}</span>${fileLineageBtn}`
        : `<span style="font-size:11px;color:var(--text)">${j.object_name || '—'}</span>
           <span style="font-size:11px;color:var(--muted);font-weight:700">${j.database_name || ''}</span>`;
      const tagKey = encodeURIComponent(objKey);
      const tagBtn = window.__isViewer ? '' : `<button onclick="event.stopPropagation();_tagEdit('${tagKey}')"
        style="font-size:10px;padding:1px 6px;border-radius:4px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer"
        title="Classificar objeto">🏷</button>`;
      return `<div style="display:grid;grid-template-columns:26px 1fr auto 1fr auto auto;gap:8px;align-items:center;
        padding:.4rem .75rem;border-bottom:1px solid var(--border);font-size:12px">
        <span style="font-size:11px;font-weight:700;color:var(--muted);text-align:center">#${j.execution_order}</span>
        <span style="font-family:monospace;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${j.job_name}</span>
        ${_catDirBadge(j.direction)}
        ${detail}
        ${colsChip}
        ${tagBtn}
      </div>`;
    }).join('');

    const isOpen = pi < 3;
    const pipeEnc = encodeURIComponent(p.pipeline_name);
    return `<div class="cat-pipeline-card" style="border:1px solid var(--border);border-radius:12px;margin-bottom:.65rem;overflow:hidden">
      <div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none';this.querySelector('.cat-arrow').textContent=this.nextElementSibling.style.display===''?'▲':'▼'"
        style="display:flex;align-items:center;gap:.65rem;padding:.7rem 1rem;cursor:pointer;background:var(--bg);user-select:none">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
            <span style="font-size:13px;font-weight:600;font-family:monospace">${p.pipeline_name}</span>
            ${_catActiveChip(p.active)}
            <span class="tag-pill" style="font-size:10px">${p.project_name}</span>
            <span class="tag-pill" style="font-size:10px;background:var(--bg)">${p.domain}</span>
          </div>
          <div style="display:flex;align-items:center;gap:.5rem;margin-top:.2rem;flex-wrap:wrap">
            <span style="font-size:11px;color:var(--muted)">${p.ocorrencias} ocorrência(s)</span>
            <span id="health-${pi}" style="font-size:10px;color:var(--muted)">⏳</span>
          </div>
        </div>
        <button onclick="event.stopPropagation();_catHistory('${p.pipeline_name.replace(/'/g,"\\'")}')"
          style="font-size:10px;font-weight:600;padding:3px 10px;border-radius:6px;border:1px solid var(--border);
                 background:none;color:var(--muted);cursor:pointer;white-space:nowrap;flex-shrink:0"
          title="Histórico de importações">📋 Histórico</button>
        <button onclick="event.stopPropagation();_catGoLineage('${p.pipeline_name.replace(/'/g,"\\'")}')"
          style="font-size:10px;font-weight:600;padding:3px 10px;border-radius:6px;border:1px solid var(--cvp-blue);
                 background:rgba(24,95,165,.08);color:var(--cvp-blue);cursor:pointer;white-space:nowrap;flex-shrink:0"
          title="Ver lineage deste pipeline">→ Lineage</button>
        <span class="cat-arrow" style="color:var(--muted);font-size:12px;flex-shrink:0">${isOpen ? '▲' : '▼'}</span>
      </div>
      <div style="display:${isOpen ? '' : 'none'}">
        <div style="display:grid;grid-template-columns:26px 1fr auto 1fr auto;gap:8px;padding:.35rem .75rem;
          background:var(--bg);border-bottom:1px solid var(--border);border-top:1px solid var(--border)">
          <span style="font-size:10px;color:var(--muted);font-weight:600">Ord.</span>
          <span style="font-size:10px;color:var(--muted);font-weight:600">Job</span>
          <span style="font-size:10px;color:var(--muted);font-weight:600">Direção</span>
          <span style="font-size:10px;color:var(--muted);font-weight:600">Objeto / Arquivo</span>
          <span style="font-size:10px;color:var(--muted);font-weight:600">Campos</span>
        </div>
        ${jobRows}
        <!-- Ownership inline -->
        <div style="display:flex;align-items:center;gap:.5rem;padding:.45rem .75rem;background:rgba(128,128,128,.04);border-top:1px solid var(--border);flex-wrap:wrap">
          <span style="font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">Responsável:</span>
          <span id="own-${pi}-display" style="font-size:11px;color:var(--muted)">—</span>
          ${window.__isViewer ? '' : `<button onclick="_ownerEdit(${pi},'${p.pipeline_name.replace(/'/g,"\\'")}')"
            style="font-size:10px;padding:1px 7px;border-radius:4px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;margin-left:auto">✎ Editar</button>`}
        </div>
      </div>
    </div>`;
  }).join('');

  // Carrega owners e saúde de forma assíncrona após render
  pipelines.forEach((p, pi) => {
    _ownerLoad(pi, p.pipeline_name);
    _pipelineHealthLoad(pi, p.pipeline_name);
  });
}

async function _ownerLoad(idx, pipelineName) {
  try {
    const payload = await _catTrigger({ mode: 'get_owner', pipeline_name: pipelineName }, '');
    if (!payload) return;
    const el = document.getElementById('own-' + idx + '-display');
    if (!el) return;
    const parts = [];
    if (payload.owner_name)   parts.push('Owner: <strong>' + _escHtml(payload.owner_name) + '</strong>');
    if (payload.steward_name) parts.push('Steward: <strong>' + _escHtml(payload.steward_name) + '</strong>');
    el.innerHTML = parts.length ? parts.join(' · ') : '—';
  } catch(_) {}
}

const _TAG_OPTIONS = ['PII', 'Confidencial', 'Regulado', 'Publico'];
const _TAG_COLORS  = { PII: 'gov-tag-pii', Confidencial: 'gov-tag-confidencial', Regulado: 'gov-tag-regulado', Publico: 'gov-tag-publico' };

async function _tagEdit(encodedKey) {
  const objectKey = decodeURIComponent(encodedKey);
  // Carrega tags atuais
  let current = [];
  try {
    const r = await _catTrigger({ mode: 'get_tags', object_key: objectKey }, '');
    if (r && r.tags) current = r.tags.map(t => t.tag);
  } catch(_) {}

  const chosen = prompt(
    'Classificações para "' + objectKey + '".\n\nOpções: ' + _TAG_OPTIONS.join(', ') +
    '\nAtuais: ' + (current.join(', ') || 'nenhuma') +
    '\n\nDigite as tags separadas por vírgula (deixe vazio para remover todas):'
  , current.join(', '));
  if (chosen === null) return;

  const newTags = chosen.split(',').map(t => t.trim()).filter(t => _TAG_OPTIONS.includes(t));
  const toAdd   = newTags.filter(t => !current.includes(t));
  const toRemove = current.filter(t => !newTags.includes(t));
  const user = window._authUser || 'sistema';

  try {
    for (const t of toAdd)    await _catTrigger({ mode: 'save_tag', object_key: objectKey, tag: t, user, remove: false }, '');
    for (const t of toRemove) await _catTrigger({ mode: 'save_tag', object_key: objectKey, tag: t, user, remove: true  }, '');
    showToast('Tags salvas: ' + (newTags.join(', ') || 'nenhuma'));
  } catch(_) { showToast('Erro ao salvar tags.', true); }
}

async function _ownerEdit(idx, pipelineName) {
  const current = document.getElementById('own-' + idx + '-display');
  const ownerName   = prompt('Nome do Data Owner (ex: João Silva):',   '');
  if (ownerName === null) return;
  const ownerEmail  = prompt('Email do Data Owner:',  '');
  if (ownerEmail === null) return;
  const stewardName = prompt('Nome do Data Steward:', '');
  if (stewardName === null) return;
  const stewardEmail = prompt('Email do Data Steward:', '');
  if (stewardEmail === null) return;
  try {
    await _catTrigger({
      mode: 'save_owner', pipeline_name: pipelineName,
      user: window._authUser || 'sistema',
      data: { owner_name: ownerName, owner_email: ownerEmail,
              steward_name: stewardName, steward_email: stewardEmail }
    }, '');
    showToast('Responsabilidade salva.');
    _ownerLoad(idx, pipelineName);
  } catch(_) { showToast('Erro ao salvar.', true); }
}

async function catalogoSearch() {
  const btn  = $('btn-cat-search');
  const btnT = $('btn-cat-txt');
  if (btn)  btn.disabled = true;
  if (btnT) btnT.textContent = '⏳';
  $('cat-results').innerHTML = '';

  try {
    let conf, statusMsg;
    if (_catSearchType === 'arquivo') {
      const fn  = $('cat-file-name') ? $('cat-file-name').value.trim() : '';
      const dir = $('cat-direction-arq') ? $('cat-direction-arq').value : 'all';
      if (!fn) { showToast('Informe o nome do arquivo.', true); return; }
      conf = { mode: 'search', search_type: 'arquivo', file_name: fn, direction: dir };
      statusMsg = 'Buscando arquivo "' + fn + '"...';
    } else {
      const obj = $('cat-object-name') ? $('cat-object-name').value.trim() : '';
      const dir = $('cat-direction')   ? $('cat-direction').value           : 'all';
      const db  = $('cat-database')    ? $('cat-database').value.trim()     : '';
      if (!obj) { showToast('Informe o nome da tabela.', true); return; }
      conf = { mode: 'search', search_type: 'tabela', object_name: obj, direction: dir, database_name: db || null };
      statusMsg = 'Buscando "' + obj + '"...';
    }
    const payload = await _catTrigger(conf, statusMsg);
    if (payload) {
      _renderCatResults(payload, false);
      catalogoRanking(); // auto-refresh ranking após busca
    }
  } finally {
    if (btn)  btn.disabled = false;
    if (btnT) btnT.textContent = 'Buscar';
  }
}

async function catalogoImpacto() {
  const obj  = $('cat-object-name') ? $('cat-object-name').value.trim() : '';
  const db   = $('cat-database')    ? $('cat-database').value.trim()    : '';
  const btn  = $('btn-cat-search');
  const btnI = $('btn-cat-imp-txt');

  if (!obj) { showToast('Informe o nome da tabela para análise de impacto.', true); return; }
  if (btn)  btn.disabled = true;
  if (btnI) btnI.textContent = '⏳';
  $('cat-results').innerHTML = '';

  try {
    const payload = await _catTrigger(
      { mode: 'search', search_type: 'tabela', object_name: obj, direction: 'origem', database_name: db || null },
      '⚡ Analisando impacto de "' + obj + '"...'
    );
    if (payload) {
      if (payload.pipelines) {
        payload.pipelines = payload.pipelines.filter(p => p.active);
        payload.total_pipelines   = payload.pipelines.length;
        payload.total_ocorrencias = payload.pipelines.reduce((s, p) => s + p.ocorrencias, 0);
      }
      _renderCatResults(payload, true);
    }
  } finally {
    if (btn)  btn.disabled = false;
    if (btnI) btnI.textContent = '⚡ Impacto';
  }
}

async function catalogoRanking() {
  const el = $('cat-ranking');
  if (!el) return;
  el.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:.5rem 0">Carregando ranking...</div>';

  try {
    const payload = await _catTrigger({ mode: 'ranking', ranking_type: _rankType, top_n: 20 }, '');
    _catRankingLoaded = true;

    const data = (payload && payload.data) || [];
    if (!data.length) {
      el.innerHTML = '<div style="font-size:12px;color:var(--muted)">Nenhum objeto com lineage cadastrada.</div>';
      return;
    }

    const maxCount = data[0].pipeline_count || 1;
    el.innerHTML =
      '<div style="border:1px solid var(--border);border-radius:12px;overflow:hidden">' +
      data.map((d, i) => {
        const pct   = Math.round((d.pipeline_count / maxCount) * 100);
        const tags  = [
          d.as_origem  > 0 ? `<span style="font-size:10px;padding:1px 6px;border-radius:999px;background:rgba(24,95,165,.1);color:#185FA5;border:1px solid rgba(24,95,165,.25)">Origem ×${d.as_origem}</span>` : '',
          d.as_destino > 0 ? `<span style="font-size:10px;padding:1px 6px;border-radius:999px;background:rgba(39,80,10,.1);color:#27500A;border:1px solid rgba(39,80,10,.25)">Destino ×${d.as_destino}</span>` : '',
        ].filter(Boolean).join(' ');

        const isArq = _rankType === 'arquivo';
        const nameVal  = isArq ? d.file_path  : d.object_name;
        const clickFn  = isArq
          ? `catSwitchTab('arquivo');$('cat-file-name').value='${(d.file_path||'').replace(/'/g,"\\'")}';catalogoSearch()`
          : `catSwitchTab('tabela');$('cat-object-name').value='${(d.object_name||'').replace(/'/g,"\\'")}';${d.database_name ? `$('cat-database').value='${d.database_name}';` : ''}catalogoSearch()`;

        return `<div style="padding:.65rem 1rem;border-bottom:${i < data.length-1 ? '1px solid var(--border)' : 'none'};
                  display:grid;grid-template-columns:28px 1fr auto;gap:.65rem;align-items:center">
          <span style="font-size:12px;font-weight:700;color:var(--muted);text-align:center">${i+1}</span>
          <div>
            <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.3rem">
              <span style="font-size:13px;font-weight:600;font-family:monospace;cursor:pointer;color:var(--cvp-blue)"
                onclick="${clickFn}" title="Clique para buscar">${nameVal || '—'}</span>
              ${(!isArq && d.database_name) ? `<span style="font-size:11px;color:var(--muted);font-weight:700">${d.database_name}</span>` : ''}
              ${tags}
            </div>
            <div style="background:var(--border);border-radius:999px;height:4px;overflow:hidden">
              <div style="background:var(--cvp-blue);width:${pct}%;height:100%;border-radius:999px;transition:width .3s"></div>
            </div>
          </div>
          <div style="text-align:right;min-width:64px">
            <div style="font-size:15px;font-weight:700">${d.pipeline_count}</div>
            <div style="font-size:10px;color:var(--muted)">pipeline(s)</div>
          </div>
        </div>`;
      }).join('') + '</div>';
  } catch(e) {
    if (el) el.innerHTML = '<div style="font-size:12px;color:var(--red)">Erro: ' + (e && e.message ? e.message : e) + '</div>';
  }
}

/* ══ S2 — Badge de falhas no header ══════════════════════════════ */
let _failureBadgeTimer = null;

function _updateFailureBadge(count) {
  // Persiste as horas usadas na contagem para que o clique envie exatamente o mesmo filtro
  const hours = (window.__appConfig && window.__appConfig.failure_badge_hours_lookback) || 24;
  window.__badgeHoursLookback = hours;
  const badge = $('failure-badge');
  const wrap  = $('failure-badge-wrap');
  if (!badge || !wrap) return;
  if (!count || count <= 0) {
    wrap.style.display = 'none';
    return;
  }
  wrap.style.display = 'flex';
  badge.textContent  = count > 99 ? '99+' : String(count);
  badge.title        = count + ' pipeline(s) com falha últimas ' + hours + 'h — clique para filtrar';
}

function _extractFailuresFromDash(dashPayload) {
  if (!dashPayload) return 0;
  const hours   = (window.__appConfig && window.__appConfig.failure_badge_hours_lookback) || 24;
  const cutoffMs = Date.now() - hours * 3600000;

  // Filtra ultimas_falhas pela mesma janela de tempo usada na query de logs
  const ff = dashPayload.ultimas_falhas || [];
  if (ff.length) {
    const recent = ff.filter(f => {
      const t = f.inicio || f.start_time;
      // Se não tiver timestamp, inclui (confiança no backend)
      return !t || new Date(t).getTime() >= cutoffMs;
    });
    const pipelines = new Set(recent.map(f => f.pipeline || f.pipeline_name || '').filter(Boolean));
    return pipelines.size || recent.length;
  }

  // Fallback: pipeline_status — filtra pelo mesmo cutoff (pipeline_status não tem filtro de tempo no backend)
  const ps = dashPayload.pipeline_status || [];
  return ps.filter(p =>
    (p.ultimo_status || '').toUpperCase() === 'FAILED' &&
    (!p.inicio || new Date(p.inicio).getTime() >= cutoffMs)
  ).length;
}

function _startFailureBadgeTimer() {
  if (_failureBadgeTimer) clearInterval(_failureBadgeTimer);
  const interval = (window.__appConfig.failure_badge_refresh_sec || 300) * 1000;
  _failureBadgeTimer = setInterval(() => {
    // Reutiliza dados já carregados — sem nova DAG
    if (window.__lastDashPayload) {
      _updateFailureBadge(_extractFailuresFromDash(window.__lastDashPayload));
    }
  }, interval);
}

/* ══ S5 — Auto-refresh do Dashboard ══════════════════════════════ */
let _dashRefreshTimer = null;
let _dashLastUpdate   = null;

function _startDashAutoRefresh() {
  _stopDashAutoRefresh();
  const toggle = $('dash-autorefresh-toggle');
  if (!toggle || !toggle.checked) return;
  const secs = window.__appConfig.dashboard_refresh_interval_sec || 60;
  if (secs <= 0) return;
  _dashRefreshTimer = setInterval(() => {
    if (document.getElementById('page-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  }, secs * 1000);
  console.log('[ORQ] Auto-refresh dashboard: ' + secs + 's');
}

function _stopDashAutoRefresh() {
  if (_dashRefreshTimer) { clearInterval(_dashRefreshTimer); _dashRefreshTimer = null; }
}

function _toggleDashAutoRefresh() {
  const toggle = $('dash-autorefresh-toggle');
  const label  = $('dash-autorefresh-label');
  const on = toggle && toggle.checked;
  if (label) label.textContent = on ? 'Auto' : 'Manual';
  if (on) _startDashAutoRefresh();
  else    _stopDashAutoRefresh();
}

function _updateDashLastUpdated() {
  _dashLastUpdate = new Date();
  const el = $('dash-last-updated');
  if (el) {
    const hm = _dashLastUpdate.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'});
    el.textContent = 'Atualizado às ' + hm;
  }
}

/* ══ ORDENAÇÃO POR COLUNA (client-side) ══════════════════════════ */
// Estado global de ordenação por tabela
window.__sortState = {};

function _sortData(data, col, dir) {
  if (!col || !data || !data.length) return data;
  return [...data].sort((a, b) => {
    let va = a[col], vb = b[col];
    // Null/undefined sempre por último
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    // Numérico
    if (typeof va === 'number' && typeof vb === 'number') {
      return dir === 'asc' ? va - vb : vb - va;
    }
    // String case-insensitive
    va = String(va).toLowerCase();
    vb = String(vb).toLowerCase();
    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ?  1 : -1;
    return 0;
  });
}

// Renderiza o ícone de sort na coluna ativa
function _sortIcon(tableId, col) {
  const st = window.__sortState[tableId];
  if (!st || st.col !== col) return '<span style="opacity:.3;font-size:10px;margin-left:3px">⇅</span>';
  return st.dir === 'asc'
    ? '<span style="font-size:10px;margin-left:3px;color:var(--cvp-blue)">↑</span>'
    : '<span style="font-size:10px;margin-left:3px;color:var(--cvp-blue)">↓</span>';
}

// Clique numa coluna → alterna dir ou define nova coluna
function _onSortClick(tableId, col, renderFn) {
  const st = window.__sortState[tableId] || {};
  const newDir = (st.col === col && st.dir === 'asc') ? 'desc' : 'asc';
  window.__sortState[tableId] = { col, dir: newDir };
  renderFn();
}


/* ══ ADMIN — Painel restrito (perfil com acao_admin) ══════════════════════════ */
const ADMIN_DAG_ID    = 'etl_admin_manage';
// Permissões vêm do banco (etl_perfil_permissao) via /auth/login ou GET /me
function _isAdmin() { return _hasPerm('acao_admin') || window.__userPerfil === 'admin'; }

// Mostra/oculta aba Admin baseado no usuário logado
function _applyAdminVisibility() {
  const tab = $('tab-admin');
  if (!tab) return;
  if (_isAdmin()) tab.classList.remove('hidden');
  else            tab.classList.add('hidden');
}

/* ── Admin: Usuários & Perfis (RBAC) ─────────────────────────────────────────── */
const RBAC_RECURSOS = [
  ['tela_dashboard',  'Dashboard'],   ['tela_pipelines', 'Pipelines'],
  ['tela_jobs',       'Jobs'],        ['tela_logs',      'Logs'],
  ['tela_ds_monitor', 'DS Monitor'],  ['tela_governanca','Governança'],
  ['tela_malha',      'Malha'],       ['tela_admin',     'Admin'],
  ['acao_executar',   'Executar/Rerun/Ack'],
  ['acao_editar',     'Cadastrar/Editar'],
  ['acao_admin',      'Administração'],
];

async function _admRbac(action, extra) {
  const r = await fetch(ORQUESTRA_API + '/admin', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
    body: JSON.stringify({ action, ...(extra || {}) }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
  return d;
}

async function admLoadUsuariosPerfis() {
  await Promise.all([admLoadUsuarios(), admLoadPerfis(), admLoadRoleMap()]);
}

async function admLoadUsuarios() {
  const el = $('adm-user-list');
  if (!el) return;
  el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Carregando...</span>';
  try {
    const d = await _admRbac('user_list');
    const us = d.usuarios || [];
    if (!us.length) { el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Nenhum usuário cadastrado ainda — entram automaticamente no 1º login.</span>'; return; }
    let h = '<table style="width:100%;font-size:12px;border-collapse:collapse">' +
      '<tr style="text-align:left;color:var(--muted)"><th style="padding:.3rem">Matrícula</th><th>Nome</th><th>Perfil</th><th>Último login</th><th>Ativo</th><th></th></tr>';
    us.forEach(u => {
      const nome = [u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || '—';
      h += '<tr style="border-top:1px solid var(--border)">' +
        '<td style="padding:.35rem .3rem;font-weight:600">' + u.matricula + '</td>' +
        '<td>' + nome + '</td>' +
        '<td><span style="background:rgba(0,92,169,.1);border-radius:6px;padding:.1rem .45rem">' + u.perfil + '</span></td>' +
        '<td style="color:var(--muted)">' + (u.ultimo_login || '—') + '</td>' +
        '<td>' + (u.ativo ? '✓' : '<span style="color:var(--red)">✕</span>') + '</td>' +
        '<td style="text-align:right;white-space:nowrap">' +
          '<button class="btn btn-outline btn-sm" onclick="admUserEdit(\'' + u.matricula + '\',\'' + u.perfil + '\')">✎</button> ' +
          '<button class="btn btn-outline btn-sm" onclick="admUserDelete(\'' + u.matricula + '\')">🗑</button>' +
        '</td></tr>';
    });
    el.innerHTML = h + '</table>';
  } catch(e) { el.innerHTML = '<span style="font-size:12px;color:var(--red)">Erro: ' + e.message + '</span>'; }
}

function admUserEdit(mat, perfil) {
  if ($('adm-user-mat'))    $('adm-user-mat').value = mat;
  if ($('adm-user-perfil')) $('adm-user-perfil').value = perfil;
}

async function admUserSave() {
  const mat    = $('adm-user-mat')    ? $('adm-user-mat').value.trim().toUpperCase() : '';
  const perfil = $('adm-user-perfil') ? $('adm-user-perfil').value : 'consulta';
  const msg    = $('adm-user-msg');
  if (!mat) { if (msg) { msg.textContent = 'Informe a matrícula.'; msg.style.color = 'var(--red)'; } return; }
  try {
    const d = await _admRbac('user_upsert', { matricula: mat, perfil, ativo: true });
    if (msg) { msg.textContent = d.mensagem || 'Salvo.'; msg.style.color = 'var(--green)'; }
    if ($('adm-user-mat')) $('adm-user-mat').value = '';
    admLoadUsuarios();
  } catch(e) { if (msg) { msg.textContent = 'Erro: ' + e.message; msg.style.color = 'var(--red)'; } }
}

async function admUserDelete(mat) {
  const ok = await showConfirm('Remover o usuário ' + mat + ' do ORQUESTRA?\n\nEle volta ao perfil "consulta" se logar novamente.', '🗑 Remover');
  if (!ok) return;
  try {
    await _admRbac('user_delete', { matricula: mat });
    showToast('Usuário ' + mat + ' removido.', false);
    admLoadUsuarios();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

let __admPerfis = [];
async function admLoadPerfis() {
  const el = $('adm-perfil-list');
  if (!el) return;
  el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Carregando...</span>';
  try {
    const d = await _admRbac('perfil_list');
    __admPerfis = d.perfis || [];
    // popula os selects de perfis (formulário de usuário e de mapeamento de roles)
    const perfisOpts = __admPerfis.map(p =>
      '<option value="' + p.perfil_nome + '">' + p.perfil_nome + '</option>').join('');
    const sel = $('adm-user-perfil');
    if (sel) sel.innerHTML = perfisOpts;
    const selRm = $('adm-rm-perfil');
    if (selRm) selRm.innerHTML = perfisOpts;
    let h = '';
    __admPerfis.forEach(p => {
      const checks = RBAC_RECURSOS.map(([rec, lbl]) => {
        const on = (p.permissoes || []).includes(rec);
        return '<label style="display:inline-flex;align-items:center;gap:.3rem;font-size:11px;' +
          'margin:.15rem .5rem .15rem 0;text-transform:none;letter-spacing:0;cursor:pointer">' +
          '<input type="checkbox" data-perfil="' + p.perfil_nome + '" data-rec="' + rec + '"' +
          (on ? ' checked' : '') + ' style="width:auto"> ' + lbl + '</label>';
      }).join('');
      const protegido = (p.perfil_nome === 'admin' || p.perfil_nome === 'consulta');
      h += '<div style="border:1px solid var(--border);border-radius:10px;padding:.6rem .75rem;margin-bottom:.5rem">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.25rem">' +
          '<span style="font-size:12px;font-weight:700">' + p.perfil_nome + '</span>' +
          '<span>' +
            '<button class="btn btn-primary btn-sm" onclick="admPerfilSave(\'' + p.perfil_nome + '\')">💾</button>' +
            (protegido ? '' : ' <button class="btn btn-outline btn-sm" onclick="admPerfilDelete(\'' + p.perfil_nome + '\')">🗑</button>') +
          '</span>' +
        '</div>' +
        '<div style="font-size:11px;color:var(--muted);margin-bottom:.35rem">' + (p.descricao || '') + '</div>' +
        '<div>' + checks + '</div></div>';
    });
    el.innerHTML = h || '<span style="font-size:12px;color:var(--muted)">Nenhum perfil.</span>';
  } catch(e) { el.innerHTML = '<span style="font-size:12px;color:var(--red)">Erro: ' + e.message + '</span>'; }
}

async function admPerfilSave(nome) {
  const permissoes = Array.from(
    document.querySelectorAll('#adm-perfil-list input[data-perfil="' + nome + '"]:checked'))
    .map(c => c.dataset.rec);
  try {
    const d = await _admRbac('perfil_upsert', { perfil_nome: nome, permissoes });
    showToast(d.mensagem || ('Perfil "' + nome + '" salvo.'), false);
    admLoadPerfis();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

async function admPerfilCreate() {
  const nome = $('adm-perfil-nome') ? $('adm-perfil-nome').value.trim().toLowerCase() : '';
  const desc = $('adm-perfil-desc') ? $('adm-perfil-desc').value.trim() : '';
  const msg  = $('adm-perfil-msg');
  if (!nome) { if (msg) { msg.textContent = 'Informe o nome.'; msg.style.color = 'var(--red)'; } return; }
  try {
    await _admRbac('perfil_upsert', { perfil_nome: nome, descricao: desc, permissoes: [] });
    if (msg) { msg.textContent = 'Perfil criado — marque as permissões e salve.'; msg.style.color = 'var(--green)'; }
    if ($('adm-perfil-nome')) $('adm-perfil-nome').value = '';
    if ($('adm-perfil-desc')) $('adm-perfil-desc').value = '';
    admLoadPerfis();
  } catch(e) { if (msg) { msg.textContent = 'Erro: ' + e.message; msg.style.color = 'var(--red)'; } }
}

async function admPerfilDelete(nome) {
  const ok = await showConfirm('Excluir o perfil "' + nome + '"?\n\nSó é possível se nenhum usuário o utiliza.', '🗑 Excluir');
  if (!ok) return;
  try {
    await _admRbac('perfil_delete', { perfil_nome: nome });
    showToast('Perfil "' + nome + '" removido.', false);
    admLoadPerfis();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

// ── Mapeamento Airflow Role → Perfil ────────────────────────────────────────
async function admLoadRoleMap() {
  const el = $('adm-rolemap-list');
  if (!el) return;
  el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Carregando...</span>';
  try {
    const d = await _admRbac('role_map_list', {});
    const rows = d.dados || [];
    if (!rows.length) { el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Nenhum mapeamento cadastrado.</span>'; return; }
    let h = '<table style="width:100%;font-size:12px;border-collapse:collapse">'
      + '<thead><tr style="border-bottom:1px solid var(--border)">'
      + '<th style="text-align:left;padding:.35rem .5rem;color:var(--muted)">Role Airflow</th>'
      + '<th style="text-align:left;padding:.35rem .5rem;color:var(--muted)">Perfil</th>'
      + '<th style="text-align:center;padding:.35rem .5rem;color:var(--muted)">Prio</th>'
      + '<th style="text-align:left;padding:.35rem .5rem;color:var(--muted)">Descrição</th>'
      + '<th style="text-align:center;padding:.35rem .5rem;color:var(--muted)">Ativo</th>'
      + '<th></th></tr></thead><tbody>';
    rows.forEach(r => {
      h += '<tr style="border-bottom:.5px solid var(--border);vertical-align:middle">'
        + '<td style="padding:.35rem .5rem;font-weight:600">' + _escHtml(r.role_airflow) + '</td>'
        + '<td style="padding:.35rem .5rem"><code>' + _escHtml(r.perfil_nome) + '</code></td>'
        + '<td style="padding:.35rem .5rem;text-align:center">' + r.ordem_prioridade + '</td>'
        + '<td style="padding:.35rem .5rem;color:var(--muted)">' + _escHtml(r.descricao || '') + '</td>'
        + '<td style="padding:.35rem .5rem;text-align:center">' + (r.ativo ? '✅' : '⏸') + '</td>'
        + '<td style="padding:.35rem .5rem;white-space:nowrap">'
        + '<button class="btn btn-outline btn-xs" style="font-size:11px;padding:2px 8px" '
        + 'onclick="admRoleMapEdit(' + JSON.stringify(r) + ')">✏</button> '
        + '<button class="btn btn-outline btn-xs" style="font-size:11px;padding:2px 8px;color:var(--red);border-color:var(--red)" '
        + 'onclick="admRoleMapDelete(' + JSON.stringify(r.role_airflow) + ')">🗑</button>'
        + '</td></tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h;
  } catch(e) { el.innerHTML = '<span style="color:var(--red);font-size:12px">Erro: ' + e.message + '</span>'; }
}

function admRoleMapEdit(r) {
  if ($('adm-rm-role'))  { $('adm-rm-role').value  = r.role_airflow; }
  if ($('adm-rm-prio'))  { $('adm-rm-prio').value  = r.ordem_prioridade; }
  if ($('adm-rm-desc'))  { $('adm-rm-desc').value  = r.descricao || ''; }
  if ($('adm-rm-ativo')) { $('adm-rm-ativo').checked = !!r.ativo; }
  // seleciona o perfil no <select>
  const sel = $('adm-rm-perfil');
  if (sel) { for (let o of sel.options) { if (o.value === r.perfil_nome) { o.selected = true; break; } } }
}

async function admRoleMapSave() {
  const role   = $('adm-rm-role')  ? $('adm-rm-role').value.trim()   : '';
  const perfil = $('adm-rm-perfil')? $('adm-rm-perfil').value        : '';
  const prio   = $('adm-rm-prio')  ? parseInt($('adm-rm-prio').value) : 99;
  const desc   = $('adm-rm-desc')  ? $('adm-rm-desc').value.trim()   : '';
  const ativo  = $('adm-rm-ativo') ? $('adm-rm-ativo').checked       : true;
  const msg    = $('adm-rm-msg');
  if (!role)   { if (msg) { msg.textContent='Role obrigatório.';  msg.style.color='var(--red)'; } return; }
  if (!perfil) { if (msg) { msg.textContent='Perfil obrigatório.';msg.style.color='var(--red)'; } return; }
  try {
    const d = await _admRbac('role_map_upsert', { role_airflow: role, perfil_nome: perfil, ordem_prioridade: prio, descricao: desc, ativo });
    showToast(d.mensagem, false);
    if ($('adm-rm-role'))  $('adm-rm-role').value  = '';
    if ($('adm-rm-desc'))  $('adm-rm-desc').value  = '';
    if ($('adm-rm-prio'))  $('adm-rm-prio').value  = '99';
    if ($('adm-rm-ativo')) $('adm-rm-ativo').checked = true;
    if (msg) msg.textContent = '';
    admLoadRoleMap();
  } catch(e) { if (msg) { msg.textContent='Erro: '+e.message; msg.style.color='var(--red)'; } }
}

async function admRoleMapDelete(role) {
  const ok = await showConfirm('Remover mapeamento do role "' + role + '"?', '🗑 Remover');
  if (!ok) return;
  try {
    await _admRbac('role_map_delete', { role_airflow: role });
    showToast('Mapeamento "' + role + '" removido.', false);
    admLoadRoleMap();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

// Sub-navegação Admin
function admSwitch(panel) {
  ['config','delete','regen','versoes','tipos','agenda','usuarios'].forEach(p => {
    const el = $('adm-panel-' + p);
    if (el) el.style.display = p === panel ? '' : 'none';
    const btn = $('adm-tab-' + p);
    if (btn) btn.classList.toggle('active', p === panel);
  });
  if (panel === 'config')   admLoadConfig();
  if (panel === 'versoes')  admLoadVersoes();
  if (panel === 'tipos')    admLoadJobTypes();
  if (panel === 'agenda')   admLoadAgenda();
  if (panel === 'usuarios') admLoadUsuariosPerfis();
}

//* ── Admin: Agendamento avançado (Fase 4) ─────────────────────────────────── */
async function admLoadAgenda() {
  await Promise.all([admLoadCalendarios(), admLoadBlackouts()]);
}

async function admLoadCalendarios() {
  const el = $('adm-cal-list');
  if (!el) return;
  el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Carregando…</span>';
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/calendarios');
    const data = r.ok ? await r.json() : { calendarios: [] };
    const cals = data.calendarios || [];
    if ($('adm-cal-nomes')) {
      $('adm-cal-nomes').innerHTML = cals.map(c => '<option value="' + _escHtml(c.calendario_nome) + '">').join('');
    }
    if (!cals.length) {
      el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Nenhum calendário cadastrado.</span>';
      return;
    }
    el.innerHTML = cals.map(c =>
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--border);font-size:13px">' +
        '<div><strong>' + _escHtml(c.calendario_nome) + '</strong>' +
        ' <span style="color:var(--muted);font-size:11px">' + c.datas + ' data(s)' +
        (c.proxima ? ' · próx. bloqueio ' + _escHtml(c.proxima) : '') + '</span></div>' +
        '<div style="white-space:nowrap">' +
        '<button class="btn-ghost btn-sm" onclick="admCalVerDatas(\'' + _escHtml(c.calendario_nome).replace(/'/g, "\\'") + '\')">⊞ datas</button> ' +
        '<button class="btn-ghost btn-sm" style="color:var(--red)" onclick="admCalDelete(\'' + _escHtml(c.calendario_nome).replace(/'/g, "\\'") + '\')">✕</button>' +
        '</div></div>'
    ).join('');
  } catch(e) {
    el.innerHTML = '<span style="font-size:12px;color:var(--red)">Erro: ' + _escHtml(e.message) + '</span>';
  }
}

async function admCalVerDatas(nome) {
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/calendarios/' + encodeURIComponent(nome));
    const data = await r.json();
    const linhas = (data.datas || []).map(d => d.data + (d.descricao ? ' — ' + d.descricao : ''));
    _lsDetailPopover(null, linhas.join('\n'), 'Calendário ' + nome);
  } catch(e) { showToast('Erro ao listar datas: ' + e.message, true); }
}

async function admCalAdd() {
  const nome  = ($('adm-cal-nome')  ? $('adm-cal-nome').value.trim()  : '');
  const datas = ($('adm-cal-datas') ? $('adm-cal-datas').value : '').split('\n').map(s => s.trim()).filter(Boolean);
  const desc  = ($('adm-cal-desc')  ? $('adm-cal-desc').value.trim()  : '');
  const msg   = $('adm-cal-msg');
  if (!nome || !datas.length) { if (msg) { msg.textContent = 'Informe calendário e ao menos 1 data.'; msg.style.color = 'var(--red)'; } return; }
  if (datas.some(d => !/^\d{4}-\d{2}-\d{2}$/.test(d))) { if (msg) { msg.textContent = 'Use o formato AAAA-MM-DD.'; msg.style.color = 'var(--red)'; } return; }
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/calendarios', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({ calendario_nome: nome, datas, descricao: desc || null }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    if (msg) { msg.textContent = d.inseridas + ' data(s) adicionada(s).'; msg.style.color = 'var(--green)'; }
    if ($('adm-cal-datas')) $('adm-cal-datas').value = '';
    admLoadCalendarios();
  } catch(e) { if (msg) { msg.textContent = 'Erro: ' + e.message; msg.style.color = 'var(--red)'; } }
}

async function admCalDelete(nome) {
  const ok = await showConfirm('Excluir o calendário "' + nome + '" inteiro?\n\nPipelines que o utilizam deixarão de ter datas bloqueadas.', '✕ Excluir');
  if (!ok) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/calendarios/' + encodeURIComponent(nome), {
      method: 'DELETE', headers: { ..._orqAuthHeader() },
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    showToast('Calendário "' + nome + '" removido (' + d.removidas + ' data(s)).', false);
    admLoadCalendarios();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

async function admLoadBlackouts() {
  const el = $('adm-blk-list');
  if (!el) return;
  el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Carregando…</span>';
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/blackouts');
    const data = r.ok ? await r.json() : { blackouts: [], ambiente_congelado: false };
    _admRenderFreeze(!!data.ambiente_congelado);
    const list = (data.blackouts || []).filter(b => b.ativo);
    if (!list.length) {
      el.innerHTML = '<span style="font-size:12px;color:var(--muted)">Nenhum blackout ativo.</span>';
      return;
    }
    el.innerHTML = list.map(b =>
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem;padding:.4rem 0;border-bottom:1px solid var(--border);font-size:12px">' +
        '<div>' + (b.vigente ? '<span style="color:var(--red);font-weight:700">● vigente</span> ' : '<span style="color:var(--muted)">○ agendado</span> ') +
        '<strong>' + _escHtml(b.motivo || '') + '</strong>' +
        '<br><span style="color:var(--muted)">' + _escHtml(b.inicio || '') + ' → ' + _escHtml(b.fim || '') +
        ' · escopo: ' + _escHtml(b.escopo || 'global') + '</span></div>' +
        '<button class="btn-ghost btn-sm" style="color:var(--red);white-space:nowrap" onclick="admBlkEncerrar(' + b.id + ')">✕ encerrar</button>' +
      '</div>'
    ).join('');
  } catch(e) {
    el.innerHTML = '<span style="font-size:12px;color:var(--red)">Erro: ' + _escHtml(e.message) + '</span>';
  }
}

async function admBlkAdd() {
  const inicio = $('adm-blk-inicio') ? $('adm-blk-inicio').value : '';
  const fim    = $('adm-blk-fim')    ? $('adm-blk-fim').value    : '';
  const escopo = $('adm-blk-escopo') ? $('adm-blk-escopo').value.trim() : '';
  const motivo = $('adm-blk-motivo') ? $('adm-blk-motivo').value.trim() : '';
  const msg    = $('adm-blk-msg');
  if (!inicio || !fim || !motivo) { if (msg) { msg.textContent = 'Início, fim e motivo são obrigatórios.'; msg.style.color = 'var(--red)'; } return; }
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/blackouts', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({
        inicio: inicio.replace('T', ' '), fim: fim.replace('T', ' '),
        escopo: escopo || null, motivo }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    if (msg) { msg.textContent = 'Blackout criado.'; msg.style.color = 'var(--green)'; }
    ['adm-blk-inicio','adm-blk-fim','adm-blk-escopo','adm-blk-motivo'].forEach(id => { if ($(id)) $(id).value = ''; });
    admLoadBlackouts();
  } catch(e) { if (msg) { msg.textContent = 'Erro: ' + e.message; msg.style.color = 'var(--red)'; } }
}

async function admBlkEncerrar(id) {
  const ok = await showConfirm('Encerrar este blackout agora? As execuções voltam ao normal.', '✕ Encerrar');
  if (!ok) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/blackouts/' + id + '/encerrar', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({}),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    showToast('Blackout encerrado.', false);
    admLoadBlackouts();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

let _admCongelado = false;
function _admRenderFreeze(congelado) {
  _admCongelado = congelado;
  const st  = $('adm-freeze-status');
  const btn = $('adm-freeze-btn');
  if (st)  { st.textContent = congelado ? '🔴 AMBIENTE CONGELADO — execuções pausadas' : '🟢 Ambiente liberado';
             st.style.color = congelado ? 'var(--red)' : 'var(--green)'; }
  if (btn) { btn.textContent = congelado ? '▶ Descongelar ambiente' : '🚫 Congelar ambiente'; }
}

async function admToggleFreeze() {
  const acao = _admCongelado ? 'descongelar' : 'congelar';
  const aviso = acao === 'congelar'
    ? 'Congelar o ambiente?\n\nNENHUMA DAG gerada iniciará execução até descongelar. Execuções em andamento não são interrompidas.'
    : 'Descongelar o ambiente? As execuções voltam ao agendamento normal.';
  const ok = await showConfirm(aviso, acao === 'congelar' ? '🚫 Congelar' : '▶ Descongelar');
  if (!ok) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/admin/freeze', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({ acao }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    showToast(d.mensagem || 'OK', false);
    admLoadBlackouts();
  } catch(e) { showToast('Erro: ' + e.message, true); }
}

// ── Admin: Tipos de Job ──────────────────────────────────────────────────────
async function admLoadJobTypes() {
  const st  = $('adm-tipos-status');
  const tbl = $('adm-tipos-table');
  if (st)  st.textContent  = 'Carregando tipos de job...';
  if (tbl) tbl.innerHTML   = '';
  if (!authHeader) { if (st) st.textContent = 'Sem autenticação.'; return; }
  try {
    const r = await fetch(ORQUESTRA_API + '/catalogo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'list_job_types' }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const list = (data && data.job_types) || [];
    window.__jobTypes = list;
    if (st) st.textContent = list.length + ' tipo(s) encontrado(s)';
    _admRenderJobTypesTable(list);
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + e.message;
  }
}

function _admRenderJobTypesTable(list) {
  const tbl = $('adm-tipos-table');
  if (!tbl) return;
  if (!list.length) { tbl.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:1rem">Nenhum tipo cadastrado.</div>'; return; }
  tbl.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:12px">' +
    '<thead><tr style="border-bottom:1px solid var(--border)">' +
    '<th style="text-align:left;padding:.4rem .6rem;font-size:11px;color:var(--muted)">ID</th>' +
    '<th style="text-align:left;padding:.4rem .6rem;font-size:11px;color:var(--muted)">Nome</th>' +
    '<th style="text-align:left;padding:.4rem .6rem;font-size:11px;color:var(--muted)">Descrição</th>' +
    '<th style="text-align:center;padding:.4rem .6rem;font-size:11px;color:var(--muted)">Lineage</th>' +
    '<th style="text-align:center;padding:.4rem .6rem;font-size:11px;color:var(--muted)">Status</th>' +
    '<th style="text-align:right;padding:.4rem .6rem;font-size:11px;color:var(--muted)">Ações</th>' +
    '</tr></thead><tbody>' +
    list.map(t =>
      '<tr style="border-bottom:1px solid var(--border)">' +
      '<td style="padding:.4rem .6rem;color:var(--muted)">' + _escHtml(String(t.id||'')) + '</td>' +
      '<td style="padding:.4rem .6rem;font-weight:600">' + _escHtml(t.nome||'') + '</td>' +
      '<td style="padding:.4rem .6rem;color:var(--muted)">' + _escHtml(t.descricao||'—') + '</td>' +
      '<td style="padding:.4rem .6rem;text-align:center">' + (t.lineage_enabled ? '<span class="bit-on">✓</span>' : '<span class="bit-off">—</span>') + '</td>' +
      '<td style="padding:.4rem .6rem;text-align:center">' + (t.status ? '<span class="bit-on">ativo</span>' : '<span style="color:var(--muted);font-size:11px">inativo</span>') + '</td>' +
      '<td style="padding:.4rem .6rem;text-align:right;white-space:nowrap">' +
        '<button class="btn-ghost btn-sm" onclick="admOpenJobTypeForm(' + (t.id||0) + ')">✎ Editar</button> ' +
        '<button class="btn-ghost btn-sm" style="color:var(--red)" onclick="admDeleteJobType(' + (t.id||0) + ',\'' + _escHtml(t.nome||'') + '\')">✕</button>' +
      '</td></tr>'
    ).join('') + '</tbody></table>';
}

function admOpenJobTypeForm(id) {
  $('adm-tipo-form-title').textContent = id ? 'Editar Tipo de Job' : 'Novo Tipo de Job';
  $('adm-tipo-edit-id').value = id || '';
  $('adm-tipo-msg').textContent = '';
  if (id) {
    const t = (window.__jobTypes || []).find(x => x.id === id);
    if (t) {
      $('adm-tipo-nome').value   = t.nome    || '';
      $('adm-tipo-desc').value   = t.descricao || '';
      $('adm-tipo-status').value = t.status ? '1' : '0';
      $('adm-tipo-lineage').checked = !!t.lineage_enabled;
    }
  } else {
    $('adm-tipo-nome').value   = '';
    $('adm-tipo-desc').value   = '';
    $('adm-tipo-status').value = '1';
    $('adm-tipo-lineage').checked = true;
  }
  $('adm-tipo-form').style.display = '';
  $('adm-tipo-nome').focus();
}

function admCloseJobTypeForm() {
  $('adm-tipo-form').style.display = 'none';
}

async function admSaveJobType() {
  const nome = ($('adm-tipo-nome').value || '').trim();
  const msg  = $('adm-tipo-msg');
  if (!nome) { if (msg) { msg.textContent = 'Nome é obrigatório.'; msg.className = 'msg msg-error'; } return; }
  const id   = $('adm-tipo-edit-id').value || null;
  const conf = {
    mode: 'save_job_type',
    id: id ? parseInt(id) : null,
    nome,
    descricao:       ($('adm-tipo-desc').value   || '').trim(),
    status:          $('adm-tipo-status').value === '1' ? 1 : 0,
    lineage_enabled: $('adm-tipo-lineage').checked ? 1 : 0,
  };
  if (msg) { msg.textContent = 'Salvando...'; msg.className = 'msg'; }
  try {
    const r = await fetch(ORQUESTRA_API + '/catalogo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(conf),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    if (msg) { msg.textContent = 'Salvo com sucesso!'; msg.className = 'msg msg-ok'; }
    setTimeout(() => { admCloseJobTypeForm(); admLoadJobTypes(); }, 800);
  } catch(e) {
    if (msg) { msg.textContent = 'Erro: ' + e.message; msg.className = 'msg msg-error'; }
  }
}

async function admDeleteJobType(id, nome) {
  if (!confirm('Excluir tipo de job "' + nome + '"? Pipelines já cadastrados não serão afetados.')) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/catalogo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'delete_job_type', id }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    showToast('Tipo "' + nome + '" excluído.');
    admLoadJobTypes();
  } catch(e) {
    showToast('Erro ao excluir: ' + e.message, true);
  }
}

// ── Configurações: carregar tabela ─────────────────────────────
async function admTestWebhook() {
  const st = $('adm-config-status');
  if (st) st.textContent = 'Enviando card de teste ao Teams...';
  try {
    const r = await fetch(ORQUESTRA_API + '/admin/test-webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({})
    });
    const raw = await r.text();
    let d;
    try { d = JSON.parse(raw); }
    catch(_) {
      // Resposta não-JSON (ex.: 500 de proxy, container antigo sem o endpoint)
      d = { ok: false, erro: 'HTTP ' + r.status + ' — resposta não-JSON (container da API foi rebuildado?)',
            http_status: r.status, corpo_bruto: raw.slice(0, 400) };
    }
    if (!r.ok || !d.ok) {
      const msg = d.erro || d.detail || JSON.stringify(d);
      if (st) st.innerHTML = '<span style="color:var(--red)">✗ Falha: ' + msg + '</span>';
      // Exibe diagnóstico completo abaixo
      const tbl = $('adm-config-table');
      const box = document.createElement('div');
      box.style = 'background:rgba(220,38,38,.06);border:1px solid rgba(220,38,38,.3);border-radius:10px;padding:1rem;margin-bottom:1rem;font-size:12px';
      box.innerHTML = '<div style="font-weight:600;margin-bottom:.5rem;color:var(--red)">📋 Diagnóstico</div>' +
        '<pre style="margin:0;white-space:pre-wrap;word-break:break-all">' + JSON.stringify(d, null, 2) + '</pre>';
      tbl.insertAdjacentElement('beforebegin', box);
    } else {
      if (st) st.innerHTML = '<span style="color:var(--green)">✓ Card enviado (HTTP ' + d.http_status + '). Verifique o canal Teams.</span>';
    }
  } catch(e) {
    if (st) st.innerHTML = '<span style="color:var(--red)">✗ Erro: ' + (e.message || e) + '</span>';
  }
}

async function admLoadConfig() {
  if (!authHeader) return;
  const st = $('adm-config-status');
  const tbl = $('adm-config-table');
  if (st) st.textContent = 'Carregando parâmetros...';
  if (tbl) tbl.innerHTML = '';

  try {
    // Lista completa (inclui chaves sensíveis como teams_webhook_url) — só via /admin
    const r = await fetch(ORQUESTRA_API + '/admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({ action: 'config_list' })
    });
    if (!r.ok) { if (st) st.textContent = 'Erro ao carregar: ' + r.status; return; }
    const resp = await r.json();
    const cfg = (resp && resp.config) || {};
    window.__appConfig = { ...window.__appConfig, ...cfg };
    _renderConfigTable(cfg);
    if (st) st.textContent = Object.keys(cfg || {}).length + ' parâmetro(s) carregado(s).';
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + (e.message || e);
  }
}

function _renderConfigTable(cfg) {
  const tbl = $('adm-config-table');
  if (!tbl || !cfg) return;
  const rows = Object.entries(cfg).map(([key, value]) => {
    const safeKey = key.replace(/'/g, "\'");
    const safeVal = String(value).replace(/'/g, "\'").replace(/"/g, '&quot;');
    return '<tr>' +
      '<td style="font-family:monospace;font-size:12px;font-weight:600;white-space:nowrap">' + key + '</td>' +
      '<td><input class="cfg-edit-input" id="cfgval-' + key + '" value="' + safeVal + '" /></td>' +
      '<td class="col-actions">' +
        '<div class="row-actions">' +
          '<button class="act-btn act-save" data-cfg-action="save" data-cfg-key="' + key + '" title="Salvar configuração">' + ICONS.check + '</button>' +
          '<button class="act-btn act-del" data-cfg-action="del" data-cfg-key="' + key + '" title="Excluir configuração">' + ICONS.trash + '</button>' +
        '</div>' +
      '</td>' +
    '</tr>';
  }).join('');

  tbl.innerHTML =
    '<div class="query-table-wrap"><table class="query-table"><thead><tr>' +
    '<th>Chave</th><th>Valor</th><th class="col-actions">Ações</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table></div>';
}

function admOpenNewParam() {
  const f = $('adm-new-param-form');
  if (f) { f.style.display = ''; $('adm-new-key').focus(); }
}
function admCloseNewParam() {
  const f = $('adm-new-param-form');
  if (f) f.style.display = 'none';
  ['adm-new-key','adm-new-value','adm-new-desc'].forEach(id => { if ($(id)) $(id).value = ''; });
}

async function admSaveParam(key) {
  const input = $('cfgval-' + key);
  if (!input) return;
  const value = input.value.trim();
  if (!value) { showToast('Valor não pode ser vazio.', true); return; }
  await _admAction({ action: 'config_upsert', config_key: key, config_value: value });
  window.__appConfig[key] = value;
}

async function admSaveNewParam() {
  const key   = $('adm-new-key')   ? $('adm-new-key').value.trim()   : '';
  const value = $('adm-new-value') ? $('adm-new-value').value.trim() : '';
  const desc  = $('adm-new-desc')  ? $('adm-new-desc').value.trim()  : '';
  if (!key || !value) { showToast('Chave e valor são obrigatórios.', true); return; }
  const ok = await _admAction({ action: 'config_upsert', config_key: key, config_value: value, descricao: desc });
  if (ok) { admCloseNewParam(); admLoadConfig(); }
}

async function admDeleteParam(key) {
  const ok = await showConfirm(
    'Remover "' + key + '"? Se for parâmetro do sistema, o ORQUESTRA usará o valor padrão.',
    'Remover parâmetro'
  );
  if (!ok) return;
  const res = await _admAction({ action: 'config_delete', config_key: key });
  if (res) { delete window.__appConfig[key]; admLoadConfig(); }
}

// ── Excluir Pipeline ────────────────────────────────────────────
async function admFetchDeps() {
  const pipeline = $('adm-del-pipeline') ? $('adm-del-pipeline').value.trim() : '';
  if (!pipeline) { showToast('Informe o nome do pipeline.', true); return; }
  const st = $('adm-delete-status');
  if (st) st.textContent = 'Buscando dependências...';

  try {
    const params = new URLSearchParams({ filter_name: pipeline, offset: 0, limit: 1 });
    const r = await fetch(ORQUESTRA_API + '/pipelines?' + params.toString());
    if (!r.ok) { if (st) st.textContent = 'Erro API: ' + r.status; return; }
    const payload = await r.json();
    const found = (payload && payload.data || []).find(p => p.pipeline_name.toUpperCase() === pipeline);
    const preview = $('adm-del-preview');
    const prevContent = $('adm-del-preview-content');
    if (preview) preview.style.display = '';
    if (found && prevContent) {
      prevContent.innerHTML =
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:.5rem;font-size:12px">' +
          '<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.5rem .75rem">' +
            '<div style="font-weight:600;color:var(--red)">Pipeline</div>' +
            '<div>' + found.pipeline_name + '</div>' +
            '<div style="color:var(--muted)">' + (found.project_name||'') + '</div>' +
          '</div>' +
          '<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.5rem .75rem">' +
            '<div style="font-weight:600">DAG Airflow</div>' +
            '<div>' + (found.dag_criada ? '✅ Criada' : '—') + '</div>' +
          '</div>' +
          '<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.5rem .75rem">' +
            '<div style="font-weight:600">Status</div>' +
            '<div>' + (found.active ? '🟢 Ativo' : '🔴 Inativo') + '</div>' +
          '</div>' +
        '</div>';
      if (st) st.textContent = 'Pipeline encontrado. Confirme a exclusão abaixo.';
    } else {
      if (prevContent) prevContent.innerHTML = '<span style="color:var(--red);font-size:12px">Pipeline não encontrado.</span>';
      if (st) st.textContent = 'Pipeline não encontrado no banco.';
    }
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + (e.message || e);
  }
}

async function admConfirmDelete() {
  const pipeline = $('adm-del-pipeline') ? $('adm-del-pipeline').value.trim() : '';
  if (!pipeline) { showToast('Informe o nome do pipeline.', true); return; }
  _admDeleteWizardOpen(pipeline);
}

function _admDeleteWizardOpen(pipeline) {
  const nameEl = $('adm-wizard-pipeline-name');
  if (nameEl) nameEl.textContent = pipeline;
  const inp = $('adm-wizard-confirm-input');
  if (inp) inp.value = '';
  const msg = $('adm-wizard-step2-msg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }
  const btn = $('adm-wiz-confirm-btn');
  if (btn) { btn.disabled = false; btn.textContent = 'Confirmar Exclusão'; }
  _admDeleteWizardStep(1);
  $('modal-adm-delete-wizard').classList.add('open');
}

function _admDeleteWizardStep(n) {
  [$('adm-wiz-step1'), $('adm-wiz-step2')].forEach((el, i) => {
    if (el) el.style.display = (i + 1 === n) ? '' : 'none';
  });
  const lbl = $('adm-wiz-step-label');
  if (lbl) lbl.textContent = 'Etapa ' + n + ' de 2';
  if (n === 2) {
    setTimeout(() => { try { $('adm-wizard-confirm-input').focus(); } catch(e) {} }, 100);
  }
}

function _admDeleteWizardClose() {
  const m = $('modal-adm-delete-wizard');
  if (m) m.classList.remove('open');
}

async function _admDeleteWizardConfirm() {
  const pipeline = $('adm-wizard-pipeline-name') ? $('adm-wizard-pipeline-name').textContent.trim() : '';
  const typed    = $('adm-wizard-confirm-input')  ? $('adm-wizard-confirm-input').value.trim()      : '';
  const msgEl    = $('adm-wizard-step2-msg');

  if (typed.toUpperCase() !== pipeline.toUpperCase()) {
    if (msgEl) { msgEl.textContent = 'Nome digitado não confere. Digite exatamente: ' + pipeline; msgEl.className = 'msg erro'; }
    return;
  }

  const btn = $('adm-wiz-confirm-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Excluindo...'; }

  const res = await _admAction({ action: 'pipeline_delete', pipeline_name: pipeline });
  if (res) {
    // Remover DAG do Airflow (arquivo .py + metadata)
    await _deleteDagFromAirflow(pipeline);
    _admDeleteWizardClose();
    if ($('adm-del-pipeline')) $('adm-del-pipeline').value = '';
    const preview = $('adm-del-preview');
    if (preview) preview.style.display = 'none';
    showToast('Pipeline "' + pipeline + '" removido do banco e do Airflow.', false);
    try { loadQuery(0); } catch(e) {}
  } else {
    if (btn) { btn.disabled = false; btn.textContent = 'Confirmar Exclusão'; }
  }
}

// ── Helper genérico para ações admin via DAG ────────────────────
async function _admAction(conf) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return false; }
  conf.requested_by = window.__currentUser || '';
  const st = conf.action.startsWith('config') ? $('adm-config-status') : $('adm-delete-status');
  if (st) st.textContent = 'Processando...';
  try {
    const r = await fetch(ORQUESTRA_API + '/admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(conf),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = data.detail || data.message || ('Erro ' + r.status);
      if (st) st.textContent = '✗ ' + (typeof msg === 'string' ? msg : JSON.stringify(msg));
      showToast('Erro: ' + (typeof msg === 'string' ? msg : 'Falha na operação'), true);
      return false;
    }
    if (st) st.textContent = '✓ ' + (data.mensagem || 'Operação concluída com sucesso.');
    showToast(data.mensagem || 'Operação concluída.', false);
    return data;
  } catch(e) {
    if (st) st.textContent = 'Erro: ' + (e.message || e);
    return false;
  }
}


// Wrappers globais para re-renderização após sort
// (necessários porque as tabelas usam variáveis locais area/statusEl)
function _reRenderPipelines() {
  if (window.__lastQueryPayload) renderQueryTable(window.__lastQueryPayload);
}
function _reRenderJobs() {
  if (window.__lastJobsPayload) renderJobsTable(window.__lastJobsPayload);
}
function _reRenderLogs() {
  const area = $('logs-table-area');
  const st   = $('logs-status');
  if (window.__lastLogsPayload) renderLogsTable(window.__lastLogsPayload, area, st);
}


// Event delegation para ordenação por coluna (data-sort-table + data-sort-col)
// Evita o problema de aspas simples em onclick strings
document.addEventListener('click', function(e) {
  const th = e.target && e.target.closest ? e.target.closest('th[data-sort-col]') : null;
  if (!th) return;
  const tbl = th.getAttribute('data-sort-table');
  const col = th.getAttribute('data-sort-col');
  if (!tbl || !col) return;
  const renders = {
    'pipelines': _reRenderPipelines,
    'jobs':      _reRenderJobs,
    'logs':      _reRenderLogs,
  };
  if (renders[tbl]) _onSortClick(tbl, col, renders[tbl]);
});


// Event delegation para botões da tabela de config admin
document.addEventListener('click', function(e) {
  const btn = e.target && e.target.closest ? e.target.closest('[data-cfg-action]') : null;
  if (!btn) return;
  const action = btn.getAttribute('data-cfg-action');
  const key    = btn.getAttribute('data-cfg-key');
  if (!key) return;
  if (action === 'save') admSaveParam(key);
  if (action === 'del')  admDeleteParam(key);
});


// S2 — Filtros rápidos de período nos Logs
function _applyQuickPeriod() {
  const period = $('lf-period') ? $('lf-period').value : '';
  // Limpar sempre ao trocar
  if ($('lf-datetime-from')) $('lf-datetime-from').value = '';
  if (!period) {
    if ($('lf-date-from')) $('lf-date-from').value = '';
    return;
  }
  const hours = parseInt(period, 10);
  // Gravar horas no hidden (enviado ao backend como filter_hours_back)
  if ($('lf-datetime-from')) $('lf-datetime-from').value = String(hours);
  // Atualizar campo visual com a data calculada (só feedback — não enviado ao backend)
  const d = new Date(Date.now() - hours * 3600000);
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const dd = String(d.getDate()).padStart(2,'0');
  if ($('lf-date-from')) $('lf-date-from').value = d.getFullYear() + '-' + mm + '-' + dd;
}

function _applyFailedFilter(hours) {
  if ($('lf-status')) $('lf-status').value = 'FAILED';
  // Tenta selecionar opção visual no select (para feedback ao usuário)
  if ($('lf-period')) $('lf-period').value = hours > 0 ? String(hours) : '';
  if (hours > 0) {
    // Seta o hidden field diretamente — garante filter_hours_back mesmo se a opção
    // não existir no <select> (ex: failure_badge_hours_lookback = 12 ou 72)
    if ($('lf-datetime-from')) $('lf-datetime-from').value = String(hours);
    const d  = new Date(Date.now() - hours * 3600000);
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    if ($('lf-date-from')) $('lf-date-from').value = d.getFullYear() + '-' + mm + '-' + dd;
  } else {
    _applyQuickPeriod();
  }
  loadLogs(0);
}

// Clique no badge de falhas → aplica filtro FAILED + últimas 24h
// (sobrescreve o onclick inline do header que apenas mudava de aba)


// Remover DAG do Airflow: chama REST API DELETE + dispara DAG de limpeza de arquivo
async function _deleteDagFromAirflow(pipelineName) {
  const dagId = _pipelineToDagId(pipelineName);

  // 1. Pausar a DAG imediatamente (evita execuções enquanto remove)
  try {
    await fetch('/api/v1/dags/' + dagId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
      body: JSON.stringify({ is_paused: true }),
    });
  } catch(e) { console.warn('[ORQ] Não foi possível pausar DAG antes de deletar:', e.message); }

  // 2. Deletar DAG do Airflow via REST API (remove do metadata do scheduler)
  try {
    const r = await fetch('/api/v1/dags/' + dagId, {
      method: 'DELETE',
      headers: { 'Authorization': authHeader },
    });
    if (r.ok || r.status === 404) {
      console.log('[ORQ] DAG "' + dagId + '" removida do Airflow.');
    } else {
      console.warn('[ORQ] DELETE /api/v1/dags/' + dagId + ' retornou ' + r.status);
    }
  } catch(e) {
    console.warn('[ORQ] Erro ao deletar DAG do Airflow:', e.message);
  }

  // 3. Remover arquivo .py via API ORQUESTRA
  try {
    await fetch(ORQUESTRA_API + '/admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'dag_file_delete',
        pipeline_name: pipelineName,
        requested_by: window.__currentUser || '',
      }),
    });
    console.log('[ORQ] Arquivo DAG removido via API para "' + pipelineName + '"');
  } catch(e) {
    console.warn('[ORQ] Não foi possível remover arquivo DAG:', e.message);
  }
}


// ── Regenerar Todas as DAGs ──────────────────────────────────────────────────
async function admRegenEstimate() {
  const project = $('adm-regen-project') ? $('adm-regen-project').value : '';
  const estEl   = $('adm-regen-estimate');
  if (estEl) estEl.textContent = '⏳ Consultando...';
  try {
    const params = new URLSearchParams({ limit: 1, offset: 0 });
    if (project) params.set('filter_project', project);
    const r = await fetch(ORQUESTRA_API + '/pipelines?' + params.toString());
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    const total = data.total ?? '?';
    if (estEl) estEl.textContent = '📊 ' + total + ' pipeline(s) serão regenerados' + (project ? ' no projeto ' + project : '') + '.';
  } catch(e) {
    if (estEl) estEl.textContent = 'Não foi possível estimar — clique em Regenerar para prosseguir.';
  }
}

async function admRegenAllDags() {
  const project = $('adm-regen-project') ? $('adm-regen-project').value : '';
  const statusEl = $('adm-regen-status');
  const titleEl  = $('adm-regen-title');
  const logEl    = $('adm-regen-log');
  const btn      = $('adm-regen-btn');

  if (statusEl) statusEl.style.display = '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Processando...'; }
  if (logEl)  logEl.textContent = '';

  function _log(msg) {
    if (!logEl) return;
    logEl.textContent += '[' + new Date().toLocaleTimeString('pt-BR') + '] ' + msg + '\n';
    logEl.scrollTop = logEl.scrollHeight;
  }

  try {
    // Passo 1: resetar dag_criada via etl_admin_manage
    if (titleEl) titleEl.textContent = 'Passo 1/2 — Marcando pipelines para regeneração...';
    _log('Disparando reset de dag_criada...');

    const res = await _admAction({ action: 'regenerate_all_dags', filter_project: project });
    if (!res) throw new Error('Falha no passo 1');
    _log('✓ ' + (res.mensagem || 'Pipelines marcados.'));

    // Passo 2: disparar etl_dag_factory com force_all=true
    if (titleEl) titleEl.textContent = 'Passo 2/2 — Disparando etl_dag_factory...';
    _log('Disparando etl_dag_factory com force_all=true...');

    const runId2 = 'orq_regen_factory_' + Date.now();
    const r2 = await fetch('/api/v1/dags/etl_dag_factory/dagRuns', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization': authHeader},
      body: JSON.stringify({ dag_run_id: runId2, conf: {
        force_all: true,
        filter_project: project,
        requested_by: window.__currentUser || '',
      }}),
    });
    if (!r2.ok) {
      const err = await r2.text();
      throw new Error('Factory falhou: ' + err);
    }
    _log('✓ etl_dag_factory disparada: ' + runId2);
    _log('Aguardando conclusão...');

    // Aguardar conclusão da factory
    const fState = await waitDagRun('etl_dag_factory', runId2, 120);
    _log(fState === 'success' ? '✓ Factory concluída.' : '⚠ Factory finalizou com estado: ' + fState);

    if (titleEl) titleEl.textContent = '✅ Regeneração concluída!';
    _log('Todos os .py foram regenerados com as novas regras (fail-fast, etc).');
    _log('O Airflow detectará as mudanças automaticamente no próximo scan.');
    showToast('DAGs regeneradas com sucesso.', false);

  } catch(e) {
    if (titleEl) titleEl.textContent = '❌ Erro durante regeneração';
    _log('ERRO: ' + e.message);
    showToast('Erro ao regenerar: ' + e.message, true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '♻ Regenerar DAGs'; }
  }
}


// Abre o log do Airflow diretamente para um job específico (sem picker)
function _showAirflowJobLog(pipeline, executionId, taskId) {
  if (!pipeline || !executionId || !taskId) {
    showToast('Dados insuficientes para buscar o log.', true);
    return;
  }

  // Reusar o modal existente de log do Airflow
  const sub = $('afl-subtitle');
  if (sub) sub.textContent = taskId + ' · ' + executionId;

  // Alimentar o _aflState do IIFE via setter global (evita problema de escopo)
  if (window._setAflState) {
    window._setAflState(pipeline, executionId, taskId);
  }

  // Esconder o seletor de job (já sabemos qual é)
  const selDiv = $('afl-job-selector');
  if (selDiv) selDiv.style.display = 'none';

  // Preencher o select oculto para que _airflowLogFetch funcione
  const selEl = $('afl-job-select');
  if (selEl) {
    selEl.innerHTML = '<option value="' + taskId + '" data-try="1">' + taskId + '</option>';
    selEl.value = taskId;
  }

  // Abrir modal — _airflowLogFetch usará _aflState já alimentado acima
  $('modal-airflow-log').classList.add('open');
  _airflowLogFetch();
}

/* ══ LOGIN ══ */
async function entrar() {
  const m = $('login_msg');
  m.className = 'msg';
  const u = $('login_user').value.trim();
  const p = $('login_pass').value;
  if (!u) { m.textContent = 'Informe o usuário'; m.className = 'msg erro'; return; }
  if (!p) { m.textContent = 'Informe a senha'; m.className = 'msg erro'; return; }
  $('login_btn_txt').textContent = 'Validando...';
  $('login_btn').disabled = true;
  try {
    // Login na API ORQUESTRA: valida no Airflow, registra o usuário no banco
    // (dados do Airflow no 1º acesso) e devolve token de sessão + perfil
    const r = await fetch(ORQUESTRA_API + '/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario: u, senha: p }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 401) {
      m.textContent = 'Usuário ou senha inválidos. Verifique e tente novamente.';
      m.className = 'msg erro';
      $('login_pass').value = ''; $('login_pass').focus(); return;
    }
    if (r.status === 403) {
      m.textContent = d.detail || 'Acesso negado.';
      m.className = 'msg erro'; return;
    }
    if (!r.ok) {
      m.textContent = (d.detail || ('Erro HTTP ' + r.status)) + '. Contate o administrador.';
      m.className = 'msg erro'; return;
    }
    __orqToken = d.token;
    _saveSession(d.token, d.expira_em_horas);
    _applyUserInfo(d.usuario || {});
    // Basic em memória apenas nesta aba, para chamadas diretas ao Airflow
    authHeader = 'Basic ' + btoa(u + ':' + p);
    $('loginScreen').classList.add('hidden');
    $('appScreen').classList.remove('hidden');
    $('login_pass').value = '';
    const cw = $('caps-warn'); if (cw) cw.style.display = 'none';
    // Nome ainda não veio do banco (1º login sem permissão no /users do Airflow)?
    if (!(d.usuario || {}).primeiro_nome) {
      fetchUserFirstName().then(firstName => {
        if (firstName) $('who').textContent = firstName;
      }).catch(() => {});
    }
    _postLoginInit();
    // Uma vez logado, o usuário entra direto na UI React (/v2). A UI legada passa
    // a funcionar apenas como porta de login e para telas ainda não migradas
    // (ex.: DS Monitor, acessível via /?tab=ds-monitor).
    window.location.href = '/v2/';
  } catch(e) {
    m.textContent = 'Não foi possível conectar ao servidor. Verifique a rede.';
    m.className = 'msg erro';
  } finally {
    $('login_btn_txt').textContent = 'ENTRAR';
    $('login_btn').disabled = false;
  }
}

/** Inicialização comum pós-login (login manual ou sessão restaurada no F5). */
function _postLoginInit() {
  _applyPermVisibility();
  _applyAdminVisibility();
  _initSystemAuth().then(() => _detectViewerRole()).then(() => {
    _applyAdminVisibility(); // reaplica após detecção de viewer
    if (window.__isViewer) {
      try { if (window.__lastQueryPayload) renderQueryTable(window.__lastQueryPayload); } catch(e) {}
      try { if (window.__lastJobsPayload)  renderJobsTable(window.__lastJobsPayload);  } catch(e) {}
    }
  });
  // Carregar config do banco (assíncrono, não bloqueia)
  loadAppConfig().then(() => {
    _startDashAutoRefresh();
    _startFailureBadgeTimer();
    const hint = $('dash-refresh-interval-hint');
    const secs = window.__appConfig.dashboard_refresh_interval_sec || 60;
    if (hint) hint.textContent = secs >= 60 ? Math.round(secs/60) + 'min' : secs + 's';
  });
  try { loadProjectList(); } catch(e) {}
  try { goDashboard(); } catch(e) {}
}

function sair() {
  // Revoga o token de sessão no servidor (best-effort)
  if (__orqToken) {
    try {
      fetch(ORQUESTRA_API + '/auth/logout', {
        method: 'POST', headers: { Authorization: 'Bearer ' + __orqToken } });
    } catch(e) {}
  }
  _clearSession();
  authHeader = null;
  window.__userPerfil = 'consulta';
  window.__userPerms  = [];
  $('appScreen').classList.add('hidden');
  $('loginScreen').classList.remove('hidden');
  $('login_msg').textContent = '';
  $('login_user').value = '';
  $('login_pass').value = '';
  setTimeout(() => { try { $('login_user').focus(); } catch(e){} }, 100);
}

// ── Boot: tenta restaurar a sessão salva (F5 não desloga mais) ───────────────
window.addEventListener('DOMContentLoaded', () => { restoreSession(); });

function checkCapsLock(e) {
  const warn = $('caps-warn');
  if (!warn) return;
  warn.style.display = (e.getModifierState && e.getModifierState('CapsLock')) ? 'flex' : 'none';
}

/* ══ TEMA ══ */
function applyTheme(m) {
  const dark = m === 'dark';
  document.documentElement.classList.toggle('dark', dark);
  try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch(e) {}
  // Spec: evitar emojis — usar símbolo unicode neutro
  const e = $('theme-emoji'); if (e) e.textContent = dark ? '◑' : '◐';
}
function toggleTheme() { applyTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark'); }
(function(){ let s=null; try{s=localStorage.getItem('theme');}catch(e) {} applyTheme(s==='dark'?'dark':'light'); })();

/* ══ TOAST ══ */
let _tt = null;
function showToast(msg, isErr) {
  $('toastDot').className = 'dot' + (isErr ? ' err' : '');
  $('toastText').textContent = msg || 'Registro salvo';
  $('toast').classList.remove('hidden');
  if (_tt) clearTimeout(_tt);
  _tt = setTimeout(() => $('toast').classList.add('hidden'), 2800);
}

/* ══ TABS ══ */
function switchPage(pageId, btn) {
  // Ao trocar de aba, sempre “zera” o estado para evitar filtros antigos e dados enganadores
  try {
    if (pageId === 'page-pipelines') {
      closePipelineEditor();
      clearQuery();
    }
    if (pageId === 'page-jobs') {
      if ($('job_pipeline_name')) $('job_pipeline_name').value = '';
      clearJobsQuery();
    }
    if (pageId === 'page-logs') {
      clearLogsFilters();
    }
    if (pageId === 'page-governanca') {
      clearGovernanca();
    }
    if (pageId === 'page-admin') {
      // Carregar configs ao abrir o painel Admin
      try { admSwitch('config'); } catch(_) {}
    }
  } catch(_) {}

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.hd-tab').forEach(b => b.classList.remove('active'));
  $(pageId).classList.add('active');
  btn.classList.add('active');
}

function goDashboard() {
  const btn = $('tab-dashboard');
  if (btn) switchPage('page-dashboard', btn);
  try { loadDashboard(); } catch(e) {}
}

/* ══ STATUS ATIVO/INATIVO ══ */
function setStatus(val) {
  pipelineStatus = val;
  $('p-active').value = val;
  $('st-ativo').className   = 'st-opt' + (val === 1 ? ' active-green' : '');
  $('st-inativo').className = 'st-opt' + (val === 0 ? ' active-red'   : '');
}

/* ══ SYNC TOGGLE VISUAL ══ */
function syncToggle(lblId, chk) {
  $(lblId).classList.toggle('on', chk.checked);
}

/* ══ MODO JOBS ══ */
function setMode(m) {
  jobMode = m;
  $('mode-manual-btn').classList.toggle('active', m === 'manual');
  $('mode-bulk-btn').classList.toggle('active', m === 'bulk');
  $('mode-manual').classList.toggle('hidden', m !== 'manual');
  $('mode-bulk').classList.toggle('hidden', m !== 'bulk');
}

/* ══ OPÇÃO B — LISTA DE JOBS + MODAL DE LINEAGE ══ */
let jobsBdata = [];
let jbLineId  = 0;
let activeJobModal = null;
const OBJ_TYPES_B = ['Tabela','View','CSV','DataSet','TXT','XLS','XLSX','Proc','Query'];
const JOB_TYPES_B  = ['datastage','shell','python','storedproc'];
const JOB_LABELS_B = {'datastage':'DataStage','shell':'Shell','python':'Python','storedproc':'Proc SQL'};

function _ensureModal() {
  if ($('modal-lineage-b')) return;
  const d = document.createElement('div');
  d.id = 'modal-lineage-b';
  d.className = 'modal-backdrop';
  // Modal de formulário: alinhado ao topo (não centralizado), cresce com o conteúdo,
  // scroll interno no body para não ultrapassar a viewport.
  d.innerHTML = `
    <div style="
      background:var(--card);
      border:1px solid var(--border);
      border-radius:18px;
      width:100%;
      max-width:600px;
      max-height:calc(100vh - 2rem);
      display:flex;
      flex-direction:column;
      box-shadow:var(--shadow-modal);
      animation:fade .2s ease-out;
      overflow:hidden;
    ">
      <!-- cabeçalho fixo -->
      <div style="
        display:flex;
        align-items:center;
        justify-content:space-between;
        padding:.85rem 1.25rem;
        border-bottom:1px solid var(--border);
        flex-shrink:0;
      ">
        <span class="modal-title" id="mlb-title" style="margin:0;font-size:1rem">Lineage do job</span>
        <button onclick="closeLineageModal()" style="
          background:none;border:none;cursor:pointer;
          color:var(--muted);font-size:1.3rem;line-height:1;
          padding:2px 6px;border-radius:6px;
        " title="Fechar">×</button>
      </div>
      <!-- corpo com scroll -->
      <div id="mlb-body" style="
        overflow-y:auto;
        padding:1rem 1.25rem 1.25rem;
        flex:1;
        min-height:0;
      "></div>
    </div>`;
  d.style.alignItems = 'flex-start';
  d.style.paddingTop = '3rem';
  d.addEventListener('click', e => { if (e.target === d) closeLineageModal(); });
  document.body.appendChild(d);
}

let _mlbView = 'edit'; // 'edit' | 'diagram'

function _mlbToggleView() {
  _mlbView = _mlbView === 'edit' ? 'diagram' : 'edit';
  renderModalBody();
}

// Converte as linhas em edição do modal para o formato de job do GET /lineage,
// para renderizar o mesmo diagrama da aba Governança.
function _mlbRowsToJob(j) {
  const map = arr => (arr || []).filter(o => (o.n || '').trim()).map(o => ({
    object_name: o.n, object_type: o.t, stage_name: o.stage_name || null,
    database_name: o.database_name || null, sql_expression: o.sql_expression || null,
    file_path: o.file_path || null, columns: Array.isArray(o.columns) ? o.columns : [],
  }));
  return { job_name: j.name || 'job', execution_order: j.order, job_type: j.type,
           origens: map(j.origens), transformacoes: map(j.transformacoes), destinos: map(j.destinos) };
}

function openLineageModal(jobId) {
  _ensureModal();
  activeJobModal = jobId;
  _mlbView = 'edit';
  const j = jobsBdata.find(x => x.id === jobId);
  const isStep2 = window.__lineageTableCtx && window.__lineageTableCtx.source === 'jobCreate';
  $('mlb-title').textContent = (isStep2 ? 'Etapa 2/2 — Lineage — ' : 'Lineage — ') + (j.name || 'job sem nome');
  renderModalBody();
  $('modal-lineage-b').classList.add('open');
}

function closeLineageModal() {
  if ($('modal-lineage-b')) $('modal-lineage-b').classList.remove('open');
  activeJobModal = null;

  if (window.__lineageTableCtx) {
    const ctx = window.__lineageTableCtx;
    window.__lineageTableCtx = null;
    const jobs = collectJobRows();
    const j0 = jobs[0];

    // Sem job válido ou pipeline: apenas fecha
    if (!j0 || !ctx.pipeline) return;

    // Edição de lineage de job já cadastrado: substitui no banco (permite editar/excluir)
    if (ctx.source === 'jobEdit') {
      if (ctx.orig && ctx.orig === JSON.stringify(jobs)) return; // nada mudou
      const vazio = !(j0.origens || []).length && !(j0.destinos || []).length && !(j0.transformacoes || []).length;
      if (vazio && !confirm('Remover TODA a lineage do job "' + j0.job_name + '"?')) return;
      fetch(ORQUESTRA_API + '/lineage/job', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
        body: JSON.stringify({
          pipeline_name: ctx.pipeline, job_name: j0.job_name,
          origens: j0.origens, destinos: j0.destinos, transformacoes: j0.transformacoes,
        }),
      }).then(async r => {
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
        showToast('Lineage de "' + j0.job_name + '" atualizada (' + d.inseridos + ' objeto(s)).', false);
      }).catch(e => showToast('Erro ao salvar lineage: ' + e.message, true));
      return;
    }

    const temOrigem  = j0.origens  && j0.origens.length  > 0;
    const temDestino = j0.destinos && j0.destinos.length > 0;

    // Nenhum campo preenchido: fecha silenciosamente (usuário saiu sem preencher)
    if (!temOrigem && !temDestino) return;

    // Preenchimento parcial: avisa e NÃO dispara a DAG
    if (!temOrigem || !temDestino) {
      showToast(
        'Preencha ao menos 1 ' + (!temOrigem ? 'origem' : 'destino') + ' para salvar a linhagem.',
        true
      );
      return;
    }

    // Tudo OK: dispara etl_pipeline_job_register
    triggerAndPoll(
      'etl_pipeline_job_register',
      { pipeline_name: ctx.pipeline, jobs },
      'Lineage de "' + j0.job_name + '"',
      null, null, null
    );
  } else {
    renderJobLinesB();
  }
}

function renderModalBody() {
  const j = jobsBdata.find(x => x.id === activeJobModal);
  if (!j) return;

  // Modo visualização: mesmo diagrama da aba Governança ▸ Lineage
  if (_mlbView === 'diagram') {
    const job = _mlbRowsToJob(j);
    const temAlgo = job.origens.length || job.transformacoes.length || job.destinos.length;
    $('mlb-body').innerHTML =
      '<div style="overflow-x:auto;padding-bottom:.25rem">' +
      (temAlgo
        ? _lineageJobDiagramHtml(job)
        : '<div class="empty-state"><span class="es-icon">◎</span><p class="es-title">Sem lineage para visualizar</p><p class="es-sub">Adicione origens e destinos no modo de edição.</p></div>') +
      '</div>' +
      `<div style="display:flex;gap:8px;margin-top:1rem;padding-top:.75rem;border-top:1px solid var(--border)">
        <button class="btn-ghost" onclick="_mlbToggleView()" style="flex:1">✎ Voltar à edição</button>
      </div>`;
    return;
  }

  const linRows = (arr, dir) => arr.map((o, i) => `
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:5px">
      <select style="font-size:13px;flex:0 0 120px" onchange="updateLinB(${activeJobModal},'${dir}',${i},'t',this.value)">
        ${(OBJ_TYPES_B.includes(o.t) ? OBJ_TYPES_B : [o.t].concat(OBJ_TYPES_B)).map(t => `<option value="${t}" ${o.t===t?'selected':''}>${t}</option>`).join('')}
      </select>
      <input type="text" style="font-size:13px;flex:1;min-width:0" placeholder="ex: dbo.tabela" value="${o.n}"
        oninput="updateLinB(${activeJobModal},'${dir}',${i},'n',this.value)" />
      <button class="rm-btn" style="flex:0 0 28px;width:28px;height:28px;font-size:12px"
        onclick="rmLinB(${activeJobModal},'${dir}',${i})" aria-label="Remover">×</button>
    </div>`).join('');
  const canDSX = (j.type || '') === 'datastage';
  $('mlb-body').innerHTML = `
    ${canDSX ? `
    <div style="margin-bottom:1rem">
      <button class="btn btn-outline btn-sm" style="width:100%" onclick="loadLineageDSX(${j.id})" id="btn-dsx-extract">
        ⬡ Extrair linhagem do DSX
      </button>
      <div class="helper" style="margin-top:.35rem">
        Busca origens e destinos automaticamente no arquivo <strong>.dsx</strong> do projeto.
      </div>
    </div>` : ``}
    <div style="margin-bottom:1rem">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem">
        <span class="lin-label" style="color:var(--cvp-blue)">
          Origens <span style="color:var(--red)">*</span>
        </span>
        <button class="btn-ghost btn-sm" onclick="addLinB(${j.id},'ori')">+ adicionar</button>
      </div>
      <div id="mlb-origens">${linRows(j.origens,'ori')}</div>
    </div>
    <div style="margin-bottom:1.25rem">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem">
        <span class="lin-label" style="color:#15803d">
          Destinos <span style="color:var(--red)">*</span>
        </span>
        <button class="btn-ghost btn-sm" onclick="addLinB(${j.id},'dst')">+ adicionar</button>
      </div>
      <div id="mlb-destinos">${linRows(j.destinos,'dst')}</div>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-outline" onclick="_mlbToggleView()" style="flex:1" title="Visualizar o diagrama de lineage (igual à aba Governança)">◈ Ver diagrama</button>
      <button class="btn-ghost" onclick="closeLineageModal()" style="flex:1">${(window.__lineageTableCtx && window.__lineageTableCtx.source === 'jobEdit') ? 'Salvar alterações' : 'Confirmar'}</button>
    </div>`;
}

function updateLinB(jobId, dir, idx, field, val) {
  const j = jobsBdata.find(x => x.id === jobId);
  const arr = dir === 'ori' ? j.origens : j.destinos;
  arr[idx][field] = val;
}

function addLinB(jobId, dir) {
  const j = jobsBdata.find(x => x.id === jobId);
  if (dir === 'ori') j.origens.push({t:'Tabela', n:''});
  else               j.destinos.push({t:'Tabela', n:''});
  renderModalBody();
}

function rmLinB(jobId, dir, idx) {
  const j = jobsBdata.find(x => x.id === jobId);
  const arr = dir === 'ori' ? j.origens : j.destinos;
  arr.splice(idx, 1);
  renderModalBody();
}

function addJobLineB(data) {
  jbLineId++;
  const id = jbLineId;
  jobsBdata.push({
    id,
    name:    data && data.job_name        || '',
    type:    data && data.job_type        || 'datastage',
    order:   data && data.execution_order || id,
    cmd:     data && data.job_command     || '',
    origens: [{t:'Tabela', n:''}],
    destinos:[{t:'Tabela', n:''}],
    transformacoes: [],
  });
  renderJobLinesB();
}

function removeJobLineB(id) {
  jobsBdata = jobsBdata.filter(j => j.id !== id);
  if (!jobsBdata.length) addJobLineB();
  else renderJobLinesB();
}

function renderJobLinesB() {
  const el = $('job-lines-b');
  if (!el) return;
  el.innerHTML = jobsBdata.map(j => {
    const hasOri = j.origens.some(o => o.n.trim());
    const hasDst = j.destinos.some(o => o.n.trim());
    const ok = hasOri && hasDst;
    return `
    <div style="display:grid;grid-template-columns:minmax(0,1fr) 110px 52px 80px 32px;gap:6px;align-items:center;margin-bottom:6px">
      <input type="text" style="font-size:13px" placeholder="job_extrai_pedidos"
        value="${j.name}" oninput="jobsBdata.find(x=>x.id===${j.id}).name=this.value" />
      <select style="font-size:13px" onchange="onJobTypeChangeB(${j.id},this.value)">
        ${JOB_TYPES_B.map(t => '<option value="'+t+'" '+(j.type===t?'selected':'')+'>'+JOB_LABELS_B[t]+'</option>').join('')}
      </select>
      <input type="number" min="1" style="font-size:13px;text-align:center"
        value="${j.order}" oninput="jobsBdata.find(x=>x.id===${j.id}).order=+this.value" />
      <button onclick="openLineageModal(${j.id})"
        class="lineage-btn ${ok ? 'lineage-btn-ok' : 'lineage-btn-pending'}">
        ${ok ? 'OK' : 'Lineage'}
      </button>
      <button class="rm-btn" style="width:32px;height:32px;font-size:12px"
        onclick="removeJobLineB(${j.id})" aria-label="Remover job">x</button>
    </div>`;
  }).join('');
}

function onJobTypeChangeB(id, val) {
  jobsBdata.find(x => x.id === id).type = val;
  renderJobLinesB();
}

function normalizeLineageObjectType(t) {
  // Compatibilidade com backend legado (que validava tipos fixos)
  // e padronização para armazenamento.
  const v = (t || '').toString().trim();
  if (!v) return 'Tabela';
  if (['CSV','DataSet','TXT','XLS','XLSX'].includes(v)) return 'Arquivo';
  return v;
}

function collectJobRows() {
  return jobsBdata
    .filter(j => j.name.trim() && !isNaN(j.order))
    .map(j => ({
      job_name:        j.name.trim(),
      execution_order: j.order,
      job_type:        j.type,
      job_command:     j.cmd || null,
      origens: j.origens
        .filter(o => o.n.trim())
        .map(o => ({
          object_type: normalizeLineageObjectType(o.t),
          object_name: o.n.trim(),
          stage_name: o.stage_name || null,
          stage_type_raw: o.stage_type_raw || null,
          database_name: o.database_name || null,
          sql_expression: o.sql_expression || null,
          dsx_source_file: o.dsx_source_file || null,
          extracted_at: o.extracted_at || null,
          extraction_method: o.extraction_method || null,
          columns: Array.isArray(o.columns) ? o.columns : null,
        })),
      transformacoes: (j.transformacoes || []).filter(o => (o.n || '').trim()).map(o => ({
        object_type: normalizeLineageObjectType(o.t),
        object_name: (o.n || '').trim(),
        stage_name: o.stage_name || null,
        stage_type_raw: o.stage_type_raw || null,
        database_name: o.database_name || null,
        sql_expression: o.sql_expression || null,
        file_path: o.file_path || null,
        dsx_source_file: o.dsx_source_file || null,
        extracted_at: o.extracted_at || null,
        extraction_method: o.extraction_method || null,
        columns: Array.isArray(o.columns) ? o.columns : null,
      })),
      destinos: j.destinos
        .filter(o => o.n.trim())
        .map(o => ({
          object_type: normalizeLineageObjectType(o.t),
          object_name: o.n.trim(),
          stage_name: o.stage_name || null,
          stage_type_raw: o.stage_type_raw || null,
          database_name: o.database_name || null,
          sql_expression: o.sql_expression || null,
          file_path: o.file_path || null,
          dsx_source_file: o.dsx_source_file || null,
          extracted_at: o.extracted_at || null,
          extraction_method: o.extraction_method || null,
          columns: Array.isArray(o.columns) ? o.columns : null,
        })),
    }));
}

function addJobRow(n, o, t, c) { addJobLineB({job_name:n, execution_order:o, job_type:t, job_command:c}); }
function removeJobRow(id) { removeJobLineB(id); }

addJobLineB();

/* ══ MODAL DE STATUS DA DAG ══ */
let _pollTimer = null;

function openModal() {
  $('statusModal').classList.add('open');
  $('md-icon').className    = 'modal-icon sending';
  $('md-icon').textContent  = '...';
  $('md-spinner').style.display  = 'block';
  $('md-progress').style.display = 'block';
  $('md-fill').style.width  = '0%';
  $('md-title').textContent = 'Enviando para o Airflow...';
  $('md-desc').textContent  = 'Sua solicitação foi recebida. Aguarde enquanto verificamos a execução no banco de dados.';
  $('md-meta').classList.add('hidden');
  $('md-link').classList.add('hidden');
  $('md-close').classList.add('hidden');
}

function closeModal() {
  $('statusModal').classList.remove('open');
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
}

function setModalProcessing(runId) {
  $('md-title').textContent = 'Verificando execução...';
  $('md-desc').textContent  = 'A tarefa foi iniciada no Airflow. Aguardando confirmação de que os dados foram gravados no banco.';
  $('md-meta').textContent  = 'run_id: ' + runId;
  $('md-meta').classList.remove('hidden');
}

function setModalSuccess(label) {
  $('md-icon').className   = 'modal-icon success';
  $('md-icon').textContent = 'OK';
  $('md-spinner').style.display  = 'none';
  $('md-progress').style.display = 'none';
  $('md-fill').style.width = '100%';
  $('md-title').textContent = 'Dados gravados com sucesso!';
  $('md-desc').textContent  = label + ' foi registrado no banco de dados.';
  $('md-close').classList.remove('hidden');
}

function setModalFailed(runId, dagId) {
  $('md-icon').className   = 'modal-icon failed';
  $('md-icon').textContent = 'ERRO';
  $('md-spinner').style.display  = 'none';
  $('md-progress').style.display = 'none';
  $('md-title').textContent = 'Falha na execução';
  $('md-desc').textContent  = 'Ocorreu um erro ao gravar os dados. Verifique o log completo no Airflow.';
  $('md-link').href = AIRFLOW_UI + '/dags/' + dagId + '/grid';
  $('md-link').classList.remove('hidden');
  $('md-close').classList.remove('hidden');
}

function setModalTimeout(dagId) {
  $('md-icon').className   = 'modal-icon timeout';
  $('md-icon').textContent = 'TIMEOUT';
  $('md-spinner').style.display  = 'none';
  $('md-progress').style.display = 'none';
  $('md-title').textContent = 'Tempo de espera excedido';
  $('md-desc').textContent  = 'Não foi possível confirmar a execução em 30 segundos. Verifique o status no Airflow.';
  $('md-link').href = AIRFLOW_UI + '/dags/' + dagId + '/grid';
  $('md-link').classList.remove('hidden');
  $('md-close').classList.remove('hidden');
}

async function pollDagRun(dagId, runId, label, startTime, resolve) {
  const elapsed = (Date.now() - startTime) / 1000;
  $('md-fill').style.width = Math.min(90, Math.round((elapsed/30)*90)) + '%';
  if (elapsed > 30) { setModalTimeout(dagId); resolve('timeout'); return; }
  try {
    const r = await fetch('/api/v1/dags/' + dagId + '/dagRuns/' + runId, {
      headers: { 'Authorization': _sysAuth() }
    });
    if (!r.ok) { _pollTimer = setTimeout(() => pollDagRun(dagId, runId, label, startTime, resolve), 2000); return; }
    const data = await r.json();
    if (data.state === 'success') {
      $('md-fill').style.width = '100%'; setModalSuccess(label); resolve('success');
    } else if (data.state === 'failed') {
      setModalFailed(runId, dagId); resolve('failed');
    } else {
      _pollTimer = setTimeout(() => pollDagRun(dagId, runId, label, startTime, resolve), 2000);
    }
  } catch(e) {
    _pollTimer = setTimeout(() => pollDagRun(dagId, runId, label, startTime, resolve), 2000);
  }
}

async function triggerDag(dagId, conf) {
  return fetch('/api/v1/dags/' + dagId + '/dagRuns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': authHeader },
    body: JSON.stringify({ conf }),
  });
}

async function triggerAndPoll(dagId, conf, label, btnId, btnTxtId, btnTxt) {
  const btn = btnId ? $(btnId) : null;
  const btnTxtEl = btnTxtId ? $(btnTxtId) : null;
  if (btn) btn.disabled = true;
  if (btnTxtEl) btnTxtEl.textContent = 'Enviando...';
  openModal();
  try {
    const r = await triggerDag(dagId, conf);
    if (r.status === 401) { closeModal(); sair(); return; }
    if (r.status === 403) { closeModal(); showToast('Sem permissão (requer Operator ou Admin no Airflow).', true); return; }
    if (!r.ok) { closeModal(); showToast('Erro ao enviar: ' + await r.text(), true); return; }
    const data = await r.json();
    const runId = data.dag_run_id || data.run_id;
    setModalProcessing(runId);
    await new Promise(resolve => pollDagRun(dagId, runId, label, Date.now(), resolve));
  } catch(e) {
    closeModal(); showToast('Erro de conexão com o Airflow.', true);
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxtEl && btnTxt) btnTxtEl.textContent = btnTxt;
  }
}

async function _orqPost(url, body, label, btnId, btnTxtId, btnTxt) {
  const btn = btnId ? $(btnId) : null;
  const btnTxtEl = btnTxtId ? $(btnTxtId) : null;
  if (btn) btn.disabled = true;
  if (btnTxtEl) btnTxtEl.textContent = 'Enviando...';
  openModal();
  $('md-title').textContent = 'Processando...';
  $('md-desc').textContent  = 'Gravando dados no banco de dados...';
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = data.detail || data.message || ('HTTP ' + r.status);
      $('md-icon').className = 'modal-icon failed';
      $('md-icon').textContent = 'ERRO';
      $('md-spinner').style.display = 'none';
      $('md-progress').style.display = 'none';
      $('md-title').textContent = 'Erro ao salvar';
      $('md-desc').textContent  = typeof msg === 'string' ? msg : JSON.stringify(msg);
      $('md-close').classList.remove('hidden');
      return null;
    }
    setModalSuccess(label);
    return { ok: true, data };
  } catch(e) {
    $('md-icon').className = 'modal-icon failed';
    $('md-icon').textContent = 'ERRO';
    $('md-spinner').style.display = 'none';
    $('md-progress').style.display = 'none';
    $('md-title').textContent = 'Erro de conexão';
    $('md-desc').textContent  = e.message || String(e);
    $('md-close').classList.remove('hidden');
    return null;
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxtEl && btnTxt) btnTxtEl.textContent = btnTxt;
  }
}

/* ══ PIPELINE EDITOR — helpers novos ══ */

function _toggleAdvSection() {
  const s = $('adv-section');
  const icon = $('sep-adv-icon');
  if (!s) return;
  const isHidden = s.style.display === 'none';
  s.style.display = isHidden ? 'block' : 'none';
  if (icon) icon.textContent = isHidden ? '(clique para recolher)' : '(clique para expandir)';
}

function handleDepsInput(event) {
  if (event.key !== 'Enter' && event.key !== ',') return;
  event.preventDefault();
  const input = $('p-depends-on');
  if (!input) return;
  const val = input.value.trim().toUpperCase();
  if (!val) return;
  const hidden = $('p-deps-hidden');
  const existing = hidden && hidden.value ? hidden.value.split(',').filter(Boolean) : [];
  const self = $('pipeline_name') ? $('pipeline_name').value.trim() : '';
  const errEl = $('err-depends-on');
  if (val === self) { if (errEl) errEl.textContent = 'Um pipeline não pode depender de si mesmo.'; return; }
  if (existing.includes(val)) { input.value = ''; return; }
  existing.push(val);
  if (hidden) hidden.value = existing.join(',');
  _addDepChip(val);
  input.value = '';
  if (errEl) errEl.textContent = '';
}

function _addDepChip(name) {
  const wrap = $('deps-wrap');
  const input = $('p-depends-on');
  if (!wrap || !input) return;
  const chip = document.createElement('span');
  chip.className = 'chip';
  chip.setAttribute('data-dep', name);
  chip.innerHTML = _escHtml(name) + '<span style="cursor:pointer;margin-left:4px;opacity:.7" onclick="_removeDepChip(this)">×</span>';
  wrap.insertBefore(chip, input);
}

function _removeDepChip(spanEl) {
  const chip = spanEl.closest('.chip');
  if (!chip) return;
  const name = chip.getAttribute('data-dep');
  chip.remove();
  const hidden = $('p-deps-hidden');
  if (hidden) hidden.value = hidden.value.split(',').filter(v => v && v !== name).join(',');
}

function _cronOverlapCheck() {
  const cron = _scheduleUpdatePreview ? _scheduleUpdatePreview() : '';
  const pipelines = window.__pipelines || [];
  const self = $('pipeline_name') ? $('pipeline_name').value.trim() : '';
  function buildCron(p) {
    const st = p.schedule_type || 'daily';
    const h = p.schedule_hour ?? 6, m = p.schedule_minute ?? 0;
    if (st === 'hourly')  return `${m} * * * *`;
    if (st === 'daily')   return `${m} ${h} * * *`;
    if (st === 'weekly')  return `${m} ${h} * * ${p.schedule_dow ?? 1}`;
    if (st === 'monthly') return `${m} ${h} ${p.schedule_dom ?? 1} * *`;
    return `${m} ${h} * * *`;
  }
  const conflicts = pipelines.filter(p => p.pipeline_name !== self && p.active && buildCron(p) === cron);
  const hint = $('sch-overlap-hint');
  if (!hint) return;
  if (conflicts.length) {
    hint.innerHTML = '⚠ <strong>' + conflicts.length + '</strong> pipeline(s) com mesmo horário: ' +
      conflicts.map(p => '<code>' + _escHtml(p.pipeline_name) + '</code>').join(', ');
    hint.style.color = 'var(--cvp-orange,#f59e0b)';
  } else {
    hint.textContent = '';
  }
}

/* DSX drag-and-drop upload */
function _dszDragOver(e) {
  e.preventDefault();
  const dz = $('dsx-dropzone');
  if (dz) { dz.style.borderColor = 'var(--cvp-orange)'; dz.style.background = 'rgba(255,140,0,.06)'; }
}
function _dszDragLeave(e) {
  const dz = $('dsx-dropzone');
  if (dz) { dz.style.borderColor = 'var(--border)'; dz.style.background = ''; }
}
function _dszDrop(e) {
  e.preventDefault();
  _dszDragLeave(e);
  const file = e.dataTransfer?.files?.[0];
  if (file) _dszProcessFile(file);
}
function _dszFileSelected(e) {
  const file = e.target?.files?.[0];
  if (file) _dszProcessFile(file);
  if (e.target) e.target.value = '';
}
async function _dszProcessFile(file) {
  const status = $('dsx-drop-status');
  const dz = $('dsx-dropzone');
  if (!file.name.match(/\.(dsx|xml)$/i)) {
    if (status) status.textContent = '❌ Arquivo inválido. Use .dsx ou .xml';
    return;
  }
  if (file.size > 100 * 1024 * 1024) {
    if (status) status.textContent = '❌ Arquivo muito grande (máx 100 MB)';
    return;
  }
  if (status) status.textContent = '⏳ Lendo arquivo…';
  if (dz) dz.style.borderColor = 'var(--cvp-orange)';
  try {
    const text = await file.text();
    window.__dszFileContent = text;
    window.__dszFileName = file.name;
    const sizeKB = (file.size / 1024).toFixed(0);
    if (status) status.innerHTML = '✅ <strong>' + _escHtml(file.name) + '</strong> (' + sizeKB + ' KB) — pronto para importar';
    if (dz) dz.style.borderColor = 'var(--green,#22c55e)';
    showToast('Arquivo "' + file.name + '" carregado — clique em Pré-visualizar para continuar.', false);
    // Pre-fill server path field hint if empty
    const pathInput = document.querySelector('[id*="dsx"][id*="path"], [placeholder*=".dsx"]');
    if (pathInput && !pathInput.value) pathInput.value = file.name;
  } catch(err) {
    if (status) status.textContent = '❌ Erro ao ler arquivo: ' + err.message;
    if (dz) dz.style.borderColor = 'var(--red)';
  }
}

/* ══ SALVAR PIPELINE ══ */
function normalizeIdent(val) {
  // Regra: permitir somente A-Z 0-9 e underscore. Sem espaços e sem caracteres especiais.
  const v = (val || '').trim().toUpperCase();
  if (!v) return '';
  if (!IDENT_RE.test(v)) return null;
  return v;
}

function _pad2(n) { return String(n).padStart(2, '0'); }

/* ── S4: Validação de dependência circular (client-side) ───────────────── */
function _detectCircularDep(startPipeline, targetDep, pipelines) {
  // Monta mapa depends_on a partir dos pipelines carregados
  const depMap = {};
  for (const p of pipelines) depMap[p.pipeline_name] = (p.depends_on || '').trim() || null;

  const visited = new Set();
  let current = targetDep;
  let hops = 0;
  while (current && hops < 50) {
    if (current === startPipeline) return true;  // ciclo encontrado
    if (visited.has(current)) break;             // nó já visitado, sem ciclo
    visited.add(current);
    current = depMap[current] || null;
    hops++;
  }
  return false;
}

function _validateDependsOnField() {
  const val      = ($('p-depends-on') ? $('p-depends-on').value.trim() : '');
  const errEl    = $('err-depends-on');
  const self     = ($('pipeline_name') ? $('pipeline_name').value.trim() : '');
  const pipelines = window.__pipelines || [];

  if (!errEl) return true;
  errEl.textContent = '';

  if (!val) return true;

  if (val === self) {
    errEl.textContent = 'Um pipeline não pode depender de si mesmo.';
    return false;
  }

  // Verifica se o pipeline alvo existe
  const exists = pipelines.some(p => p.pipeline_name === val);
  if (!exists) {
    errEl.textContent = 'Pipeline "' + val + '" não encontrado. Verifique o nome exato.';
    return false;
  }

  // Detecção de ciclo
  if (self && _detectCircularDep(self, val, pipelines)) {
    errEl.textContent = 'Dependência circular detectada: "' + val + '" já depende (direta ou indiretamente) de "' + self + '".';
    return false;
  }

  return true;
}

function _scheduleTypeChange() {
  const type = $('sch-type') ? $('sch-type').value : 'daily';
  const timeRow = $('sch-time-row');
  const dowRow = $('sch-dow-row');
  const domRow = $('sch-dom-row');
  const customRows = $('sch-custom-rows');
  if (timeRow) timeRow.style.display = (type === 'hourly' || type === 'custom') ? 'none' : 'flex';
  if (dowRow) dowRow.style.display = type === 'weekly' ? 'flex' : 'none';
  if (domRow) domRow.style.display = (type === 'monthly' || type === 'biweekly') ? 'flex' : 'none';
  if (customRows) customRows.style.display = type === 'custom' ? '' : 'none';
  // Quinzenal: o dia escolhido vale para a 1ª quinzena (máx 15)
  const domInput = $('sch-dom'), domLabel = $('sch-dom-label'), domHint = $('sch-dom-hint');
  if (domInput) domInput.max = type === 'biweekly' ? 15 : 31;
  if (domLabel) domLabel.textContent = type === 'biweekly' ? 'Dia da 1ª quinzena' : 'Dia do mês';
  if (domHint)  domHint.style.display = type === 'biweekly' ? '' : 'none';
  _scheduleUpdatePreview();
}

function _schGetHorarios() {
  const raw = $('sch-horarios') ? $('sch-horarios').value : '';
  const out = [];
  for (const t of raw.split(',')) {
    const m = t.trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!m) continue;
    const hh = parseInt(m[1], 10), mm = parseInt(m[2], 10);
    if (hh > 23 || mm > 59) continue;
    const v = String(hh).padStart(2,'0') + ':' + String(mm).padStart(2,'0');
    if (!out.includes(v)) out.push(v);
  }
  return out.sort();
}

function _schGetDiasSemana() {
  const box = $('sch-dias-semana');
  if (!box) return [];
  return Array.from(box.querySelectorAll('input:checked')).map(c => c.value);
}

function _scheduleUpdatePreview() {
  const type = $('sch-type') ? $('sch-type').value : 'daily';
  const h = parseInt($('sch-hour') ? $('sch-hour').value : 6) || 0;
  const m = parseInt($('sch-minute') ? $('sch-minute').value : 0) || 0;
  const dow = $('sch-dow') ? $('sch-dow').value : 1;
  const dom = parseInt($('sch-dom') ? $('sch-dom').value : 1) || 1;
  let cron;
  if (type === 'custom') {
    const horarios = _schGetHorarios();
    const dias = _schGetDiasSemana();
    const diasLbl = { '1':'Seg','2':'Ter','3':'Qua','4':'Qui','5':'Sex','6':'Sáb','0':'Dom' };
    if ($('sch-preview')) {
      $('sch-preview').textContent = horarios.length
        ? horarios.length + ' execução(ões)/dia às ' + horarios.join(', ') +
          ' (' + (dias.length === 7 || dias.length === 0 ? 'todos os dias' : dias.map(d => diasLbl[d]).join(', ')) + ')'
        : 'Informe ao menos um horário (HH:MM).';
    }
    const hint = $('sch-horarios-hint');
    if (hint) {
      const raw = ($('sch-horarios') ? $('sch-horarios').value : '').split(',').map(s=>s.trim()).filter(Boolean);
      const invalid = raw.filter(t => !/^(\d{1,2}):(\d{2})$/.test(t) || parseInt(t) > 23 || parseInt(t.split(':')[1]) > 59);
      hint.textContent = invalid.length
        ? '⚠ Horário(s) inválido(s): ' + invalid.join(', ') + ' — use o formato HH:MM.'
        : 'Separe os horários por vírgula (formato HH:MM).';
      hint.style.color = invalid.length ? 'var(--red)' : '';
    }
    try { _cronOverlapCheck(); } catch(_) {}
    return null;
  }
  if (type === 'hourly') cron = `${m} * * * *`;
  else if (type === 'daily') cron = `${m} ${h} * * *`;
  else if (type === 'weekly') cron = `${m} ${h} * * ${dow}`;
  else if (type === 'biweekly') cron = `${m} ${h} ${dom},${dom + 15} * *`;
  else if (type === 'monthly') cron = `${m} ${h} ${dom} * *`;
  else cron = `${m} ${h} * * *`;
  if ($('sch-preview')) $('sch-preview').textContent = type === 'biweekly'
    ? `cron: ${cron} — dias ${dom} e ${dom + 15} de cada mês`
    : 'cron: ' + cron;
  try { _cronOverlapCheck(); } catch(_) {}
  return cron;
}

function _scheduleGetConf() {
  const type = $('sch-type') ? $('sch-type').value : 'daily';
  if (type === 'custom') {
    const horarios = _schGetHorarios();
    const dias = _schGetDiasSemana();
    const first = horarios[0] || '06:00';
    return {
      schedule_type: 'custom',
      schedule_hour: parseInt(first.split(':')[0], 10),
      schedule_minute: parseInt(first.split(':')[1], 10),
      schedule_dow: null,
      schedule_dom: null,
      horarios_especificos: horarios.join(','),
      dias_semana: (dias.length && dias.length < 7) ? dias.join(',') : null,
    };
  }
  const h = parseInt($('sch-hour') ? $('sch-hour').value : 6);
  const m = parseInt($('sch-minute') ? $('sch-minute').value : 0);
  const dow = type === 'weekly' ? parseInt($('sch-dow') ? $('sch-dow').value : 1) : null;
  const dom = (type === 'monthly' || type === 'biweekly') ? parseInt($('sch-dom') ? $('sch-dom').value : 1) : null;
  return {
    schedule_type: type,
    schedule_hour: isNaN(h) ? null : h,
    schedule_minute: isNaN(m) ? null : m,
    schedule_dow: isNaN(dow) ? null : dow,
    schedule_dom: isNaN(dom) ? null : dom,
    horarios_especificos: null,
    dias_semana: null,
  };
}

function _scheduleSetFromRecord(rec) {
  // Pré-popula o builder ao editar um pipeline existente
  if (!rec) return;
  const type = rec.schedule_type || 'daily';
  if ($('sch-type')) $('sch-type').value = type;

  // fallback: se não houver schedule_hour/minute, tenta parse do scheduled_time (HH:MM:SS)
  let hh = rec.schedule_hour;
  let mm = rec.schedule_minute;
  if ((hh === undefined || hh === null || mm === undefined || mm === null) && rec.scheduled_time) {
    const st = String(rec.scheduled_time);
    const parts = st.split(':');
    if (parts.length >= 2) {
      hh = parseInt(parts[0], 10);
      mm = parseInt(parts[1], 10);
    }
  }

  if ($('sch-hour')) $('sch-hour').value = (hh ?? 6);
  if ($('sch-minute')) $('sch-minute').value = (mm ?? 0);
  if ($('sch-dow')) $('sch-dow').value = (rec.schedule_dow ?? 1);
  if ($('sch-dom')) $('sch-dom').value = (rec.schedule_dom ?? 1);
  // Horários específicos (migration 018)
  if ($('sch-horarios')) $('sch-horarios').value = rec.horarios_especificos || '';
  if ($('sch-dias-semana')) {
    const dias = (rec.dias_semana || '').split(',').map(s => s.trim()).filter(Boolean);
    const def = ['1','2','3','4','5'];  // padrão seg-sex quando não configurado
    const sel = dias.length ? dias : def;
    $('sch-dias-semana').querySelectorAll('input').forEach(c => { c.checked = sel.includes(c.value); });
  }
  if (rec.horarios_especificos && $('sch-type')) $('sch-type').value = 'custom';
  _scheduleTypeChange();
}

/* ── Fase 4: calendários no wizard ──────────────────────────────── */
async function loadCalendarioOptions(selected) {
  const sel = $('sch-calendario');
  if (!sel) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/agenda/calendarios');
    const data = r.ok ? await r.json() : { calendarios: [] };
    const cals = data.calendarios || [];
    sel.innerHTML = '<option value="">— nenhum —</option>' +
      cals.map(c => '<option value="' + _escHtml(c.calendario_nome) + '">' +
        _escHtml(c.calendario_nome) + ' (' + c.datas + ' data(s))</option>').join('');
  } catch(_) {
    sel.innerHTML = '<option value="">— nenhum —</option>';
  }
  sel.value = selected || '';
  if (sel.value !== (selected || '')) sel.value = ''; // calendário removido do banco
}

/* ── S4: Validação de dependências (multi-dep) ──────────────────── */
function _detectCircularDep(startPipeline, targetDep, pipelines) {
  const depMap = {};
  for (const p of pipelines) depMap[p.pipeline_name] = (p.depends_on || '').trim() || null;
  const visited = new Set();
  let current = targetDep;
  let hops = 0;
  while (current && hops < 50) {
    if (current === startPipeline) return true;
    if (visited.has(current)) break;
    visited.add(current);
    current = depMap[current] || null;
    hops++;
  }
  return false;
}

function _validateDependsOnField() {
  // Use multi-dep hidden field if available, else fall back to text input
  const hiddenEl = $('p-deps-hidden');
  const inputEl  = $('p-depends-on');
  const errEl    = $('err-depends-on');
  const self     = ($('pipeline_name') ? $('pipeline_name').value.trim() : '');
  const pipelines = window.__pipelines || [];

  if (!errEl) return true;
  errEl.textContent = '';

  const depsRaw = (hiddenEl && hiddenEl.value) ? hiddenEl.value : (inputEl ? inputEl.value.trim() : '');
  const deps = depsRaw ? depsRaw.split(',').map(d => d.trim().toUpperCase()).filter(Boolean) : [];

  if (!deps.length) return true;

  for (const val of deps) {
    if (val === self) {
      errEl.textContent = 'Um pipeline não pode depender de si mesmo.';
      return false;
    }
    const exists = pipelines.some(p => p.pipeline_name === val);
    if (!exists) {
      errEl.textContent = 'Pipeline "' + val + '" não encontrado. Verifique o nome exato.';
      return false;
    }
    if (self && _detectCircularDep(self, val, pipelines)) {
      errEl.textContent = 'Dependência circular detectada: "' + val + '" já depende (direta ou indiretamente) de "' + self + '".';
      return false;
    }
  }
  return true;
}

async function registrarPipeline() {
  // Validação antecipada (mostra erros no próprio campo)
  const okPipeline = validateIdentField('pipeline_name', 'err-pipeline', 'Nome do pipeline', true);
  const okDomain   = validateIdentField('p-domain', 'err-domain', 'Domínio', true);

  // Tags: validar todos os chips já adicionados (p-tags)
  const tagsRaw = ($('p-tags') ? $('p-tags').value : '').trim();
  if (tagsRaw) {
    const parts = tagsRaw.split(',').map(s => s.trim()).filter(Boolean);
    for (const t of parts) {
      if (!IDENT_RE.test(String(t).toUpperCase())) {
        setFieldInvalidById('tag-input', 'err-tags', 'Tag inválida: "' + t + '". Use apenas letras, números e "_" (sem espaços).');
        break;
      }
    }
  }
  const okTags = !$('tag-input') ? true : !($('tag-input').closest('.field')?.classList.contains('invalid'));

  if (!okPipeline || !okDomain || !okTags) {
    const m = $('msg-pipeline');
    if (m) { m.textContent = ''; m.className = 'msg'; }
    // foca no primeiro campo inválido
    if (!okPipeline) { try { $('pipeline_name').focus(); } catch(_) {} return; }
    if (!okDomain)   { try { $('p-domain').focus(); } catch(_) {} return; }
    try { $('tag-input')?.focus(); } catch(_) {}
    return;
  }

  const pipelineIn = $('pipeline_name').value;
  const project  = $('p-project').value.trim();
  const domainIn = $('p-domain').value;
  const tagsIn   = $('p-tags').value;
  const m        = $('msg-pipeline');
  m.className    = 'msg';

  const pipeline = normalizeIdent(pipelineIn);
  if (!pipeline) { m.textContent = 'Informe o nome do pipeline'; m.className = 'msg erro'; return; }
  if (pipeline === null) { m.textContent = 'Nome do pipeline inválido. Use apenas letras, números e "_" (sem espaços).'; m.className = 'msg erro'; return; }

  if (!project)  { m.textContent = 'Selecione o projeto'; m.className = 'msg erro'; return; }

  // Descrição obrigatória
  const descricaoEl = $('p-descricao');
  if (!descricaoEl || !descricaoEl.value.trim()) {
    if (descricaoEl) setFieldInvalidById('p-descricao', 'err-descricao', 'Descrição / Objetivo é obrigatório.');
    m.textContent = 'Descrição / Objetivo é obrigatório.'; m.className = 'msg erro';
    if ($('adv-section')) { $('adv-section').style.display = 'block'; if ($('sep-adv-icon')) $('sep-adv-icon').textContent = '(clique para recolher)'; }
    try { descricaoEl && descricaoEl.focus(); } catch(_) {}
    return;
  }

  // Ambiente obrigatório
  const ambienteEl = $('p-ambiente');
  if (!ambienteEl || !ambienteEl.value.trim()) {
    if (ambienteEl) setFieldInvalidById('p-ambiente', 'err-ambiente', 'Ambiente é obrigatório.');
    m.textContent = 'Ambiente é obrigatório.'; m.className = 'msg erro';
    if ($('adv-section')) { $('adv-section').style.display = 'block'; if ($('sep-adv-icon')) $('sep-adv-icon').textContent = '(clique para recolher)'; }
    try { ambienteEl && ambienteEl.focus(); } catch(_) {}
    return;
  }

  const domain = normalizeIdent(domainIn);
  if (!domain) { m.textContent = 'Informe o domínio (use "_" no lugar de espaços)'; m.className = 'msg erro'; return; }
  if (domain === null) { m.textContent = 'Domínio inválido. Use apenas letras, números e "_" (sem espaços).'; m.className = 'msg erro'; return; }

  // Tags: podem ser vazias, mas quando houver, validar e padronizar em caixa alta.
  const tags = (tagsIn || '').trim();
  if (tags) {
    const parts = tags.split(',').map(s => s.trim()).filter(Boolean);
    for (const t of parts) {
      const nt = normalizeIdent(t);
      if (nt === null) { m.textContent = 'Tag inválida: "' + t + '". Use apenas letras, números e "_" (sem espaços).'; m.className = 'msg erro'; return; }
    }
  }

  // Reflete padronização no formulário (exibição sempre em caixa alta)
  $('pipeline_name').value = pipeline;
  $('p-domain').value = domain;
  $('p-tags').value = (tags ? tags.split(',').map(s => normalizeIdent(s)).filter(Boolean).join(',') : '');

  // Agendamento (Fase 3): builder avançado
  const schedConf = _scheduleGetConf();
  const cron = _scheduleUpdatePreview();

  // Valida ranges básicos
  const stype = schedConf.schedule_type || 'daily';
  const sh = (schedConf.schedule_hour ?? 0);
  const sm = (schedConf.schedule_minute ?? 0);
  if (stype === 'custom' && !(schedConf.horarios_especificos || '').length) {
    m.textContent = 'Informe ao menos um horário de execução (formato HH:MM).';
    m.className = 'msg erro';
    _wizShowStep(2);
    try { $('sch-horarios').focus(); } catch(_) {}
    return;
  }
  if (stype !== 'hourly') {
    if (sh < 0 || sh > 23) { m.textContent = 'Hora inválida (0-23)'; m.className = 'msg erro'; return; }
  }
  if (sm < 0 || sm > 59) { m.textContent = 'Minuto inválido (0-59)'; m.className = 'msg erro'; return; }
  if (stype === 'weekly' && (schedConf.schedule_dow < 0 || schedConf.schedule_dow > 6)) { m.textContent = 'Dia da semana inválido'; m.className = 'msg erro'; return; }
  if (stype === 'monthly' && (schedConf.schedule_dom < 1 || schedConf.schedule_dom > 31)) { m.textContent = 'Dia do mês inválido'; m.className = 'msg erro'; return; }
  if (stype === 'biweekly' && (schedConf.schedule_dom < 1 || schedConf.schedule_dom > 15)) { m.textContent = 'Quinzenal: o dia da 1ª quinzena deve estar entre 1 e 15.'; m.className = 'msg erro'; return; }

  // scheduled_time (legado) — mantém compatibilidade
  // hourly: cron usa somente minuto; salvamos scheduled_time como 00:MM:00
  const scheduled_time = _pad2(stype === 'hourly' ? 0 : sh) + ':' + _pad2(sm) + ':00';

  const dependsOnLegacy = ($('p-depends-on') ? $('p-depends-on').value.trim().toUpperCase() : '') || null;
  const changedBy    = window.__currentUser || 'system';

  // Validação client-side de dependência circular antes de enviar ao backend
  if (!_validateDependsOnField()) {
    m.textContent = 'Corrija o campo "Depende de" antes de salvar.';
    m.className = 'msg erro';
    return;
  }

  // Fase 4: disparo por dependência exige ao menos 1 pipeline em "Depende de"
  if ($('sch-trigger-dep') && $('sch-trigger-dep').checked) {
    const depsVal = ($('p-deps-hidden') ? $('p-deps-hidden').value.trim() : '') ||
                    ($('p-depends-on') ? $('p-depends-on').value.trim() : '');
    if (!depsVal) {
      m.textContent = 'Disparo por dependência exige ao menos 1 pipeline em "Depende de".';
      m.className = 'msg erro';
      return;
    }
  }

  await _orqPost(
    ORQUESTRA_API + '/pipelines/register',
    {
      pipeline_name: pipeline, scheduled_time: scheduled_time,
      active: pipelineStatus,
      envia_msg_inicio: $('tog-inicio').checked ? 1 : 0,
      envia_msg_fim:    $('tog-fim').checked    ? 1 : 0,
      envia_msg_erro:   $('tog-erro').checked   ? 1 : 0,
      project_name: project, domain: domain, tags: tags,
      depends_on:          $('p-deps-hidden') ? ($('p-deps-hidden').value.trim() || null) : dependsOnLegacy,
      dag_start_date:      ($('p-dag-start-date') ? $('p-dag-start-date').value.trim() : '') || null,
      changed_by:          changedBy,
      descricao:           ($('p-descricao') ? $('p-descricao').value.trim() : '') || null,
      runbook_md:          ($('p-runbook') ? $('p-runbook').value.trim() : '') || null,
      criticidade:         $('p-criticidade') ? $('p-criticidade').value : 'Media',
      ambiente:            $('p-ambiente') ? $('p-ambiente').value : 'PROD',
      sla_minutos:         $('p-sla-minutos') ? (parseInt($('p-sla-minutos').value) || null) : null,
      max_active_runs:     $('p-max-active-runs') ? (parseInt($('p-max-active-runs').value) || 1) : 1,
      retries_count:       $('p-retries') ? (parseInt($('p-retries').value) ?? 1) : 1,
      retry_delay_seconds: $('p-retry-delay') ? (parseInt($('p-retry-delay').value) || 300) : 300,
      pool_name:           ($('p-pool') ? $('p-pool').value.trim() : '') || null,
      calendario_nome:     ($('sch-calendario') ? $('sch-calendario').value : '') || null,
      somente_dias_uteis:  ($('sch-dias-uteis') && $('sch-dias-uteis').checked) ? 1 : 0,
      trigger_por_dependencia: ($('sch-trigger-dep') && $('sch-trigger-dep').checked) ? 1 : 0,
      ...schedConf,
    },
    'Pipeline "' + pipeline + '"',
    'btn-save-pipeline', 'save_pipeline_txt', 'Salvar'
  );

  // Salva jobs + lineage do wizard (passos 5 e 6)
  const wizJobs = _wizGetJobs();
  if (wizJobs.length) {
    const lg = _wizGetLineage();
    const mapObjs = arr => (arr || []).map(o => ({ object_type: o.type || 'Tabela', object_name: o.name }));
    const jobsPayload = {
      pipeline_name: pipeline,
      require_lineage: false,
      jobs: wizJobs.map(j => ({
        job_name: j.name,
        execution_order: j.order,
        job_type: (j.type || 'datastage').toLowerCase(),
        job_command: j.command || null,
        origens:  mapObjs((lg[j.name] || {}).origens),
        destinos: mapObjs((lg[j.name] || {}).destinos),
      })),
    };
    try {
      await _orqPost(ORQUESTRA_API + '/pipelines/jobs/register', jobsPayload,
        wizJobs.length + ' job(s) do pipeline "' + pipeline + '"', null, null, null);
    } catch(e) { console.warn('[WIZ] Falha ao salvar jobs:', e); }
  }

  $('pipeline_name').value = '';
  _scheduleSetFromRecord({ schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0, schedule_dow: 1, schedule_dom: 1 });
  $('p-project').value = ''; $('p-domain').value = '';
  $('p-tags').value = ''; $('tags-wrap').querySelectorAll('.chip').forEach(c => c.remove());
  if ($('p-depends-on'))     $('p-depends-on').value = '';
  if ($('p-deps-hidden'))    $('p-deps-hidden').value = '';
  if ($('deps-wrap'))        $('deps-wrap').querySelectorAll('.chip').forEach(c => c.remove());
  if ($('p-dag-start-date')) $('p-dag-start-date').value = '';
  if ($('p-descricao'))      $('p-descricao').value = '';
  if ($('p-runbook'))        $('p-runbook').value = '';
  if ($('p-criticidade'))    $('p-criticidade').value = 'Media';
  if ($('p-ambiente'))       $('p-ambiente').value = 'PROD';
  if ($('p-sla-minutos'))    $('p-sla-minutos').value = '';
  if ($('p-max-active-runs')) $('p-max-active-runs').value = 1;
  if ($('p-retries'))        $('p-retries').value = 1;
  if ($('p-retry-delay'))    $('p-retry-delay').value = 300;
  if ($('p-pool'))           $('p-pool').value = '';
  if ($('adv-section'))      { $('adv-section').style.display = 'none'; if ($('sep-adv-icon')) $('sep-adv-icon').textContent = '(clique para expandir)'; }
  setStatus(1);
  ['tog-inicio','tog-fim','tog-erro'].forEach(id => { $(id).checked = true; syncToggle('lbl-'+id.replace('tog-',''), $(id)); });
  closePipelineEditor();
  try { loadQuery(0); } catch(e) {}
  // F3/F2 — só para pipelines existentes (não novos)
  if (!_pipelineIsNew) {
    try { await _toggleDagAirflow(pipeline, pipelineStatus); } catch(e) {}
    try { _offerRegenDag(pipeline); } catch(e) {}
  }
}

/* ══ SALVAR JOBS ══ */
async function registrarJobs() {
  const pipeline = $('job_pipeline_name').value.trim();
  if (!pipeline) {
    const m = $('msg-job'); m.textContent = 'Informe o nome do pipeline'; m.className = 'msg erro'; return;
  }
  let jobs = [];
  if (jobMode === 'bulk') {
    const raw = $('bulk-jobs').value.trim();
    if (!raw) { const m = $('msg-job'); m.textContent = 'Cole ao menos um job'; m.className = 'msg erro'; return; }
    raw.split('\n').forEach(line => {
      const p = line.trim().split(',').map(s => s.trim());
      if (p.length >= 2 && p[0] && !isNaN(parseInt(p[1])))
        jobs.push({ job_name:p[0], execution_order:parseInt(p[1]), job_type:p[2]||'datastage', job_command:p[3]||null, origens:[], destinos:[] });
    });
    if (!jobs.length) { const m = $('msg-job'); m.textContent = 'Nenhuma linha válida. Formato: nome,ordem,tipo,comando'; m.className = 'msg erro'; return; }
  } else {
    jobs = collectJobRows();
    if (!jobs.length) { const m = $('msg-job'); m.textContent = 'Preencha ao menos um job com nome e ordem'; m.className = 'msg erro'; return; }
    for (const j of jobs) {
      if (!j.origens || j.origens.length === 0) {
        const m = $('msg-job'); m.textContent = 'Job "' + j.job_name + '": clique em Lineage e informe 1 origem'; m.className = 'msg erro'; return;
      }
      if (!j.destinos || j.destinos.length === 0) {
        const m = $('msg-job'); m.textContent = 'Job "' + j.job_name + '": clique em Lineage e informe 1 destino'; m.className = 'msg erro'; return;
      }
    }
  }
  await _orqPost(
    ORQUESTRA_API + '/pipelines/jobs/register',
    { pipeline_name: pipeline, jobs },
    jobs.length + ' job(s) do pipeline "' + pipeline + '"',
    'btn-save-job', 'save_job_txt', 'Salvar Jobs'
  );
  $('job_pipeline_name').value = '';
  jobsBdata = []; jbLineId = 0; addJobLineB();
  $('bulk-jobs').value = '';
}

/* ══ CHIPS DE TAGS ══ */
function handleTagInput(e) {
  if (e.key !== 'Enter' && e.key !== ',') return;
  e.preventDefault();
  const input = $('tag-input');
  const val = input.value.trim().replace(/,/g,'');
  if (!val) return;
  addChip(val);
  input.value = '';
}
function addChip(val) {
  const norm = normalizeIdent(val);
  if (!norm) return;
  if (norm === null) { setFieldInvalidById('tag-input', 'err-tags', 'Tag inválida. Use apenas letras, números e "_" (sem espaços).'); return; }
  const existing = [...$('tags-wrap').querySelectorAll('.chip')].map(c => c.dataset.val);
  if (existing.includes(norm)) return;
  const chip = document.createElement('span');
  chip.className = 'chip'; chip.dataset.val = norm;
  chip.innerHTML = norm + '<button class="chip-rm" onclick="removeChip(this)" title="Remover">×</button>';
  $('tags-wrap').insertBefore(chip, $('tag-input'));
  syncTags();
  clearFieldInvalidById('tag-input', 'err-tags');
}
function removeChip(btn) { btn.parentElement.remove(); syncTags(); }
function syncTags() {
  const vals = [...$('tags-wrap').querySelectorAll('.chip')].map(c => c.dataset.val);
  $('p-tags').value = vals.join(',');
}

/* ══ ENTER no login ══ */
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !$('loginScreen').classList.contains('hidden')) entrar();
});


/* ══ CONSULTA DE PIPELINES ══ */
let queryState = { offset: 0, limit: 20, total: 0, pages: 0 };

function normalizeXcomValue(x) {
  // Airflow API normalmente retorna: { key: "return_value", value: <...> }
  if (x && typeof x === 'object' && x.value !== undefined && x.data === undefined) {
    x = x.value;
  }

  // Às vezes o "value" chega como string (JSON stringificado)
  if (typeof x === 'string') {
    const s = x.trim();
    // tenta JSON puro primeiro
    if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
      try { x = JSON.parse(s); } catch(e) {}
    }

    // fallback: alguns ambientes salvam repr de dict python (aspas simples / True/False/None)
    if (typeof x === 'string') {
      const py = s
        .replace(/\bNone\b/g, 'null')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false');
      // tenta converter aspas simples para duplas quando parece dict/list
      if ((py.startsWith('{') && py.endsWith('}')) || (py.startsWith('[') && py.endsWith(']'))) {
        try { x = JSON.parse(py.replace(/'/g, '"')); } catch(e) {}
      }
    }
  }

  // Se "data" veio como string, tenta parsear
  if (x && typeof x === 'object' && typeof x.data === 'string') {
    try { x.data = JSON.parse(x.data); } catch(e) {}
  }

  return x;
}

/* ══ CONSULTA DE JOBS ══ */
let jobQueryState = { offset: 0, limit: 50, total: 0, pages: 0 };
let jobOrderDirty = false;

async function loadJobsQuery(offset) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const pipeline = $('job_pipeline_name') ? $('job_pipeline_name').value.trim() : '';
  const name = $('jq-name') ? $('jq-name').value.trim() : '';
  const type = $('jq-type') ? $('jq-type').value : '';
  const qs = $('job-query-status');
  const btn = $('btn-jq');
  const btnTxt = $('btn-jq-txt');

  if (!pipeline) {
    if (qs) qs.textContent = 'Informe o pipeline para consultar os jobs.';
    return;
  }

  if (offset !== undefined) jobQueryState.offset = offset;
  const conf = { offset: jobQueryState.offset, limit: jobQueryState.limit, filter_pipeline: pipeline };
  if (name) conf.filter_job_name = name;
  if (type) conf.filter_job_type = type;

  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = 'Buscando...';
  if (qs) qs.textContent = 'Consultando API...';

  try {
    const params = new URLSearchParams();
    params.set('offset', conf.offset || 0);
    params.set('limit',  conf.limit  || 50);
    params.set('filter_pipeline', conf.filter_pipeline);
    if (conf.filter_job_name) params.set('filter_job_name', conf.filter_job_name);
    if (conf.filter_job_type) params.set('filter_job_type', conf.filter_job_type);

    if (qs) qs.textContent = 'Carregando dados...';
    const r = await fetch(ORQUESTRA_API + '/jobs?' + params.toString());
    if (r.status === 401) { sair(); return; }
    if (!r.ok) { if (qs) qs.textContent = 'Erro API: ' + r.status; return; }

    const payload = await r.json();
    try { window.__lastJobsPayload = payload; } catch(e) {}
    renderJobsTable(payload);
  } catch (err) {
    if (qs) qs.textContent = 'Erro de conexão: ' + err.message;
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Buscar jobs';
  }
}

async function pollJobsRun(runId) {
  const start = Date.now();
  const timeoutMs = 120000;
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch('/api/v1/dags/etl_pipeline_job_query/dagRuns/' + runId, { headers: { 'Authorization': _sysAuth() } });
      if (r.ok) {
        const d = await r.json();
        if (d.state === 'success') return 'success';
        if (d.state === 'failed') { if ($('job-query-status')) $('job-query-status').textContent = 'A execução falhou no Airflow. Verifique o log do DAG.'; return 'failed'; }
      }
    } catch(e) {}
    await new Promise(res => setTimeout(res, 2000));
  }
  if ($('job-query-status')) $('job-query-status').textContent = 'A execução está demorando (timeout de 2 min). Você pode aguardar e clicar em Buscar jobs novamente.';
  return 'timeout';
}

function renderJobsTable(payload) {
  const area = $('job-query-table-area');
  if (!area) return;
  payload = normalizeXcomValue(payload);
  if (!payload || !payload.data || !payload.data.length) {
    const act = $('job-query-actions');
    if (act) act.classList.add('hidden');
    jobOrderDirty = false;
    const btnSave = $('btn-save-order'); if (btnSave) btnSave.disabled = true;
    area.innerHTML =
      '<div class="empty-state">' +
        '<span class="es-icon">⬡</span>' +
        '<p class="es-title">Nenhum job encontrado</p>' +
        '<p class="es-sub">Ajuste os filtros ou cadastre um job para este pipeline.</p>' +
        '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:1rem">' +
          '<button class="btn btn-outline btn-sm" onclick="openJobCreateModal(\'single\')">+ Adicionar job</button>' +
          '<button class="btn-ghost btn-sm" onclick="openJobCreateModal(\'bulk\')">Colar lista</button>' +
        '</div>' +
      '</div>';
    if ($('job-query-status')) $('job-query-status').textContent = 'Nenhum resultado';
    return;
  }
  const { total, offset, limit, pages, table } = payload;
  const st_j = window.__sortState['jobs'];
  const data  = st_j ? _sortData(payload.data, st_j.col, st_j.dir) : payload.data;
  try { window.__jobs = payload.data; window.__lastJobsPayload = payload; } catch(e) {}
  const act = $('job-query-actions');
  if (act) act.classList.remove('hidden');
  jobOrderDirty = false;
  const btnSave = $('btn-save-order'); if (btnSave) btnSave.disabled = true;
  jobQueryState.total = total; jobQueryState.pages = pages; jobQueryState.offset = offset;
  const from = offset + 1, to = Math.min(offset + limit, total);
  if ($('job-query-status')) $('job-query-status').textContent = 'Exibindo ' + from + '–' + to + ' de ' + total + ' job(s)' + (table ? ' · fonte: ' + table : '');

  const rows = data.map((j, i) =>
    '<tr>' +
    '<td style="font-weight:500;white-space:nowrap">' + (j.pipeline_name || '—') + '</td>' +
    '<td style="font-weight:500;white-space:nowrap">' +
      (j.job_name || '—') +
      '<button class="btn-copy-inline" onclick="_copyText(\'' + _escHtml(j.job_name || '') + '\',this)" title="Copiar nome do job" style="margin-left:5px;background:none;border:none;cursor:pointer;color:var(--muted);padding:0 2px;vertical-align:middle;font-size:13px;opacity:.55;transition:opacity .15s" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=.55">⎘</button>' +
    '</td>' +
    '<td style="text-align:center">' +
      '<input class="inline-order" type="number" min="1" value="' + (j.execution_order ?? '') + '" ' +
        'oninput="onJobOrderChange(' + i + ', this.value)" />' +
    '</td>' +
    '<td><span class="tag-pill">' + (j.job_type || '—') + '</span></td>' +
    '<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + (j.job_command || '') + '">' + (j.job_command || '—') + (j.job_type === 'shell' && j.ssh_conn_id ? ' <span class="tag-pill" style="font-size:10px;margin-left:4px">' + _escHtml(j.ssh_conn_id) + '</span>' : '') + '</td>' +
    '<td>' + (j.job_type === 'datastage' && j.verbose_log ? '<span class="tag-pill" style="background:rgba(245,158,11,.15);color:#f59e0b;font-size:10px" title="Log detalhado ativo — registra progresso dos jobs filhos a cada 5 min">🔍 detalhado</span>' : '<span style="color:#3d4152;font-size:12px">—</span>') + '</td>' +
    '<td class="col-actions">' +
      '<div class="row-actions">' +
        (!window.__isViewer ? '<button class="act-btn act-edit" onclick="openJobEdit(' + i + ')" title="Editar job">' + ICONS.edit + '</button>' : '') +
        '<button class="act-btn act-lineage" onclick="openJobLineageFromTable(' + i + ')" title="Ver lineage">' + ICONS.graph + '</button>' +
      '</div>' +
    '</td>' +
    '</tr>'
  ).join('');

  const _jHdr = (label, col) =>
    '<th style="cursor:pointer;user-select:none;white-space:nowrap" ' +
    'data-sort-table="jobs" data-sort-col="' + col + '">' +
    label + _sortIcon('jobs', col) + '</th>';

  area.innerHTML =
    '<div class="query-table-wrap"><table class="query-table"><thead><tr>' +
    _jHdr('Pipeline','pipeline_name') + _jHdr('Job','job_name') +
    _jHdr('Ordem','execution_order') + _jHdr('Tipo','job_type') +
    '<th>Comando</th><th>Log</th><th class="col-actions">Ações</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table></div>' +
    (pages > 1 ? renderJobsPagination(offset, limit, total, pages) : '');
}

function renderJobsPagination(offset, limit, total, pages) {
  const cur = Math.floor(offset / limit);
  let btns = '<button class="pag-btn" ' + (cur > 0 ? '' : 'disabled') + ' onclick="loadJobsQuery(' + ((cur-1)*limit) + ')">‹</button>';
  for (let i = 0; i < Math.min(pages, 7); i++)
    btns += '<button class="pag-btn ' + (i === cur ? 'active' : '') + '" onclick="loadJobsQuery(' + (i*limit) + ')">' + (i+1) + '</button>';
  if (pages > 7) btns += '<span style="padding:.3rem .4rem;font-size:12px;color:var(--muted)">…' + pages + '</span>';
  btns += '<button class="pag-btn" ' + (cur < pages-1 ? '' : 'disabled') + ' onclick="loadJobsQuery(' + ((cur+1)*limit) + ')">›</button>';
  return '<div class="pagination"><span>' + total + ' registros · página ' + (cur+1) + ' de ' + pages + '</span><div class="pag-btns">' + btns + '</div></div>';
}

function clearJobsQuery() {
  if ($('jq-name')) $('jq-name').value = '';
  if ($('jq-type')) $('jq-type').value = '';
  jobQueryState = { offset: 0, limit: 50, total: 0, pages: 0 };
  const area = $('job-query-table-area');
  if (area) area.innerHTML =
    '<div class="empty-state">' +
      '<span class="es-icon">⬡</span>' +
      '<p class="es-title">Nenhum job carregado</p>' +
      '<p class="es-sub">Informe o pipeline e clique em Buscar jobs.</p>' +
    '</div>';
  if ($('job-query-status')) $('job-query-status').textContent = '';
  const act = $('job-query-actions');
  if (act) act.classList.add('hidden');
  jobOrderDirty = false;
  const btnSave = $('btn-save-order'); if (btnSave) btnSave.disabled = true;
}

function onJobOrderChange(idx, val) {
  const list = window.__jobs || [];
  const j = list[idx];
  if (!j) return;
  const n = parseInt((val || '').toString().trim(), 10);
  j.execution_order = isNaN(n) ? null : n;
  jobOrderDirty = true;
  const btnSave = $('btn-save-order');
  if (btnSave) btnSave.disabled = false;
}

async function saveJobsOrder() {
  const pipeline = $('job_pipeline_name') ? $('job_pipeline_name').value.trim() : '';
  const list = window.__jobs || [];
  const btnSave = $('btn-save-order');
  const qs = $('job-query-status');

  if (!pipeline) { if (qs) qs.textContent = 'Informe o pipeline.'; return; }
  if (!jobOrderDirty) { if (qs) qs.textContent = 'Nenhuma alteração de ordem para salvar.'; return; }
  if (!list.length) { if (qs) qs.textContent = 'Nenhum job carregado.'; return; }

  for (const j of list) {
    if (!j.job_name) { if (qs) qs.textContent = 'Existe um job sem nome (não é possível salvar).'; return; }
    if (!j.execution_order || isNaN(j.execution_order) || j.execution_order < 1) {
      if (qs) qs.textContent = 'Ordem inválida no job "' + j.job_name + '".';
      return;
    }
  }

  const seen = new Set();
  let hasDup = false;
  for (const j of list) {
    if (seen.has(j.execution_order)) { hasDup = true; break; }
    seen.add(j.execution_order);
  }
  if (hasDup) {
    const ok = await showConfirm('Existem ordens repetidas nos jobs. Deseja salvar mesmo assim?', 'Ordens duplicadas');
    if (!ok) return;
  }

  // Reorder seguro: envia SOMENTE {job_name, execution_order}
  // (não toca em lineage / não exige origens/destinos)
  const jobs = list.map(j => ({
    job_name: j.job_name,
    execution_order: j.execution_order,
  }));

  const ok = await showConfirm(
    'Salvar nova ordem de execução para ' + jobs.length + ' job(s) do pipeline "' + pipeline + '"?',
    'Salvar ordem'
  );
  if (!ok) return;

  if (btnSave) btnSave.disabled = true;
  await triggerAndPoll(
    'etl_pipeline_job_reorder',
    { pipeline_name: pipeline, jobs },
    'Atualizar ordem de execução (pipeline "' + pipeline + '")',
    null, null, null
  );
  jobOrderDirty = false;
  try { loadJobsQuery(jobQueryState.offset); } catch(e) {}
}

/* ══ CADASTRO DE JOBS (MODAL) ══ */
let _jobCreateMode = 'single'; // 'single' | 'bulk'

function openJobCreateModal(mode) {
  const pipeline = $('job_pipeline_name') ? $('job_pipeline_name').value.trim() : '';
  if (!pipeline) {
    if ($('job-query-status')) $('job-query-status').textContent = 'Informe o pipeline antes de adicionar jobs.';
    return;
  }
  _jobCreateMode = mode === 'bulk' ? 'bulk' : 'single';

  // título
  const ttl = $('jcm-title');
  if (ttl) ttl.textContent = _jobCreateMode === 'bulk' ? 'Colar lista de jobs' : 'Etapa 1/2 — Dados do job';

  // pipeline (fixo)
  $('jcm-pipeline').value = pipeline;

  // reset mensagens
  $('jobCreateMsg').textContent = '';
  $('jobCreateMsg').className = 'msg';

  // alterna views
  $('jcm-single').classList.toggle('hidden', _jobCreateMode !== 'single');
  $('jcm-bulk').classList.toggle('hidden', _jobCreateMode !== 'bulk');

  // reset campos
  if (_jobCreateMode === 'single') {
    $('jcm-name').value = '';
    $('jcm-order').value = '';
    $('jcm-type').value = '';
    $('jcm-cmd').value = '';
    try { $('jcm-name').focus(); } catch(e) {}
  } else {
    $('jcm-bulk-text').value = '';
    try { $('jcm-bulk-text').focus(); } catch(e) {}
  }

  $('jobCreateModal').classList.add('open');
}

function closeJobCreateModal() {
  $('jobCreateModal').classList.remove('open');
}

async function saveJobCreate() {
  return (_jobCreateMode === 'bulk') ? saveJobCreateBulk() : saveJobCreateSingle();
}

async function saveJobCreateSingle() {
  const pipeline = $('jcm-pipeline').value.trim();
  const name = $('jcm-name').value.trim();
  const order = parseInt(($('jcm-order').value || '').trim(), 10);
  const type = ($('jcm-type').value || '').trim();
  const cmd = ($('jcm-cmd').value || '').trim();
  const m = $('jobCreateMsg');
  m.className = 'msg';

  if (!pipeline) { m.textContent = 'Pipeline obrigatório'; m.className = 'msg erro'; return; }
  if (!name) { m.textContent = 'Nome do job obrigatório'; m.className = 'msg erro'; return; }
  if (!order || isNaN(order) || order < 1) { m.textContent = 'Ordem inválida'; m.className = 'msg erro'; return; }
  if (!type) { m.textContent = 'Tipo obrigatório'; m.className = 'msg erro'; return; }

  closeJobCreateModal();

  // O backend exige lineage (origem + destino). Então abrimos o modal de Lineage
  // e salvamos automaticamente ao confirmar.
  jobsBdata = [];
  jbLineId  = 0;
  addJobLineB({
    job_name: name,
    execution_order: order,
    job_type: type,
    job_command: cmd || null,
    ssh_conn_id: (type === 'shell') ? ($('jcm-ssh').value || null) : null,
  });

  if ($('job_pipeline_name')) $('job_pipeline_name').value = pipeline;

  const project =
    _tryGetProjectFromJobsList(pipeline) ||
    _tryGetProjectFromPipelinesCache(pipeline) ||
    _inferProjectFromPipeline(pipeline) ||
    null;

  window.__lineageTableCtx = { pipeline: pipeline, project: project, source: 'jobCreate' };
  openLineageModal(jobsBdata[0].id);
  showToast('Preencha a lineage e clique em Confirmar para concluir o cadastro.', false);
}

function _parseBulkJobs(raw) {
  const jobs = [];
  raw.split('\n').forEach(line => {
    const p = line.trim();
    if (!p) return;
    const parts = p.split(',').map(s => s.trim());
    const nm = parts[0];
    const ord = parseInt(parts[1], 10);
    const tp = parts[2] || 'datastage';
    const cm = parts[3] || null;
    if (!nm || isNaN(ord)) return;
    jobs.push({
      job_name: nm,
      execution_order: ord,
      job_type: tp,
      job_command: cm,
      origens: [],
      destinos: [],
    });
  });
  return jobs;
}

async function saveJobCreateBulk() {
  const pipeline = $('jcm-pipeline').value.trim();
  const raw = ($('jcm-bulk-text').value || '').trim();
  const m = $('jobCreateMsg');
  m.className = 'msg';

  if (!pipeline) { m.textContent = 'Pipeline obrigatório'; m.className = 'msg erro'; return; }
  if (!raw) { m.textContent = 'Cole ao menos uma linha de job'; m.className = 'msg erro'; return; }

  const jobs = _parseBulkJobs(raw);
  if (!jobs.length) {
    m.textContent = 'Nenhuma linha válida. Formato: nome,ordem,tipo,comando(opcional)';
    m.className = 'msg erro';
    return;
  }

  closeJobCreateModal();

  // Em lote, o backend também exige lineage. Então carregamos os jobs no modo manual
  // para o usuário preencher lineage e clicar em "Salvar Jobs".
  if ($('job_pipeline_name')) $('job_pipeline_name').value = pipeline;
  jobsBdata = [];
  jbLineId  = 0;
  jobs.forEach(j => addJobLineB({
    job_name: j.job_name,
    execution_order: j.execution_order,
    job_type: j.job_type || 'datastage',
    job_command: j.job_command || null,
  }));
  showToast('Jobs carregados. Agora preencha a lineage de cada um e clique em "Salvar Jobs".', false);
}

function _dsmToggleSshField(prefix) {
  const type = $(prefix + '-type').value;
  const wrap = $(prefix + '-ssh-wrap');
  if (wrap) {
    wrap.style.display = type === 'shell' ? '' : 'none';
    if (type === 'shell' && !$(prefix + '-ssh').dataset.loaded) {
      _loadSshOptions(prefix + '-ssh');
    }
  }
  const verboseWrap = $(prefix + '-verbose-wrap');
  if (verboseWrap) verboseWrap.style.display = type === 'datastage' ? '' : 'none';
}

async function _loadSshOptions(selectId) {
  const sel = $(selectId);
  if (!sel || sel.dataset.loaded) return;
  try {
    const r = await fetch(ORQUESTRA_API + '/airflow/connections/ssh', {
      headers: authHeader ? { Authorization: authHeader } : {},
    });
    if (!r.ok) return;
    const d = await r.json();
    const opts = (d.connections || []).map(c =>
      `<option value="${_escHtml(c.conn_id)}">${_escHtml(c.conn_id)}${c.host ? ' · ' + _escHtml(c.host) : ''}</option>`
    ).join('');
    sel.innerHTML = '<option value="">Padrão do pipeline (SSH_CONN_ID)</option>' + opts;
    sel.dataset.loaded = '1';
  } catch(e) {}
}

function openJobEdit(idx) {
  const list = window.__jobs || [];
  const j = list[idx];
  if (!j) return;
  // garante que o filtro principal esteja preenchido (boa UX)
  if ($('job_pipeline_name') && j.pipeline_name) $('job_pipeline_name').value = j.pipeline_name;

  $('jem-pipeline').value = j.pipeline_name || '';
  $('jem-name').value = j.job_name || '';
  $('jem-order').value = (j.execution_order ?? '');
  $('jem-type').value = j.job_type || '';
  $('jem-cmd').value = j.job_command || '';
  $('jobEditMsg').textContent = '';
  $('jobEditMsg').className = 'msg';

  const sshWrap = $('jem-ssh-wrap');
  if (sshWrap) sshWrap.style.display = (j.job_type === 'shell') ? '' : 'none';
  const sshSel = $('jem-ssh');
  if (sshSel) { sshSel.value = j.ssh_conn_id || ''; if (j.job_type === 'shell' && !sshSel.dataset.loaded) _loadSshOptions('jem-ssh'); }

  const verboseWrap = $('jem-verbose-wrap');
  if (verboseWrap) verboseWrap.style.display = (j.job_type === 'datastage') ? '' : 'none';
  const verboseChk = $('jem-verbose');
  if (verboseChk) verboseChk.checked = !!(j.verbose_log);

  $('jobEditModal').classList.add('open');
}

function closeJobEdit() {
  $('jobEditModal').classList.remove('open');
}

async function saveJobEdit() {
  const pipeline = $('jem-pipeline').value.trim();
  const name = $('jem-name').value.trim();
  const order = parseInt(($('jem-order').value || '').trim(), 10);
  const type = ($('jem-type').value || '').trim();
  const cmd = ($('jem-cmd').value || '').trim();
  const m = $('jobEditMsg');
  m.className = 'msg';

  if (!pipeline) { m.textContent = 'Pipeline obrigatório'; m.className = 'msg erro'; return; }
  if (!name) { m.textContent = 'Nome do job obrigatório'; m.className = 'msg erro'; return; }
  if (!order || isNaN(order) || order < 1) { m.textContent = 'Ordem inválida'; m.className = 'msg erro'; return; }
  if (!type) { m.textContent = 'Tipo obrigatório'; m.className = 'msg erro'; return; }

  const jobPayload = {
    pipeline_name: pipeline,
    job_name: name,
    execution_order: order,
    job_type: type,
    job_command: cmd || null,
    ssh_conn_id: (type === 'shell') ? ($('jem-ssh').value || null) : null,
    verbose_log: (type === 'datastage') ? !!($('jem-verbose') && $('jem-verbose').checked) : false,
    require_lineage: false,
    operacao: 'upsert',
  };

  await _orqPost(
    ORQUESTRA_API + '/pipelines/jobs/register',
    jobPayload,
    'Job "' + name + '" do pipeline "' + pipeline + '"',
    null, null, null
  );

  closeJobEdit();
  try { loadJobsQuery(jobQueryState.offset); } catch(e) {}
  // F2 — oferecer regenerar DAG após editar job
  try {
    const _jePipeline = $('jem-pipeline') ? $('jem-pipeline').value.trim() : '';
    if (_jePipeline) _offerRegenDag(_jePipeline);
  } catch(e) {}
}

// ── Wizard state ──────────────────────────────────────────────────────────────
let _wizCurrentStep = 1;
const WIZ_TOTAL = 7;
let _pipelineIsNew = true;

function _syncNotifCard(cardId, checkbox) {
  const card = $(cardId);
  if (!card) return;
  card.style.borderColor = checkbox.checked ? 'var(--accent)' : 'var(--border)';
  card.style.background  = checkbox.checked ? 'rgba(0,92,169,.04)' : '';
}

function _wizUpdateStepper(step) {
  for (let i = 1; i <= WIZ_TOTAL; i++) {
    const el = $("wstep-" + i);
    if (!el) continue;
    el.classList.remove("active", "done", "error");
    if (i < step) el.classList.add("done");
    else if (i === step) el.classList.add("active");
  }
}

function _wizShowStep(step) {
  for (let i = 1; i <= WIZ_TOTAL; i++) {
    const el = $("wiz-step-" + i);
    if (el) el.style.display = (i === step) ? "" : "none";
  }
  _wizUpdateStepper(step);
  const lbl = $("wiz-step-label");
  if (lbl) lbl.textContent = "Passo " + step + " de " + WIZ_TOTAL;
  const topLbl = $("wiz-step-label-top");
  if (topLbl) topLbl.textContent = "Passo " + step + " de " + WIZ_TOTAL;
  const back = $("wiz-btn-back");
  const next = $("wiz-btn-next");
  const save = $("btn-save-pipeline");
  if (back) back.style.display = step > 1 ? "" : "none";
  if (next) next.style.display = step < WIZ_TOTAL ? "" : "none";
  if (save) {
    save.style.display = step === WIZ_TOTAL ? "" : "none";
    const txt = $("save_pipeline_txt");
    if (txt) txt.textContent = _pipelineIsNew ? "Criar Pipeline" : "Salvar Alterações";
  }
  if (step === 6) _wizRenderLineageStep();
  if (step === WIZ_TOTAL) _wizRenderReview();
}

function wizGoTo(n) {
  if (n > _wizCurrentStep) {
    for (let s = _wizCurrentStep; s < n; s++) {
      if (!_wizValidateStep(s)) return;
    }
  }
  _wizCurrentStep = n;
  _wizShowStep(n);
}

function wizNext() {
  if (!_wizValidateStep(_wizCurrentStep)) return;
  if (_wizCurrentStep < WIZ_TOTAL) {
    _wizCurrentStep++;
    _wizShowStep(_wizCurrentStep);
    try { document.getElementById("pipeline-editor").scrollTop = 0; } catch(e) {}
  }
}

function wizBack() {
  if (_wizCurrentStep > 1) {
    _wizCurrentStep--;
    _wizShowStep(_wizCurrentStep);
    try { document.getElementById("pipeline-editor").scrollTop = 0; } catch(e) {}
  }
}

function _wizValidateStep(step) {
  const mark = (elId, errId, msg) => {
    if ($(elId)) $(elId).classList.add("field-invalid");
    if ($(errId)) { $(errId).textContent = msg; $(errId).style.display = ""; }
    const el = $("wstep-" + step);
    if (el) { el.classList.remove("done"); el.classList.add("error"); }
    try { if ($(elId)) $(elId).focus(); } catch(e) {}
    return false;
  };
  const clear = (elId, errId) => {
    if ($(elId)) $(elId).classList.remove("field-invalid");
    if ($(errId)) { $(errId).textContent = ""; $(errId).style.display = "none"; }
  };

  if (step === 1) {
    clear("pipeline_name","err-pipeline");
    const nm = $("pipeline_name");
    if (!nm || !nm.value.trim()) return mark("pipeline_name","err-pipeline","Nome do pipeline é obrigatório.");
    clear("p-domain","err-domain");
    const dom = $("p-domain");
    if (!dom || !dom.value.trim()) return mark("p-domain","err-domain","Domínio é obrigatório.");
  }
  if (step === 2) {
    const h = $("p-deps-hidden");
    const depVal = h ? h.value : ($("p-depends-on") ? $("p-depends-on").value : "");
    const deps = depVal.split(",").map(d => d.trim()).filter(Boolean);
    const pname = ($("pipeline_name") ? $("pipeline_name").value : "").trim().toUpperCase();
    for (const d of deps) {
      if (d.toUpperCase() === pname) return mark("p-depends-on","err-depends-on","Pipeline não pode depender de si mesmo.");
    }
    clear("p-depends-on","err-depends-on");
  }
  if (step === 4) {
    clear("p-descricao","err-descricao");
    const desc = $("p-descricao");
    if (!desc || !desc.value.trim()) return mark("p-descricao","err-descricao","Descrição / Objetivo é obrigatório.");
    clear("p-ambiente","err-ambiente");
    const amb = $("p-ambiente");
    if (!amb || !amb.value.trim()) return mark("p-ambiente","err-ambiente","Ambiente é obrigatório.");
  }
  return true;
}

function wizAddJobRow() {
  const body = $('wiz-jobs-body');
  if (!body) return;
  const empty = $('wiz-jobs-empty');
  if (empty) empty.style.display = 'none';
  const idx = body.children.length + 1;
  const row = document.createElement('div');
  row.className = 'wiz-job-row';
  const types = window.__jobTypes || [{nome:'datastage'},{nome:'shell'},{nome:'python'},{nome:'storedproc'}];
  const typeOpts = types.map(t => '<option value=' + JSON.stringify(t.nome||t) + '>' + (t.nome||t) + '</option>').join('');
  const rmBtn = document.createElement('button');
  rmBtn.className = 'btn btn-outline btn-sm';
  rmBtn.style.cssText = 'padding:2px 6px;color:#ef4444';
  rmBtn.title = 'Remover job';
  rmBtn.textContent = '✕';
  rmBtn.onclick = function(){ this.closest('.wiz-job-row').remove(); _wizRenumberJobs(); };
  row.innerHTML = '' +
    '<span style="color:var(--muted);font-size:11px;text-align:center">' + idx + '</span>' +
    '<input type="text" placeholder="NOME_DO_JOB" style="text-transform:uppercase">' +
    '<input type="number" value="' + idx + '" min="1">' +
    '<select>' + typeOpts + '</select>' +
    '<input type="text" placeholder="comando ou caminho">';
  row.appendChild(rmBtn);
  row.querySelector('input[type=text]').addEventListener('input', function(){ this.value = this.value.toUpperCase(); });
  body.appendChild(row);
}

function _wizAppendJobRow(name, order, type, command) {
  wizAddJobRow();
  const body = $('wiz-jobs-body');
  const row = body.lastElementChild;
  if (!row) return;
  const inputs = row.querySelectorAll('input, select');
  if (inputs[0]) inputs[0].value = (name || '').toUpperCase();
  if (inputs[1]) inputs[1].value = order != null ? order : body.children.length;
  if (inputs[2]) {
    const sel = inputs[2];
    const want = (type || '').toLowerCase();
    let found = false;
    for (const opt of sel.options) {
      if (opt.value.toLowerCase() === want) { sel.value = opt.value; found = true; break; }
    }
    if (!found && type) {
      const o = document.createElement('option');
      o.value = o.textContent = type;
      sel.appendChild(o);
      sel.value = type;
    }
  }
  if (inputs[3]) inputs[3].value = command || '';
}

async function _wizLoadExistingJobs(pname) {
  const body  = $('wiz-jobs-body');
  const empty = $('wiz-jobs-empty');
  if (body) body.innerHTML = '';
  if (empty) { empty.style.display = ''; empty.textContent = 'Carregando jobs existentes…'; }
  window.__wizLineage = {};
  try {
    const r = await fetch(ORQUESTRA_API + '/jobs?limit=200&filter_pipeline=' + encodeURIComponent(pname));
    const d = r.ok ? await r.json() : { data: [] };
    (d.data || []).forEach(j => _wizAppendJobRow(j.job_name, j.execution_order, j.job_type, j.job_command));
  } catch(e) { console.warn('[WIZ] Falha ao carregar jobs:', e); }
  try {
    const r2 = await fetch(ORQUESTRA_API + '/lineage?pipeline_name=' + encodeURIComponent(pname));
    if (r2.ok) {
      const d2 = await r2.json();
      (d2.jobs || []).forEach(j => {
        window.__wizLineage[j.job_name] = {
          origens:  (j.origens  || []).map(o => ({ type: o.object_type || 'Tabela', name: o.object_name || '' })),
          destinos: (j.destinos || []).map(o => ({ type: o.object_type || 'Tabela', name: o.object_name || '' })),
        };
      });
    }
  } catch(e) { console.warn('[WIZ] Falha ao carregar lineage:', e); }
  if (empty) {
    empty.textContent = 'Nenhum job adicionado — pipeline sem jobs por ora.';
    empty.style.display = (body && body.children.length) ? 'none' : '';
  }
}

function _wizRenumberJobs() {
  const body = $("wiz-jobs-body");
  if (!body) return;
  Array.from(body.children).forEach((row, i) => {
    const num = row.querySelector("span");
    if (num) num.textContent = i + 1;
  });
  const empty = $("wiz-jobs-empty");
  if (empty) empty.style.display = body.children.length === 0 ? "" : "none";
}

function _wizGetJobs() {
  const body = $("wiz-jobs-body");
  if (!body) return [];
  return Array.from(body.children).map((row, i) => {
    const inputs = row.querySelectorAll("input, select");
    return {
      name:    inputs[0] ? inputs[0].value.trim() : "",
      order:   parseInt(inputs[1] ? inputs[1].value : i + 1, 10),
      type:    inputs[2] ? inputs[2].value : "sql",
      command: inputs[3] ? inputs[3].value.trim() : "",
    };
  }).filter(j => j.name);
}

function _wizRenderReview() {
  const nm   = $('pipeline_name')    ? $('pipeline_name').value    : '—';
  const proj = $('p-project')        ? $('p-project').value        : '—';
  const dom  = $('p-domain')         ? $('p-domain').value         : '—';
  const tags = $('p-tags')           ? $('p-tags').value           : '';
  const schEl = $('sch-preview');
  const sch  = schEl ? schEl.textContent : '—';
  const deps = $('p-deps-hidden')    ? $('p-deps-hidden').value    : ($('p-depends-on') ? $('p-depends-on').value : '—');
  const sdt  = $('p-dag-start-date') ? $('p-dag-start-date').value : '—';
  const crit = $('p-criticidade')    ? $('p-criticidade').value    : '—';
  const env  = $('p-ambiente')       ? $('p-ambiente').value       : '—';
  const sla  = $('p-sla-minutos')    ? $('p-sla-minutos').value    : '—';
  const pool = $('p-pool')           ? $('p-pool').value           : '—';
  const ret  = $('p-retries')        ? $('p-retries').value        : '—';
  const desc = $('p-descricao')      ? $('p-descricao').value      : '—';

  const rows = [
    ['Nome', nm], ['Projeto', proj], ['Domínio', dom], ['Tags', tags || '—'],
    ['Descrição', desc ? desc.substring(0,80) + (desc.length>80?'…':'') : '—'],
    ['Agendamento', sch], ['Data início', sdt || '—'], ['Dependências', deps || '—'],
    ['Criticidade', crit], ['Ambiente', env], ['SLA (min)', sla || '—'], ['Fila exec.', pool || '—'], ['Retries', ret],
  ];
  const sumEl = $('wiz-review-summary');
  if (sumEl) {
    sumEl.innerHTML = rows.map(([k,v]) =>
      '<div class="wiz-review-row"><span class="wiz-review-key">' + _escHtml(k) + '</span>' +
      '<span class="wiz-review-val">' + _escHtml(String(v)) + '</span></div>'
    ).join('');
  }
  const jobs = _wizGetJobs();
  const jobsEl = $('wiz-review-jobs');
  if (jobsEl) {
    if (!jobs.length) {
      jobsEl.innerHTML = '<span style="color:var(--muted);font-size:12px">Nenhum job adicionado — pipeline sem jobs.</span>';
    } else {
      jobsEl.innerHTML = jobs.map((j,i) =>
        '<div class="wiz-review-row"><span class="wiz-review-key">' + (i+1) + '. ' + _escHtml(j.name) + '</span>' +
        '<span class="wiz-review-val" style="color:var(--muted)">' + _escHtml(j.type) + (j.command ? ' · ' + _escHtml(j.command) : '') + '</span></div>'
      ).join('');
    }
  }
}

// ── Wizard lineage step ───────────────────────────────────────────────────────
const OBJ_TYPES_WIZ = ['Tabela','View','CSV','DataSet','TXT','XLS','XLSX','Proc','Query','API'];

function _wizRenderLineageStep() {
  const body = $('wiz-lineage-body');
  if (!body) return;
  const jobs = _wizGetJobs();
  if (!jobs.length) {
    body.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:1.5rem">Volte ao passo anterior e adicione jobs para configurar o lineage.</div>';
    return;
  }
  if (!window.__wizLineage) window.__wizLineage = {};
  const optTypes = OBJ_TYPES_WIZ.map(t => '<option>' + t + '</option>').join('');
  body.innerHTML = jobs.map((j, ji) => {
    const key = j.name;
    const lg = window.__wizLineage[key] || { origens: [], destinos: [] };
    const mkRows = (arr, side) => arr.map((r, ri) =>
      '<div class="lineage-row" data-job="' + _escHtml(key) + '" data-side="' + side + '" data-idx="' + ri + '">' +
      '<select>' + OBJ_TYPES_WIZ.map(t => '<option' + (r.type===t?' selected':'') + '>' + t + '</option>').join('') + '</select>' +
      '<input type="text" value="' + _escHtml(r.name||'') + '" placeholder="schema.tabela ou caminho">' +
      '<button class="lineage-rm" onclick="_wizLineageRemoveRow(this)" title="Remover">✕</button>' +
      '</div>'
    ).join('');
    return '<div style="border:1px solid var(--border);border-radius:10px;margin-bottom:.6rem;overflow:hidden">' +
      '<div style="padding:.4rem .75rem;background:rgba(0,92,169,.05);border-bottom:1px solid var(--border);font-size:12px;font-weight:600">' +
      (ji+1) + '. ' + _escHtml(j.name) + ' <span style="font-weight:400;color:var(--muted)">· ' + _escHtml(j.type) + '</span></div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem;padding:.5rem .75rem">' +
      '<div>' +
        '<div class="lineage-header origem" style="padding:.25rem .5rem;font-size:10px;font-weight:700;letter-spacing:.05em;border-radius:6px 6px 0 0">ORIGENS</div>' +
        '<div class="lineage-body" id="wiz-lg-orig-' + ji + '" data-job="' + _escHtml(key) + '" data-side="orig">' + mkRows(lg.origens,'orig') + '</div>' +
        '<button class="lineage-add" onclick="_wizLineageAddRow(' + ji + ',\'orig\')" style="margin:.25rem 0 0 .25rem">+ Adicionar origem</button>' +
      '</div>' +
      '<div>' +
        '<div class="lineage-header destino" style="padding:.25rem .5rem;font-size:10px;font-weight:700;letter-spacing:.05em;border-radius:6px 6px 0 0">DESTINOS</div>' +
        '<div class="lineage-body" id="wiz-lg-dest-' + ji + '" data-job="' + _escHtml(key) + '" data-side="dest">' + mkRows(lg.destinos,'dest') + '</div>' +
        '<button class="lineage-add" onclick="_wizLineageAddRow(' + ji + ',\'dest\')" style="margin:.25rem 0 0 .25rem">+ Adicionar destino</button>' +
      '</div>' +
      '</div></div>';
  }).join('');
}

function _wizLineageAddRow(ji, side) {
  const body = $('wiz-lg-' + (side === 'orig' ? 'orig' : 'dest') + '-' + ji);
  if (!body) return;
  const optTypes = OBJ_TYPES_WIZ.map(t => '<option>' + t + '</option>').join('');
  const row = document.createElement('div');
  row.className = 'lineage-row';
  row.innerHTML =
    '<select>' + optTypes + '</select>' +
    '<input type="text" placeholder="schema.tabela ou caminho">' +
    '<button class="lineage-rm" title="Remover">✕</button>';
  row.querySelector('.lineage-rm').onclick = function(){ this.closest('.lineage-row').remove(); };
  body.appendChild(row);
}

function _wizLineageRemoveRow(btn) {
  btn.closest('.lineage-row').remove();
}

function _wizGetLineage() {
  const result = {};
  const jobs = _wizGetJobs();
  jobs.forEach((j, ji) => {
    const readSide = (sideId) => {
      const el = $(sideId);
      if (!el) return [];
      return Array.from(el.querySelectorAll('.lineage-row')).map(r => {
        const sel = r.querySelector('select');
        const inp = r.querySelector('input');
        return { type: sel ? sel.value : 'Tabela', name: inp ? inp.value.trim() : '' };
      }).filter(x => x.name);
    };
    result[j.name] = { origens: readSide('wiz-lg-orig-' + ji), destinos: readSide('wiz-lg-dest-' + ji) };
  });
  return result;
}

// ── Wizard CSV import ─────────────────────────────────────────────────────────
function wizDownloadJobTemplate() {
  const csv = 'nome_job,ordem,tipo,comando\nJOB_EXEMPLO_A,1,SQL,SELECT * FROM tabela\nJOB_EXEMPLO_B,2,Python,scripts/transformacao.py\n';
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'template_jobs.csv';
  a.click();
}

function wizImportJobsCSV(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    const lines = (e.target.result || '').split(/\r?\n/).filter(l => l.trim());
    if (!lines.length) return showToast('Arquivo vazio ou inválido.', true);
    let start = 0;
    if (lines[0].toLowerCase().includes('nome_job') || lines[0].toLowerCase().includes('nome')) start = 1;
    let added = 0;
    lines.slice(start).forEach(line => {
      const cols = line.split(',').map(c => c.trim().replace(/^"|"$/g,''));
      const nome = (cols[0]||'').toUpperCase();
      if (!nome) return;
      const ordem = parseInt(cols[1]) || ($('wiz-jobs-body') ? $('wiz-jobs-body').children.length + 1 : 1);
      const tipo = cols[2] || 'SQL';
      const cmd = cols[3] || '';
      _wizAddJobRowData(nome, ordem, tipo, cmd);
      added++;
    });
    if (added) showToast(added + ' job(s) importado(s) com sucesso.');
    else showToast('Nenhum job encontrado no arquivo.', true);
  };
  reader.readAsText(file);
  input.value = '';
}

function _wizAddJobRowData(nome, ordem, tipo, cmd) {
  const body = $('wiz-jobs-body');
  if (!body) return;
  const empty = $('wiz-jobs-empty');
  if (empty) empty.style.display = 'none';
  const idx = body.children.length + 1;
  const row = document.createElement('div');
  row.className = 'wiz-job-row';
  const types = window.__jobTypes || [{nome:'datastage'},{nome:'shell'},{nome:'python'},{nome:'storedproc'}];
  const typeOpts = types.map(t => {
    const v = t.nome||t;
    return '<option value="' + v + '"' + (v===tipo?' selected':'') + '>' + v + '</option>';
  }).join('');
  const rmBtn = document.createElement('button');
  rmBtn.className = 'btn btn-outline btn-sm';
  rmBtn.style.cssText = 'padding:2px 6px;color:#ef4444';
  rmBtn.title = 'Remover job';
  rmBtn.textContent = '✕';
  rmBtn.onclick = function(){ this.closest('.wiz-job-row').remove(); _wizRenumberJobs(); };
  row.innerHTML =
    '<span style="color:var(--muted);font-size:11px;text-align:center">' + idx + '</span>' +
    '<input type="text" placeholder="NOME_DO_JOB" style="text-transform:uppercase" value="' + _escHtml(nome) + '">' +
    '<input type="number" value="' + ordem + '" min="1">' +
    '<select>' + typeOpts + '</select>' +
    '<input type="text" placeholder="comando ou caminho" value="' + _escHtml(cmd) + '">';
  row.appendChild(rmBtn);
  row.querySelector('input[type=text]').addEventListener('input', function(){ this.value = this.value.toUpperCase(); });
  body.appendChild(row);
}

// ──────────────────────────────────────────────────────────────────────────────

// ── View mode (read-only) ─────────────────────────────────────────────────────
function openPipelineView(idx) {
  const p = (window.__pipelines || [])[idx];
  if (!p) return;
  window.__viewPipelineIdx = idx;
  const m = $('modal-view-pipeline');
  if (!m) return;
  $('view-pipeline-title').textContent = p.pipeline_name;
  $('view-pipeline-sub').textContent = (p.project_name || '') + (p.domain ? ' · ' + p.domain : '');
  const pill = (v, ok) => ok
    ? '<span style="display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;background:rgba(22,163,74,.1);color:#15803d;border:1px solid rgba(22,163,74,.3)">' + _escHtml(v) + '</span>'
    : '<span style="display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;background:rgba(128,128,128,.08);color:var(--muted);border:1px solid var(--border)">' + _escHtml(v) + '</span>';
  const row = (label, val) =>
    '<div style="padding:.3rem 0;border-bottom:1px solid rgba(128,128,128,.07)">' +
    '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:.15rem">' + label + '</div>' +
    '<div style="font-size:13px;font-weight:500">' + val + '</div></div>';
  const crit = p.criticidade || '—';
  const critColor = crit === 'Alta' ? '#ef4444' : crit === 'Media' ? '#ca8a04' : '#16a34a';
  const body = $('view-pipeline-body');
  body.innerHTML = [
    row('Nome',          '<span style="font-family:ui-monospace,monospace;font-size:12px">' + _escHtml(p.pipeline_name) + '</span>'),
    row('Projeto',       _escHtml(p.project_name || '—')),
    row('Domínio',       _escHtml(p.domain || '—')),
    row('Tags',          p.tags ? p.tags.split(',').map(t => pill(t.trim(), true)).join(' ') : '—'),
    row('Agendamento',   _escHtml(p.scheduled_time || '—') + (p.schedule_type ? ' <span style="font-size:10px;color:var(--muted)">(' + p.schedule_type + ')</span>' : '')),
    row('Data início',   _escHtml(p.dag_start_date || 'imediato')),
    row('Depende de',    p.depends_on ? p.depends_on.split(',').map(d => pill(d.trim(), false)).join(' ') : '—'),
    row('Status',        p.active ? pill('Ativo', true) : pill('Inativo', false)),
    row('Descrição',     p.descricao ? '<span style="font-size:12px;white-space:pre-wrap">' + _escHtml(p.descricao) + '</span>' : '<span style="color:var(--muted);font-size:11px">— sem descrição —</span>'),
    row('Criticidade',   '<span style="color:' + critColor + ';font-weight:600">' + _escHtml(crit) + '</span>'),
    row('Ambiente',      _escHtml(p.ambiente || 'PROD')),
    row('SLA',           p.sla_minutos ? p.sla_minutos + ' min' : '—'),
    row('Retries',       (p.retries_count != null ? p.retries_count : 1) + 'x · ' + (p.retry_delay_seconds || 300) + 's'),
    row('Fila exec.',    _escHtml(p.pool_name || 'padrão')),
    row('Notificações',  (p.envia_msg_inicio ? '▶ Início ' : '') + (p.envia_msg_fim ? '✓ Conclusão ' : '') + (p.envia_msg_erro ? '⚠ Erro' : '') || '—'),
    row('Criado em',     _escHtml(p.created_at || '—')),
    row('Atualizado',    _escHtml(p.updated_at || '—')),
  ].join('');
  m.style.display = 'flex';
}
function closePipelineView() {
  const m = $('modal-view-pipeline');
  if (m) m.style.display = 'none';
}
document.addEventListener('DOMContentLoaded', function() {
  const mv = $('modal-view-pipeline');
  if (mv) mv.addEventListener('click', function(e){ if(e.target===this) closePipelineView(); });
});
// ── Pipeline Lineage modal ────────────────────────────────────────────────────
const PIPE_JOBS_DAG = 'etl_catalogo_query';

function closePipelineLineage() {
  const m = $('modal-pipeline-lineage');
  if (m) m.style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function() {
  const ml = $('modal-pipeline-lineage');
  if (ml) ml.addEventListener('click', function(e){ if(e.target===this) closePipelineLineage(); });
});

async function openPipelineLineage(idx) {
  const p = (window.__pipelines || [])[idx];
  if (!p) return;
  const modal = $('modal-pipeline-lineage');
  const body  = $('pipe-lineage-body');
  if (!modal || !body) return;
  $('pipe-lineage-title').textContent = 'Lineage — ' + p.pipeline_name;
  $('pipe-lineage-sub').textContent   = (p.project_name||'') + (p.domain ? ' · ' + p.domain : '');
  body.innerHTML = '<div class="empty-state"><span class="es-icon">⏳</span><p class="es-title">Carregando jobs e lineage...</p></div>';
  modal.style.display = 'flex';

  try {
    const r = await fetch(ORQUESTRA_API + '/lineage?pipeline_name=' + encodeURIComponent(p.pipeline_name));
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    _renderPipelineLineageBody(body, data);
  } catch(e) {
    body.innerHTML = '<div class="empty-state"><span class="es-icon">⚠</span><p class="es-title">Erro ao carregar lineage</p><p class="es-sub">' + _escHtml(e.message) + '</p></div>';
  }
}

function _renderPipelineLineageBody(body, data) {
  // Visão consolidada a nível de PIPELINE (somente visualização):
  // origens únicas de todos os jobs → nó do pipeline → destinos únicos.
  const jobs = (data && data.jobs) || [];
  if (!jobs.length) {
    body.innerHTML = '<div class="empty-state"><span class="es-icon">◎</span><p class="es-title">Nenhum job cadastrado</p><p class="es-sub">Adicione jobs ao pipeline para visualizar o lineage.</p></div>';
    return;
  }

  const dedupe = (side) => {
    const seen = {};
    jobs.forEach(j => (j[side] || []).forEach(o => {
      const nm = o.object_name || o.nome || o.name || '';
      if (!nm) return;
      const key = nm.toLowerCase();
      if (!seen[key]) seen[key] = { nome: nm, tipo: o.object_type || o.tipo || o.type || '', db: o.database_name || '' };
    }));
    return Object.values(seen).sort((a, b) => a.nome.localeCompare(b.nome));
  };
  const origens  = dedupe('origens');
  const destinos = dedupe('destinos');

  const mkNode = (o, cls) =>
    '<div class="ls-node"><div class="ls-node-box ' + cls + '" style="min-width:140px;max-width:240px">' +
      '<span style="font-size:11px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block" title="' + _escHtml(o.nome) + '">' + _escHtml(o.nome) + '</span>' +
      '<span class="ls-node-label" style="font-size:9px">' + _escHtml(o.db ? o.db : o.tipo) + '</span>' +
    '</div></div>';

  const col = (arr, cls, vazio) => arr.length
    ? '<div style="display:flex;flex-direction:column;gap:6px">' + arr.map(o => mkNode(o, cls)).join('') + '</div>'
    : '<span style="font-size:11px;color:var(--muted)">' + vazio + '</span>';

  const pipeNode =
    '<div class="ls-node"><div class="ls-node-box job" style="min-width:160px">' +
      '<span style="font-size:12px;font-weight:700;display:block">' + _escHtml(data.pipeline_name || '') + '</span>' +
      '<span class="ls-node-label">' + jobs.length + ' job(s)</span>' +
    '</div></div>';

  body.innerHTML =
    '<div style="display:grid;grid-template-columns:1fr 60px auto 60px 1fr;gap:.5rem;align-items:center;justify-items:center;padding:.5rem 0">' +
      '<div style="justify-self:stretch"><div style="font-size:10px;font-weight:700;letter-spacing:.05em;color:var(--cvp-blue);margin-bottom:.4rem;text-align:center">ORIGENS (' + origens.length + ')</div>' + col(origens, 'origem', 'sem origens cadastradas') + '</div>' +
      '<div class="ls-arrow" style="font-size:20px">→</div>' +
      pipeNode +
      '<div class="ls-arrow" style="font-size:20px">→</div>' +
      '<div style="justify-self:stretch"><div style="font-size:10px;font-weight:700;letter-spacing:.05em;color:#15803d;margin-bottom:.4rem;text-align:center">DESTINOS (' + destinos.length + ')</div>' + col(destinos, 'destino', 'sem destinos cadastrados') + '</div>' +
    '</div>' +
    '<div style="font-size:11px;color:var(--muted);text-align:center;border-top:1px solid var(--border);padding-top:.5rem;margin-top:.25rem">Visualização consolidada do pipeline — para detalhe por job, use Governança ▸ Lineage.</div>';
}

// ─────────────────────────────────────────────────────────────────────────────

function openPipelineCreate() {
  _pipelineIsNew = true;
  $('pipelineFormTitle').innerHTML = '<span class="orange">+</span> Novo Pipeline';
  $('pipelineFormHint').textContent = 'Cadastro de novo pipeline. O nome é a chave única (pipeline_name).';
  $('pipeline_name').disabled = false;
  $('pipeline_name').value = '';
  _scheduleSetFromRecord({ schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0, schedule_dow: 1, schedule_dom: 1 });
  $('p-project').value = '';
  $('p-domain').value = '';
  $('p-tags').value = '';
  $('tags-wrap').querySelectorAll('.chip').forEach(c => c.remove());
  if ($('p-depends-on'))     $('p-depends-on').value = '';
  if ($('p-deps-hidden'))    $('p-deps-hidden').value = '';
  if ($('deps-wrap'))        $('deps-wrap').querySelectorAll('.chip').forEach(c => c.remove());
  if ($('p-dag-start-date')) $('p-dag-start-date').value = '';
  if ($('p-descricao'))      $('p-descricao').value = '';
  if ($('p-runbook'))        $('p-runbook').value = '';
  if ($('p-criticidade'))    $('p-criticidade').value = 'Media';
  if ($('p-ambiente'))       $('p-ambiente').value = 'PROD';
  if ($('p-sla-minutos'))    $('p-sla-minutos').value = '';
  if ($('p-max-active-runs')) $('p-max-active-runs').value = 1;
  if ($('p-retries'))        $('p-retries').value = 1;
  if ($('p-retry-delay'))    $('p-retry-delay').value = 300;
  if ($('p-pool'))           $('p-pool').value = '';
  loadCalendarioOptions('');
  if ($('sch-dias-uteis'))  $('sch-dias-uteis').checked  = false;
  if ($('sch-trigger-dep')) $('sch-trigger-dep').checked = false;
  setStatus(1);
  ['tog-inicio','tog-fim','tog-erro'].forEach(id => { $(id).checked = true; syncToggle('lbl-'+id.replace('tog-',''), $(id)); _syncNotifCard('card-'+id.replace('tog-',''), $(id)); });
  $('msg-pipeline').textContent = '';
  $('msg-pipeline').className = 'msg';
  clearFieldInvalidById('pipeline_name','err-pipeline');
  clearFieldInvalidById('p-domain','err-domain');
  clearFieldInvalidById('tag-input','err-tags');
  clearFieldInvalidById('p-descricao','err-descricao');
  clearFieldInvalidById('p-ambiente','err-ambiente');
  const _wjb = $('wiz-jobs-body'); if (_wjb) _wjb.innerHTML = '';
  const _wje = $('wiz-jobs-empty'); if (_wje) { _wje.style.display = ''; _wje.textContent = 'Nenhum job adicionado — pipeline sem jobs por ora.'; }
  window.__wizLineage = {};
  _wizCurrentStep = 1;
  $('pipeline-editor').style.display = 'flex';
  _wizShowStep(1);
  try { $('pipeline_name').focus(); } catch(e) {}
}

function closePipelineEditor() {
  const pe = $('pipeline-editor');
  if (pe) pe.style.display = 'none';
}

document.getElementById('pipeline-editor').addEventListener('click', function(e){ if(e.target===this) closePipelineEditor(); });

function openPipelineEdit(idx) {
  _pipelineIsNew = false;
  const list = window.__pipelines || [];
  const p = list[idx];
  if (!p) return;
  $('pipelineFormTitle').innerHTML = '<span class="orange">✎</span> Editar Pipeline';
  $('pipelineFormHint').textContent = 'Edição do pipeline. Para “renomear”, crie um novo pipeline.';
  $('pipeline_name').disabled = true;
  $('pipeline_name').value = (p.pipeline_name || '').toString().toUpperCase();
  $('p-project').value = p.project_name || '';
  $('p-domain').value = (p.domain || '').toString().toUpperCase();
  _scheduleSetFromRecord({
    schedule_type: p.schedule_type,
    schedule_hour: p.schedule_hour,
    schedule_minute: p.schedule_minute,
    schedule_dow: p.schedule_dow,
    schedule_dom: p.schedule_dom,
    scheduled_time: p.scheduled_time,
    horarios_especificos: p.horarios_especificos,
    dias_semana: p.dias_semana,
  });
  // tags
  $('p-tags').value = '';
  $('tags-wrap').querySelectorAll('.chip').forEach(c => c.remove());
  if (p.tags) {
    p.tags.split(',').map(t => t.trim()).filter(Boolean).forEach(t => addChip(t));
  }
  // S4: dependência
  if ($('p-depends-on')) $('p-depends-on').value = (p.depends_on || '').toString().toUpperCase();
  // dag_start_date
  if ($('p-dag-start-date')) $('p-dag-start-date').value = p.dag_start_date || '';
  // Preenche datalist com pipelines disponíveis (exceto o próprio)
  const dl = $('depends-on-list');
  if (dl) {
    dl.innerHTML = (window.__pipelines || [])
      .filter(pl => pl.pipeline_name !== p.pipeline_name)
      .map(pl => '<option value="' + pl.pipeline_name + '">')
      .join('');
  }

  // status e notificações
  setStatus(p.active ? 1 : 0);
  $('tog-inicio').checked = !!p.envia_msg_inicio; syncToggle('lbl-inicio', $('tog-inicio')); _syncNotifCard('card-inicio', $('tog-inicio'));
  $('tog-fim').checked    = !!p.envia_msg_fim;    syncToggle('lbl-fim',    $('tog-fim'));    _syncNotifCard('card-fim',    $('tog-fim'));
  $('tog-erro').checked   = !!p.envia_msg_erro;   syncToggle('lbl-erro',   $('tog-erro'));   _syncNotifCard('card-erro',   $('tog-erro'));

  // Advanced fields
  if ($('p-descricao'))      $('p-descricao').value      = p.descricao || '';
  if ($('p-runbook'))        $('p-runbook').value        = p.runbook_md || '';
  if ($('p-criticidade'))    $('p-criticidade').value    = p.criticidade || 'Media';
  if ($('p-ambiente'))       $('p-ambiente').value       = p.ambiente || 'PROD';
  if ($('p-sla-minutos'))    $('p-sla-minutos').value    = p.sla_minutos != null ? p.sla_minutos : '';
  if ($('p-max-active-runs')) $('p-max-active-runs').value = p.max_active_runs || 1;
  if ($('p-retries'))        $('p-retries').value        = p.retries_count != null ? p.retries_count : 1;
  if ($('p-retry-delay'))    $('p-retry-delay').value    = p.retry_delay_seconds || 300;
  if ($('p-pool'))           $('p-pool').value           = p.pool_name || '';
  if ($('p-dag-start-date')) $('p-dag-start-date').value = p.dag_start_date || '';
  // Fase 4 — scheduling avançado
  loadCalendarioOptions(p.calendario_nome || '');
  if ($('sch-dias-uteis'))  $('sch-dias-uteis').checked  = !!p.somente_dias_uteis;
  if ($('sch-trigger-dep')) $('sch-trigger-dep').checked = !!p.trigger_por_dependencia;
  // Multi-dep chips
  if ($('deps-wrap')) {
    $('deps-wrap').querySelectorAll('.chip').forEach(c => c.remove());
    if ($('p-deps-hidden')) $('p-deps-hidden').value = '';
    const deps = (p.depends_on || '').split(',').map(d => d.trim()).filter(Boolean);
    deps.forEach(d => {
      _addDepChip(d);
      const h = $('p-deps-hidden');
      if (h) { const cur = h.value ? h.value.split(',') : []; if (!cur.includes(d)) { cur.push(d); h.value = cur.join(','); } }
    });
  }
  if ($('p-depends-on')) $('p-depends-on').value = '';

  $('msg-pipeline').textContent = '';
  $('msg-pipeline').className = 'msg';
  clearFieldInvalidById('pipeline_name','err-pipeline');
  clearFieldInvalidById('p-domain','err-domain');
  clearFieldInvalidById('tag-input','err-tags');
  clearFieldInvalidById('p-descricao','err-descricao');
  clearFieldInvalidById('p-ambiente','err-ambiente');
  // Carrega jobs e lineage já cadastrados no passo 5/6
  _wizLoadExistingJobs(p.pipeline_name);
  _wizCurrentStep = 1;
  $('pipeline-editor').style.display = 'flex';
  _wizShowStep(1);
  try { $('sch-type').focus(); } catch(e) {}
}

async function softDeletePipeline(idx) {
  const list = window.__pipelines || [];
  const p = list[idx];
  if (!p) return;
  const ok = await showConfirm(
    'Inativar o pipeline "' + (p.pipeline_name || '') + '"? Esta ação pode ser revertida reativando o pipeline.',
    'Inativar pipeline'
  );
  if (!ok) return;
  const conf = {
    pipeline_name: p.pipeline_name,
    scheduled_time: (p.scheduled_time || '00:00:00'),
    schedule_type: p.schedule_type || null,
    schedule_hour: (p.schedule_hour ?? null),
    schedule_minute: (p.schedule_minute ?? null),
    schedule_dow: (p.schedule_dow ?? null),
    schedule_dom: (p.schedule_dom ?? null),
    active: 0,
    envia_msg_inicio: p.envia_msg_inicio ? 1 : 0,
    envia_msg_fim:    p.envia_msg_fim ? 1 : 0,
    envia_msg_erro:   p.envia_msg_erro ? 1 : 0,
    project_name: p.project_name || '',
    domain: p.domain || '',
    tags: p.tags || '',
  };
  await _orqPost(ORQUESTRA_API + '/pipelines/register', conf, 'Inativar pipeline "' + p.pipeline_name + '"', null, null, null);
  // F3 — pausar/ativar DAG no Airflow
  try { await _toggleDagAirflow(p.pipeline_name, 0); } catch(e) {}
  try { loadQuery(0); } catch(e) {}
}

async function loadQuery(offset) {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  if (offset !== undefined) queryState.offset = offset;
  const conf = { offset: queryState.offset, limit: queryState.limit };
  const fname = $('qf-name') ? $('qf-name').value.trim() : '';
  const fproj = $('qf-project') ? $('qf-project').value : '';
  const fact  = $('qf-active')  ? $('qf-active').value  : '';
  if (fname)        conf.filter_name    = fname;
  if (fproj)        conf.filter_project = fproj;
  if (fact !== '')  conf.filter_active  = parseInt(fact);
  const btn = $('btn-query'), btnTxt = $('query-btn-txt'), qs = $('query-status');
  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = 'Buscando...';
  if (qs) qs.textContent = 'Consultando API...';
  try {
    const params = new URLSearchParams();
    params.set('offset', conf.offset || 0);
    params.set('limit',  conf.limit  || 20);
    if (conf.filter_name)    params.set('filter_name',    conf.filter_name);
    if (conf.filter_project) params.set('filter_project', conf.filter_project);
    if (conf.filter_active !== undefined && conf.filter_active !== '') params.set('filter_active', conf.filter_active);

    if (qs) qs.textContent = 'Carregando dados...';
    const r = await fetch(ORQUESTRA_API + '/pipelines?' + params.toString());
    if (r.status === 401) { sair(); return; }
    if (!r.ok) { if (qs) qs.textContent = 'Erro API: ' + r.status; return; }

    let payload = await r.json();
    try { window.__lastQueryPayload = payload; } catch(e) {}

    if (qs) {
      try {
        const keys = payload && typeof payload === 'object' ? Object.keys(payload).join(',') : '';
        const len  = payload && payload.data && Array.isArray(payload.data) ? payload.data.length : 0;
        qs.textContent = (qs.textContent || '') + (keys ? ` | payload.keys=[${keys}] data.len=${len}` : '');
      } catch(e) {}
    }
    try {
      renderQueryTable(payload);
    } catch (e) {
      if (qs) qs.textContent = 'Erro ao renderizar o grid: ' + (e && e.message ? e.message : e);
      const area = $('query-table-area');
      if (area) {
        const pretty = (() => { try { return JSON.stringify(payload, null, 2); } catch(_) { return String(payload); } })();
        area.innerHTML = '<div class="empty-query" style="text-align:left;white-space:pre-wrap;font-family:monospace;line-height:1.45">' +
          pretty.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch])) +
          '</div>';
      }
    }
  } catch(err) {
    if (qs) qs.textContent = 'Erro de conexão: ' + err.message;
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Buscar';
  }
}

async function pollQueryRun(runId) {
  const start = Date.now();
  const timeoutMs = 120000; // 2 min
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch('/api/v1/dags/etl_pipeline_query/dagRuns/' + runId, { headers: { 'Authorization': _sysAuth() } });
      if (r.ok) {
        const d = await r.json();
        if (d.state === 'success') return 'success';
        if (d.state === 'failed') { if ($('query-status')) $('query-status').textContent = 'A execução falhou no Airflow. Verifique o log do DAG.'; return 'failed'; }
      }
    } catch(e) {}
    await new Promise(res => setTimeout(res, 2000));
  }
  if ($('query-status')) $('query-status').textContent = 'A execução está demorando (timeout de 2 min). Você pode aguardar e clicar em Buscar novamente.';
  return 'timeout';
}

function renderQueryTable(payload) {
  const area = $('query-table-area');
  if (!area) return;
  payload = normalizeXcomValue(payload);
  if (!payload || !payload.data || !payload.data.length) {
    area.innerHTML =
      '<div class="empty-state">' +
        '<span class="es-icon">≡</span>' +
        '<p class="es-title">Nenhum pipeline encontrado</p>' +
        '<p class="es-sub">Ajuste os filtros e tente novamente.</p>' +
      '</div>';
    if ($('query-status')) $('query-status').textContent = 'Nenhum resultado';
    return;
  }
  const { total, offset, limit, pages } = payload;
  try { window.__pipelines = payload.data; window.__lastQueryPayload = payload; } catch(e) {}
  queryState.total = total; queryState.pages = pages; queryState.offset = offset;
  const from = offset + 1, to = Math.min(offset + limit, total);
  if ($('query-status')) $('query-status').textContent = 'Exibindo ' + from + '–' + to + ' de ' + total + ' pipeline(s)';

  // ── Agrupa: projeto → domínio → pipelines ─────────────────────────────────
  const tree = {};
  payload.data.forEach((p, globalIdx) => {
    const proj = p.project_name || '(sem projeto)';
    const dom  = p.domain       || '(sem domínio)';
    if (!tree[proj])       tree[proj] = {};
    if (!tree[proj][dom])  tree[proj][dom] = [];
    tree[proj][dom].push({ ...p, _idx: globalIdx });
  });

  const ICON_PROJ   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>';
  const ICON_DOM    = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>';
  const ICON_PIPE   = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>';

  function _pipelineRow(p, i) {
    const statusDot = p.active
      ? '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);flex-shrink:0" title="Ativo"></span>'
      : '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--border);flex-shrink:0" title="Inativo"></span>';
    const dagBadge = p.dag_criada
      ? '<span style="font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;background:rgba(22,163,74,.12);color:#16a34a;border:1px solid rgba(22,163,74,.25)">DAG ✓</span>'
      : '<span style="font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;background:rgba(100,116,139,.10);color:var(--muted);border:1px solid var(--border)">DAG —</span>';
    const sched = p.scheduled_time ? '<span style="font-size:11px;color:var(--muted)">' + p.scheduled_time + '</span>' : '';
    const lastExec = p.last_execution
      ? '<span style="font-size:10px;color:var(--muted)">' + p.last_execution.substring(0,16) + '</span>'
      : '';
    const notifBits = (p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro)
      ? '<span style="font-size:10px;color:var(--muted)" title="Notificações: ' +
          (p.envia_msg_inicio ? 'início ' : '') + (p.envia_msg_fim ? 'fim ' : '') + (p.envia_msg_erro ? 'erro' : '') + '">✉</span>'
      : '';

    return '<div class="ptree-pipeline" data-idx="' + i + '">' +
      '<div class="ptree-pipeline-main">' +
        statusDot +
        '<span class="ptree-pipeline-name" title="' + _escHtml(p.pipeline_name) + '">' + _escHtml(p.pipeline_name) + '</span>' +
        dagBadge +
        (p.scheduled_time ? '<span style="font-size:9px;color:var(--muted);white-space:nowrap;flex-shrink:0">' + p.scheduled_time + '</span>' : '') +
        ((p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro) ? '<span style="font-size:9px;color:var(--muted);flex-shrink:0" title="Notificações">✉</span>' : '') +
        '<div class="ptree-acts">' +
          '<button class="act-btn act-view" onclick="openPipelineView(' + i + ')" title="Visualizar">' + ICONS.detail + '</button>' +
          (!window.__isViewer ? '<button class="act-btn act-edit" onclick="openPipelineEdit(' + i + ')" title="Editar">' + ICONS.edit + '</button>' : '') +
          '<button class="act-btn act-lineage" onclick="openPipelineLineage(' + i + ')" title="Lineage">' + ICONS.graph + '</button>' +
          '<button class="act-btn act-audit" onclick="openPipelineAudit(' + i + ')" title="Histórico">' + ICONS.history + '</button>' +
          (!window.__isViewer && p.active ? '<button class="act-btn act-disable" onclick="softDeletePipeline(' + i + ')" title="Inativar">' + ICONS.disable + '</button>' : '') +
          (!window.__isViewer ? (
            !p.dag_criada
              ? '<button class="btn-dag act-btn act-dag" id="dag-btn-' + i + '" onclick="gerarDAG(' + i + ')" title="Gerar DAG">' + ICONS.gear + '</button>'
              : '<button class="btn-dag-ok act-btn act-regen" id="dag-btn-' + i + '" onclick="gerarDAG(' + i + ')" title="Regenerar DAG">' + ICONS.refresh + '</button>'
          ) : '') +
          (!window.__isViewer && p.dag_criada
            ? '<button class="act-btn act-exec" id="exec-btn-' + i + '" onclick="executarPipelineAgora(' + i + ')" title="Executar agora">' + ICONS.play + '</button>'
            : ''
          ) +
        '</div>' +
      '</div>' +
    '</div>';
  }

  let html = '<div class="ptree">';
  const projNames = Object.keys(tree).sort();
  projNames.forEach((proj, pi) => {
    const projId  = 'ptree-p-' + pi;
    const domNames = Object.keys(tree[proj]).sort();
    const totalProj = domNames.reduce((s, d) => s + tree[proj][d].length, 0);
    const activeProj = domNames.reduce((s, d) => s + tree[proj][d].filter(p => p.active).length, 0);
    html +=
      '<div class="ptree-project">' +
        '<div class="ptree-project-hdr" onclick="_ptreeToggle(\'' + projId + '\')">' +
          '<span class="ptree-chevron" id="chv-' + projId + '">▸</span>' +
          '<span style="color:var(--cvp-blue)">' + ICON_PROJ + '</span>' +
          '<span class="ptree-project-name">' + _escHtml(proj) + '</span>' +
          '<span class="ptree-badge">' + totalProj + ' pipeline' + (totalProj !== 1 ? 's' : '') + '</span>' +
          '<span class="ptree-badge" style="background:rgba(22,163,74,.1);color:#16a34a">' + activeProj + ' ativo' + (activeProj !== 1 ? 's' : '') + '</span>' +
        '</div>' +
        '<div class="ptree-project-body" id="' + projId + '" style="display:none">';

    domNames.forEach((dom, di) => {
      const domId    = 'ptree-d-' + pi + '-' + di;
      const pipes    = tree[proj][dom];
      const activeDom = pipes.filter(p => p.active).length;
      html +=
        '<div class="ptree-domain">' +
          '<div class="ptree-domain-hdr" onclick="_ptreeToggle(\'' + domId + '\')">' +
            '<span class="ptree-chevron" id="chv-' + domId + '">▸</span>' +
            '<span style="color:var(--cvp-orange)">' + ICON_DOM + '</span>' +
            '<span class="ptree-domain-name">' + _escHtml(dom) + '</span>' +
            '<span class="ptree-badge">' + pipes.length + '</span>' +
            '<span class="ptree-badge" style="background:rgba(22,163,74,.1);color:#16a34a">' + activeDom + ' ativo' + (activeDom !== 1 ? 's' : '') + '</span>' +
          '</div>' +
          '<div class="ptree-domain-body" id="' + domId + '" style="display:none">';

      pipes.sort((a, b) => a.pipeline_name.localeCompare(b.pipeline_name))
           .forEach(p => { html += _pipelineRow(p, p._idx); });

      html += '</div></div>'; // domain-body, domain
    });

    html += '</div></div>'; // project-body, project
  });

  html += '</div>'; // ptree

  if (pages > 1) html += renderPagination(offset, limit, total, pages);
  area.innerHTML = html;
}

function _ptreeToggle(id) {
  const el  = $(id);
  const chv = $('chv-' + id);
  if (!el) return;
  const isHidden = el.style.display === 'none';
  if (isHidden) {
    el.style.display = el.classList.contains('ptree-domain-body') ? 'flex' : '';
  } else {
    el.style.display = 'none';
  }
  if (chv) chv.textContent = isHidden ? '▾' : '▸';
}

function renderPagination(offset, limit, total, pages, loaderFnName) {
  const cur = Math.floor(offset / limit);
  const fn = loaderFnName || 'loadQuery';
  let btns = '<button class="pag-btn" ' + (cur > 0 ? '' : 'disabled') + ' onclick="' + fn + '(' + ((cur-1)*limit) + ')">‹</button>';
  for (let i = 0; i < Math.min(pages, 7); i++)
    btns += '<button class="pag-btn ' + (i === cur ? 'active' : '') + '" onclick="' + fn + '(' + (i*limit) + ')">' + (i+1) + '</button>';
  if (pages > 7) btns += '<span style="padding:.3rem .4rem;font-size:12px;color:var(--muted)">…' + pages + '</span>';
  btns += '<button class="pag-btn" ' + (cur < pages-1 ? '' : 'disabled') + ' onclick="' + fn + '(' + ((cur+1)*limit) + ')">›</button>';
  return '<div class="pagination"><span>' + total + ' registros · página ' + (cur+1) + ' de ' + pages + '</span><div class="pag-btns">' + btns + '</div></div>';
}

function clearQuery() {
  if ($('qf-name')) $('qf-name').value = '';
  if ($('qf-project')) $('qf-project').value = '';
  if ($('qf-active')) $('qf-active').value = '';
  queryState = { offset:0, limit:20, total:0, pages:0 };
  const area = $('query-table-area');
  if (area) area.innerHTML =
    '<div class="empty-state">' +
      '<span class="es-icon">≡</span>' +
      '<p class="es-title">Nenhum pipeline carregado</p>' +
      '<p class="es-sub">Use os filtros acima e clique em Buscar para carregar os pipelines.</p>' +
    '</div>';
  if ($('query-status')) $('query-status').textContent = '';
}
