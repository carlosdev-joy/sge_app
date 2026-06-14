  // Atualizar display do nome no step 2
  const _admWizOrig = _admDeleteWizardStep;
  _admDeleteWizardStep = function(n) {
    _admWizOrig(n);
    if (n === 2) {
      const nameEl = $('adm-wizard-pipeline-name');
      const dispEl = $('adm-wiz-pipeline-display');
      if (nameEl && dispEl) dispEl.textContent = nameEl.textContent;
    }
  };
  // Fechar ao clicar fora
  document.getElementById('modal-adm-delete-wizard').addEventListener('click', function(e) {
    if (e.target === this) _admDeleteWizardClose();
  });
