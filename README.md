# Bilfen Hata Analizi

Bilfen Bilgi Merkezi (bilgimerkezi.bilfen.com) sınav sonuçlarını okuyup, akran
ortalamasının altında kalınan konuları tespit eden; bu konular için AI (Claude)
ile konu anlatımı ve benzer sorular üreten bir uygulama.

## Nasıl çalışır?

1. Bilfen sitesinde her sınav için ders bazlı doğru/yanlış sayıları ve **konu
   (kazanım) bazlı karşılaştırmalı puanlar** (öğrenci vs sınıf/okul/tüm okullar
   ortalaması) yayınlanıyor. Uygulama bu karşılaştırmadan öğrencinin akranlarına
   göre zayıf olduğu konuları otomatik tespit ediyor.
2. Yanlış yapılan sorular için sitedeki video çözümünden (Doceri kaydı) bir
   kare yakalanıp Claude'un görsel anlama özelliğiyle sorunun gerçek metni ve
   şıkları çıkarılıyor. Not: siteden soru numarası ↔ konu eşleşmesi doğrudan
   gelmiyor; bir derste tek zayıf konu varsa eşleşme kesin, birden fazla zayıf
   konu varsa o dersin tüm yanlışları ortak referans olarak kullanılıyor.
3. Her zayıf konu için Claude, seviyeye uygun bir konu anlatımı ve 5 adet özgün
   benzer soru (cevap anahtarı + çözümüyle) üretiyor.
4. Sonuçlar web arayüzünde gösteriliyor; her sınav için Word (.docx) raporu
   olarak da indirilebiliyor.

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

Tarayıcıda `http://localhost:5000` açılır.

### 2. Bilfen'e giriş yapın (bir kerelik, web arayüzünden)

Ana sayfadaki **"Bilfen'e Giriş Yap"** butonuna basın: gerçek bir Chrome
penceresi açılır, o pencerede **kendi** kullanıcı adı/şifrenizle giriş
yapın (şifreniz uygulamadan hiç geçmez). Giriş yaptıktan sonra web
sayfasındaki **"Girişi Tamamladım"** butonuna basın; oturum
`data/storage_state.json` içine kaydedilir (bu dosya `.gitignore` ile hariç
tutulur, GitHub'a gitmez). Oturum süresi dolarsa aynı adımı tekrarlayın
("Yeniden Giriş Yap").

Alternatif olarak terminalden `python login.py` ile de aynı giriş akışı
çalıştırılabilir.

### 3. Senkronize edin

Girişten sonra **"Bilfen'den Senkronize Et"** butonuna basın: sınav verileri
çekilir (yanlış soruların video ekran görüntüleri de bu adımda arka planda
kaydedilir, biraz sürebilir). Ardından zayıf konulara tıklayarak konu
anlatımı ve benzer soruları görebilir, sınav detay sayfasından Word raporu
indirebilirsiniz.

## Proje yapısı

```
login.py                  # Terminalden alternatif tek seferlik manuel giriş
app.py                    # Flask web uygulaması
bilfen/login_flow.py      # Web arayüzünden tetiklenen giriş akışı
bilfen/scraper.py         # Sınav/ders/soru verisini Playwright ile çeker
bilfen/video_capture.py   # Yanlış sorunun video çözümünden ekran görüntüsü alır
bilfen/vision_extract.py  # Görüntüden soru metnini Claude vision ile çıkarır
bilfen/analyzer.py        # Akran ortalamasına göre zayıf konu tespiti
bilfen/content_generator.py  # Konu anlatımı + benzer soru üretimi (Claude)
bilfen/docx_export.py     # Word raporu oluşturma
templates/, static/       # Web arayüzü
```

## Gizlilik notu

`data/` klasörü (oturum çerezi, çekilen sınav verisi, soru görüntüleri, Claude
API ile üretilen içerik) `.gitignore` ile deposunun dışında tutulur; bu
klasörü paylaşmayın. `.env` dosyanızdaki API anahtarını da kimseyle
paylaşmayın.
