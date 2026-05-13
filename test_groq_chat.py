#!/usr/bin/env python3
"""Test Groq Chat API - Try multiple models"""
import requests
from config import config

groq_key = config.GROQ_CONFIG.get('api_key')

# Try multiple models from latest to fallback
models_to_try = [
    'llama-3.2-90b-text',
    'llama3-70b-8191',
    'llama3-8b-8191',
    'gemma-7b-it',
]

url = 'https://api.groq.com/openai/v1/chat/completions'
headers = {
    'Authorization': f'Bearer {groq_key}',
    'Content-Type': 'application/json',
}

payload_template = {
    'messages': [
        {'role': 'system', 'content': 'Tu es un expert en environnement. Reponds brievement.'},
        {'role': 'user', 'content': 'Quelle est la qualite de lair a Casablanca?'}
    ],
    'max_tokens': 150,
}

for model in models_to_try:
    try:
        print(f'Trying model: {model}...')
        payload = {**payload_template, 'model': model}
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f'  HTTP Status: {response.status_code}')
        
        if response.status_code == 200:
            result = response.json()
            msg = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f'\nSUCCESS with model: {model}')
            print(f'Response: {msg}')
            break
        else:
            try:
                error = response.json()
                error_msg = error.get('error', {}).get('message', '')
                print(f'  Error: {error_msg[:100]}')
            except:
                print(f'  Error: {response.status_code}')
    except Exception as e:
        print(f'  Exception: {str(e)[:80]}')
else:
    print('\nNo models worked. Check your Groq API key and available models at console.groq.com')

