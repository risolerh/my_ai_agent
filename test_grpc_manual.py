import grpc
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "protos"))

from protos import translate_pb2
from protos import translate_pb2_grpc

def test_grpc():
    host = os.getenv("TRANSLATE_SERVICE_HOST", "localhost")
    port = os.getenv("TRANSLATE_SERVICE_PORT", "5001") # Default to external port for test from host
    target = f"{host}:{port}"
    print(f"Connecting to {target}...")
    
    channel = grpc.insecure_channel(target)
    stub = translate_pb2_grpc.TranslationServiceStub(channel)
    
    try:
        response = stub.Translate(translate_pb2.TranslateRequest(
            text="Hello world",
            source_lang="en",
            target_lang="es"
        ))
        print(f"Response: {response.translated_text}")
    except grpc.RpcError as e:
        print(f"RPC failed: {e}")

if __name__ == "__main__":
    test_grpc()
