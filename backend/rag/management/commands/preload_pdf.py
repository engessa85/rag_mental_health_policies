from django.conf import settings
from django.core.management.base import BaseCommand

from rag.models import Document
from rag.services import ingest_pdf_path


class Command(BaseCommand):
    help = "Preload a configured PDF into the vector database if it is not indexed yet."

    def handle(self, *args, **options):
        pdf_path = settings.PRELOAD_PDF_PATH
        filename = settings.PRELOAD_PDF_NAME

        if Document.objects.filter(filename=filename).exists():
            self.stdout.write(self.style.SUCCESS(f"PDF already indexed: {filename}"))
            return

        doc, chunks = ingest_pdf_path(pdf_path, filename=filename)
        self.stdout.write(self.style.SUCCESS(f"Indexed PDF id={doc.id}, filename={doc.filename}, chunks={chunks}"))
