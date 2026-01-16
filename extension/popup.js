document.getElementById('sendBtn').addEventListener('click', async () => {
  const btn = document.getElementById('sendBtn');
  const status = document.getElementById('status');

  btn.disabled = true;
  btn.textContent = 'Pobieram...';
  status.style.display = 'none';

  try {
    // Pobierz sessionKey cookie z claude.ai
    const cookie = await chrome.cookies.get({
      url: 'https://claude.ai',
      name: 'sessionKey'
    });

    if (!cookie || !cookie.value) {
      throw new Error('Nie znaleziono sessionKey. Zaloguj sie na claude.ai');
    }

    // Wyslij do aplikacji
    const response = await fetch('http://localhost:8089/api/session-key', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sessionKey: cookie.value })
    });

    if (!response.ok) {
      throw new Error('Aplikacja nie odpowiada. Sprawdz czy jest uruchomiona.');
    }

    const result = await response.json();

    status.textContent = 'Klucz wyslany! Rozszerzenie zostanie usuniete...';
    status.className = 'success';
    status.style.display = 'block';
    btn.textContent = 'Gotowe!';

    // Samobójstwo rozszerzenia po 2 sekundach
    setTimeout(() => {
      chrome.management.uninstallSelf({ showConfirmDialog: false });
    }, 2000);

  } catch (error) {
    status.textContent = error.message;
    status.className = 'error';
    status.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Wyslij klucz do aplikacji';
  }
});
