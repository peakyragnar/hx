from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

try:
    # List available models
    models = client.models.list()
    print("Available models:")
    for model in models.data:
        if "gpt" in model.id:
            print(f"  - {model.id}")
except Exception as e:
    print(f"Error: {e}")
