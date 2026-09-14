"""Zayif konular icin Claude ile konu anlatimi ve benzer soru uretir."""
import json
import os
import re
from pathlib import Path

import anthropic

DATA_DIR = Path(__file__).parent.parent / "data"
GEN_DIR = DATA_DIR / "generated"

MODEL = "claude-sonnet-5"

PROMPT_TEMPLATE = """Sen deneyimli bir {grade}. sinif {subject_name} ogretmenisin. \
Bir ogrenci son sinavda "{topic_name}" konusunda akranlarinin gerisinde kaldi \
(ogrencinin basari yuzdesi: %{student_score:.1f}, akran ortalamasi: %{peer_avg:.1f}).
{wrong_questions_block}
Gorevin:
1. "{topic_name}" konusunu {grade}. sinif seviyesine uygun, net, ornekli ve \
ogrencinin kendi basina okuyup anlayabilecegi bir konu anlatimi olarak yaz. \
Ogrencinin yukarida verilmisse gercekten yanlis yaptigi soru(lar)daki hataya/kavram \
yanilgisina ozellikle deginmeye calis.
2. Bu konuyla ilgili tamamen OZGUN, sinav formatina benzer 5 adet cikmis soruya \
benzer cok secmeli (A, B, C, D) soru uret (yukaridaki gercek sorularin BIREBIR \
kopyasi olmasin, ayni kavrami/zorluk seviyesini test eden yeni sorular olsun). \
Her sorunun dogru cevabini ve kisa cozum aciklamasini ekle.

SADECE asagidaki JSON formatinda yanit ver, baska hicbir aciklama veya metin ekleme:
{{
  "anlatim": "markdown formatinda konu anlatimi",
  "sorular": [
    {{"soru": "...", "secenekler": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, \
"dogru_cevap": "A", "cozum": "..."}}
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

    prompt = PROMPT_TEMPLATE.format(
        grade=grade,
        subject_name=subject_name,
        topic_name=topic_name,
        student_score=student_score,
        peer_avg=peer_avg,
        wrong_questions_block=_format_wrong_questions_block(wrong_questions),
    )

    client = _client()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError(
            "ANTHROPIC_API_KEY gecersiz. .env dosyasindaki anahtari "
            "console.anthropic.com adresinden aldiginiz gecerli bir anahtarla degistirin."
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude API hatasi: {e}")
    text = "".join(block.text for block in resp.content if block.type == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("Model yanitindan JSON cikarilamadi: " + text[:500])
    data = json.loads(match.group(0))

    if cache_path:
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return data
