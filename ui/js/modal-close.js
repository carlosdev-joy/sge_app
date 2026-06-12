  // Fecha modais clicando fora
  (function () {
    const m = document.getElementById('jobEditModal');
    if (!m) return;
    m.addEventListener('click', (e) => { if (e.target === m) closeJobEdit(); });
  })();
  (function () {
    const m = document.getElementById('jobCreateModal');
    if (!m) return;
    m.addEventListener('click', (e) => { if (e.target === m) closeJobCreateModal(); });
  })();
  (function () {
    const m = document.getElementById('logDetailModal');
    if (!m) return;
    m.addEventListener('click', (e) => { if (e.target === m) closeLogDetail(); });
  })();
  (function () {
    const m = document.getElementById('lineageDSXPreviewModal');
    if (!m) return;
    m.addEventListener('click', (e) => { if (e.target === m) closeLineageDSXPreview(); });
  })();
