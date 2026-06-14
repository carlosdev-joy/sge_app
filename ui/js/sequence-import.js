/* ══ IMPORTAR SEQUENCE DATASTAGE ══════════════════════════════════ */
const SEQ_PARSE_DAG   = 'etl_sequence_import_parse';
const SEQ_APPROVE_DAG = 'etl_sequence_import_approve';
let _seqImportId    = null;
let _seqPreviewData = null;
window._seqJobs     = [];  // jobs editáveis durante revisão

function openSeqImportModal() {
  _seqImportId    = null;
  _seqPreviewData = null;
  window._seqJobs = [];
  // Reset campos
  if ($('seq-project'))       $('seq-project').value = '';
  if ($('seq-name-input'))    $('seq-name-input').value = '';
  if ($('seq-domain'))        $('seq-domain').value = '';
  if ($('seq-step1-msg'))     { $('seq-step1-msg').textContent = ''; $('seq-step1-msg').className = 'msg'; }
  if ($('seq-jobs-table'))    $('seq-jobs-table').innerHTML = '';
  if ($('seq-active'))        $('seq-active').value = '1';
  if ($('seq-dag-start-date')) {
    const today = new Date(); const y=today.getFullYear(), m=String(today.getMonth()+1).padStart(2,'0'), d=String(today.getDate()).padStart(2,'0');
    $('seq-dag-start-date').value = y+'-'+m+'-'+d;
  }
  if ($('seq-msg-inicio'))    $('seq-msg-inicio').checked = true;
  if ($('seq-msg-fim'))       $('seq-msg-fim').checked = true;
  if ($('seq-msg-erro'))      $('seq-msg-erro').checked = true;
  _seqShowStep(1);
  $('modal-seq-import').classList.add('open');
  setTimeout(() => { try { $('seq-name-input').focus(); } catch(e) {} }, 120);
}

function closeSeqImportModal() {
  $('modal-seq-import').classList.remove('open');
  _seqImportId    = null;
  _seqPreviewData = null;
  window._seqJobs = [];
}

function _seqShowStep(n) {
  [1, 2, 3].forEach(i => {
    const el = $('seq-step-' + i);
    if (el) el.style.display = i === n ? '' : 'none';
  });
  const labels = {
    1: 'Etapa 1 de 3 — Configuração',
    2: 'Etapa 2 de 3 — Revisão',
    3: 'Etapa 3 de 3 — Agendamento e Aprovação',
  };
  if ($('seq-step-label')) $('seq-step-label').textContent = labels[n] || '';
}

function seqImportBack()    { _seqShowStep(1); }
function seqImportBackTo2() { _seqShowStep(2); }

function _seqSchTypeChange() {
  const type = $('seq-sch-type') ? $('seq-sch-type').value : 'daily';
  if ($('seq-sch-time-row')) $('seq-sch-time-row').style.display = type === 'hourly' ? 'none' : 'flex';
  if ($('seq-sch-dow-row'))  $('seq-sch-dow-row').style.display  = type === 'weekly'  ? 'flex' : 'none';
  if ($('seq-sch-dom-row'))  $('seq-sch-dom-row').style.display  = type === 'monthly' ? 'flex' : 'none';
  _seqSchPreview();
}

function _seqSchPreview() {
  const type = $('seq-sch-type') ? $('seq-sch-type').value : 'daily';
  const h   = parseInt($('seq-sch-hour')   ? $('seq-sch-hour').value   : 6)  || 0;
  const m   = parseInt($('seq-sch-minute') ? $('seq-sch-minute').value : 0)  || 0;
  const dow = $('seq-sch-dow') ? $('seq-sch-dow').value : 1;
  const dom = parseInt($('seq-sch-dom') ? $('seq-sch-dom').value : 1) || 1;
  let cron;
  if (type === 'hourly')  cron = m + ' * * * *';
  else if (type === 'weekly')  cron = m + ' ' + h + ' * * ' + dow;
  else if (type === 'monthly') cron = m + ' ' + h + ' ' + dom + ' * *';
  else cron = m + ' ' + h + ' * * *';
  if ($('seq-sch-preview')) $('seq-sch-preview').textContent = 'cron: ' + cron;
  return cron;
}

function _seqSchGetConf() {
  const type = $('seq-sch-type') ? $('seq-sch-type').value : 'daily';
  const h   = parseInt($('seq-sch-hour')   ? $('seq-sch-hour').value   : 6);
  const m   = parseInt($('seq-sch-minute') ? $('seq-sch-minute').value : 0);
  const dow = type === 'weekly'  ? parseInt($('seq-sch-dow') ? $('seq-sch-dow').value : 1)  : null;
  const dom = type === 'monthly' ? parseInt($('seq-sch-dom') ? $('seq-sch-dom').value : 1)  : null;
  return {
    schedule_type: type,
    schedule_hour: isNaN(h) ? 6 : h,
    schedule_minute: isNaN(m) ? 0 : m,
    schedule_dow: isNaN(dom) ? null : dow,
    schedule_dom: isNaN(dom) ? null : dom,
  };
}

/* ─── Etapa 1 → disparar DAG de parse ──────────────────────────── */
async function seqImportAnalyze() {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  const project = $('seq-project') ? $('seq-project').value : '';
  const seqName = $('seq-name-input') ? $('seq-name-input').value.trim() : '';
  const domain  = $('seq-domain') ? $('seq-domain').value.trim() : '';
  const msg = $('seq-step1-msg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }

  if (!project) { if (msg) { msg.textContent = 'Selecione o projeto.'; msg.className = 'msg erro'; } return; }
  if (!seqName) { if (msg) { msg.textContent = 'Informe o nome da sequence.'; msg.className = 'msg erro'; } return; }
  if (!domain)  { if (msg) { msg.textContent = 'Informe o domínio.'; msg.className = 'msg erro'; } return; }

  const btn    = $('btn-seq-analyze');
  const btnTxt = $('btn-seq-analyze-txt');
  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = '⏳ Analisando...';

  try {
    const importedBy = window.__currentUser || ($('who') ? $('who').textContent.trim() : 'system');

    if (msg) { msg.textContent = 'Analisando sequence...'; msg.className = 'msg'; }
    const r = await fetch(ORQUESTRA_API + '/sequence/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({
        project_name: project,
        seq_name:     seqName,
        imported_by:  importedBy,
        domain:       domain || null,
      }),
    });
    const payload = await r.json().catch(() => null);
    if (!r.ok) {
      const errMsg = (payload && payload.detail) ? payload.detail : ('HTTP ' + r.status);
      if (msg) { msg.textContent = 'Erro: ' + (typeof errMsg === 'string' ? errMsg : JSON.stringify(errMsg)); msg.className = 'msg erro'; }
      return;
    }
    if (!payload || payload.erro) {
      if (msg) { msg.textContent = payload && payload.erro ? payload.erro : 'Resultado inválido.'; msg.className = 'msg erro'; }
      return;
    }

    _seqImportId    = payload.import_id;
    _seqPreviewData = payload;
    _seqRenderPreview(payload);
    _seqShowStep(2);

  } catch (e) {
    if (msg) { msg.textContent = 'Erro: ' + (e && e.message ? e.message : e); msg.className = 'msg erro'; }
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Analisar sequence →';
  }
}

/* ─── Renderizar preview da etapa 2 ────────────────────────────── */
function _seqRenderPreview(payload) {
  if ($('seq-preview-name'))    $('seq-preview-name').textContent = payload.seq_name || '—';
  if ($('seq-preview-project')) $('seq-preview-project').textContent = payload.project_name || '';
  const jobs = payload.jobs || [];
  if ($('seq-preview-count')) $('seq-preview-count').textContent = jobs.length + ' job(s)';

  // Sugestão de nome do pipeline (já sanitizado pela DAG)
  if ($('seq-pipeline-name'))
    $('seq-pipeline-name').value = (payload.pipeline_name_suggestion || '').toUpperCase();

  // Guardar cópia mutável para edição de nomes
  window._seqJobs = jobs.map(j => ({ ...j }));

  const tbl = $('seq-jobs-table');
  if (!tbl) return;
  if (!jobs.length) {
    tbl.innerHTML = '<div class="empty-state"><span class="es-icon">⬡</span><p class="es-title">Nenhum job encontrado na sequence.</p></div>';
    return;
  }

  tbl.innerHTML = jobs.map((j, i) => {
    const linItems = (j.lineage || []).map(l => {
      const dir = (l.direction || '').toLowerCase();
      const clr = dir.startsWith('orig') ? '#185FA5' : dir.startsWith('dest') ? '#27500A' : '#3C3489';
      const lbl = dir.startsWith('orig') ? 'Origem' : dir.startsWith('dest') ? 'Destino' : 'Transf.';
      const detail = l.file_path || (l.sql_expression || '').replace(/\n/g, ', ') || '';
      return '<div style="font-size:11px;padding:2px 0;border-bottom:1px solid var(--border);display:grid;grid-template-columns:52px 1fr auto;gap:6px;align-items:baseline">' +
        '<span style="font-weight:600;color:' + clr + '">' + lbl + '</span>' +
        '<span style="font-family:monospace">' + (l.object_name || '—') + '</span>' +
        (detail ? '<span style="color:var(--muted);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px" title="' + detail + '">' + detail + '</span>' : '') +
      '</div>';
    }).join('');

    return '<div id="seq-job-row-' + i + '" style="border:1px solid var(--border);border-radius:10px;margin-bottom:5px;overflow:hidden">' +
      '<div style="display:grid;grid-template-columns:26px 1fr 80px 70px 24px;gap:6px;align-items:center;padding:.45rem .65rem;background:var(--bg)">' +
        '<span style="font-size:11px;font-weight:700;color:var(--muted);text-align:center">' + (j.execution_order + 1) + '</span>' +
        '<input type="text" style="font-size:13px;padding:.3rem .5rem;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text)"' +
          ' value="' + (j.job_name_orq || '') + '"' +
          ' oninput="if(window._seqJobs[' + i + ']) window._seqJobs[' + i + '].job_name_orq=this.value" />' +
        '<span class="tag-pill" style="text-align:center;white-space:nowrap">' + (j.lineage_count || 0) + ' obj.</span>' +
        (j.lineage_count
          ? '<button class="btn-ghost btn-sm" style="font-size:11px;padding:.22rem .45rem" onclick="_seqToggleLineage(' + i + ')">+ Lineage</button>'
          : '<span style="font-size:11px;color:var(--muted)">—</span>'
        ) +
        '<button style="border:none;background:none;cursor:pointer;color:var(--muted);font-size:16px;padding:0;line-height:1" title="Ignorar este job" onclick="_seqToggleIgnore(' + i + ', this)">×</button>' +
      '</div>' +
      '<div id="seq-lin-' + i + '" style="display:none;padding:.45rem .65rem;background:var(--card);border-top:1px solid var(--border);font-size:11px">' +
        (linItems || '<span style="color:var(--muted)">Lineage não extraída.</span>') +
      '</div>' +
    '</div>';
  }).join('');
}

function _seqToggleLineage(idx) {
  const el = $('seq-lin-' + idx);
  if (el) el.style.display = el.style.display === 'none' ? '' : 'none';
}

function _seqToggleIgnore(idx, btn) {
  if (!window._seqJobs[idx]) return;
  const ignored = !window._seqJobs[idx]._ignored;
  window._seqJobs[idx]._ignored = ignored;
  const row = $('seq-job-row-' + idx);
  if (row) row.style.opacity = ignored ? '0.35' : '1';
  btn.title = ignored ? 'Reativar este job' : 'Ignorar este job';
  btn.textContent = ignored ? '↩' : '×';
}

/* ─── Etapa 2 → etapa 3 ─────────────────────────────────────────── */
function seqImportGoStep3() {
  const pipeName = $('seq-pipeline-name') ? $('seq-pipeline-name').value.trim() : '';
  const msg = $('seq-step2-msg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }
  if (!pipeName) {
    if (msg) { msg.textContent = 'Informe o nome do pipeline no ORQUESTRA.'; msg.className = 'msg erro'; }
    return;
  }
  _seqSchPreview();
  _seqShowStep(3);
}

/* ─── Etapa 3 → aprovação ───────────────────────────────────────── */
async function approveSeqImport() {
  if (!authHeader) { showToast('Faça login primeiro.', true); return; }
  if (!_seqImportId) { showToast('Import ID inválido. Refaça a análise.', true); return; }

  const pipeName = $('seq-pipeline-name') ? $('seq-pipeline-name').value.trim().toUpperCase() : '';
  const msg = $('seq-step3-msg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }
  if (!pipeName) {
    if (msg) { msg.textContent = 'Informe o nome do pipeline.'; msg.className = 'msg erro'; }
    return;
  }

  const schedConf   = _seqSchGetConf();
  const cron        = _seqSchPreview();
  const reviewedBy  = window.__currentUser || ($('who') ? $('who').textContent.trim() : 'system');

  const btn    = $('btn-seq-approve');
  const btnTxt = $('btn-seq-approve-txt');
  if (btn) btn.disabled = true;
  if (btnTxt) btnTxt.textContent = '⏳ Importando...';
  if (msg) { msg.textContent = 'Aprovando importação...'; msg.className = 'msg'; }

  try {
    const r = await fetch(ORQUESTRA_API + '/sequence/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._orqAuthHeader() },
      body: JSON.stringify({
        import_id:              _seqImportId,
        reviewed_by:            reviewedBy,
        pipeline_name_override: pipeName,
        ...schedConf,
        active:           parseInt($('seq-active') ? $('seq-active').value : 1),
        dag_start_date:   $('seq-dag-start-date') ? $('seq-dag-start-date').value : '',
        envia_msg_inicio: ($('seq-msg-inicio') && $('seq-msg-inicio').checked) ? 1 : 0,
        envia_msg_fim:    ($('seq-msg-fim')    && $('seq-msg-fim').checked)    ? 1 : 0,
        envia_msg_erro:   ($('seq-msg-erro')   && $('seq-msg-erro').checked)   ? 1 : 0,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const errMsg = data.detail || data.message || ('HTTP ' + r.status);
      if (msg) { msg.textContent = 'Erro: ' + (typeof errMsg === 'string' ? errMsg : JSON.stringify(errMsg)); msg.className = 'msg erro'; }
      return;
    }
    closeSeqImportModal();
    showToast('Pipeline "' + pipeName + '" importado com sucesso!', false);
    try { loadQuery(0); } catch(e) {}
  } catch (e) {
    if (msg) { msg.textContent = 'Erro: ' + (e && e.message ? e.message : e); msg.className = 'msg erro'; }
  } finally {
    if (btn) btn.disabled = false;
    if (btnTxt) btnTxt.textContent = 'Aprovar e Importar';
  }
}

// Fechar ao clicar fora
document.getElementById('modal-seq-import').addEventListener('click', function(e) {
  if (e.target === this) closeSeqImportModal();
});
document.getElementById('modal-changelog') && document.getElementById('modal-changelog').addEventListener('click', function(e) {
  if (e.target === this) closeChangelog();
});
