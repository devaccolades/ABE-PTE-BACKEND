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
def generate_session_pdf(session, file_path):
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        file_path,
        leftMargin=40,
        rightMargin=40,
        topMargin=60,
        bottomMargin=40
    )

    elements = []

    # ======================
    # TOP SECTION (INFO + SCORE)
    # ======================
    info = [
        Paragraph(f"<b>{session.name}</b>", styles["Heading2"]),
        Paragraph(session.mock_test.title, styles["Normal"]),
        Spacer(1, 10),
        Paragraph(f"Session ID: {session.session_id}", styles["Normal"]),
    ]

    top = Table([
        [info, ScoreBlock(session.total_score)]
    ], colWidths=[LEFT_COL, RIGHT_COL])

    elements.append(top)
    elements.append(Spacer(1, 25))

    # ======================
    # SKILLS
    # ======================
    skills = [
        ("Listening", session.listening_score_awarded),
        ("Reading", session.reading_score_awarded),
        ("Speaking", session.speaking_score_awarded),
        ("Writing", session.writing_score_awarded),
    ]

    skill_elements = []
    for label, score in skills:
        skill_elements.append(SkillRow(label, score))
        skill_elements.append(Spacer(1, 12))

    elements.append(section("Communicative Skills", skill_elements))
    elements.append(Spacer(1, 20))

    # ======================
    # SESSION INFO
    # ======================
    session_info = [
        Paragraph(
            f"Started: {session.started_at.strftime('%d %b %Y')}",
            styles["Normal"]
        ),
        Paragraph(
            f"Completed: {session.completed_at.strftime('%d %b %Y') if session.completed_at else 'In Progress'}",
            styles["Normal"]
        ),
        Paragraph(
            f"Status: {'Completed' if session.is_completed else 'In Progress'}",
            styles["Normal"]
        ),
    ]

    elements.append(section("Session Information", session_info))

    doc.build(elements, onFirstPage=draw_header)