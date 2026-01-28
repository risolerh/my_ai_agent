import requests
import json
import os

class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def is_available(self):
        """Check if Ollama server is reachable."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self):
        """List available models in Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                # 'models' is the key in recent versions of Ollama API
                return [model['name'] for model in data.get('models', [])]
            return []
        except Exception as e:
            print(f"Error listing models: {e}")
            return []

    def ensure_model(self, model_name):
        """Pull a model if it doesn't exist."""
        current_models = self.list_models()
        if model_name not in current_models and f"{model_name}:latest" not in current_models:
             print(f"Model {model_name} not found. Attempting to pull...")
             try:
                 url = f"{self.base_url}/api/pull"
                 response = requests.post(url, json={"name": model_name}, stream=True)
                 for line in response.iter_lines():
                     if line:
                         data = json.loads(line)
                         status = data.get("status")
                         if status:
                             print(f"Pulling {model_name}: {status}")
                 print(f"Model {model_name} pulled successfully.")
                 return True
             except Exception as e:
                 print(f"Error pulling model {model_name}: {e}")
                 return False
        return True

    def generate(self, model, prompt, stream=False, callback=None):
        """
        Generate text response.
        If stream=True and callback provided, calls callback(text_chunk) for each chunk.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream
        }
        
        try:
            if stream:
                response = requests.post(url, json=payload, stream=True, timeout=30)
                full_text = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        chunk = data.get("response", "")
                        full_text += chunk
                        if callback:
                            callback(chunk)
                return full_text
            else:
                response = requests.post(url, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.json().get('response', "")
                else:
                    print(f"Ollama API Error: {response.text}")
                    return None
        except Exception as e:
            print(f"Error generating text: {e}")
            return None

if __name__ == "__main__":
    # Test execution
    client = OllamaClient()
    if client.is_available():
        print("Ollama is available via HTTP.")
        models = client.list_models()
        print(f"Available models: {models}")
        
        test_model = "llama2" # Default or pick first available if exists
        if models:
            test_model = models[0]
            
        print(f"Testing generation with model: {test_model}")
        response = client.generate(test_model, "Hello, are you working?")
        print(f"Response: {response}")
    else:
        print("Ollama server is not running at http://localhost:11434")
