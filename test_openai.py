#!/usr/bin/env python3
import os
from pathlib import Path

# Завантажуємо змінні середовища
def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

def test_openai():
    load_env()
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Знайди адресу в тексті: 'Здається квартира по вул. Хмельницького 84'"}
            ],
            max_tokens=30
        )
        
        print("✅ OpenAI API працює!")
        print("Відповідь:", response.choices[0].message.content)
        
    except Exception as e:
        print("❌ Помилка OpenAI:", e)

if __name__ == "__main__":
    test_openai() 