/* ══ S1 — Audit Trail ══════════════════════════════════════════════════ */
const AUDIT_DAG_ID = 'etl_pipeline_audit_query';

function closeAuditModal() {
  const m = $('modal-audit');
  if (m) m.style.display = 'none';
}
document.getElementById('modal-audit').addEventListener('click', function(e) {
  if (e.target === this) closeAuditModal();
});

async function openPipelineAudit(idx) {
  const p = (window.__pipelines || [])[idx];
  if (!p) return;
  const modal = $('modal-audit');
  const body  = $('audit-modal-body');
  $('audit-modal-title').textContent = 'Histórico — ' + p.pipeline_name;
  $('audit-modal-sub').textContent   = p.project_name + ' · ' + (p.domain || '');
  body.innerHTML = '<div class="empty-state"><span class="es-icon">⏳</span><p class="es-title">Consultando...</p></div>';
  modal.style.display = 'flex';

  try {
    const r = await fetch(ORQUESTRA_API + '/audit?pipeline_name=' + encodeURIComponent(p.pipeline_name) + '&limit=50');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const payload = await r.json();
    _renderAuditTable(payload, body);
  } catch(e) {
    body.innerHTML = '<p style="color:var(--red);font-size:13px;padding:1rem">Erro: ' + (e.message || e) + '</p>';
  }
}

function _renderAuditTable(payload, body) {
  const rows = (payload && (payload.data || payload)) || [];
  if (!Array.isArray(rows) || rows.length === 0) {
    body.innerHTML =
      '<div class="empty-state"><span class="es-icon">📋</span>' +
      '<p class="es-title">Sem histórico registrado</p>' +
      '<p class="es-sub">Alterações futuras aparecerão aqui.</p></div>';
    return;
  }
  // Group by date (YYYY-MM-DD)
  const byDate = {};
  rows.forEach(r => {
    const dt = (r.changed_at || r.timestamp || '').toString();
    const day = dt.split('T')[0] || dt.substring(0,10) || 'Desconhecido';
    if (!byDate[day]) byDate[day] = [];
    byDate[day].push(r);
  });
  const note = '<div style="font-size:11px;color:var(--muted);margin-bottom:.75rem;padding:.4rem .6rem;background:rgba(128,128,128,.07);border-radius:8px;border:1px solid var(--border)">' +
    '📌 São exibidas as <strong>últimas 10 alterações</strong> por pipeline (configurável em Admin → Configurações). O registro de <em>criação</em> é sempre preservado.' +
    '</div>';
  let html = note;
  const dateKeys = Object.keys(byDate).sort((a,b)=>b.localeCompare(a));
  dateKeys.forEach((day, di) => {
    const dayRows = byDate[day];
    const totalFields = dayRows.length;
    const user = dayRows[0] ? (dayRows[0].changed_by || '—') : '—';
    const groupId = 'aud-grp-' + di;
    const fmt = day.split('-').reverse().join('/');
    html += '<div style="border:1px solid var(--border);border-radius:10px;margin-bottom:.5rem;overflow:hidden">' +
      '<div onclick="document.getElementById(\'' + groupId + '\').style.display=document.getElementById(\'' + groupId + '\').style.display===\'none\'?\'table-row-group\':\'\';this.querySelector(\'.aud-arrow\').textContent=document.getElementById(\'' + groupId + '\').style.display===\'none\'?\'▶\':\'▼\'" ' +
      'style="display:flex;align-items:center;justify-content:space-between;padding:.5rem .75rem;cursor:pointer;background:rgba(128,128,128,.04);border-bottom:1px solid transparent;user-select:none">' +
        '<span style="font-size:12px;font-weight:600">' + fmt + '</span>' +
        '<span style="font-size:11px;color:var(--muted)">' + _escHtml(user) + ' · ' + totalFields + ' campo(s)</span>' +
        '<span class="aud-arrow" style="font-size:10px;color:var(--muted)">▶</span>' +
      '</div>' +
      '<table style="width:100%;border-collapse:collapse;font-size:11px;display:none" id="' + groupId + '">' +
      '<thead><tr style="background:rgba(128,128,128,.04)">' +
        '<th style="padding:.3rem .6rem;text-align:left;color:var(--muted);font-weight:600;width:100px">Hora</th>' +
        '<th style="padding:.3rem .6rem;text-align:left;color:var(--muted);font-weight:600;width:100px">Usuário</th>' +
        '<th style="padding:.3rem .6rem;text-align:left;color:var(--muted);font-weight:600">Campo</th>' +
        '<th style="padding:.3rem .6rem;text-align:left;color:var(--muted);font-weight:600">Antes</th>' +
        '<th style="padding:.3rem .6rem;text-align:left;color:var(--muted);font-weight:600">Depois</th>' +
      '</tr></thead>' +
      '<tbody id="' + groupId + '-body">' +
      dayRows.map(r => {
        const dt = (r.changed_at || r.timestamp || '');
        const time = dt.includes('T') ? dt.split('T')[1].substring(0,8) : dt.substring(11,19);
        return '<tr style="border-top:1px solid var(--border)">' +
          '<td style="padding:.25rem .6rem;color:var(--muted)">' + _escHtml(time) + '</td>' +
          '<td style="padding:.25rem .6rem">' + _escHtml(r.changed_by || '—') + '</td>' +
          '<td style="padding:.25rem .6rem;font-weight:500">' + _escHtml(r.field_name || r.campo || '—') + '</td>' +
          '<td style="padding:.25rem .6rem;color:var(--muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + _escHtml(String(r.old_value||'')) + '">' + _escHtml(String(r.old_value||'—').substring(0,60)) + '</td>' +
          '<td style="padding:.25rem .6rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + _escHtml(String(r.new_value||'')) + '">' + _escHtml(String(r.new_value||'—').substring(0,60)) + '</td>' +
        '</tr>';
      }).join('') +
      '</tbody></table></div>';
  });
  body.innerHTML = html;
}
