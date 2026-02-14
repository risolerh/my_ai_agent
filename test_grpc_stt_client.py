import asyncio
import os
import sys

# Ensure imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.grpc_stt import GrpcSttStrategy

async def test_client():
    print("Testing GrpcSttStrategy...")
    
    # Use the path to the model we know exists
    model_path = "/home/risolerh/proyectos/service_agent_voice/models/vosk-model-en-us-0.22"
    
    client = GrpcSttStrategy(
        strategy="vosk",
        model_path=model_path
    )
    
    print("Initializing client...")
    client.initialize(sample_rate=16000)
    
    # Mock callback
    def on_partial(text):
        print(f"Partial: {text}")
        
    def on_final(text, confidence):
        print(f"Final: {text} (conf: {confidence})")
        
    client.set_on_partial(on_partial)
    client.set_on_final(on_final)
    
    print("Sending silence (simulating audio)...")
    # Send 5 chunks of silence
    for i in range(5):
        client.process(b'\x00' * 4000)
        await asyncio.sleep(0.1)
        
    print("Stopping client...")
    client.close()
    print("Test finished.")

if __name__ == "__main__":
    asyncio.run(test_client())
