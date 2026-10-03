"""Datos configurables del estudiante para el pie de pagina de la interfaz."""
import os
from datetime import date


def student_footer(request):
    return {
        "student_name": os.getenv("STUDENT_NAME", "Nombre Completo del Estudiante"),
        "student_section": os.getenv("STUDENT_SECTION", "Seccion por completar"),
        "student_year": os.getenv("STUDENT_YEAR", str(date.today().year)),
    }