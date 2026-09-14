"""Web arayuzunden tetiklenen, kullanicinin kendi tarayicida giris yaptigi oturum akisi.

Sifre bu modulde asla islenmez: kalici bir Chrome profili (bkz. browser.py)
ile gercek bir pencere acilir, kullanici kendi kullanici adi/sifresini o
pencereye yazar. Profil kalici oldugu icin Chrome sifreyi kaydetmeyi teklif
edebilir; kabul edilirse sonraki girislerde otomatik dolar.
"""
import threading

from playwright.sync_api import sync_playwright

from . import browser

BASE_URL = "https://bilgimerkezi.bilfen.com"

_lock = threading.Lock()
_state = {
    "thread": None,
    "browser_open": False,
    "finish_event": None,
}


def has_saved_session():
    return browser.has_profile()


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
                context = browser.launch_persistent(p, headless=False)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(f"{BASE_URL}/welcome")
                _state["browser_open"] = True
                finish_event.wait(timeout=15 * 60)
                _state["browser_open"] = False
                context.close()

        thread = threading.Thread(target=worker, daemon=True)
        _state["thread"] = thread
        thread.start()


def finish():
    """Kullanici tarayicida girisi tamamladiktan sonra pencereyi kapatir.
    Kalici profil sayesinde oturum cerezleri zaten diskte kalir."""
    event = _state["finish_event"]
    if event:
        event.set()
    thread = _state["thread"]
    if thread:
        thread.join(timeout=10)
