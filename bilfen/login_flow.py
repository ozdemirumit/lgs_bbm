"""Web arayuzunden tetiklenen, kullanicinin kendi tarayicida giris yaptigi oturum akisi.

Sifre bu modulde asla islenmez: gercek bir Chrome penceresi acilir, kullanici
kendi kullanici adi/sifresini o pencereye yazar. Kullanici arayuzde "Girisi
Tamamladim" dedigi anda mevcut oturum cerezleri storage_state.json'a kaydedilir.
"""
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://bilgimerkezi.bilfen.com"
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_PATH = DATA_DIR / "storage_state.json"

_lock = threading.Lock()
_state = {
    "thread": None,
    "browser_open": False,
    "finish_event": None,
}


def has_saved_session():
    return STATE_PATH.exists()


def is_in_progress():
    t = _state["thread"]
    return bool(t and t.is_alive() and _state["browser_open"])


def start():
    """Kullanicinin kendi kullanici adi/sifresini girecegi bir tarayici penceresi acar."""
    with _lock:
        if is_in_progress():
            return
        finish_event = threading.Event()
        _state["finish_event"] = finish_event
        _state["browser_open"] = False

        def worker():
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(f"{BASE_URL}/welcome")
                _state["browser_open"] = True
                finish_event.wait(timeout=15 * 60)
                DATA_DIR.mkdir(exist_ok=True)
                try:
                    context.storage_state(path=str(STATE_PATH))
                finally:
                    _state["browser_open"] = False
                    browser.close()

        thread = threading.Thread(target=worker, daemon=True)
        _state["thread"] = thread
        thread.start()


def finish():
    """Kullanici tarayicida girisi tamamladiktan sonra oturumu kaydeder.
    Dosyanin gercekten yazilmasini beklemek icin kisa sure thread'in bitmesine bakar."""
    event = _state["finish_event"]
    if event:
        event.set()
    thread = _state["thread"]
    if thread:
        thread.join(timeout=10)
