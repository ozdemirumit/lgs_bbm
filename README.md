# Bilfen Hata Analizi

Bilfen Bilgi Merkezi (bilgimerkezi.bilfen.com) sınav sonuçlarını okuyup
yanlış yapılan konuları tespit eden; bu konular için AI (Claude) ile LGS
seviyesinde konu anlatımı ve benzer sorular üreten bir uygulama.

## Nasıl çalışır?

1. Bilfen sitesinde her sınav için ders bazlı doğru/yanlış sayıları ve **konu
   (kazanım) bazlı puanlar** (öğrenci vs sınıf/okul/tüm okullar ortalaması)
   yayınlanıyor. Uygulama, içinde en az bir yanlışın bulunduğu (puanı
   %100'ün altında olan) her konuyu "Zayıf Konular" olarak listeler; akran
   ortalamasıyla karşılaştırma da bilgi/sıralama amacıyla gösterilir.
2. Yanlış yapılan sorular için sitedeki video çözümünden (Doceri kaydı) bir
   kare yakalanıp Claude'un görsel anlama özelliğiyle sorunun gerçek metni ve
   şıkları çıkarılıyor. Bu gerçek görüntü web sayfasında ve Word raporunda da
   gösterilir. Not: siteden soru numarası ↔ konu eşleşmesi doğrudan gelmiyor;
   bir derste tek zayıf konu varsa eşleşme kesin, birden fazla zayıf konu
   varsa o dersin tüm yanlışları ortak referans olarak kullanılıyor.
3. Her zayıf konu için Claude, **web search ile son 5 yılın gerçek LGS
   sorularını araştırıp** LGS seviyesinde (çok adımlı, gerçek hayat bağlamlı,
   inandırıcı çeldiricili — kolay "ısınma" sorusu değil) bir konu anlatımı ve
   en fazla 25 adet özgün benzer soru (cevap anahtarı + çözümüyle) üretir.
   Sorulardan bir kısmı gerçek LGS sorularının tarzından/zorluğundan ilham
   alınarak yazılır (birebir kopya değil) ve hangi yıl/tarza yakın olduğu
   belirtilir. Tablo, sayı doğrusu, geometrik şekil veya grafik gerektiren
   yerlerde Claude gerçek bir görsel (HTML tablo / SVG çizim) üretir, formüller
   LaTeX ile yazılır ve sayfada (MathJax ile) düzgün matematik gösterimine
   çevrilir. Bu üretim (özellikle 25 soru + araştırma nedeniyle) tek bir konu
   için birkaç dakika sürebilir; sonuç diskte önbelleklenir, aynı konuyu bir
   daha açtığınızda anında gelir ve "Çalış" yazısı sayfa yenilenmeden "Aç"a
   döner. Bir sınavda birden fazla zayıf konu aynı anda üretilecekse (Word
   raporu / "Yeniden Analiz Et") hepsi paralel çalıştırılır.
4. Sonuçlar web arayüzünde (tablo/grafik/formülleriyle birlikte) gösterilir;
   her sınav veya tek bir konu için Word (.docx) raporu da indirilebilir —
   tablolar gerçek Word tablosuna, SVG şekiller ve yanlış sorunun gerçek
   görüntüsü de gerçek resme çevrilerek gömülür.

## Kurulum

```bash
pip install -r requirements.txt
playwright install chromium
```

`.env.example` dosyasını `.env` olarak kopyalayıp kendi Anthropic API
anahtarınızı girin:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Kullanım

### 1. Uygulamayı başlatın

```bash
python app.py
```

Terminalde iki adres yazdırılır: `http://localhost:5000` (bu bilgisayar) ve
aynı Wi-Fi/ağdaki diğer cihazlardan (telefon, tablet) erişim için bir ağ
IP'si. **Not:** ağ üzerinden erişim `debug` modu açıkken bir güvenlik riski
taşır (bkz. `app.py` başındaki uyarı) — sadece güvendiğiniz ev ağınızda açık
tutun.

### 2. Bilfen'e giriş yapın (bir kerelik, web arayüzünden)

Ana sayfadaki **"Bilfen'e Giriş Yap"** butonuna basın: gerçek bir Chrome
penceresi açılır, o pencerede **kendi** kullanıcı adı/şifrenizle giriş
yapın (şifreniz uygulamadan hiç geçmez). Bu pencere `data/chrome_profile`
altında **kalıcı** bir tarayıcı profili kullanır (bu klasör `.gitignore` ile
hariç tutulur, GitHub'a gitmez): ilk seferde Chrome "Şifreyi kaydet?"
sorabilir, kabul ederseniz sonraki girişlerde alanlar otomatik dolar. Giriş
yaptıktan sonra web sayfasındaki **"Girişi Tamamladım"** butonuna basın.
Oturum süresi dolarsa aynı adımı tekrarlayın ("Yeniden Giriş Yap") — bu,
daha önce üretilmiş hiçbir veriyi/içeriği etkilemez.

Alternatif olarak terminalden `python login.py` ile de aynı giriş akışı
çalıştırılabilir.

### 3. Senkronize edin

Girişten sonra **"Bilfen'den Senkronize Et"** butonuna basın: sadece daha
önce görülmemiş **yeni** sınavlar çekilir (eskiden analiz edilmiş bir sınav
tekrar taranmaz — yanlış soruların video ekran görüntüleri de bu adımda
arka planda kaydedilir, biraz sürebilir). Ana sayfada soldan bir sınav
seçince sağda o sınavın ders tablosu ve tüm zayıf konuları görünür.

Bir sınavı (ham veri + AI içeriği dahil) tamamen baştan işletmek isterseniz
sınav sayfasındaki **"Yeniden Analiz Et"** butonunu kullanın; tek bir
konunun sadece AI içeriğini tazelemek içinse o konunun sayfasındaki
**"Yeniden Üret"** linkini kullanın.

## Proje yapısı

```
login.py                  # Terminalden alternatif tek seferlik manuel giriş
app.py                     # Flask web uygulaması
bilfen/login_flow.py       # Web arayüzünden tetiklenen giriş akışı
bilfen/browser.py          # Kalıcı Chrome profili (autofill/oturum sürekliliği)
bilfen/scraper.py          # Sınav/ders/soru verisini ve konu puanlarını Playwright ile çeker
bilfen/video_capture.py    # Yanlış sorunun video çözümünden ekran görüntüsü alır
bilfen/vision_extract.py   # Görüntüden soru metnini Claude vision ile çıkarır
bilfen/analyzer.py         # Yanlış yapılan/zayıf konu tespiti
bilfen/content_generator.py  # Konu anlatımı + benzer soru üretimi (Claude, web search)
bilfen/docx_export.py      # Word raporu oluşturma (tablo/SVG -> gerçek Word içeriği)
static/live_status.js      # "Çalış" -> "Aç" gecisini sayfa yenilenmeden gunceller
templates/, static/        # Web arayüzü
```

## Gizlilik notu

`data/` klasörü (oturum profili, çekilen sınav verisi, soru görüntüleri,
Claude API ile üretilen içerik) `.gitignore` ile deponun dışında tutulur; bu
klasörü paylaşmayın. `.env` dosyanızdaki API anahtarını da kimseyle
paylaşmayın.
