import grpc
import os
import sys

# Ensure we can import from protos which is in the parent directory
# modules/grpc_translator.py -> parent is modules/ -> parent is service_agent_voice/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "protos"))

from protos import translate_pb2
from protos import translate_pb2_grpc

class GrpcTranslator:
    def __init__(self, source_lang="en", target_lang="es", host="127.0.0.1", port=5001):
        self.source_lang = source_lang
        self.target_lang = target_lang
        # Allow override via env var
        host = os.getenv("TRANSLATE_SERVICE_HOST", host)
        port = os.getenv("TRANSLATE_SERVICE_PORT", str(port))
        
        self.target = f"{host}:{port}"
        print(f"Connecting to Translation Service at {self.target}...")
        self.channel = grpc.insecure_channel(self.target)
        self.stub = translate_pb2_grpc.TranslationServiceStub(self.channel)

    def translate(self, text: str) -> str:
        if not text:
            return ""
        try:
            request = translate_pb2.TranslateRequest(
                text=text,
                source_lang=self.source_lang,
                target_lang=self.target_lang
            )
            # Synchronous call
            response = self.stub.Translate(request)
            return response.translated_text
        except grpc.RpcError as e:
            status = e.code().name if hasattr(e, "code") else "UNKNOWN"
            details = e.details() if hasattr(e, "details") else str(e)
            print(f"[GrpcTranslator] RPC to {self.target} failed ({status}): {details}")
            return text

    def close(self):
        self.channel.close()
