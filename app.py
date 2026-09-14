import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, send_file, url_for

load_dotenv()

from bilfen import analyzer, content_generator, docx_export, login_flow, scraper, vision_extract  # noqa: E402

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
EXAMS_PATH = DATA_DIR / "exams.json"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")


def load_data():
    if not EXAMS_PATH.exists():
        return None
    return json.loads(EXAMS_PATH.read_text(encoding="utf-8"))


def get_wrong_question_texts(exam_id, subj):
    """Bir dersteki tum yanlis sorularin (varsa) goruntudeki metnini cikarir.
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
            results.append(data)
        except Exception:
            continue
    return results


@app.route("/")
def index():
    data = load_data()
    weak = analyzer.weak_topics(data) if data else []
    return render_template(
        "index.html",
        data=data,
        weak=weak,
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
    weak = [w for w in analyzer.weak_topics(data) if w["exam_id"] == exam_id]
    return render_template("exam.html", exam=exam, weak=weak)


@app.route("/topic/<exam_id>/<int:subject_index>/<kID>")
def topic_detail(exam_id, subject_index, kID):
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
    wrong_questions = []

    try:
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
        )
        error = None
    except RuntimeError as e:
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


@app.route("/exam/<exam_id>/export")
def export_exam(exam_id):
    data = load_data()
    exam = next(e for e in data["exams"] if e["id"] == exam_id)
    grade = (data.get("profile") or {}).get("grade") or 8
    weak = [w for w in analyzer.weak_topics(data) if w["exam_id"] == exam_id]

    items = []
    for w in weak:
        subj = next(s for s in exam["subjects"] if s["index"] == w["subject_index"])
        wrong_questions = get_wrong_question_texts(exam_id, subj)
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
        items.append({**w, "content": content, "wrong_questions": wrong_questions})

    out_path = DATA_DIR / "reports" / f"{exam_id}.docx"
    docx_export.build_exam_report(exam, items, out_path)
    return send_file(out_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
