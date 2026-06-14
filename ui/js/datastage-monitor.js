// ══════════════════════════════════════════════════════
// DataStage Monitor
// ══════════════════════════════════════════════════════

let _dsmAutoRefresh = null;

function dsMonitorInit() {
  // Se havia um auto-refresh rodando, mantém
}

async function dsmTrigger() {
  const project  = (document.getElementById('dsm-project').value || '').trim();
  const job      = (document.getElementById('dsm-job').value || '').trim();
  const interval = parseInt(document.getElementById('dsm-interval').value || '60');
  const st       = document.getElementById('dsm-trigger-status');

  if (!project || !job) {
    st.textContent = 'Preencha Projeto e Nome do Job.';
    st.style.color = 'var(--red)';
    return;
  }

  st.textContent = 'Disparando monitoramento…';
  st.style.color = 'var(--muted)';

  try {
    const r = await fetch('/orquestra/datastage/monitor', {
      method: 'POST',
      headers: {'Content-Type':'application/json', ..._orqAuthHeader()},
      body: JSON.stringify({ project, job_name: job, poll_interval: interval }),
    });
    const data = await r.json();
    if (!r.ok) {
      st.textContent = 'Erro: ' + (data.detail || r.status);
      st.style.color = 'var(--red)';
      return;
    }
    st.textContent = `Monitor iniciado — run_id: ${data.dag_run_id}`;
    st.style.color = 'var(--green)';
    showToast(`Monitorando ${project}/${job}`);

    // Inicia auto-refresh do painel a cada 30s
    _dsmStartAutoRefresh(project, job);
    await dsmLoadStatus(project, job);
  } catch(e) {
    st.textContent = 'Erro de conexão: ' + e.message;
    st.style.color = 'var(--red)';
  }
}

async function dsmRefresh() {
  const project = (document.getElementById('dsm-project').value || '').trim();
  const job     = (document.getElementById('dsm-job').value || '').trim();
  if (!project || !job) { showToast('Preencha Projeto e Job antes de atualizar.', true); return; }
  await dsmLoadStatus(project, job);
  await dsmLoadHistory(job);
}

async function dsmLoadStatus(project, job) {
  try {
    const r    = await fetch(`/orquestra/datastage/status?project=${encodeURIComponent(project)}&job_name=${encodeURIComponent(job)}`);
    if (r.status === 404) { document.getElementById('dsm-panel').style.display = 'none'; return; }
    const data = await r.json();

    document.getElementById('dsm-panel').style.display = '';
    _dsmRenderStatus(data);
    await dsmLoadHistory(job, project);
  } catch(e) {
    console.error('[DSM]', e);
  }
}

function _dsmRenderStatus(data) {
  const badge  = document.getElementById('dsm-badge');
  const sc     = data.status_code;
  const label  = data.status || 'UNKNOWN';
  const color  = sc === 1 ? 'var(--green)' : sc === 2 ? 'var(--yellow,#f59e0b)' : sc === 0 ? 'var(--primary)' : 'var(--red)';

  badge.textContent  = label;
  badge.style.background = color;
  badge.style.color  = '#fff';
  badge.style.padding = '3px 12px';
  badge.style.borderRadius = '12px';
  badge.style.fontWeight = '700';

  document.getElementById('dsm-wave').textContent   = data.wave_number ?? '—';
  document.getElementById('dsm-pid').textContent    = data.pid || '—';
  document.getElementById('dsm-polled').textContent = data.last_polled_at
    ? new Date(data.last_polled_at).toLocaleString('pt-BR') : '—';

  // Audit trail de snapshots
  const snaps   = Array.isArray(data.poll_snapshots) ? data.poll_snapshots : [];
  const trail   = document.getElementById('dsm-trail');
  if (snaps.length > 0) {
    trail.textContent = snaps.map(s => {
      const t = s.ts ? new Date(s.ts).toLocaleTimeString('pt-BR') : '?';
      return `${t} → ${s.status_text || s.status_code}`;
    }).join('  ▸  ');
  } else {
    trail.textContent = '';
  }

  // Snapshots brutos
  const snapBox = document.getElementById('dsm-snapshots');
  snapBox.textContent = snaps.length
    ? snaps.map(s => `${s.ts || ''} | code=${s.status_code} | ${s.status_text || ''}`).join('\n')
    : '(sem snapshots ainda)';

  // Jobs filhos
  const children = Array.isArray(data.child_jobs) ? data.child_jobs : [];
  const tbody     = document.querySelector('#dsm-children tbody');
  tbody.innerHTML = children.map(cj => {
    const csc   = cj.status_code;
    const cbg   = csc === 1 ? '#dcfce7' : csc === 2 ? '#fef9c3' : csc === 3 ? '#fee2e2' : '#f1f5f9';
    const ctxt  = csc === 1 ? '#16a34a' : csc === 2 ? '#a16207' : csc === 3 ? '#dc2626' : '#64748b';
    return `<tr>
      <td style="font-family:monospace;font-size:.82rem">${_escHtml(cj.name)}</td>
      <td><span style="background:${cbg};color:${ctxt};padding:2px 8px;border-radius:10px;font-size:.8rem;font-weight:600">${_escHtml(cj.status||'')}</span></td>
      <td style="text-align:center;color:var(--muted)">${cj.status_code ?? '—'}</td>
    </tr>`;
  }).join('');

  // Log summary
  const ls = typeof data.log_summary === 'string' ? data.log_summary : '';
  document.getElementById('dsm-logsum').textContent = ls || '(sem log summary neste registro)';
}

async function dsmLoadHistory(job, project) {
  try {
    let url = `/orquestra/datastage/log?job_name=${encodeURIComponent(job)}&limit=5`;
    if (project) url += `&project=${encodeURIComponent(project)}`;
    const r    = await fetch(url);
    const data = await r.json();
    const rows = (data.logs || []);
    const tbody = document.querySelector('#dsm-history tbody');
    tbody.innerHTML = rows.map(row => {
      const sc  = row.status_code;
      const bg  = sc === 1 ? '#dcfce7' : sc === 2 ? '#fef9c3' : sc === 3 || sc === null ? '#fee2e2' : '#e0f2fe';
      const txt = sc === 1 ? '#16a34a' : sc === 2 ? '#a16207' : sc === 3 ? '#dc2626' : '#0369a1';
      const upd = row.updated_at ? new Date(row.updated_at).toLocaleString('pt-BR') : '—';
      return `<tr>
        <td style="font-size:.8rem;color:var(--muted)">${row.execution_id || '—'}</td>
        <td style="font-size:.82rem">${(row.pipeline_name||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</td>
        <td><span style="background:${bg};color:${txt};padding:2px 8px;border-radius:10px;font-size:.78rem;font-weight:600">${row.status||'?'}</span></td>
        <td style="text-align:center">${row.wave_number ?? '—'}</td>
        <td style="font-size:.78rem;color:var(--muted)">${upd}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--muted)">Nenhum registro ainda</td></tr>';
  } catch(e) {
    console.error('[DSM history]', e);
  }
}

function _dsmStartAutoRefresh(project, job) {
  if (_dsmAutoRefresh) clearInterval(_dsmAutoRefresh);
  _dsmAutoRefresh = setInterval(async () => {
    if (document.getElementById('page-ds-monitor').classList.contains('active')) {
      await dsmLoadStatus(project, job);
    }
  }, 30000);
}

/* ══ COPY HELPER ══ */
function _copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const prev = btn.textContent;
    btn.textContent = '✓';
    btn.style.color = 'var(--green, #16a34a)';
    btn.style.opacity = '1';
    setTimeout(() => { btn.textContent = prev; btn.style.color = ''; btn.style.opacity = '.55'; }, 1200);
  }).catch(() => showToast('Não foi possível copiar.', true));
}

/* ══ DS MONITOR — SUB-TABS ══ */
function dsmSwitchTab(tab) {
  document.getElementById('dsm-panel-job').style.display      = tab === 'job'      ? '' : 'none';
  document.getElementById('dsm-panel-pipeline').style.display = tab === 'pipeline' ? '' : 'none';
  document.getElementById('dsm-tab-job').classList.toggle('dsm-subtab--active',      tab === 'job');
  document.getElementById('dsm-tab-pipeline').classList.toggle('dsm-subtab--active', tab === 'pipeline');
}

async function dsmPipelineLoad() {
  const pipeline = (document.getElementById('dsm-pip-name-input').value || '').trim();
  const project  = (document.getElementById('dsm-pip-project-input').value || '').trim();
  const msg = document.getElementById('dsm-pip-status-msg');
  if (!pipeline) { showToast('Informe o nome do pipeline.', true); return; }

  msg.textContent = 'Carregando…';
  document.getElementById('dsm-pip-header').style.display     = 'none';
  document.getElementById('dsm-pip-table-wrap').style.display = 'none';
  document.getElementById('dsm-pip-empty').style.display      = 'none';

  try {
    // Busca jobs da última execução via /execucoes (detail_mode)
    const params = new URLSearchParams({ detail_mode: 'true', limit: 100, filter_pipeline: pipeline });
    if (project) params.set('filter_project', project);
    const r = await fetch(ORQUESTRA_API + '/execucoes?' + params.toString(), {
      headers: authHeader ? { Authorization: authHeader } : {},
    });
    if (!r.ok) { msg.textContent = 'Erro API: ' + r.status; return; }
    const d = await r.json();
    const jobs = d.data || d.rows || [];

    // Busca logs DS (etl_ds_job_log) para cruzar status DataStage
    let dsLogs = {};
    try {
      const rl = await fetch(ORQUESTRA_API + '/datastage/log?limit=100&pipeline_name=' + encodeURIComponent(pipeline), {
        headers: authHeader ? { Authorization: authHeader } : {},
      });
      if (rl.ok) {
        const dl = await rl.json();
        (dl.logs || []).forEach(l => { dsLogs[l.job_name] = l; });
      }
    } catch(_) {}

    // Pipeline header
    const pipName    = pipeline;
    const pipProject = project || jobs[0]?.project || '';
    const pipStatus  = d.filters?.status_geral || jobs.find(j => j.status === 'RUNNING')?.status || jobs[0]?.status || '—';
    const execId     = jobs[0]?.execution_id || d.filters?.execution_id || '';

    document.getElementById('dsm-pip-name').textContent    = pipName;
    document.getElementById('dsm-pip-project').textContent = pipProject;
    _dsmSetBadge(document.getElementById('dsm-pip-status-badge'), pipStatus);
    document.getElementById('dsm-pip-header').style.display = '';

    if (!jobs.length) {
      document.getElementById('dsm-pip-empty').style.display = '';
      msg.textContent = 'Nenhum job registrado para este pipeline.';
      return;
    }

    const fmtDt = (v) => v ? String(v).slice(0,16) : '—';
    const fmtDur = (s) => {
      if (!s && s !== 0) return '—';
      const n = parseInt(s, 10); if (isNaN(n)) return '—';
      return n < 60 ? n + 's' : Math.floor(n/60) + 'm ' + (n%60) + 's';
    };

    const tbody = document.getElementById('dsm-pip-tbody');
    tbody.innerHTML = jobs.map((j, i) => {
      const dsLog  = dsLogs[j.job_name] || {};
      const wave   = dsLog.wave_number ?? '—';
      const ex     = _escHtml(j.execution_id || execId);
      const jn     = _escHtml(j.job_name || '');
      const statusLabel = dsLog.status || j.status || '—';
      let badge = '';
      const sv = (statusLabel).toUpperCase();
      if (sv === 'SUCCESS')        badge = '<span class="log-pill success">✓ SUCCESS</span>';
      else if (sv === 'RUNNING')   badge = '<span class="log-pill running">▶ RUNNING</span>';
      else if (sv === 'QUEUED')    badge = '<span class="log-pill running">◌ QUEUED</span>';
      else if (sv === 'WARNING')   badge = '<span class="log-pill warning">! WARNING</span>';
      else if (sv === 'ABORTED' || sv === 'FAILED') badge = '<span class="log-pill failed">✕ ' + sv + '</span>';
      else badge = '<span class="log-pill running">… ' + _escHtml(statusLabel) + '</span>';

      return `<tr>
        <td style="text-align:center;color:var(--muted);font-weight:600">${i+1}</td>
        <td style="font-family:monospace;font-size:.8rem;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${jn}">${jn}</td>
        <td>${badge}</td>
        <td style="text-align:center">${wave}</td>
        <td style="white-space:nowrap;font-size:.78rem">${fmtDt(j.inicio)}</td>
        <td style="white-space:nowrap;font-size:.78rem">${fmtDur(j.duration_seconds)}</td>
        <td><button class="btn-ghost btn-sm" style="font-size:11px;padding:.2rem .5rem"
          onclick="_showDsLog('${ex}','${jn}')" title="Ver log DataStage">⬡ DS Log</button></td>
      </tr>`;
    }).join('');

    document.getElementById('dsm-pip-table-wrap').style.display = '';
    msg.textContent = `Pipeline: ${jobs.length} job(s) · Execution: ${execId || '—'}`;
  } catch(e) {
    msg.textContent = 'Erro: ' + (e && e.message ? e.message : e);
  }
}

function _dsmSetBadge(el, status) {
  const v = (status || '').toUpperCase();
  const map = {
    SUCCESS: ['#dcfce7','#16a34a'],
    RUNNING: ['#dbeafe','#1d4ed8'],
    QUEUED:  ['#e0f2fe','#0369a1'],
    WARNING: ['#fef9c3','#a16207'],
    ABORTED: ['#fee2e2','#dc2626'],
    FAILED:  ['#fee2e2','#dc2626'],
  };
  const [bg, fg] = map[v] || ['var(--surface3)', 'var(--text)'];
  el.style.background = bg;
  el.style.color      = fg;
  el.textContent      = status || '—';
}

// CSS para os stat-cards do monitor (injeta uma vez)
(function() {
  if (document.getElementById('dsm-styles')) return;
  const s = document.createElement('style');
  s.id = 'dsm-styles';
  s.textContent = `
    .dsm-subtab {
      background: none;
      border: none;
      border-bottom: 3px solid transparent;
      padding: .45rem 1.1rem;
      font-size: .85rem;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
      margin-bottom: -2px;
      border-radius: 0;
      transition: color .15s, border-color .15s;
    }
    .dsm-subtab:hover { color: var(--primary); }
    .dsm-subtab--active { color: var(--primary); border-bottom-color: var(--primary); }
    .ds-stat-card {
      background: var(--surface2);
      border-radius: 8px;
      padding: .6rem 1rem;
      min-width: 120px;
      flex: 1;
    }
    .ds-stat-label {
      font-size: .72rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .05em;
      margin-bottom: .25rem;
    }
  `;
  document.head.appendChild(s);
})();
