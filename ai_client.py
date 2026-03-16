"""
Free AI Client - Supports Groq, Google Gemini, and Ollama (local)
No paid API keys required!
"""
import json
import base64
import re
import httpx
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from rich.console import Console

from config import (
    AI_PROVIDER, GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_VISION_MODEL,
    OPENAI_API_KEY, AI_MODEL, AI_VISION_MODEL,
    AI_PROMPTS
)

console = Console()


class AIClient(ABC):
    """Abstract base class for AI clients"""
    
    @abstractmethod
    def analyze_text(self, text: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze text and return structured data"""
        pass
    
    @abstractmethod
    def analyze_image(self, image_data: bytes, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze image and return structured data"""
        pass
    
    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this client supports image analysis"""
        pass
    
    def _parse_json_response(self, content: Optional[str]) -> Dict[str, Any]:
        """Parse JSON from AI response, handling markdown code blocks"""
        if not content:
            return {"error": "Empty response", "parse_error": True}
        
        # Remove markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Try to find JSON object in the response
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from the text
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return {"raw_content": content, "parse_error": True}


class GroqClient(AIClient):
    """
    Groq API Client - FREE and FAST!
    Get your free API key at: https://console.groq.com/keys
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key:
            raise ValueError(
                "Groq API key required. Get FREE key at: https://console.groq.com/keys"
            )
        self.model = GROQ_MODEL
        self.base_url = "https://api.groq.com/openai/v1"
    
    @property
    def supports_vision(self) -> bool:
        return False  # Groq doesn't support vision yet
    
    def analyze_text(self, text: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze text using Groq's fast LLM inference"""
        if prompt is None:
            prompt = AI_PROMPTS["text_extraction"]
        
        full_prompt = f"{prompt}\n\nTEXT TO ANALYZE:\n{text[:15000]}"  # Limit text length
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": full_prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 4096
                    }
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._parse_json_response(content)
                
        except Exception as e:
            console.print(f"[red]Groq API error: {e}[/red]")
            return {"error": str(e)}
    
    def analyze_image(self, image_data: bytes, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Groq doesn't support vision - returns error"""
        return {
            "error": "Groq doesn't support image analysis. Use Gemini or Ollama for vision.",
            "suggestion": "Set AI_PROVIDER=gemini or AI_PROVIDER=ollama in .env"
        }


class GeminiClient(AIClient):
    """
    Google Gemini Client - FREE tier with vision support!
    Get your free API key at: https://aistudio.google.com/apikey
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Get FREE key at: https://aistudio.google.com/apikey"
            )
        self.model = GEMINI_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    @property
    def supports_vision(self) -> bool:
        return True
    
    def analyze_text(self, text: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze text using Gemini"""
        if prompt is None:
            prompt = AI_PROMPTS["text_extraction"]
        
        full_prompt = f"{prompt}\n\nTEXT TO ANALYZE:\n{text[:30000]}"
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/models/{self.model}:generateContent",
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [
                            {"parts": [{"text": full_prompt}]}
                        ],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 4096
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                if "candidates" in result and result["candidates"]:
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
                    return self._parse_json_response(content)
                else:
                    return {"error": "No response from Gemini"}
                    
        except Exception as e:
            console.print(f"[red]Gemini API error: {e}[/red]")
            return {"error": str(e)}
    
    def analyze_image(self, image_data: bytes, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze image using Gemini Vision"""
        if prompt is None:
            prompt = AI_PROMPTS["vision_extraction"]
        
        # Encode image to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        try:
            with httpx.Client(timeout=90.0) as client:
                response = client.post(
                    f"{self.base_url}/models/{self.model}:generateContent",
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt},
                                    {
                                        "inline_data": {
                                            "mime_type": "image/png",
                                            "data": base64_image
                                        }
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 4096
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                if "candidates" in result and result["candidates"]:
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
                    return self._parse_json_response(content)
                else:
                    return {"error": "No response from Gemini Vision"}
                    
        except Exception as e:
            console.print(f"[red]Gemini Vision error: {e}[/red]")
            return {"error": str(e)}


class OllamaClient(AIClient):
    """
    Ollama Client - FREE local models, no API key needed!
    Install Ollama: https://ollama.ai
    Run: ollama pull llama3.2 && ollama pull llava
    """
    
    def __init__(self, host: Optional[str] = None):
        self.host = host or OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.vision_model = OLLAMA_VISION_MODEL
    
    @property
    def supports_vision(self) -> bool:
        return True
    
    def _check_ollama_running(self) -> bool:
        """Check if Ollama is running"""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except:
            return False
    
    def analyze_text(self, text: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze text using local Ollama model"""
        if not self._check_ollama_running():
            return {
                "error": "Ollama not running. Start with: ollama serve",
                "suggestion": "Install from https://ollama.ai, then run: ollama pull llama3.2"
            }
        
        if prompt is None:
            prompt = AI_PROMPTS["text_extraction"]
        
        full_prompt = f"{prompt}\n\nTEXT TO ANALYZE:\n{text[:10000]}"
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 4096
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                content = result.get("response", "")
                return self._parse_json_response(content)
                
        except Exception as e:
            console.print(f"[red]Ollama error: {e}[/red]")
            return {"error": str(e)}
    
    def analyze_image(self, image_data: bytes, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze image using Ollama's LLaVA model"""
        if not self._check_ollama_running():
            return {
                "error": "Ollama not running. Start with: ollama serve",
                "suggestion": "Install from https://ollama.ai, then run: ollama pull llava"
            }
        
        if prompt is None:
            prompt = AI_PROMPTS["vision_extraction"]
        
        # Encode image to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        try:
            with httpx.Client(timeout=180.0) as client:
                response = client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.vision_model,
                        "prompt": prompt,
                        "images": [base64_image],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 4096
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                content = result.get("response", "")
                return self._parse_json_response(content)
                
        except Exception as e:
            console.print(f"[red]Ollama LLaVA error: {e}[/red]")
            return {"error": str(e)}


class OpenAIClient(AIClient):
    """OpenAI Client - Paid option (fallback)"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        self.model = AI_MODEL
        self.vision_model = AI_VISION_MODEL
    
    @property
    def supports_vision(self) -> bool:
        return True
    
    def analyze_text(self, text: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze text using OpenAI"""
        from openai import OpenAI
        
        if prompt is None:
            prompt = AI_PROMPTS["text_extraction"]
        
        try:
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": f"{prompt}\n\nTEXT:\n{text[:15000]}"}
                ],
                temperature=0.1,
                max_tokens=4096
            )
            content = response.choices[0].message.content
            return self._parse_json_response(content)
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_image(self, image_data: bytes, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyze image using OpenAI Vision"""
        from openai import OpenAI
        
        if prompt is None:
            prompt = AI_PROMPTS["vision_extraction"]
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        try:
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1
            )
            content = response.choices[0].message.content
            return self._parse_json_response(content)
        except Exception as e:
            return {"error": str(e)}


def get_ai_client(provider: Optional[str] = None, api_key: Optional[str] = None) -> AIClient:
    """
    Factory function to get the appropriate AI client.
    
    Priority: groq > gemini > ollama > openai
    """
    provider = (provider or AI_PROVIDER).lower()
    
    console.print(f"[cyan]Using AI Provider: {provider.upper()}[/cyan]")
    
    if provider == "groq":
        key = api_key or GROQ_API_KEY
        if key:
            return GroqClient(key)
        console.print("[yellow]Groq key not set, trying Gemini...[/yellow]")
        provider = "gemini"
    
    if provider == "gemini":
        key = api_key or GEMINI_API_KEY
        if key:
            return GeminiClient(key)
        console.print("[yellow]Gemini key not set, trying Ollama...[/yellow]")
        provider = "ollama"
    
    if provider == "ollama":
        client = OllamaClient()
        if client._check_ollama_running():
            return client
        console.print("[yellow]Ollama not running, trying OpenAI...[/yellow]")
        provider = "openai"
    
    if provider == "openai":
        key = api_key or OPENAI_API_KEY
        if key:
            return OpenAIClient(key)
    
    raise ValueError(
        "No AI provider configured!\n\n"
        "FREE options:\n"
        "1. GROQ_API_KEY - Get free key at https://console.groq.com/keys\n"
        "2. GEMINI_API_KEY - Get free key at https://aistudio.google.com/apikey\n"
        "3. Ollama - Install from https://ollama.ai (local, no key needed)\n"
    )


if __name__ == "__main__":
    # Test the client
    console.print("[bold]Testing AI Client...[/bold]")
    
    try:
        client = get_ai_client()
        console.print(f"[green]✓ Client initialized: {type(client).__name__}[/green]")
        console.print(f"[green]✓ Supports vision: {client.supports_vision}[/green]")
        
        # Quick test
        result = client.analyze_text("LED Street Light 100W, 5000K CCT, 15000 lumens, IP66", prompt=None)
        console.print(f"[green]✓ Test result: {json.dumps(result, indent=2)[:500]}...[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
