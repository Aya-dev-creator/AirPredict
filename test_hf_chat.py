#!/usr/bin/env python3
"""Test Hugging Face Chat API"""
import requests
from config import config

hf_key = config.HF_CONFIG.get('api_key')

print(f'Testing Hugging Face API...')

# Use the HF router with OpenAI-compatible endpoint
url = 'https://router.huggingface.co/v1/chat/completions'
headers = {
    'Authorization': f'Bearer {hf_key}',
    'Content-Type': 'application/json',
}

# Try with different models
models_to_try = [
    'Qwen/Qwen2.5-0.5B-Instruct',
    'HuggingFaceTB/SmolLM2-360M-Instruct',
    'meta-llama/Llama-3.2-1B-Instruct',
]

payload_template = {
    'messages': [
        {'role': 'system', 'content': 'Tu es un expert en environnement. Reponds brievement en francais.'},
        {'role': 'user', 'content': 'Quelle est la qualite de lair a Casablanca?'}
    ],
    'max_tokens': 150,
    'temperature': 0.7,
}

for model in models_to_try:
    try:
        print(f'Trying HF model: {model}...')
        payload = {**payload_template, 'model': model}
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        print(f'  HTTP Status: {response.status_code}')
        
        if response.status_code == 200:
            result = response.json()
            msg = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            if msg:
                print(f'\nSUCCESS with Hugging Face model: {model}')
                print(f'Response: {msg}')
                break
            else:
                print(f'  Empty response')
        else:
            try:
                error = response.json()
                error_msg = error.get('error', {}).get('message', '') if isinstance(error, dict) else str(error)
                print(f'  Error: {error_msg[:100]}')
            except:
                print(f'  Error Status: {response.status_code}')
                print(f'  Body: {response.text[:100]}')
    except Exception as e:
        print(f'  Exception: {str(e)[:80]}')
else:
    print('\nNote: If HF also fails, you may need to activate your Groq account')
    print('Visit: https://console.groq.com/models and ensure models are available')
