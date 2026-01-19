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
from xml.sax.saxutils import escape as xml_escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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
    doctor_title: str = ""
    doctor_pwz: str = ""
    nip: str = ""
    regon: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class PDFGenerator:
    """PDF report generator for visits (ReportLab)."""

    def __init__(self, clinic_config: Optional[ClinicConfig] = None):
        self.clinic_config = clinic_config or ClinicConfig()
        self.styles = getSampleStyleSheet()

        # Register Unicode fonts (Polish diacritics)
        fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
        regular_path = fonts_dir / "DejaVuSans.ttf"
        bold_path = fonts_dir / "DejaVuSans-Bold.ttf"
        self.base_font = "Helvetica"
        self.bold_font = "Helvetica-Bold"
        try:
            if regular_path.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular_path)))
                self.base_font = "DejaVuSans"
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold_path)))
                self.bold_font = "DejaVuSans-Bold"
        except Exception:
            # Fallback to built-in fonts
            self.base_font = "Helvetica"
            self.bold_font = "Helvetica-Bold"

        # Apply fonts to base styles
        self.styles["Normal"].fontName = self.base_font
        self.styles["Heading1"].fontName = self.bold_font
        self.styles["Heading2"].fontName = self.bold_font
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
        self.styles.add(
            ParagraphStyle(
                name="FieldLabel",
                parent=self.styles["Normal"],
                fontSize=9,
                leading=11,
                fontName=self.bold_font,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TableCell",
                parent=self.styles["Normal"],
                fontSize=8.5,
                leading=10,
                wordWrap="CJK",
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TableHeader",
                parent=self.styles["Normal"],
                fontSize=8.5,
                leading=10,
                textColor=colors.black,
                spaceAfter=2,
                fontName=self.bold_font,
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

    @staticmethod
    def _safe_text(value) -> str:
        if value is None:
            return ""
        return str(value)

    def _sync_clinic_config(self) -> None:
        """Sync clinic config from config.json if available."""
        try:
            from core.config_manager import ConfigManager

            config = ConfigManager()
            self.update_clinic_config(
                name=config.get("clinic_name", self.clinic_config.name),
                address=config.get("clinic_address", self.clinic_config.address),
                phone=config.get("clinic_phone", self.clinic_config.phone),
                email=config.get("clinic_email", self.clinic_config.email),
                nip=config.get("clinic_nip", self.clinic_config.nip),
                regon=config.get("clinic_regon", self.clinic_config.regon),
                doctor_name=config.get("doctor_name", self.clinic_config.doctor_name),
                doctor_title=config.get("doctor_title", self.clinic_config.doctor_title),
                doctor_pwz=config.get("doctor_pwz", self.clinic_config.doctor_pwz),
            )
        except Exception:
            # Nie blokuj generowania PDF
            return

    def generate_visit_report(
        self,
        visit: Visit,
        output_path: Optional[str] = None,
        open_after: bool = False,
    ) -> str:
        self._sync_clinic_config()
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

        def fmt(value, fallback: str = "Brak danych") -> str:
            text = self._safe_text(value).strip()
            return text if text else fallback

        def add_text_section(title: str, content: str, always_show: bool = True) -> None:
            if not always_show and not (content or "").strip():
                return
            story.append(Paragraph(title, self.styles["SectionTitle"]))
            text = fmt(content) if always_show else self._safe_text(content)
            story.append(Paragraph(xml_escape(text).replace("\n", "<br/>"), self.styles["Normal"]))
            story.append(Spacer(1, 8))

        clinic_name = xml_escape(self._safe_text(clinic.get("name", "Gabinet Medyczny")) or "Gabinet Medyczny")
        story.append(Paragraph(clinic_name, self.styles["Heading1"]))
        clinic_lines = []
        if clinic.get("address"):
            clinic_lines.append(xml_escape(self._safe_text(clinic.get("address", ""))))
        contact_bits = []
        if clinic.get("phone"):
            contact_bits.append(f"Tel: {clinic.get('phone')}")
        if clinic.get("email"):
            contact_bits.append(f"Email: {clinic.get('email')}")
        if contact_bits:
            clinic_lines.append(xml_escape(" | ".join(contact_bits)))
        id_bits = []
        if clinic.get("nip"):
            id_bits.append(f"NIP: {clinic.get('nip')}")
        if clinic.get("regon"):
            id_bits.append(f"REGON: {clinic.get('regon')}")
        if id_bits:
            clinic_lines.append(xml_escape(" | ".join(id_bits)))
        if clinic_lines:
            story.append(Paragraph("<br/>".join(clinic_lines), self.styles["Small"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("DOKUMENTACJA WIZYTY AMBULATORYJNEJ", self.styles["SectionTitle"]))

        visit_date = visit.visit_date if hasattr(visit, "visit_date") else None
        visit_date_str = self._format_datetime(visit_date) if isinstance(visit_date, datetime) else str(visit_date or "")
        patient_name = self._safe_text(visit.patient_name or "Pacjent anonimowy")
        model_used = self._safe_text(visit_dict.get("model_used", "-"))

        meta_lines = [
            f"<b>Data wizyty:</b> {xml_escape(fmt(visit_date_str))}",
            f"<b>Pacjent:</b> {xml_escape(fmt(patient_name, 'Pacjent anonimowy'))}",
            f"<b>PESEL / identyfikator:</b> {xml_escape(fmt(getattr(visit, 'patient_identifier', '')))}",
            f"<b>Data urodzenia:</b> {xml_escape(fmt(getattr(visit, 'patient_birth_date', '')))}",
            f"<b>Plec:</b> {xml_escape(fmt(getattr(visit, 'patient_sex', '')))}",
            f"<b>Adres:</b> {xml_escape(fmt(getattr(visit, 'patient_address', '')))}",
            f"<b>Telefon:</b> {xml_escape(fmt(getattr(visit, 'patient_phone', '')))}",
            f"<b>Email:</b> {xml_escape(fmt(getattr(visit, 'patient_email', '')))}",
            f"<b>Model AI:</b> {xml_escape(fmt(model_used))}",
        ]
        story.append(Paragraph("<br/>".join(meta_lines), self.styles["Normal"]))
        story.append(Spacer(1, 8))

        doctor_title = self._safe_text(clinic.get("doctor_title", "")).strip()
        doctor_name = self._safe_text(clinic.get("doctor_name", "")).strip()
        doctor_display = " ".join([doctor_title, doctor_name]).strip()
        doctor_lines = [
            f"<b>Lekarz:</b> {xml_escape(fmt(doctor_display))}",
            f"<b>PWZ:</b> {xml_escape(fmt(clinic.get('doctor_pwz', '')))}",
        ]
        story.append(Paragraph("Dane lekarza", self.styles["SectionTitle"]))
        story.append(Paragraph("<br/>".join(doctor_lines), self.styles["Normal"]))
        story.append(Spacer(1, 8))

        transcript = visit_dict.get("transcript", "") or ""
        subjective_text = self._safe_text(getattr(visit, "subjective", "")).strip()
        if subjective_text:
            add_text_section("Wywiad (S)", subjective_text, always_show=True)
            add_text_section("Transkrypcja", transcript, always_show=False)
        else:
            add_text_section("Wywiad (S)", transcript or "", always_show=True)

        add_text_section("Badanie przedmiotowe (O)", getattr(visit, "objective", ""), always_show=True)
        add_text_section("Ocena / Rozpoznanie opisowe (A)", getattr(visit, "assessment", ""), always_show=True)

        story.append(Paragraph("Rozpoznanie (ICD-10)", self.styles["SectionTitle"]))
        diag_rows = [
            [
                Paragraph("Kod", self.styles["TableHeader"]),
                Paragraph("Lokalizacja", self.styles["TableHeader"]),
                Paragraph("Nazwa", self.styles["TableHeader"]),
                Paragraph("Opis kliniczny", self.styles["TableHeader"]),
            ]
        ]
        if diagnoses:
            for d in diagnoses:
                diag_rows.append(
                    [
                        Paragraph(xml_escape(self._safe_text(d.get("icd10_code"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(d.get("location"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(d.get("icd10_name"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(d.get("description"))), self.styles["TableCell"]),
                    ]
                )
        else:
            diag_rows.append(
                [
                    Paragraph("-", self.styles["TableCell"]),
                    Paragraph("-", self.styles["TableCell"]),
                    Paragraph("Brak diagnoz", self.styles["TableCell"]),
                    Paragraph("-", self.styles["TableCell"]),
                ]
            )

        diag_col_widths = [
            22 * mm,
            28 * mm,
            50 * mm,
            doc.width - (22 + 28 + 50) * mm,
        ]
        diag_table = Table(diag_rows, colWidths=diag_col_widths, repeatRows=1)
        diag_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), self.bold_font),
                    ("FONTNAME", (0, 1), (-1, -1), self.base_font),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(diag_table)
        story.append(Spacer(1, 10))

        add_text_section("Plan (P)", getattr(visit, "plan", ""), always_show=True)
        add_text_section("Zalecenia", getattr(visit, "recommendations", ""), always_show=True)
        add_text_section("Leki (z dawkowaniem)", getattr(visit, "medications", ""), always_show=True)
        add_text_section("Zlecone badania / konsultacje", getattr(visit, "tests_ordered", ""), always_show=True)
        add_text_section("Wyniki badan / konsultacji", getattr(visit, "tests_results", ""), always_show=True)
        add_text_section("Skierowania", getattr(visit, "referrals", ""), always_show=True)
        add_text_section("Zaswiadczenia / Niezdolnosc do pracy", getattr(visit, "certificates", ""), always_show=True)

        story.append(Paragraph("Wykonane procedury", self.styles["SectionTitle"]))
        proc_rows = [
            [
                Paragraph("Kod", self.styles["TableHeader"]),
                Paragraph("Lokalizacja", self.styles["TableHeader"]),
                Paragraph("Procedura", self.styles["TableHeader"]),
                Paragraph("Opis wykonania", self.styles["TableHeader"]),
            ]
        ]
        if procedures:
            for p in procedures:
                proc_rows.append(
                    [
                        Paragraph(xml_escape(self._safe_text(p.get("procedure_code"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(p.get("location"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(p.get("procedure_name"))), self.styles["TableCell"]),
                        Paragraph(xml_escape(self._safe_text(p.get("description"))), self.styles["TableCell"]),
                    ]
                )
        else:
            proc_rows.append(
                [
                    Paragraph("-", self.styles["TableCell"]),
                    Paragraph("-", self.styles["TableCell"]),
                    Paragraph("Brak procedur", self.styles["TableCell"]),
                    Paragraph("-", self.styles["TableCell"]),
                ]
            )

        proc_col_widths = [
            22 * mm,
            28 * mm,
            50 * mm,
            doc.width - (22 + 28 + 50) * mm,
        ]
        proc_table = Table(proc_rows, colWidths=proc_col_widths, repeatRows=1)
        proc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), self.bold_font),
                    ("FONTNAME", (0, 1), (-1, -1), self.base_font),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(proc_table)
        story.append(Spacer(1, 12))

        add_text_section("Dodatkowe uwagi", getattr(visit, "additional_notes", ""), always_show=True)

        story.append(Spacer(1, 6))
        story.append(Paragraph("Podpis osoby udzielajacej swiadczen:", self.styles["Small"]))
        story.append(Paragraph("........................................................", self.styles["Small"]))
        if doctor_display:
            story.append(Paragraph(xml_escape(doctor_display), self.styles["Small"]))
        if clinic.get("doctor_pwz"):
            story.append(Paragraph(f"PWZ: {xml_escape(self._safe_text(clinic.get('doctor_pwz')))}", self.styles["Small"]))

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
