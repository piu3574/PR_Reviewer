from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime

styles = getSampleStyleSheet()

# Custom styles for our report
section_style = ParagraphStyle(
    'SectionHeader', parent=styles['Heading2'],
    spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#1a1a2e")
)
label_style = ParagraphStyle(
    'Label', parent=styles['Normal'], fontSize=9, textColor=colors.grey
)


SEVERITY_COLORS = {
    "high": colors.HexColor("#d64545"),
    "medium": colors.HexColor("#e0a030"),
    "low": colors.HexColor("#6b8e6b")
}

RISK_COLORS = {
    "High": colors.HexColor("#d64545"),
    "Medium": colors.HexColor("#e0a030"),
    "Low": colors.HexColor("#6b8e6b")
}


def build_pr_summary(pr_data: dict) -> list:
    elements = []
    elements.append(Paragraph("AI PR Review Report", styles['Title']))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        label_style
    ))
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("PR Summary", section_style))
    summary_data = [
        ["Repository", f"{pr_data['owner']}/{pr_data['repo']}"],
        ["PR Number", f"#{pr_data['pr_number']}"],
        ["Title", pr_data.get('title', 'N/A')],
        ["Author", pr_data.get('author', 'N/A')],
        ["Files Changed", str(len(pr_data.get('files', [])))]
    ]
    table = Table(summary_data, colWidths=[1.5 * inch, 4.5 * inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(table)
    return elements


def build_scorecard(scores: dict) -> list:
    elements = []
    elements.append(Paragraph("Final Scorecard", section_style))
    elements.append(Paragraph(
        "Quality and maintainability scores are calculated deterministically "
        "from weighted issue counts. Security risk uses known risk floors for "
        "dangerous patterns (e.g. hardcoded secrets) in addition to tool-reported severity.",
        label_style
    ))
    elements.append(Spacer(1, 8))

    risk = scores.get('security_risk', 'Low')
    risk_color = RISK_COLORS.get(risk, colors.grey)

    score_data = [
        ["Metric", "Score"],
        ["Code Quality", f"{scores.get('quality_score', 'N/A')} / 10"],
        ["Security Risk", risk],
        ["Maintainability", f"{scores.get('maintainability_score', 'N/A')} / 10"],
    ]
    table = Table(score_data, colWidths=[3 * inch, 3 * inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('TEXTCOLOR', (1, 2), (1, 2), risk_color),
        ('FONTNAME', (1, 2), (1, 2), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    return elements


def build_issues_section(title: str, issues: list, source_filter: str) -> list:
    elements = []
    filtered = [i for i in issues if i['source'] == source_filter]

    elements.append(Paragraph(title, section_style))

    if not filtered:
        elements.append(Paragraph("No issues found in this category.", styles['Normal']))
        return elements

    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)

    table_data = [["File", "Line", "Type", "Severity", "Description"]]
    for issue in filtered:
        sev = issue.get('severity', 'low').lower()
        sev_color = SEVERITY_COLORS.get(sev, colors.black)
        sev_style = ParagraphStyle(
            'SevCell', parent=cell_style, textColor=sev_color, fontName='Helvetica-Bold'
        )

        table_data.append([
            Paragraph(issue.get('file_name', ''), cell_style),
            Paragraph(str(issue.get('line_number', '-')), cell_style),
            Paragraph(issue.get('issue_type', ''), cell_style),
            Paragraph(sev.upper(), sev_style),
            Paragraph(issue.get('description', ''), cell_style)
        ])

    table = Table(table_data, colWidths=[1.0 * inch, 0.4 * inch, 1.2 * inch, 0.7 * inch, 2.7 * inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(table)
    return elements


def build_verdict(scores: dict) -> list:
    elements = []
    elements.append(Paragraph("Final Verdict", section_style))

    quality = scores.get('quality_score', 10)
    risk = scores.get('security_risk', 'Low')

    if risk == "High":
        verdict = "This PR contains high security risk findings. Address these before merging."
    elif quality < 6:
        verdict = "This PR has significant code quality concerns. Review recommended before merging."
    elif quality < 8:
        verdict = "This PR is reasonable but has some issues worth addressing."
    else:
        verdict = "This PR looks good overall, with only minor issues noted."

    elements.append(Paragraph(verdict, styles['Normal']))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        "Note: This verdict is a generated summary based on calculated scores, "
        "not a substitute for human review.",
        label_style
    ))
    return elements


def generate_pdf_report(pr_data: dict, issues: list, scores: dict, output_path: str):
    """
    Builds the full PDF report and writes it to output_path.
    issues: list of dicts with file_name, line_number, issue_type,
            severity, source, description keys.
    scores: dict from scoring.calculate_all_scores()
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    story = []

    story.extend(build_pr_summary(pr_data))
    story.append(Spacer(1, 12))
    story.extend(build_scorecard(scores))
    story.append(PageBreak())

    story.extend(build_issues_section(
        "Static Analysis Findings (Tool-Verified)", issues, "static"
    ))
    story.append(Spacer(1, 16))
    story.extend(build_issues_section(
        "AI-Inferred Findings", issues, "ai"
    ))
    story.append(PageBreak())

    story.extend(build_verdict(scores))

    doc.build(story)
    return output_path