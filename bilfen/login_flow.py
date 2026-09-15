"""Web arayuzunden tetiklenen, kullanicinin kendi tarayicida giris yaptigi oturum akisi.

Sifre bu modulde asla islenmez: kalici bir Chrome profili (bkz. browser.py)
ile gercek bir pencere acilir, kullanici kendi kullanici adi/sifresini o
pencereye yazar. Profil kalici oldugu icin Chrome sifreyi kaydetmeyi teklif
edebilir; kabul edilirse sonraki girislerde otomatik dolar.

'in progress' durumu ayrica diske de yaziliyor: Flask'in debug/reload modu
(kod degisince otomatik yeniden baslama) bellekteki thread/pencere baglantisini
koparabilir - bu durumda dahi "Girisi Tamamladim" butonu gorunmeye devam eder
ve tiklaninca (thread artik olmasa da) durumu guvenle temizler; kalici profil
sayesinde giris zaten tamamlandiysa cerezler diskte kalmis olur.
"""
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import browser

BASE_URL = "https://bilgimerkezi.bilfen.com"
DATA_DIR = Path(__file__).parent.parent / "data"
_FLAG_PATH = DATA_DIR / "login_in_progress.flag"

_lock = threading.Lock()
_state = {
    "thread": None,
    "browser_open": False,
    "finish_event": None,
}


def has_saved_session():
    return browser.has_profile()


def is_in_progress():
    # Ayni surecte (restart olmadiysa) gercek durumu yansitir; bir restart
    # sonrasi bellek sifirlanmis olsa da diskteki bayrak devam eder.
    t = _state["thread"]
    if t and t.is_alive() and _state["browser_open"]:
        return True
    return _FLAG_PATH.exists()


def start():
    """Kullanicinin kendi kullanici adi/sifresini girecegi bir tarayici penceresi acar."""
    with _lock:
        if is_in_progress():
            return
        DATA_DIR.mkdir(exist_ok=True)
        _FLAG_PATH.write_text("1", encoding="utf-8")

        finish_event = threading.Event()
        _state["finish_event"] = finish_event
        _state["browser_open"] = False

        def worker():
            try:
                with sync_playwright() as p:
                    context = browser.launch_persistent(p, headless=False)
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(f"{BASE_URL}/welcome")
                    _state["browser_open"] = True
                    finish_event.wait(timeout=15 * 60)
                    _state["browser_open"] = False
                    context.close()
            finally:
                _FLAG_PATH.unlink(missing_ok=True)

        thread = threading.Thread(target=worker, daemon=True)
        _state["thread"] = thread
        thread.start()


def finish():
    """Kullanici tarayicida girisi tamamladiktan sonra pencereyi kapatir.
    Kalici profil sayesinde oturum cerezleri zaten diskte kalir. Eger (ornegin
    sunucu yeniden basladigi icin) bu surecte artik bir thread yoksa, sadece
    bayragi temizler - kalici profildeki cerezler zaten yerinde durur."""
    event = _state["finish_event"]
    if event:
        event.set()
    thread = _state["thread"]
    if thread:
        thread.join(timeout=10)
    _FLAG_PATH.unlink(missing_ok=True)
