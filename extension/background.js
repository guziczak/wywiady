// Background service worker - obsluguje pobieranie cookies i komunikacje

const TARGET_URL = 'https://claude.ai';
const COOKIE_NAME = 'sessionKey';
const API_URL = 'http://localhost:8089/api/session-key';

// 1. Sluchaj wiadomosci (jesli ktos ja wywola recznie)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getSessionKey') {
    checkAndSendKey().then(sendResponse);
    return true;
  }
});

// 2. Sluchaj zmian w ciasteczkach (gdy uzytkownik sie zaloguje)
chrome.cookies.onChanged.addListener((changeInfo) => {
  if (changeInfo.cookie.domain.includes('claude.ai') && 
      changeInfo.cookie.name === COOKIE_NAME && 
      !changeInfo.removed) {
    console.log("Wykryto nowe ciasteczko sessionKey!");
    checkAndSendKey();
  }
});

// 3. Sprawdz przy starcie
chrome.runtime.onInstalled.addListener(() => {
  console.log("Rozszerzenie zainstalowane/odswiezone.");
  // Otworz Claude jesli nie jest otwarty
  chrome.tabs.query({url: "https://claude.ai/*"}, (tabs) => {
    if (tabs.length === 0) {
      chrome.tabs.create({ url: TARGET_URL });
    }
  });
  
  // Sprobuj pobrac klucz po chwiler
  setTimeout(checkAndSendKey, 1000);
});

async function checkAndSendKey() {
  try {
    const cookie = await chrome.cookies.get({
      url: TARGET_URL,
      name: COOKIE_NAME
    });

    if (!cookie || !cookie.value) {
      console.log("Brak ciasteczka sessionKey.");
      return { success: false, error: 'Brak sessionKey' };
    }

    console.log("Mamy klucz! Wysylam do aplikacji...");

    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionKey: cookie.value })
    });

    if (!response.ok) {
      console.error("Blad wysylania do aplikacji:", response.status);
      return { success: false, error: 'Aplikacja nie odpowiada' };
    }

    console.log("SUKCES! Klucz wyslany.");
    
    // Opcjonalnie: Zamknij karte Claude lub powiadom uzytkownika
    // chrome.tabs.create({ url: "data:text/html,<h1>Sukces! Mozesz zamknac przegladarke.</h1>" });

    return { success: true };

  } catch (error) {
    console.error("Blad:", error);
    return { success: false, error: error.message };
  }
}