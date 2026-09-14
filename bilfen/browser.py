"""Kalici Chrome profili: autofill/oturum surekliligi icin ortak yardimci.

Playwright her seferinde sifirdan bir profil acarsa Chrome'un kayitli
sifreleri/autofill'i olmaz. Bunun yerine data/chrome_profile altinda kalici
bir profil kullaniyoruz: ilk girişte kullanici kendi bilgilerini elle yazar,
Chrome "sifreyi kaydet" sorabilir; kabul ederse sonraki calistirmalarda hem
autofill calisir hem de oturum zaten acik kalmis olabilir.
"""
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
PROFILE_DIR = DATA_DIR / "chrome_profile"


def launch_persistent(playwright, headless):
    DATA_DIR.mkdir(exist_ok=True)
    try:
        return playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=headless, channel="chrome"
        )
    except Exception:
        return playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=headless
        )


def has_profile():
    return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())
