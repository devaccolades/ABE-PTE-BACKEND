import json
from collections import OrderedDict

from reportlab.platypus import (
    SimpleDocTemplate, Spacer, Paragraph, Table, TableStyle, Flowable
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# ======================
# LAYOUT CONSTANTS
# ======================
PAGE_WIDTH = 520
LEFT_COL = 320
RIGHT_COL = 160


# ======================
# HEADER (CANVAS)
# ======================
def draw_header(canvas, doc):
    canvas.saveState()

    canvas.setFillColorRGB(0.16, 0.62, 0.56)
    canvas.rect(0, doc.height + doc.topMargin - 10, doc.width + 80, 50, fill=1)

    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(40, doc.height + doc.topMargin + 10, "Axon Careers")

    canvas.setFont("Helvetica", 10)
    canvas.drawString(40, doc.height + doc.topMargin - 2, "Mock Test Score Report")

    canvas.restoreState()


# ======================
# SCORE BLOCK
# ======================
class ScoreBlock(Flowable):
    def __init__(self, score):
        super().__init__()
        self.score = int(score or 0)

    def wrap(self, availWidth, availHeight):
        return (120, 120)

    def draw(self):
        c = self.canv

        # Card background
        c.setFillColorRGB(0.42, 0.1, 0.6)
        c.roundRect(0, 0, 120, 120, 10, fill=1)

        # Label
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 10)
        c.drawCentredString(60, 85, "Overall")

        # Score
        c.setFont("Helvetica-Bold", 28)
        c.drawCentredString(60, 45, str(self.score))


# ======================
# SKILL ROW
# ======================
class SkillRow(Flowable):
    def __init__(self, label, score):
        super().__init__()
        self.label = label
        self.score = round(score or 0, 1)

    def wrap(self, availWidth, availHeight):
        return (PAGE_WIDTH, 20)

    def draw(self):
        c = self.canv

        # Label
        c.setFont("Helvetica", 10)
        c.drawString(0, 8, self.label)

        # Background bar
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.roundRect(100, 5, 200, 10, 3, fill=1)

        # Filled bar
        width = min(self.score * 2, 200)
        c.setFillColorRGB(0.2, 0.4, 0.6)
        c.roundRect(100, 5, width, 10, 3, fill=1)

        # Score text
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(320, 8, str(self.score))


# ======================
# SECTION WRAPPER
# ======================
def section(title, content):
    return Table(
        [
            [Paragraph(f"<b>{title}</b>", getSampleStyleSheet()["Normal"])],
            [content]
        ],
        style=[
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),

            ("LEFTPADDING", (0, 1), (-1, -1), 10),
            ("TOPPADDING", (0, 1), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
        ],
        colWidths=[PAGE_WIDTH]
    )


# ======================
# MAIN GENERATOR
# ======================
from django.template.loader import render_to_string
from weasyprint import HTML
from django.utils.timezone import localtime
from mocktest.models import UserResponse


def _as_display_text(value):
    if value in (None, ""):
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)

    return str(value)


def _section_css_class(section_name):
    section_name = (section_name or "").lower()

    if "speaking" in section_name:
        return "section-speaking"
    if "writing" in section_name:
        return "section-writing"
    if "reading" in section_name:
        return "section-reading"

    return "section-listening"


def _score_percent(score, maximum=100):
    try:
        score = float(score or 0)
        maximum = float(maximum or 0)
        if maximum <= 0:
            return 0
        return min(max((score / maximum) * 100, 0), 100)
    except (TypeError, ValueError):
        return 0


def _skill_score(responses, skill):
    awarded_field = f"{skill}_score_awarded"
    maximum_field = f"{skill}_score_max"
    evaluated = [response for response in responses if response.evaluated]
    awarded = sum(getattr(response, awarded_field) or 0 for response in evaluated)
    maximum = sum(
        getattr(response.question, maximum_field) or 0
        for response in evaluated
    )

    if maximum <= 0:
        return 0

    return round(min((awarded / maximum) * 90, 90), 2)


def _score_items(scores):
    if not isinstance(scores, dict):
        return []

    items = []
    for key, value in scores.items():
        score = value.get("score") if isinstance(value, dict) else value
        items.append({
            "label": str(key).replace("_", " ").title(),
            "score": score,
        })

    return items


def _feedback_items(feedback):
    if isinstance(feedback, str):
        return [{"label": "Feedback", "text": feedback}] if feedback.strip() else []

    if not isinstance(feedback, dict):
        return []

    return [
        {
            "label": str(key).replace("_", " ").title(),
            "text": _as_display_text(value),
        }
        for key, value in feedback.items()
        if key not in {"details", "explanation"}
        if value not in (None, "")
    ]


def _feedback_details(feedback):
    if not isinstance(feedback, dict):
        return []
    details = feedback.get("details")
    return details if isinstance(details, list) else []


def _reading_section_summary(subsections):
    scored = [subsection for subsection in subsections if subsection["total_max"] > 0]
    if not scored:
        return None

    total_score = sum(subsection["total_score"] for subsection in scored)
    total_max = sum(subsection["total_max"] for subsection in scored)
    accuracy = round((total_score / total_max) * 100, 1)
    strongest = max(scored, key=lambda subsection: subsection["percent"])
    focus = min(scored, key=lambda subsection: subsection["percent"])
    return {
        "accuracy": accuracy,
        "strongest": strongest["title"],
        "strongest_percent": strongest["percent"],
        "focus": focus["title"],
        "focus_percent": focus["percent"],
    }


def _evaluation_summary(responses):
    total = len(responses)
    completed = sum(1 for r in responses if r.evaluated or r.evaluation_status == "completed")
    failed = sum(1 for r in responses if r.evaluation_status == "failed")
    pending = total - completed - failed
    duplicate_groups = _duplicate_response_groups(responses)
    duplicate_rows = sum(max(0, len(group) - 1) for group in duplicate_groups.values())

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "duplicate_groups": len(duplicate_groups),
        "duplicate_rows": duplicate_rows,
        "is_complete": total == completed,
    }


def _duplicate_response_groups(responses):
    groups = {}
    for response in responses:
        key = (response.user_session_id, response.question_id)
        groups.setdefault(key, []).append(response)

    return {
        key: group
        for key, group in groups.items()
        if len(group) > 1
    }


def build_session_pdf_context(session):
    responses = list(
        UserResponse.objects
        .filter(user_session_id=session.pk)
        .select_related("question__subsection__section")
        .order_by(
            "question__mock_test_section__order",
            "question__subsection__order",
            "question__id",
            "submitted_at",
        )
    )

    structured = OrderedDict()
    duplicate_groups = _duplicate_response_groups(responses)
    duplicate_ids = {
        response.id
        for group in duplicate_groups.values()
        for response in group
    }

    for r in responses:
        question = r.question
        subsection_obj = question.subsection
        section_obj = subsection_obj.section if subsection_obj else None

        section_title = (
            section_obj.name
            if section_obj and section_obj.name
            else "Other"
        )

        subsection_title = (
            subsection_obj.get_name_display()
            if subsection_obj
            else "Other"
        )

        section_data = structured.setdefault(section_title, {
            "title": section_title,
            "css_class": _section_css_class(section_title),
            "subsections": OrderedDict(),
        })
        subsection_data = section_data["subsections"].setdefault(subsection_title, {
            "title": subsection_title,
            "responses": [],
            "avg_score": 0,
            "avg_percent": 0,
        })

        eval_data = r.evaluation_result or {}
        evaluation = (
            eval_data.get("evaluation", {})
            if isinstance(eval_data, dict)
            else {}
        )
        scores = evaluation.get("scores", {})
        feedback = evaluation.get("feedback", {})

        display_status = "completed" if r.evaluated else r.evaluation_status

        subsection_data["responses"].append({
            "question": question.text or question.name or f"Question {question.pk}",
            "answer": _as_display_text(r.answer_data),
            "response_id": r.id,
            "is_duplicate": r.id in duplicate_ids,
            "duplicate_count": len(duplicate_groups.get((r.user_session_id, r.question_id), [])),
            "evaluation_status": display_status,
            "evaluation_stage": r.evaluation_stage,
            "evaluation_error": r.evaluation_error,
            "skill_scores": {
                "speaking": r.speaking_score_awarded or 0,
                "writing": r.writing_score_awarded or 0,
                "reading": r.reading_score_awarded or 0,
                "listening": r.listening_score_awarded or 0,
            },
            "scores": _score_items(scores),
            "feedback": _feedback_items(feedback),
            "feedback_details": _feedback_details(feedback),
            "answer_explanation": (
                feedback.get("explanation", "")
                if isinstance(feedback, dict)
                else question.answer_explanation
            ) or question.answer_explanation,
            "total_score": (
                (r.speaking_score_awarded or 0) +
                (r.writing_score_awarded or 0) +
                (r.reading_score_awarded or 0) +
                (r.listening_score_awarded or 0)
            ),
            "max_score": (
                (question.speaking_score_max or 0) +
                (question.writing_score_max or 0) +
                (question.reading_score_max or 0) +
                (question.listening_score_max or 0)
            ),
        })

    # avg calculation
    sections = []
    for section_data in structured.values():
        subsections = []
        for subsection_data in section_data["subsections"].values():
            items = subsection_data["responses"]
            total = sum(i["total_score"] for i in items)
            maximum = sum(i["max_score"] for i in items)
            count = len(items) or 1
            avg_score = round(total / count, 2)
            avg_max = round(maximum / count, 2)
            subsection_data["avg_score"] = avg_score
            subsection_data["avg_max"] = avg_max
            subsection_data["avg_percent"] = _score_percent(avg_score, avg_max)
            subsection_data["total_score"] = total
            subsection_data["total_max"] = maximum
            subsection_data["percent"] = round(_score_percent(total, maximum), 1)
            subsections.append(subsection_data)

        section_data["subsections"] = subsections
        section_data["summary"] = (
            _reading_section_summary(subsections)
            if "reading" in section_data["title"].lower()
            else None
        )
        sections.append(section_data)

    return {
        "meta": {
            "name": session.name,
            "test": session.mock_test.title,
            "started_at": localtime(session.started_at),
        },
        "skills": {
            "speaking": _skill_score(responses, "speaking"),
            "writing": _skill_score(responses, "writing"),
            "reading": _skill_score(responses, "reading"),
            "listening": _skill_score(responses, "listening"),
            "overall": session.total_score,
        },
        "evaluation_summary": _evaluation_summary(responses),
        "sections": sections,
    }


def generate_session_pdf(session, file_path):
    context = build_session_pdf_context(session)
    html = render_to_string("pdf/session_report.html", context)
    HTML(string=html).write_pdf(file_path)
