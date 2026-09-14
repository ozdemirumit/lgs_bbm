"""Yakalanan soru gorselinden Claude vision ile soru metnini/secenekleri cikarir."""
import base64
import json
import re
from pathlib import Path

from .content_generator import MODEL, _client, _log

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "generated" / "questions"

EXTRACT_PROMPT = """Bu gorsel bir sinavin video cozumunden alinmis bir kare. Gorselde \
basili (orijinal) bir soru metni, A/B/C/D secenekleri ve genellikle ogretmenin elle \
ekledigi isaretlemeler/notlar bulunur.

Gorevin SADECE basili orijinal soru metnini ve secenekleri, elle yazilan notlari \
KATMADAN, birebir cikarmak. Ogretmenin dogru cevabi daire ici alma gibi \
isaretlemesi varsa bunu ayrica belirt.

SADECE asagidaki JSON formatinda yanit ver, baska aciklama ekleme:
{
  "okunabildi": true,
  "soru": "soru metni",
  "secenekler": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "isaretli_dogru_cevap": "A"
}
Gorselde net bir soru secilemiyorsa "okunabildi": false yap, digerlerini bos birak."""


def clear_cache_for_exam(exam_id):
    """'Yeniden analiz et' icin: bu sinava ait daha once cikarilmis soru
    metni onbellegini siler."""
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob(f"{exam_id}_*.json"):
        f.unlink(missing_ok=True)


def extract_question_text(image_path, cache_key, force=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    image_path = Path(image_path)
    _log(f"Yanlis sorunun goruntusu inceleniyor: {image_path.name}")
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    client = _client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("Vision yanitindan JSON cikarilamadi: " + text[:300])
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Vision yaniti JSON olarak ayristirilamadi: {e}")

    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
