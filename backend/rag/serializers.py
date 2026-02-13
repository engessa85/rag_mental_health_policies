from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()
    document_id = serializers.IntegerField(required=False)


class UploadResponseSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    filename = serializers.CharField()
    chunks = serializers.IntegerField()
