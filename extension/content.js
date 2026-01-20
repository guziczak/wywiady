// Content script - uruchamia sie automatycznie na claude.ai

(async function() {
  // Sprawdz czy juz wyslalismy (zeby nie powtarzac)
  const storage = await chrome.storage.local.get('keySent');
  if (storage.keySent) {
    return;
  }

  // Poczekaj az strona sie zaladuje i sprawdz czy user jest zalogowany
  // (obecnosc elementow UI wskazuje na zalogowanie)
  await new Promise(resolve => setTimeout(resolve, 2000));

  // Popros background o wyslanie klucza
  const result = await chrome.runtime.sendMessage({ action: 'getSessionKey' });

  if (result && result.success) {
    // Zapisz ze wyslalismy
    await chrome.storage.local.set({ keySent: true });

    // Pokaz komunikat userowi
    showNotification('Wizyta polaczona! Klucz zostal wyslany. To okno mozesz zamknac.');
  }
})();

function showNotification(message) {
  const div = document.createElement('div');
  div.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #10b981;
    color: white;
    padding: 16px 24px;
    border-radius: 8px;
    font-family: system-ui, sans-serif;
    font-size: 14px;
    z-index: 999999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    animation: slideIn 0.3s ease;
  `;
  div.textContent = message;

  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(div);

  // Zniknie po 5 sekundach
  setTimeout(() => div.remove(), 5000);
}
