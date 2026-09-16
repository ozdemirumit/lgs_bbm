"""Zayif konular icin Claude ile konu anlatimi ve benzer soru uretir."""
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

import anthropic
from json_repair import repair_json

DATA_DIR = Path(__file__).parent.parent / "data"
GEN_DIR = DATA_DIR / "generated"

MODEL = "claude-sonnet-5"
MAX_SIMILAR_QUESTIONS = 25

_BLOCK_LABELS = {
    "thinking": "düşünüyor",
    "server_tool_use": "web'de arama yapıyor",
    "web_search_tool_result": "arama sonuçlarını değerlendiriyor",
    "text": "yanıtı yazıyor",
}


def _log(msg):
    """Uzun suren AI uretimi sirasinda terminalde (konsol log) ilerlemeyi gosterir."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [icerik-uretimi] {msg}", flush=True)

PROMPT_TEMPLATE = """Sen deneyimli bir {grade}. sinif {subject_name} ogretmenisin. \
Bir ogrenci son sinavda "{topic_name}" konusunda akranlarinin gerisinde kaldi \
(ogrencinin basari yuzdesi: %{student_score:.1f}, akran ortalamasi: %{peer_avg:.1f}).
{wrong_questions_block}
Gorevin:
1. Web search araciyla son 5 yilda (yaklasik {year_from}-{year_to}) LGS sinavinda \
"{topic_name}" konusuyla ilgili cikmis sorulari arastir (MEB LGS gecmis sorulari, \
soru bankasi siteleri vb.). Bu, sorularin gercek LGS zorluk seviyesine ve tarzina \
uygun olmasini saglamak icin.
2. "{topic_name}" konusunu {grade}. sinif seviyesine uygun, net, ornekli ve \
ogrencinin kendi basina okuyup anlayabilecegi bir konu anlatimi olarak yaz. \
Ogrencinin yukarida verilmisse gercekten yanlis yaptigi soru(lar)daki hataya/kavram \
yanilgisina ozellikle deginmeye calis.
3. Bu konuyla ilgili en fazla {num_questions} adet cok secmeli (A, B, C, D) \
soru uret (konu yeterince genisse {num_questions} adete kadar cikabilirsin, \
daha dar bir konuysa daha az ama en az 10 adet olsun; asla {num_questions} \
adedi GECME). Sorularin yaklasik dortte biri, arastirdigin gercek LGS \
sorularinin zorluk seviyesine/tarzina/soru kokenine (ornegin bir grafik \
yorumlama, bir gunluk hayat problemi vb.) yakin olacak sekilde OZGUN olarak \
yazilsin (gercek sorunun BIREBIR kopyasi OLMASIN, sadece ilham alinsin); \
kalanlar da konuyu pekistiren, GERCEK SINAV ZORLUGUNDA sorular olsun (asagidaki \
ZORLUK SEVIYESI bolumune bak - "kolaydan baslayip zora git" seklinde ISINMA \
sorusu YOK, hepsi sinav seviyesinde). Her soru icin, gercek bir LGS sorusundan \
ilham alindiysa hangi yila/tarza ait oldugunu kisaca belirt (alinmadiysa null \
birak). Her sorunun dogru cevabini ve kisa cozum aciklamasini ekle.

ZORLUK SEVIYESI - COK ONEMLI: Bu sorular bir SINAVDA (LGS/okul sinavi) \
cikan gercek bir sorudan daha kolay OLMAMALI. Ozellikle su hatalardan kacin:
- Tek adimda, dogrudan bir formul/kural uygulayarak cozulen "isinma" \
sorulari YAZMA (orn. "5 sayinin ortalamasi kactir?" gibi duz/mekanik bir \
soru LGS seviyesinde DEGILDIR).
- Gercek LGS sorulari genelde COK ADIMLI olur: bir gunluk hayat/hikaye \
baglami icerir, birden fazla kavrami bir arada test eder, bir tablo/grafik \
yorumlamayi gerektirir ve secenekler arasinda ogrencinin SIK YAPTIGI \
hatayi yansitan (yanlis islem sirasi, yanlis birim, kavram karisikligi \
gibi) inandirici celdiriciler bulundurur - kolay elenecek/absurd secenekler \
degil.
- Eger yukarida ogrencinin gercekten yanlis yaptigi bir soru verilmisse, \
uretecegin TUM sorular o sorunun zorlugundan DAHA KOLAY OLMAMALI; en az \
ayni zorlukta, mumkunse ayni sayida cozum adimini gerektiren sorular olsun.
- Butun sorular icin ayni yuksek zorluk seviyesini koru; "kolaydan zora" \
diye kademelendirme yapma.
- SAYILAR GERCEKCI OLSUN: Sorularda kullandigin sayilar/degerler rastgele \
veya anlamsiz olmasin - gercek hayatta/gercek bir sinav sorusunda \
karsilasilabilecek makul, mantikli degerler sec (orn. bir bakteri kolonisi \
icin 3, 9, 27 gibi mantikli bir buyume orani; bir tarla/bina olcusu icin \
gercekci metrekare/metre degerleri; yas, fiyat, mesafe gibi degerler \
gercek hayatla tutarli olsun). Hesaplama sonucu da (varsa) tam sayi veya \
sade bir kesir gibi "temiz" bir sonuc olmali - cirkin/anlamsiz ondalikli \
sonuclar cikaran degerler SECME.

GORSELLER - ONEMLI: Konu anlatiminda veya bir soruda tablo, sayi dogrusu, \
geometrik sekil, grafik (sutun/cizgi/pasta) gibi gorsel bir oge GEREKIYORSA \
bunu SADECE YAZIYLA ANLATMA, gercekten ciz:
- Tablo icin gercek HTML <table> etiketi kullan (anlatim alaninin markdown \
metni icine dogrudan gomebilirsin).
- Sayi dogrusu, geometrik sekil (ucgen, dortgen, aci, vb.) veya grafik icin \
kucuk, sade bir inline SVG uret (orn. <svg viewBox="0 0 300 150" ...>...</svg>), \
acik renk zeminde koyu cizgiler/metinle, olcekli ve okunakli olsun.
- Bir soru gorsel gerektiriyorsa, o sorunun JSON objesine "gorsel_html" alani \
olarak bu HTML/SVG'yi ekle (gerekmiyorsa null birak). Anlatimdaki gorseller \
dogrudan "anlatim" metninin icine markdown ile karisik HTML olarak gomulebilir.
- COK ONEMLI: "soru" alaninin (sorunun metni) icine ASLA <table> veya <svg> \
gibi HTML KOYMA - o alan SADECE duz metin/LaTeX icindir ve oldugu gibi \
(HTML islenmeden) gosterilir, ham kod olarak gorunur. Tablo/sekil gereken \
bir soruda "soru" alanina "Asagidaki tabloya gore..." gibi sadece yazi yaz, \
tablonun/sekli kendisini SADECE "gorsel_html" alanina koy - bu ikisi ayri \
alanlardir, birbirine karistirma.

MATEMATIKSEL IFADELER - COK ONEMLI: Us (^), kok, kesir, alt simge iceren HER \
IFADE, cumle icinde tek basina bir sayi/degisken bile olsa, MUTLAKA dolar \
isareti icine alinmalidir - istisna YOK. Ornegin "2^6 km" DEGIL, "$2^6$ km" \
yaz; "3 uzeri 2" yerine "$3^2$" yaz. Satir ici icin tek dolar isareti \
($a^2 + b^2 = c^2$), ayri bir satirda gosterilecek formuller icin cift dolar \
isareti ($$...$$) kullan. Soru metninde, seceneklerde (A/B/C/D) ve cozumde \
gecen HER us/kok/kesir/alt simge de ayni sekilde dolar isareti icinde \
olmali - sadece anlatim bolumunde degil. Duz metinle ("2^6" veya "1/2" gibi, \
dolarsiz) YAZMA; dolarsiz yazilan bir "^" veya "_" oldugu gibi (ham metin \
olarak) gorunur ve BOZUK gorunur.

SADECE asagidaki JSON formatinda yanit ver, baska hicbir aciklama veya metin ekleme \
(web search sonuclarini veya dusunce surecini JSON disinda yazma):
{{
  "anlatim": "markdown formatinda konu anlatimi (gerekince icine HTML tablo/SVG gomulu)",
  "sorular": [
    {{"soru": "...", "secenekler": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, \
"dogru_cevap": "A", "cozum": "...", "kaynak_notu": "orn. 2022 LGS tarzi bir grafik \
sorusundan ilham alindi, ya da null", "gorsel_html": "gerekiyorsa HTML tablo/SVG, \
yoksa null"}}
  ]
}}"""


_BARE_EXP_RE = re.compile(r"(?:\([^()]*\)|[A-Za-z0-9]+)\^-?(?:\{[^}]*\}|[A-Za-z0-9]+)")
_MATH_SPAN_RE = re.compile(r"\$\$[\s\S]*?\$\$|\$[^\$\n]+?\$")


def _ensure_math_wrapped(text):
    """Model bazen '2^6' gibi bir ussu dolar isareti icine almayi unutuyor;
    boyle kalirsa MathJax onu islemez, ham metin (bozuk) olarak gorunur. Zaten
    $...$ / $$...$$ icinde olmayan cikci us ifadelerini otomatik $...$ ile sarar."""
    if not text or "^" not in text:
        return text
    parts = _MATH_SPAN_RE.split(text)
    spans = _MATH_SPAN_RE.findall(text)
    pieces = []
    for i, part in enumerate(parts):
        pieces.append(_BARE_EXP_RE.sub(lambda m: f"${m.group(0)}$", part))
        if i < len(spans):
            pieces.append(spans[i])
    return "".join(pieces)


_EMBEDDED_BLOCK_RE = re.compile(r"<table[\s\S]*?</table>|<svg[\s\S]*?</svg>")


def _extract_embedded_html(text):
    """'soru' gibi duz metin alanlarina gomulmus <table>/<svg> varsa (model
    bunlari 'gorsel_html' alanina koymasi gerekirken metnin icine yazmis
    olabilir) cikarir; boylece metin alaninda ham HTML kodu (bozuk) gorunmez.
    (temiz_metin, cikarilan_html_veya_None) dondurur."""
    if not text or ("<table" not in text and "<svg" not in text):
        return text, None
    found = []

    def repl(m):
        found.append(m.group(0))
        return ""

    cleaned = _EMBEDDED_BLOCK_RE.sub(repl, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, ("".join(found) if found else None)


def _normalize_content(data):
    """Model bazen bir soru icin bir alani (ozellikle 'secenekler') eksik
    birakiyor - hele json-repair yarim kalan bir soruyu tam onaramayinca. Bu,
    sablonun cokmesine yol aciyordu (UndefinedError). Eksik/bozuk alanlari
    guvenli varsayilanlarla doldurur, eksigi telafi edilemeyen (soru metni
    olmayan) sorulari tamamen atar. Ayrica 'soru' metnine yanlislikla
    gomulmus HTML tablo/SVG varsa (dogrusu 'gorsel_html' alaninda olmasi)
    cikarip oraya tasir - aksi halde ham HTML kodu metin olarak gorunurdu."""
    if not isinstance(data, dict):
        return {"anlatim": "", "sorular": []}
    data.setdefault("anlatim", "")
    sorular = data.get("sorular")
    if not isinstance(sorular, list):
        sorular = []
    normalized = []
    for q in sorular:
        if not isinstance(q, dict) or not q.get("soru"):
            continue
        secenekler = q.get("secenekler")
        if not isinstance(secenekler, dict):
            secenekler = {}
        soru_text, embedded_html = _extract_embedded_html(q.get("soru") or "")
        gorsel_html = q.get("gorsel_html") or embedded_html
        normalized.append({
            "soru": soru_text,
            "secenekler": secenekler,
            "dogru_cevap": q.get("dogru_cevap") or "?",
            "cozum": q.get("cozum") or "",
            "kaynak_notu": q.get("kaynak_notu"),
            "gorsel_html": gorsel_html,
        })
    data["sorular"] = normalized
    return data


def _fix_bare_math(data):
    if not isinstance(data, dict):
        return data
    if data.get("anlatim"):
        data["anlatim"] = _ensure_math_wrapped(data["anlatim"])
    for q in data.get("sorular", []) or []:
        if not isinstance(q, dict):
            continue
        if q.get("soru"):
            q["soru"] = _ensure_math_wrapped(q["soru"])
        if q.get("cozum"):
            q["cozum"] = _ensure_math_wrapped(q["cozum"])
        secenekler = q.get("secenekler")
        if isinstance(secenekler, dict):
            for k, v in list(secenekler.items()):
                if isinstance(v, str):
                    secenekler[k] = _ensure_math_wrapped(v)
    return data


def _format_wrong_questions_block(wrong_questions):
    if not wrong_questions:
        return ""
    parts = ["\nOgrencinin bu derste gercekten yanlis yaptigi soru(lar) (referans icin):"]
    for i, wq in enumerate(wrong_questions, 1):
        if not wq or not wq.get("okunabildi", True):
            continue
        secenekler = wq.get("secenekler", {})
        opts = ", ".join(f"{k}) {v}" for k, v in secenekler.items() if v)
        parts.append(f"{i}. {wq.get('soru', '')} [{opts}]")
        if wq.get("isaretli_dogru_cevap"):
            parts.append(f"   (Dogru cevap: {wq['isaretli_dogru_cevap']})")
    if len(parts) == 1:
        return ""
    return "\n".join(parts) + "\n"


def is_cached(exam_id, subject_index, kID):
    return _cache_path(exam_id, subject_index, kID).exists()


def list_cached_topics():
    """Daha once icerigi uretilip diske onbelleklenmis konularin
    (exam_id, subject_index, kID) uclusunu dondurur - boylece bunlara
    yeniden uretim beklemeden, dogrudan erisim linki verilebilir."""
    if not GEN_DIR.exists():
        return []
    results = []
    for f in GEN_DIR.glob("*.json"):
        parts = f.stem.split("_", 2)
        if len(parts) != 3:
            continue
        exam_id, subject_index, kID = parts
        try:
            subject_index = int(subject_index)
        except ValueError:
            continue
        results.append({"exam_id": exam_id, "subject_index": subject_index, "kID": kID})
    return results


def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY tanimli degil. .env dosyasina kendi API anahtarinizi ekleyin."
        )
    return anthropic.Anthropic(api_key=api_key)


def _cache_path(exam_id, subject_index, kID):
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    safe_kid = kID or "none"
    return GEN_DIR / f"{exam_id}_{subject_index}_{safe_kid}.json"


def clear_cache_for_exam(exam_id):
    """'Yeniden analiz et' icin: bu sinava ait daha once uretilmis konu
    anlatimi/benzer soru onbellegini siler, bir sonraki goruntulemede
    yeniden uretilir."""
    if not GEN_DIR.exists():
        return
    for f in GEN_DIR.glob(f"{exam_id}_*.json"):
        f.unlink(missing_ok=True)


def generate_topic_content(
    subject_name,
    topic_name,
    grade,
    student_score,
    peer_avg,
    exam_id=None,
    subject_index=None,
    kID=None,
    wrong_questions=None,
    force=False,
):
    cache_path = None
    if exam_id is not None and subject_index is not None and kID is not None:
        cache_path = _cache_path(exam_id, subject_index, kID)
        if cache_path.exists() and not force:
            return _fix_bare_math(_normalize_content(json.loads(cache_path.read_text(encoding="utf-8"))))

    this_year = date.today().year
    prompt = PROMPT_TEMPLATE.format(
        grade=grade,
        subject_name=subject_name,
        topic_name=topic_name,
        student_score=student_score,
        peer_avg=peer_avg,
        wrong_questions_block=_format_wrong_questions_block(wrong_questions),
        year_from=this_year - 5,
        year_to=this_year,
        num_questions=MAX_SIMILAR_QUESTIONS,
    )

    client = _client()
    data = None
    last_error = None
    _log(f"'{subject_name} / {topic_name}' icin uretim basliyor (en fazla {MAX_SIMILAR_QUESTIONS} soru, web search dahil)...")
    for attempt in range(3):  # yarida kesilen/bozuk JSON icin birkac kez tekrar dene
        if attempt > 0:
            _log(f"Tekrar deneniyor ({attempt + 1}/3)...")
        t0 = time.time()
        try:
            # 25 soruya kadar + web search uzun surebildigi icin streaming kullanilir
            # (SDK, >10 dk surebilecek istekler icin streaming zorunlu tutuyor).
            with client.messages.stream(
                model=MODEL,
                max_tokens=28000,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                last_block = None
                for event in stream:
                    if event.type != "content_block_start":
                        continue
                    block_type = event.content_block.type
                    if block_type == last_block:
                        continue
                    last_block = block_type
                    _log(f"  -> {_BLOCK_LABELS.get(block_type, block_type)}")
                resp = stream.get_final_message()
        except anthropic.AuthenticationError:
            raise RuntimeError(
                "ANTHROPIC_API_KEY gecersiz. .env dosyasindaki anahtari "
                "console.anthropic.com adresinden aldiginiz gecerli bir anahtarla degistirin."
            )
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API hatasi: {e}")

        elapsed = time.time() - t0
        truncated = resp.stop_reason == "max_tokens"
        text = "".join(block.text for block in resp.content if block.type == "text")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            _log(f"Yanit alindi ({elapsed:.0f} sn) ama JSON bulunamadi.")
            last_error = (
                "Model yanitindan JSON cikarilamadi"
                + (" (yanit token limitine takilip yarida kesildi)." if truncated else ".")
                + " " + text[-300:]
            )
            continue
        try:
            data = json.loads(match.group(0))
            _log(f"Basarili ({elapsed:.0f} sn): {len(data.get('sorular', []))} soru uretildi.")
            break
        except json.JSONDecodeError as e:
            # Model bazen fazladan virgul/kacis hatasi gibi kucuk bozukluklar
            # birakiyor (ozellikle HTML/SVG gomulu uzun yanitlarda); once
            # onarmayi dene, olmazsa tekrar dene.
            try:
                data = repair_json(match.group(0), return_objects=True)
                if not isinstance(data, dict) or "sorular" not in data:
                    raise ValueError("onarilan JSON beklenen sekilde degil")
                _log(f"Basarili ({elapsed:.0f} sn, JSON onarildi): {len(data.get('sorular', []))} soru uretildi.")
                break
            except Exception:
                data = None
            _log(f"Yanit alindi ({elapsed:.0f} sn) ama JSON hatali: {e}")
            last_error = (
                f"Model yaniti JSON olarak ayristirilamadi ({e})."
                + (" Yanit token limitine takilip yarida kesilmis olabilir." if truncated else "")
            )
            continue

    if data is None:
        _log("Uretim basarisiz oldu (3 deneme de basarisiz).")
        raise RuntimeError(last_error or "Model yanitindan icerik uretilemedi.")

    data = _fix_bare_math(_normalize_content(data))

    if cache_path:
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return data
