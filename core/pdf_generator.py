"""
Generator raportów PDF.

Używa Jinja2 do szablonów HTML i weasyprint/pdfkit do konwersji na PDF.
Fallback na html do pliku gdy biblioteki PDF nie są dostępne.
"""

import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import json

from core.models import Visit

# Sprawdź dostępność bibliotek PDF
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "pdf"


@dataclass
class ClinicConfig:
    """Konfiguracja gabinetu do nagłówka PDF."""
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
    """Generator raportów PDF z wizyt."""

    def __init__(self, clinic_config: Optional[ClinicConfig] = None):
        self.clinic_config = clinic_config or ClinicConfig()
        self._setup_jinja()

    def _setup_jinja(self) -> None:
        """Konfiguruje silnik szablonów Jinja2."""
        if not JINJA2_AVAILABLE:
            self.jinja_env = None
            return

        # Upewnij się że katalog szablonów istnieje
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Dodaj filtry
        self.jinja_env.filters['format_date'] = self._format_date
        self.jinja_env.filters['format_datetime'] = self._format_datetime

    @staticmethod
    def _format_date(value: datetime) -> str:
        """Formatuje datę do polskiego formatu."""
        if not value:
            return ""
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        """Formatuje datę i czas."""
        if not value:
            return ""
        return value.strftime("%d.%m.%Y, godz. %H:%M")

    def generate_visit_report(
        self,
        visit: Visit,
        output_path: Optional[str] = None,
        open_after: bool = False
    ) -> str:
        """
        Generuje raport PDF z wizyty.

        Args:
            visit: Obiekt wizyty
            output_path: Ścieżka do pliku wyjściowego (opcjonalna)
            open_after: Czy otworzyć plik po wygenerowaniu

        Returns:
            Ścieżka do wygenerowanego pliku
        """
        # Przygotuj dane do szablonu
        context = {
            'clinic': self.clinic_config.to_dict(),
            'visit': visit.to_dict(),
            'diagnoses': [d.to_dict() for d in visit.diagnoses],
            'procedures': [p.to_dict() for p in visit.procedures],
            'generated_at': datetime.now(),
            'visit_date': visit.visit_date,
            'patient_name': visit.patient_name or "Pacjent anonimowy",
        }

        # Renderuj HTML
        html_content = self._render_template('visit_report.html', context)

        # Określ ścieżkę wyjściową
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wizyta_{timestamp}.pdf"
            output_path = str(Path(tempfile.gettempdir()) / filename)

        # Generuj PDF
        if WEASYPRINT_AVAILABLE:
            self._generate_pdf_weasyprint(html_content, output_path)
        else:
            # Fallback: zapisz jako HTML
            output_path = output_path.replace('.pdf', '.html')
            Path(output_path).write_text(html_content, encoding='utf-8')
            print(f"[PDF] WeasyPrint niedostępny, zapisano jako HTML: {output_path}")

        # Otwórz plik
        if open_after:
            self._open_file(output_path)

        return output_path

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Renderuje szablon Jinja2."""
        if not self.jinja_env:
            # Fallback bez Jinja2
            return self._render_fallback(context)

        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            print(f"[PDF] Błąd szablonu: {e}, używam fallback")
            return self._render_fallback(context)

    def _render_fallback(self, context: Dict[str, Any]) -> str:
        """Prosty fallback gdy Jinja2 niedostępne."""
        clinic = context.get('clinic', {})
        visit = context.get('visit', {})
        diagnoses = context.get('diagnoses', [])
        procedures = context.get('procedures', [])

        diagnoses_html = ""
        for d in diagnoses:
            diagnoses_html += f"""
            <tr>
                <td>{d.get('icd10_code', '')}</td>
                <td>{d.get('location', '')}</td>
                <td>{d.get('icd10_name', '')}</td>
                <td>{d.get('description', '')}</td>
            </tr>
            """

        procedures_html = ""
        for p in procedures:
            procedures_html += f"""
            <tr>
                <td>{p.get('procedure_code', '')}</td>
                <td>{p.get('location', '')}</td>
                <td>{p.get('procedure_name', '')}</td>
                <td>{p.get('description', '')}</td>
            </tr>
            """

        visit_date = context.get('visit_date')
        if isinstance(visit_date, datetime):
            visit_date_str = visit_date.strftime("%d.%m.%Y, godz. %H:%M")
        else:
            visit_date_str = str(visit_date) if visit_date else ""

        return f"""
        <!DOCTYPE html>
        <html lang="pl">
        <head>
            <meta charset="UTF-8">
            <title>Raport wizyty</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; font-size: 12px; }}
                .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 20px; }}
                .clinic-name {{ font-size: 18px; font-weight: bold; }}
                .clinic-info {{ color: #666; margin-top: 5px; }}
                h1 {{ font-size: 16px; margin-top: 30px; }}
                h2 {{ font-size: 14px; color: #333; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f5f5f5; font-weight: bold; }}
                .transcript {{ background: #f9f9f9; padding: 15px; border-radius: 5px; white-space: pre-wrap; }}
                .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 10px; }}
                .meta {{ color: #666; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="clinic-name">{clinic.get('name', 'Gabinet Medyczny')}</div>
                <div class="clinic-info">
                    {clinic.get('address', '')}<br>
                    Tel: {clinic.get('phone', '')} | Email: {clinic.get('email', '')}
                </div>
            </div>

            <h1>DOKUMENTACJA WIZYTY</h1>
            <div class="meta">
                <strong>Data wizyty:</strong> {visit_date_str}<br>
                <strong>Pacjent:</strong> {context.get('patient_name', 'Anonimowy')}<br>
                <strong>Model AI:</strong> {visit.get('model_used', '-')}
            </div>

            <h2>Wywiad</h2>
            <div class="transcript">{visit.get('transcript', '-')}</div>

            <h2>Rozpoznanie (ICD-10)</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">Kod</th>
                        <th style="width: 100px;">Lokalizacja</th>
                        <th>Nazwa</th>
                        <th>Opis kliniczny</th>
                    </tr>
                </thead>
                <tbody>
                    {diagnoses_html if diagnoses_html else '<tr><td colspan="4" style="text-align: center; color: #999;">Brak diagnoz</td></tr>'}
                </tbody>
            </table>

            <h2>Wykonane procedury</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">Kod</th>
                        <th style="width: 100px;">Lokalizacja</th>
                        <th>Procedura</th>
                        <th>Opis wykonania</th>
                    </tr>
                </thead>
                <tbody>
                    {procedures_html if procedures_html else '<tr><td colspan="4" style="text-align: center; color: #999;">Brak procedur</td></tr>'}
                </tbody>
            </table>

            <div class="footer">
                Wygenerowano: {datetime.now().strftime("%d.%m.%Y %H:%M")} | System: Wywiad+ v2
            </div>
        </body>
        </html>
        """

    def _generate_pdf_weasyprint(self, html_content: str, output_path: str) -> None:
        """Generuje PDF używając WeasyPrint."""
        html = HTML(string=html_content, base_url=str(TEMPLATES_DIR))

        # Załaduj dodatkowe style jeśli istnieją
        css_path = TEMPLATES_DIR / "styles.css"
        stylesheets = []
        if css_path.exists():
            stylesheets.append(CSS(filename=str(css_path)))

        html.write_pdf(output_path, stylesheets=stylesheets)
        print(f"[PDF] Wygenerowano: {output_path}")

    def _open_file(self, path: str) -> None:
        """Otwiera plik w domyślnej aplikacji."""
        import subprocess
        import platform

        try:
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', path])
            else:
                subprocess.run(['xdg-open', path])
        except Exception as e:
            print(f"[PDF] Nie można otworzyć pliku: {e}")

    def update_clinic_config(self, **kwargs) -> None:
        """Aktualizuje konfigurację gabinetu."""
        for key, value in kwargs.items():
            if hasattr(self.clinic_config, key):
                setattr(self.clinic_config, key, value)


# Singleton
_pdf_generator: Optional[PDFGenerator] = None


def get_pdf_generator() -> PDFGenerator:
    """Zwraca singleton PDFGenerator."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator
