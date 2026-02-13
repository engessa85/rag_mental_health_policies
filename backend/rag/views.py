import json

from django.db import connection
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Document
from .serializers import ChatRequestSerializer
from .services import generate_answer, ingest_pdf, retrieve_context, stream_answer


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["POST"])
def upload_pdf(request):
    pdf = request.FILES.get("file")
    if not pdf:
        return Response({"error": "Missing 'file'"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        doc, chunk_count = ingest_pdf(pdf)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({"error": f"Failed to ingest PDF: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            "document_id": doc.id,
            "filename": doc.filename,
            "chunks": chunk_count,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def chat(request):
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    message = serializer.validated_data["message"]
    document_id = serializer.validated_data.get("document_id")

    if document_id is not None and not Document.objects.filter(id=document_id).exists():
        return Response({"error": "Invalid document_id"}, status=status.HTTP_404_NOT_FOUND)

    try:
        chunks = retrieve_context(message, document_id=document_id)
        answer = generate_answer(message, chunks)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({"error": f"Failed to generate answer: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            "answer": answer,
            "sources": _serialize_sources(chunks),
        }
    )


def _serialize_sources(chunks):
    return [
        {
            "content": chunk.content,
            "score": chunk.score,
            "page_number": chunk.page_number,
        }
        for chunk in chunks
    ]


@api_view(["POST"])
def chat_stream(request):
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    message = serializer.validated_data["message"]
    document_id = serializer.validated_data.get("document_id")

    if document_id is not None and not Document.objects.filter(id=document_id).exists():
        return Response({"error": "Invalid document_id"}, status=status.HTTP_404_NOT_FOUND)

    try:
        chunks = retrieve_context(message, document_id=document_id)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return Response({"error": f"Failed to retrieve context: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def event_stream():
        try:
            for delta in stream_answer(message, chunks):
                yield json.dumps({"type": "delta", "text": delta}) + "\n"
            yield json.dumps({"type": "sources", "sources": _serialize_sources(chunks)}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "error": f"Failed to generate answer: {exc}"}) + "\n"

    return StreamingHttpResponse(event_stream(), content_type="application/x-ndjson")


@api_view(["POST"])
def init_vector_extension(request):
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    return Response({"status": "vector extension ready"})
