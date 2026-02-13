from django.db import migrations, models
import django.db.models.deletion
import pgvector.django


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.IntegerField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(dimensions=768)),
                (
                    "document",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="rag.document"),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["document", "chunk_index"], name="rag_documen_documen_70d327_idx")],
            },
        ),
    ]
