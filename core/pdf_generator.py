"""
PDF report generator based on ReportLab (pure Python, no system deps).
"""

import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from core.models import Visit


@dataclass
class ClinicConfig:
    """Clinic header configuration."""
    name: str = "Gabinet Medyczny"
    address: str = ""
    phone: str = ""
    email: str = ""
    logo_path: Optional[str] = None
    doctor_name: str = ""
    nip: str = ""
    regon: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class PDFGenerator:
    """PDF report generator for visits (ReportLab)."""

    def __init__(self, clinic_config: Optional[ClinicConfig] = None):
        self.clinic_config = clinic_config or ClinicConfig()
        self.styles = getSampleStyleSheet()
        self.styles.add(
            ParagraphStyle(
                name="SectionTitle",
                parent=self.styles["Heading2"],
                fontSize=12,
                textColor=colors.black,
                spaceBefore=10,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="Small",
                parent=self.styles["Normal"],
                fontSize=9,
                leading=11,
                textColor=colors.HexColor("#555555"),
            )
        )

    @staticmethod
    def _format_date(value: datetime) -> str:
        if not value:
            return ""
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        if not value:
            return ""
        return value.strftime("%d.%m.%Y, %H:%M")

    def generate_visit_report(
        self,
        visit: Visit,
        output_path: Optional[str] = None,
        open_after: bool = False,
    ) -> str:
        visit_dict = visit.to_dict()
        diagnoses = [d.to_dict() for d in visit.diagnoses]
        procedures = [p.to_dict() for p in visit.procedures]

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wizyta_{timestamp}.pdf"
            output_path = str(Path(tempfile.gettempdir()) / filename)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        story = []
        clinic = self.clinic_config.to_dict()

        story.append(Paragraph(clinic.get("name", "Gabinet Medyczny"), self.styles["Heading1"]))
        clinic_lines = [
            clinic.get("address", ""),
            f"Tel: {clinic.get('phone', '')}  Email: {clinic.get('email', '')}",
        ]
        story.append(Paragraph("<br/>".join([l for l in clinic_lines if l]), self.styles["Small"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("DOKUMENTACJA WIZYTY", self.styles["SectionTitle"]))

        visit_date = visit.visit_date if hasattr(visit, "visit_date") else None
        visit_date_str = self._format_datetime(visit_date) if isinstance(visit_date, datetime) else str(visit_date or "")
        patient_name = visit.patient_name or "Pacjent anonimowy"
        model_used = visit_dict.get("model_used", "-")

        meta = (
            f"<b>Data wizyty:</b> {visit_date_str}<br/>"
            f"<b>Pacjent:</b> {patient_name}<br/>"
            f"<b>Model AI:</b> {model_used}"
        )
        story.append(Paragraph(meta, self.styles["Normal"]))
        story.append(Spacer(1, 8))

        story.append(Paragraph("Wywiad", self.styles["SectionTitle"]))
        transcript = visit_dict.get("transcript", "-") or "-"
        transcript_html = transcript.replace("\n", "<br/>")
        story.append(Paragraph(transcript_html, self.styles["Normal"]))
        story.append(Spacer(1, 10))

        story.append(Paragraph("Rozpoznanie (ICD-10)", self.styles["SectionTitle"]))
        diag_rows = [["Kod", "Lokalizacja", "Nazwa", "Opis kliniczny"]]
        if diagnoses:
            for d in diagnoses:
                diag_rows.append(
                    [
                        d.get("icd10_code", ""),
                        d.get("location", ""),
                        d.get("icd10_name", ""),
                        d.get("description", ""),
                    ]
                )
        else:
            diag_rows.append(["-", "-", "Brak diagnoz", "-"])

        diag_table = Table(diag_rows, colWidths=[22 * mm, 30 * mm, 60 * mm, 60 * mm])
        diag_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(diag_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("Wykonane procedury", self.styles["SectionTitle"]))
        proc_rows = [["Kod", "Lokalizacja", "Procedura", "Opis wykonania"]]
        if procedures:
            for p in procedures:
                proc_rows.append(
                    [
                        p.get("procedure_code", ""),
                        p.get("location", ""),
                        p.get("procedure_name", ""),
                        p.get("description", ""),
                    ]
                )
        else:
            proc_rows.append(["-", "-", "Brak procedur", "-"])

        proc_table = Table(proc_rows, colWidths=[22 * mm, 30 * mm, 60 * mm, 60 * mm])
        proc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(proc_table)
        story.append(Spacer(1, 12))

        footer = f"Wygenerowano: {datetime.now().strftime('%d.%m.%Y %H:%M')} | System: Wywiad+ v2"
        story.append(Paragraph(footer, self.styles["Small"]))

        doc.build(story)

        if open_after:
            self._open_file(output_path)

        return output_path

    def _open_file(self, path: str) -> None:
        """Open file in default app."""
        import subprocess
        import platform

        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            print(f"[PDF] Nie mozna otworzyc pliku: {e}")

    def update_clinic_config(self, **kwargs) -> None:
        """Update clinic configuration."""
        for key, value in kwargs.items():
            if hasattr(self.clinic_config, key):
                setattr(self.clinic_config, key, value)


_pdf_generator: Optional[PDFGenerator] = None


def get_pdf_generator() -> PDFGenerator:
    """Return singleton PDFGenerator."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator
