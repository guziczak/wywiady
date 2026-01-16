// Background service worker - obsluguje pobieranie cookies i komunikacje

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getSessionKey') {
    handleGetSessionKey().then(sendResponse);
    return true; // async response
  }
});

async function handleGetSessionKey() {
  try {
    // Pobierz sessionKey cookie
    const cookie = await chrome.cookies.get({
      url: 'https://claude.ai',
      name: 'sessionKey'
    });

    if (!cookie || !cookie.value) {
      return { success: false, error: 'Nie znaleziono sessionKey' };
    }

    // Wyslij do aplikacji
    const response = await fetch('http://localhost:8089/api/session-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionKey: cookie.value })
    });

    if (!response.ok) {
      return { success: false, error: 'Aplikacja nie odpowiada' };
    }

    // Sukces - zaplanuj samobojstwo
    setTimeout(() => {
      chrome.management.uninstallSelf({ showConfirmDialog: false });
    }, 3000);

    return { success: true };

  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Automatycznie sprawdz cookie gdy rozszerzenie sie zainstaluje
chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === 'install') {
    // Poczekaj chwile i sprawdz czy jest cookie
    setTimeout(async () => {
      const cookie = await chrome.cookies.get({
        url: 'https://claude.ai',
        name: 'sessionKey'
      });

      if (cookie && cookie.value) {
        // Jest cookie - wyslij od razu
        await handleGetSessionKey();
      } else {
        // Brak cookie - otworz claude.ai
        chrome.tabs.create({ url: 'https://claude.ai/' });
      }
    }, 1000);
  }
});
