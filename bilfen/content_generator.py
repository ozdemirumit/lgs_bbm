"""Zayif konular icin Claude ile konu anlatimi ve benzer soru uretir."""
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

import anthropic

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
kalanlar konuyu pekistiren, kolaydan zora dogru siralanmis standart sorular \
olsun. Her soru icin, gercek bir LGS sorusundan ilham alindiysa hangi \
yila/tarza ait oldugunu kisaca belirt (alinmadiysa null birak). Her sorunun \
dogru cevabini ve kisa cozum aciklamasini ekle.

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
            return json.loads(cache_path.read_text(encoding="utf-8"))

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
            _log(f"Yanit alindi ({elapsed:.0f} sn) ama JSON hatali: {e}")
            last_error = (
                f"Model yaniti JSON olarak ayristirilamadi ({e})."
                + (" Yanit token limitine takilip yarida kesilmis olabilir." if truncated else "")
            )
            continue

    if data is None:
        _log("Uretim basarisiz oldu (3 deneme de basarisiz).")
        raise RuntimeError(last_error or "Model yanitindan icerik uretilemedi.")

    if cache_path:
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return data
