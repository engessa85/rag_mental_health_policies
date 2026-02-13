from django.db import models
from pgvector.django import VectorField


class Document(models.Model):
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.id}: {self.filename}"


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)
    content = models.TextField()
    embedding = VectorField(dimensions=768)

    class Meta:
        indexes = [
            models.Index(fields=["document", "chunk_index"], name="rag_documen_documen_70d327_idx"),
        ]

    def __str__(self) -> str:
        return f"doc={self.document_id}, idx={self.chunk_index}, page={self.page_number}"
