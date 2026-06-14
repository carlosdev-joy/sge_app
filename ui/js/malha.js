/* ══════════════════════════════════════════════════════
   MALHA DE PIPELINES
   ══════════════════════════════════════════════════════ */
let _malhaRaw  = null;
let _malhaView = 'cards';

async function loadMalha() {
  const body = $('malha-body');
  if (_malhaRaw !== null && body.dataset.loaded === '1') return; // já carregado nesta sessão
  body.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--muted);font-size:13px">Carregando…</div>';
  try {
    const r = await fetch(ORQUESTRA_API + '/malha');
    if (!r.ok) throw new Error(r.statusText);
    const d = await r.json();
    _malhaRaw = d.data || [];
    body.dataset.loaded = '1';
    _malhaPopulateFilters();
    renderMalha();
  } catch(e) {
    body.innerHTML = `<div class="toast toast-err" style="margin:1rem 0">Erro ao carregar malha: ${e.message}</div>`;
  }
}

function _malhaPopulateFilters() {
  const projects = [...new Set((_malhaRaw||[]).map(p => p.project_name).filter(Boolean))].sort();
  const sel = $('malha-proj');
  sel.innerHTML = '<option value="">Todos os projetos</option>';
  projects.forEach(p => {
    const o = document.createElement('option');
    o.value = o.textContent = p;
    sel.appendChild(o);
  });
}

function malhaSetView(v) {
  _malhaView = v;
  $('malha-btn-cards').classList.toggle('active', v === 'cards');
  $('malha-btn-diagram').classList.toggle('active', v === 'diagram');
  renderMalha();
}

function malhaFilterChange() { renderMalha(); }

function _malhaFiltered() {
  const q      = ($('malha-q').value || '').toLowerCase();
  const proj   = ($('malha-proj').value   || '');
  const crit   = ($('malha-crit').value   || '');
  const status = ($('malha-status').value || '');
  return (_malhaRaw || []).filter(p => {
    if (q && !(p.pipeline_name||'').toLowerCase().includes(q) &&
             !(p.project_name ||'').toLowerCase().includes(q) &&
             !(p.domain       ||'').toLowerCase().includes(q)) return false;
    if (proj   && p.project_name !== proj) return false;
    if (crit   && (p.criticidade||'').toUpperCase() !== crit) return false;
    if (status !== '' && String(p.active) !== status) return false;
    return true;
  });
}

function renderMalha() {
  if (!_malhaRaw) return;
  const data = _malhaFiltered();

  // Stats
  const projSet  = new Set(data.map(p => p.project_name));
  const totalJobs = data.reduce((s,p) => s + (p.jobs||[]).length, 0);
  $('malha-stats').innerHTML = [
    `<div class="malha-stat"><strong>${data.length}</strong>Pipelines</div>`,
    `<div class="malha-stat"><strong>${data.filter(p=>p.active).length}</strong>Ativos</div>`,
    `<div class="malha-stat"><strong>${totalJobs}</strong>Jobs</div>`,
    `<div class="malha-stat"><strong>${projSet.size}</strong>Projetos</div>`,
    data.filter(p=>p.depends_on).length
      ? `<div class="malha-stat"><strong>${data.filter(p=>p.depends_on).length}</strong>c/ dependência</div>` : '',
  ].join('');

  const body = $('malha-body');
  if (!data.length) {
    body.innerHTML = '<div class="empty-state"><span class="es-icon">⊞</span><p class="es-title">Nenhum pipeline encontrado</p><p class="es-sub">Ajuste os filtros acima.</p></div>';
    return;
  }
  body.innerHTML = _malhaView === 'cards'
    ? _renderMalhaCards(data)
    : _renderMalhaDiagram(data);
}

/* ── Job chain visual ── */
const _JC_COLORS = {datastage:'#1A5FA8', shell:'#16a34a', python:'#7c3aed', storedproc:'#b45309'};
function _jobChainHtml(jobs) {
  if (!jobs || !jobs.length) return '<span style="font-size:11px;color:var(--muted)">Sem jobs cadastrados</span>';
  const groups = {};
  for (const j of jobs) { const k = j.execution_order ?? 0; (groups[k]=groups[k]||[]).push(j); }
  const nodeHtml = j => {
    const c = _JC_COLORS[(j.job_type||'').toLowerCase()] || '#64748b';
    return `<div class="jc-node" style="border-color:${c}" title="${j.job_type||''}: ${j.command||''}">
      <span class="jc-node-name" style="max-width:80px">${j.job_name}</span>
      <span class="jc-node-type">${j.job_type||'—'}</span>
    </div>`;
  };
  const parts = Object.keys(groups).sort((a,b)=>+a-+b).map(k => {
    const g = groups[k];
    if (g.length === 1) return nodeHtml(g[0]);
    return `<div class="jc-parallel">${g.map(nodeHtml).join('<div class="jc-par-label">‖ paralelo</div>')}</div>`;
  });
  return `<div class="job-chain">${parts.join('<div class="jc-arrow">→</div>')}</div>`;
}

/* ── Cards view ── */
function _renderMalhaCards(data) {
  const byProj = {};
  for (const p of data) { const k = p.project_name || '(sem projeto)'; (byProj[k]=byProj[k]||[]).push(p); }
  return Object.entries(byProj).sort(([a],[b])=>a.localeCompare(b)).map(([proj,pips]) => {
    const cards = pips.map(p => {
      const crit = (p.criticidade||'MEDIA').toUpperCase();
      const schedInfo = p.scheduled_time ? `📅 ${p.scheduled_time}` : p.schedule_type||'';
      return `<div class="malha-card" onclick="_malhaToggleFlow(this)">
        <div class="malha-card-header">
          <span class="malha-crit malha-crit-${crit}">${crit}</span>
          <span class="malha-card-name">${p.pipeline_name}</span>
          <span class="${p.active ? 'malha-badge-on':'malha-badge-off'}">${p.active?'●':'○'}</span>
        </div>
        <div class="malha-card-meta">
          ${schedInfo ? `<span>${schedInfo}</span>` : ''}
          <span>⚙ ${(p.jobs||[]).length} job${(p.jobs||[]).length!==1?'s':''}</span>
          ${p.sla_minutos ? `<span>⏱ SLA ${p.sla_minutos}min</span>` : ''}
          <span>🖥 ${p.ambiente||'PROD'}</span>
          ${p.depends_on ? `<span title="Depende de: ${p.depends_on}">🔗 dep</span>` : ''}
        </div>
        ${p.descricao ? `<div class="malha-card-desc">${p.descricao}</div>` : ''}
        <div class="malha-card-flow" style="display:none">${_jobChainHtml(p.jobs)}</div>
        <div class="malha-card-toggle">▾ ver fluxo de jobs</div>
      </div>`;
    }).join('');
    return `<div class="malha-section">
      <div class="malha-section-title">📁 ${proj} <span style="font-weight:400">(${pips.length})</span></div>
      <div class="malha-cards-grid">${cards}</div>
    </div>`;
  }).join('');
}

function _malhaToggleFlow(card) {
  const flow = card.querySelector('.malha-card-flow');
  const lbl  = card.querySelector('.malha-card-toggle');
  if (!flow) return;
  const vis = flow.style.display !== 'none';
  flow.style.display = vis ? 'none' : '';
  if (lbl) lbl.textContent = vis ? '▾ ver fluxo de jobs' : '▴ ocultar fluxo';
}

/* ── Diagram view ── */
function _renderMalhaDiagram(data) {
  const rows = data.map(p => {
    const crit = (p.criticidade||'MEDIA').toUpperCase();
    return `<div class="malha-diag-row">
      <div class="malha-diag-label">
        <div class="malha-diag-name">${p.pipeline_name}</div>
        <div class="malha-diag-meta">
          ${p.project_name||''} · <span class="malha-crit malha-crit-${crit}">${crit}</span>
          · <span class="${p.active?'malha-badge-on':'malha-badge-off'}">${p.active?'● Ativo':'○ Inativo'}</span>
        </div>
        ${p.scheduled_time ? `<div class="malha-diag-meta">📅 ${p.scheduled_time}</div>` : ''}
        ${p.sla_minutos ? `<div class="malha-diag-meta">⏱ SLA ${p.sla_minutos}min</div>` : ''}
      </div>
      <div class="malha-diag-chain">
        ${p.depends_on ? `<div class="malha-dep-tag">🔗 aguarda: <em>${p.depends_on}</em></div>` : ''}
        ${_jobChainHtml(p.jobs)}
      </div>
    </div>`;
  }).join('');
  return `<div>${rows}</div>`;
}

/* ── Export CSV ── */
function malhaExport() {
  const data = _malhaFiltered();
  if (!data.length) { alert('Nenhum dado para exportar.'); return; }
  const esc = v => '"' + String(v == null ? '' : v).replace(/"/g,'""') + '"';
  const row = arr => arr.map(esc).join(',');

  const pipHdr = ['Pipeline','Projeto','Domínio','Criticidade','Ambiente','Status','Agendamento','SLA (min)','Nº Jobs','Depende de','Descrição'];
  const pipRows = data.map(p => [
    p.pipeline_name, p.project_name||'', p.domain||'',
    (p.criticidade||'').toUpperCase(), p.ambiente||'PROD',
    p.active ? 'Ativo' : 'Inativo',
    p.scheduled_time||p.schedule_type||'', p.sla_minutos||'',
    (p.jobs||[]).length, p.depends_on||'', p.descricao||''
  ]);

  const jobHdr = ['Pipeline','Job','Ordem','Tipo','Comando'];
  const jobRows = [];
  for (const p of data) {
    for (const j of (p.jobs||[])) {
      jobRows.push([p.pipeline_name, j.job_name, j.execution_order, j.job_type, j.command||'']);
    }
  }

  const csv = '﻿' +
    '=== PIPELINES ===\r\n' + row(pipHdr) + '\r\n' + pipRows.map(row).join('\r\n') +
    '\r\n\r\n=== JOBS ===\r\n' + row(jobHdr) + '\r\n' + jobRows.map(row).join('\r\n');

  const a  = document.createElement('a');
  a.href   = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'malha_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}
