from django.urls import path

from .views import chat, chat_stream, health, init_vector_extension, upload_pdf

urlpatterns = [
    path("health/", health),
    path("init-vector/", init_vector_extension),
    path("upload/", upload_pdf),
    path("chat/", chat),
    path("chat/stream/", chat_stream),
]
