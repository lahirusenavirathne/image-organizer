'use strict';
const button = document.getElementById('copy-api-token');
if (button) {
  button.addEventListener('click', async () => {
    const field = document.getElementById('new-api-token');
    if (!field) return;
    try {
      await navigator.clipboard.writeText(field.value);
      button.textContent = 'Copied';
    } catch (_) {
      field.focus(); field.select();
      button.textContent = 'Select and copy the token';
    }
  });
}
