  // Modal de confirmação — substitui confirm() nativo
  let _confirmResolve = null;

  function showConfirm(msg, title) {
    $('confirm-title').textContent = title || 'Confirmar ação';
    $('confirm-msg').textContent   = msg;
    $('confirmModal').classList.add('open');
    return new Promise(resolve => { _confirmResolve = resolve; });
  }

  function closeConfirm(result) {
    $('confirmModal').classList.remove('open');
    if (_confirmResolve) { _confirmResolve(result); _confirmResolve = null; }
  }

  // Fecha clicando fora
  document.getElementById('confirmModal').addEventListener('click', function(e) {
    if (e.target === this) closeConfirm(false);
  });
