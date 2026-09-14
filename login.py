"""
Bilfen Bilgi Merkezi'ne bir kerelik giris yaparak oturumu kaydeder.

Bu script sizin adiniza sifre girmez: gercek bir Chrome penceresi acar,
kullanici adi ve sifrenizi KENDINIZ o pencereye yazarsiniz. Giris basarili
olduktan sonra terminale donup Enter'a basarsiniz; oturum cerezleri
data/storage_state.json dosyasina kaydedilir ve scraper.py bunu kullanir.

Kullanim:
    python login.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://bilgimerkezi.bilfen.com"
DATA_DIR = Path(__file__).parent / "data"
STATE_PATH = DATA_DIR / "storage_state.json"


def main():
    DATA_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{BASE_URL}/welcome")

        print("=" * 70)
        print("Acilan tarayici penceresinde KENDI kullanici adiniz ve sifrenizle")
        print("giris yapin. 'Sinav Sonuclari' sayfasini gorebildiginizde")
        print("bu terminale donup Enter'a basin.")
        print("=" * 70)
        input("Giris yaptiktan sonra devam etmek icin Enter'a basin...")

        context.storage_state(path=str(STATE_PATH))
        browser.close()
        print(f"Oturum kaydedildi: {STATE_PATH}")
        print("Artik 'python app.py' calistirip uygulamayi kullanabilirsiniz.")


if __name__ == "__main__":
    main()
