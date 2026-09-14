"""
Bilfen Bilgi Merkezi'ne bir kerelik giris yapmak icin terminal alternatifi.

Bu script sizin adiniza sifre girmez: kalici bir Chrome profiliyle gercek bir
pencere acar, kullanici adi ve sifrenizi KENDINIZ o pencereye yazarsiniz.
Profil data/chrome_profile altinda kalici oldugu icin Chrome sifreyi
kaydetmeyi teklif edebilir; kabul ederseniz sonraki calistirmalarda otomatik
dolar. Ayni giris akisi web arayuzundeki "Bilfen'e Giris Yap" butonuyla da
tetiklenebilir.

Kullanim:
    python login.py
"""
from playwright.sync_api import sync_playwright

from bilfen.browser import launch_persistent

BASE_URL = "https://bilgimerkezi.bilfen.com"


def main():
    with sync_playwright() as p:
        context = launch_persistent(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"{BASE_URL}/welcome")

        print("=" * 70)
        print("Acilan tarayici penceresinde KENDI kullanici adiniz ve sifrenizle")
        print("giris yapin. 'Sinav Sonuclari' sayfasini gorebildiginizde")
        print("bu terminale donup Enter'a basin.")
        print("=" * 70)
        input("Giris yaptiktan sonra devam etmek icin Enter'a basin...")

        context.close()
        print("Oturum kaydedildi (kalici Chrome profili).")
        print("Artik 'python app.py' calistirip uygulamayi kullanabilirsiniz.")


if __name__ == "__main__":
    main()
