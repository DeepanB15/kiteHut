"""
Professional Report Service (Phase 10).

Generates downloadable analysis reports in three formats:

    Markdown  - human-readable, git-friendly
    JSON      - machine-readable for tooling / CI
    PDF       - polished document via ReportLab (pure Python)

All formats are built from the persisted database records of an
analysis run (repository, run, findings, evidence, health, action plan).
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.evidence import Evidence
from app.db_models.repository import Repository
from app.db_models.repository_health import RepositoryHealth
from app.db_models.action_recommendation import ActionRecommendation
from app.db_models.root_cause_group import RootCauseGroup

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _gather_report_data(db: Session, analysis_id: int) -> dict | None:
    """Collect all report data for an analysis run (or None)."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        return None
    repo = db.query(Repository).filter(Repository.id == run.repository_id).first()
    findings = db.query(Finding).filter(
        Finding.analysis_run_id == analysis_id
    ).order_by(Finding.final_score.desc()).all()
    health = db.query(RepositoryHealth).filter(
        RepositoryHealth.analysis_run_id == analysis_id
    ).first()
    recommendations = db.query(ActionRecommendation).join(
        Finding, ActionRecommendation.finding_id == Finding.id
    ).filter(Finding.analysis_run_id == analysis_id).all()
    root_causes = db.query(RootCauseGroup).filter(
        RootCauseGroup.analysis_run_id == analysis_id
    ).all()

    return {
        "repository": repo,
        "run": run,
        "findings": findings,
        "health": health,
        "recommendations": recommendations,
        "root_causes": root_causes,
    }


def _finding_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "fingerprint": f.fingerprint,
        "claim_type": f.claim_type,
        "category": f.category,
        "statement": f.statement,
        "source_agent": f.source_agent,
        "truth_value": f.truth_value,
        "confidence": f.confidence,
        "severity": f.severity,
        "final_score": f.final_score,
        "priority": f.priority,
        "status": f.status,
    }


def build_json_report(db: Session, analysis_id: int) -> str:
    """Build the JSON report (indented)."""
    data = _gather_report_data(db, analysis_id)
    if data is None:
        raise ValueError("Analysis not found")

    repo, run, findings = data["repository"], data["run"], data["findings"]
    health = data["health"]

    report = {
        "report": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "format": "repolens-report/v1",
        },
        "repository": {
            "id": repo.id if repo else None,
            "url": repo.github_url if repo else None,
            "owner": repo.owner if repo else None,
            "name": repo.name if repo else None,
        },
        "analysis": {
            "id": run.id,
            "status": run.status,
            "branch": run.branch,
            "commit_hash": run.commit_hash,
            "mode": run.mode,
            "enabled_agents": _decode_agents(run.enabled_agents),
            "duration_seconds": run.duration_seconds,
            "total_findings": run.total_findings,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        },
        "health": {
            "overall_score": health.overall_score if health else None,
            "health_level": health.health_level if health else None,
            "critical_findings": health.critical_findings if health else 0,
            "summary": health.summary if health else None,
        } if health else None,
        "priority_summary": _priority_summary(findings),
        "findings": [_finding_dict(f) for f in findings],
        "action_recommendations": [
            {
                "finding_id": r.finding_id,
                "title": r.title,
                "effort": r.effort,
                "confidence": r.confidence,
            }
            for r in data["recommendations"]
        ],
        "root_causes": [
            {
                "root_cause": rc.root_cause,
                "category": rc.category,
                "finding_count": rc.finding_count,
                "priority": rc.priority,
            }
            for rc in data["root_causes"]
        ],
    }
    return json.dumps(report, indent=2, default=str)


def _decode_agents(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _priority_summary(findings: list[Finding]) -> dict:
    summary: dict[str, int] = {}
    for f in findings:
        summary[f.priority] = summary.get(f.priority, 0) + 1
    return summary


# ============================================================
# Markdown
# ============================================================

def build_markdown_report(db: Session, analysis_id: int) -> str:
    """Build the Markdown report."""
    data = _gather_report_data(db, analysis_id)
    if data is None:
        raise ValueError("Analysis not found")

    repo, run, findings = data["repository"], data["run"], data["findings"]
    health = data["health"]
    repo_name = f"{repo.owner}/{repo.name}" if repo else "unknown"

    lines = [
        f"# 🔍 RepoLens Analysis Report — {repo_name}",
        "",
        f"> Analysis #{run.id} · {run.branch} · "
        f"{run.created_at.isoformat() if run.created_at else 'unknown'}",
        f"> Mode: **{run.mode}** · Agents: "
        f"{', '.join(_decode_agents(run.enabled_agents) or ['all'])}",
        "",
    ]

    # Health
    if health:
        lines += [
            "## 📊 Repository Health",
            "",
            f"- **Score:** {health.overall_score:.0f}/100 "
            f"({health.health_level})",
            f"- **Critical findings:** {health.critical_findings}",
            f"- **Summary:** {health.summary or '—'}",
            "",
        ]

    # Priority summary
    summary = _priority_summary(findings)
    if summary:
        lines += ["## 🎯 Findings Summary", ""]
        for priority in ("P0", "P1", "P2", "P3", "P4"):
            if priority in summary:
                lines.append(f"- **{priority}:** {summary[priority]}")
        lines.append("")

    # Findings detail
    if findings:
        lines += ["## 🔎 Findings", ""]
        for f in sorted(findings, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)):
            lines += [
                f"### [{f.priority}] {f.claim_type.replace('_', ' ')} "
                f"({f.status})",
                "",
                f"{f.statement}",
                "",
                f"- **Category:** {f.category} · **Severity:** {f.severity} "
                f"· **Confidence:** {f.confidence:.0f}%",
                f"- **Score:** {f.final_score:.0f}/100 · **Source:** {f.source_agent}",
                "",
            ]
            evidence = db.query(Evidence).filter(
                Evidence.finding_id == f.id
            ).all()
            if evidence:
                lines += ["Evidence:", ""]
                for ev in evidence[:5]:
                    location = f"`{ev.file_path}:{ev.line_start}`" if ev.file_path else "—"
                    lines.append(f"- {location} ({ev.source}) — {ev.content[:120]}")
                lines.append("")

    # Action recommendations
    recs = data["recommendations"]
    if recs:
        lines += ["## 🔧 Recommended Actions", ""]
        for rec in recs[:10]:
            lines += [
                f"- **{rec.title}** (effort: {rec.effort}, "
                f"confidence: {rec.confidence:.0f}%)",
                f"  - {rec.description}",
                "",
            ]

    # Root causes
    if data["root_causes"]:
        lines += ["## 🧠 Root Causes", ""]
        for rc in data["root_causes"]:
            lines.append(
                f"- **{rc.root_cause}** ({rc.category}, {rc.finding_count} "
                f"finding(s), {rc.priority})"
            )
        lines.append("")

    lines += [
        "---",
        "_Generated by RepoLens. AI proposals are evidence-verified; "
        "verify critical findings before acting._",
        "",
    ]
    return "\n".join(lines)


# ============================================================
# PDF
# ============================================================

def build_pdf_report(db: Session, analysis_id: int) -> bytes:
    """
    Build the PDF report as bytes.

    Uses ReportLab (pure Python, no system dependencies). Raises
    RuntimeError with a hint when reportlab is not installed.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as error:
        raise RuntimeError(
            "PDF export requires reportlab — add it to requirements "
            "and reinstall dependencies."
        ) from error

    data = _gather_report_data(db, analysis_id)
    if data is None:
        raise ValueError("Analysis not found")

    repo, run, findings = data["repository"], data["run"], data["findings"]
    health = data["health"]
    repo_name = f"{repo.owner}/{repo.name}" if repo else "unknown"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RepoLensTitle", parent=styles["Title"], textColor=colors.HexColor("#1f2937")
    )
    heading_style = ParagraphStyle(
        "RepoLensHeading", parent=styles["Heading2"],
        textColor=colors.HexColor("#1d4ed8"), spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "RepoLensBody", parent=styles["BodyText"], fontSize=9, leading=12,
    )

    elements = [
        Paragraph(f"RepoLens Analysis Report — {repo_name}", title_style),
        Spacer(1, 4),
        Paragraph(
            f"Analysis #{run.id} · {run.branch} · "
            f"{run.created_at.strftime('%Y-%m-%d %H:%M') if run.created_at else 'unknown'}",
            styles["Italic"],
        ),
        Spacer(1, 12),
    ]

    if health:
        elements += [
            Paragraph("Repository Health", heading_style),
            Paragraph(
                f"<b>Score:</b> {health.overall_score:.0f}/100 "
                f"({health.health_level})<br/>"
                f"<b>Critical findings:</b> {health.critical_findings}<br/>"
                f"<b>Summary:</b> {health.summary or '—'}",
                body_style,
            ),
            Spacer(1, 10),
        ]

    if findings:
        elements.append(Paragraph("Findings", heading_style))
        table_rows = [["Priority", "Severity", "Category", "Finding", "Status"]]
        for f in sorted(findings, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)):
            table_rows.append([
                f.priority,
                f.severity,
                f.category,
                f.statement[:90],
                f.status,
            ])
        table = Table(
            table_rows,
            colWidths=[45, 55, 75, 250, 60],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 10))

    recs = data["recommendations"]
    if recs:
        elements.append(Paragraph("Recommended Actions", heading_style))
        for rec in recs[:10]:
            elements.append(Paragraph(
                f"<b>{rec.title}</b> (effort: {rec.effort})<br/>{rec.description}",
                body_style,
            ))
            elements.append(Spacer(1, 6))

    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(elements)
    return buffer.getvalue()