import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import markdown as markdown_lib
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, send_file, send_from_directory, url_for

load_dotenv()

from bilfen import analyzer, content_generator, docx_export, login_flow, scraper, vision_extract  # noqa: E402

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
EXAMS_PATH = DATA_DIR / "exams.json"
IMAGES_DIR = DATA_DIR / "question_images"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")


_SVG_RE = re.compile(r"<svg[\s\S]*?</svg>")


@app.template_filter("markdown")
def render_markdown(text):
    """Konu anlatimini markdown->HTML'e cevirir. <table> Python-Markdown'in
    taninan blok etiketi oldugu icin sorunsuz gecer, ama <svg> taninmadigindan
    paragraf icine al(n)ip satirlar arasina <br> sokularak bozuluyordu - bu
    yuzden SVG'ler markdown'a girmeden once cikarilip sonradan aynen geri
    konuluyor."""
    if not text:
        return ""
    protected = []

    def _stash(m):
        protected.append(m.group(0))
        return f"\n\nSVGPLACEHOLDER{len(protected) - 1}\n\n"

    text = _SVG_RE.sub(_stash, text)
    html = markdown_lib.markdown(text, extensions=["tables", "nl2br"])
    for i, svg in enumerate(protected):
        html = re.sub(rf"<p>\s*SVGPLACEHOLDER{i}\s*</p>", svg, html)
        html = html.replace(f"SVGPLACEHOLDER{i}", svg)
    return html


def load_data():
    if not EXAMS_PATH.exists():
        return None
    return json.loads(EXAMS_PATH.read_text(encoding="utf-8"))


def list_studied_topics(data):
    """Daha once icerigi uretilmis (onbellekte hazir) konulari, tekrar
    beklemeden dogrudan acilabilecek sekilde listeler."""
    if not data:
        return []
    exams_by_id = {e["id"]: e for e in data.get("exams", [])}
    studied = []
    for ref in content_generator.list_cached_topics():
        exam = exams_by_id.get(ref["exam_id"])
        if not exam:
            continue
        subj = next((s for s in exam.get("subjects", []) if s["index"] == ref["subject_index"]), None)
        if not subj:
            continue
        topic = next((t for t in subj.get("detail", {}).get("topics", []) if t["kID"] == ref["kID"]), None)
        if not topic:
            continue
        studied.append({
            "exam_id": exam["id"],
            "exam_name": exam["name"],
            "subject_index": subj["index"],
            "subject_name": subj["name"],
            "kID": topic["kID"],
            "topic": topic["name"],
        })
    return studied


@app.route("/media/question_images/<path:filename>")
def question_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


def get_wrong_question_texts(exam_id, subj):
    """Bir dersteki tum yanlis sorularin (varsa) goruntudeki metnini cikarir.
    Gercek ekran goruntusunun URL'sini de ekler (tablo/grafik gibi gorseller
    metne cikan ozette kaybolabildigi icin, orijinal goruntu de gosterilir).
    Not: siteden soru<->konu eslesmesi gelmez; bu yuzden birden fazla zayif
    konu varsa ayni dersin yanlislarinin tumu ortak baglam olarak kullanilir."""
    results = []
    for q in subj.get("detail", {}).get("questions", []):
        if q.get("correct") or not q.get("image"):
            continue
        try:
            data = vision_extract.extract_question_text(
                q["image"], cache_key=f"{exam_id}_{subj['index']}_{q['no']}"
            )
        except Exception:
            continue
        data = dict(data)
        data["image_url"] = url_for("question_image", filename=Path(q["image"]).name)
        results.append(data)
    return results


def _mark_cached(topics):
    for t in topics:
        t["cached"] = content_generator.is_cached(t["exam_id"], t["subject_index"], t["kID"])
    return topics


def generate_weak_topics_parallel(exam, weak, grade, max_workers=4):
    """Birden fazla konu ayni anda uretilecekse (Word raporu, Yeniden Analiz
    Et) her biri icin ayri ayri, sirayla dakikalarca beklemek yerine
    ThreadPoolExecutor ile paralel calistirir (AI cagrisi I/O-bound oldugu
    icin threadler GIL'i birbirine birakip gercekten es zamanli ilerler).
    (icerik, hatalar) tuple'i doner; basarisiz olan konular hatalar
    listesinde, digerleri normal calismaya devam eder."""
    # Ayni dersin yanlis sorulari birden fazla zayif konu tarafindan
    # paylasilabiliyor; her thread'in ayni goruntuyu ayri ayri (ve ayni anda
    # dosyaya yazarak) islemesini onlemek icin bir kere, sirayla hesaplanir.
    wrong_by_subject = {}
    for w in weak:
        if w["subject_index"] not in wrong_by_subject:
            subj = next(s for s in exam["subjects"] if s["index"] == w["subject_index"])
            wrong_by_subject[w["subject_index"]] = get_wrong_question_texts(exam["id"], subj)

    def work(w):
        wrong_questions = wrong_by_subject.get(w["subject_index"], [])
        content = content_generator.generate_topic_content(
            subject_name=w["subject_name"],
            topic_name=w["topic"],
            grade=grade,
            student_score=w["student"],
            peer_avg=w["peer_avg"],
            exam_id=w["exam_id"],
            subject_index=w["subject_index"],
            kID=w["kID"],
            wrong_questions=wrong_questions,
        )
        return {**w, "content": content, "wrong_questions": wrong_questions}

    items = []
    errors = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(work, w): w for w in weak}
        for future in as_completed(futures):
            try:
                items.append(future.result())
            except RuntimeError as e:
                errors.append(str(e))

    # Sirali/kararli gorunmesi icin orijinal zayiflik siralamasina geri koy
    order = {(w["subject_index"], w["kID"]): i for i, w in enumerate(weak)}
    items.sort(key=lambda it: order.get((it["subject_index"], it["kID"]), 0))
    return items, errors


@app.route("/")
def index():
    data = load_data()
    weak = _mark_cached(analyzer.weak_topics(data)) if data else []
    studied = list_studied_topics(data)

    selected_exam = None
    selected_weak = []
    selected_exam_id = request.args.get("exam")
    if data and selected_exam_id:
        selected_exam = next((e for e in data["exams"] if e["id"] == selected_exam_id), None)
        if selected_exam:
            selected_weak = _mark_cached(
                [w for w in analyzer.weak_topics(data) if w["exam_id"] == selected_exam_id]
            )

    return render_template(
        "index.html",
        data=data,
        weak=weak,
        studied=studied,
        selected_exam=selected_exam,
        selected_weak=selected_weak,
        has_session=login_flow.has_saved_session(),
        login_in_progress=login_flow.is_in_progress(),
    )


@app.route("/login/start", methods=["POST"])
def login_start():
    login_flow.start()
    flash("Açılan tarayıcı penceresinde kendi kullanıcı adı/şifrenizle giriş yapın, sonra aşağıdaki 'Girişi Tamamladım' butonuna basın.", "success")
    return redirect(url_for("index"))


@app.route("/login/finish", methods=["POST"])
def login_finish():
    login_flow.finish()
    flash("Oturum kaydedildi. Şimdi 'Senkronize Et' butonuna basabilirsiniz.", "success")
    return redirect(url_for("index"))


@app.route("/sync", methods=["POST"])
def sync():
    try:
        scraper.sync_all(headless=True)
        flash("Sinav verileri guncellendi.", "success")
    except RuntimeError as e:
        flash(str(e), "error")
    except Exception as e:  # pragma: no cover - runtime feedback
        flash(f"Senkronizasyon hatasi: {e}", "error")
    return redirect(url_for("index"))


@app.route("/exam/<exam_id>")
def exam_detail(exam_id):
    data = load_data()
    exam = next((e for e in data["exams"] if e["id"] == exam_id), None)
    weak = _mark_cached([w for w in analyzer.weak_topics(data) if w["exam_id"] == exam_id])
    return render_template("exam.html", exam=exam, weak=weak)


@app.route("/exam/<exam_id>/reanalyze", methods=["POST"])
def reanalyze_exam(exam_id):
    """Bu sinavi -ve onun AI icerigini- onbellekten degil, bastan analiz eder.
    Birden fazla zayif konu varsa, hepsi paralel uretilip 'hazir' hale getirilir."""
    try:
        content_generator.clear_cache_for_exam(exam_id)
        vision_extract.clear_cache_for_exam(exam_id)
        scraper.sync_all(headless=True, force_exam_ids=[exam_id])

        data = load_data()
        exam = next(e for e in data["exams"] if e["id"] == exam_id)
        grade = (data.get("profile") or {}).get("grade") or 8
        weak = [w for w in analyzer.weak_topics(data) if w["exam_id"] == exam_id]
        items, errors = generate_weak_topics_parallel(exam, weak, grade)

        msg = f"Sınav yeniden analiz edildi, {len(items)} konu hazır."
        if errors:
            msg += f" {len(errors)} konu üretilemedi: {errors[0]}"
        flash(msg, "error" if errors and not items else "success")
    except RuntimeError as e:
        flash(str(e), "error")
    except Exception as e:  # pragma: no cover - runtime feedback
        flash(f"Yeniden analiz hatası: {e}", "error")
    return redirect(url_for("exam_detail", exam_id=exam_id))


def _load_topic_context(exam_id, subject_index, kID, force=False):
    """topic_detail ve export_topic arasinda paylasilan yukleme/uretim mantigi."""
    data = load_data()
    exam = next(e for e in data["exams"] if e["id"] == exam_id)
    subj = next(s for s in exam["subjects"] if s["index"] == subject_index)
    topic = next(t for t in subj["detail"]["topics"] if t["kID"] == kID)
    grade = (data.get("profile") or {}).get("grade") or 8

    peer_scores = [
        v for v in [topic["class_avg"], topic["school_avg"], topic["all_schools_avg"]]
        if v is not None
    ]
    peer_avg = sum(peer_scores) / len(peer_scores) if peer_scores else 0
    wrong_questions = get_wrong_question_texts(exam_id, subj)
    content = content_generator.generate_topic_content(
        subject_name=subj["name"],
        topic_name=topic["name"],
        grade=grade,
        student_score=topic["student"],
        peer_avg=peer_avg,
        exam_id=exam_id,
        subject_index=subject_index,
        kID=kID,
        wrong_questions=wrong_questions,
        force=force,
    )
    return exam, subj, topic, peer_avg, wrong_questions, content


@app.route("/topic/<exam_id>/<int:subject_index>/<kID>")
def topic_detail(exam_id, subject_index, kID):
    force = request.args.get("force") == "1"
    wrong_questions = []
    try:
        exam, subj, topic, peer_avg, wrong_questions, content = _load_topic_context(
            exam_id, subject_index, kID, force=force
        )
        error = None
    except RuntimeError as e:
        data = load_data()
        exam = next(e for e in data["exams"] if e["id"] == exam_id)
        subj = next(s for s in exam["subjects"] if s["index"] == subject_index)
        topic = next(t for t in subj["detail"]["topics"] if t["kID"] == kID)
        content = None
        error = str(e)

    return render_template(
        "topic.html",
        exam=exam,
        subj=subj,
        topic=topic,
        content=content,
        error=error,
        wrong_questions=[wq for wq in wrong_questions if wq.get("okunabildi", True)],
    )


@app.route("/topic/<exam_id>/<int:subject_index>/<kID>/export")
def export_topic(exam_id, subject_index, kID):
    try:
        exam, subj, topic, peer_avg, wrong_questions, content = _load_topic_context(
            exam_id, subject_index, kID
        )
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("topic_detail", exam_id=exam_id, subject_index=subject_index, kID=kID))

    item = {
        "subject_name": subj["name"],
        "topic": topic["name"],
        "student": topic["student"],
        "peer_avg": peer_avg,
        "content": content,
        "wrong_questions": [wq for wq in wrong_questions if wq.get("okunabildi", True)],
    }
    safe_name = re.sub(r"[^\w]+", "_", topic["name"]).strip("_")[:40] or "konu"
    out_path = DATA_DIR / "reports" / f"{exam_id}_{subject_index}_{safe_name}.docx"
    docx_export.build_exam_report(exam, [item], out_path)
    return send_file(out_path, as_attachment=True)


@app.route("/exam/<exam_id>/export")
def export_exam(exam_id):
    data = load_data()
    exam = next(e for e in data["exams"] if e["id"] == exam_id)
    grade = (data.get("profile") or {}).get("grade") or 8
    weak = [w for w in analyzer.weak_topics(data) if w["exam_id"] == exam_id]

    items, errors = generate_weak_topics_parallel(exam, weak, grade)
    if not items and errors:
        flash(errors[0], "error")
        return redirect(url_for("exam_detail", exam_id=exam_id))
    if errors:
        flash(f"{len(errors)} konu üretilemedi, rapor kalan {len(items)} konuyla oluşturuldu.", "error")

    out_path = DATA_DIR / "reports" / f"{exam_id}.docx"
    docx_export.build_exam_report(exam, items, out_path)
    return send_file(out_path, as_attachment=True)


if __name__ == "__main__":
    # threaded=True: bir konu icin AI uretimi birkac dakika surebiliyor (25 soru +
    # web search); bu sirada diger sayfalarda gezinebilmek icin.
    app.run(debug=True, port=5000, threaded=True)
