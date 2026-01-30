"""ACE-Tool API client for semantic search and prompt enhancement."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from .templates import (
        USER_AGENT, DEFAULT_MODEL,
        DEFAULT_CLAUDE_MODEL, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL,
        ENHANCE_PROMPT_TEMPLATE, ITERATIVE_ENHANCE_TEMPLATE,
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS,
    )
    from .utils import get_session_id, is_chinese_text, parse_chat_history
except ImportError:
    from templates import (
        USER_AGENT, DEFAULT_MODEL,
        DEFAULT_CLAUDE_MODEL, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL,
        ENHANCE_PROMPT_TEMPLATE, ITERATIVE_ENHANCE_TEMPLATE,
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS,
    )
    from utils import get_session_id, is_chinese_text, parse_chat_history


class AceToolClient:
    """Client for ACE-Tool API endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("ACE_API_URL", "")).rstrip("/")
        self.token = token or os.getenv("ACE_API_TOKEN", "")
        self.endpoint = (endpoint or os.getenv("ACE_ENHANCER_ENDPOINT", "new")).lower()
        self.timeout = httpx.Timeout(180.0, connect=30.0)

        self.third_party_base_url = os.getenv("PROMPT_ENHANCER_BASE_URL", "").rstrip("/")
        self.third_party_token = os.getenv("PROMPT_ENHANCER_TOKEN", "")
        self.third_party_model = os.getenv("PROMPT_ENHANCER_MODEL", "")

    def _get_headers(self, use_third_party: bool = False) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "x-request-id": str(uuid.uuid4()),
            "x-request-session-id": get_session_id(),
        }
        if use_third_party and self.third_party_token:
            headers["Authorization"] = f"Bearer {self.third_party_token}"
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _is_third_party(self) -> bool:
        return self.endpoint in ("claude", "openai", "gemini")

    def _get_third_party_model(self) -> str:
        if self.third_party_model:
            return self.third_party_model
        return {
            "claude": DEFAULT_CLAUDE_MODEL,
            "openai": DEFAULT_OPENAI_MODEL,
            "gemini": DEFAULT_GEMINI_MODEL,
        }.get(self.endpoint, DEFAULT_MODEL)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_context(self, project_root: str, query: str) -> dict:
        """Search codebase using natural language query."""
        return self._local_search(project_root, query)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def enhance_prompt(
        self,
        prompt: str,
        conversation_history: str,
        project_root: Optional[str] = None,
    ) -> dict:
        """Enhance prompt with codebase context and conversation history."""
        if self._is_third_party():
            return self._call_third_party_api(prompt, conversation_history)

        if not self.base_url:
            return {"enhanced_prompt": prompt, "note": "No API configured, returning original"}

        chat_history = parse_chat_history(conversation_history)

        if self.endpoint == "old":
            return self._call_old_endpoint(prompt, chat_history)
        return self._call_new_endpoint(prompt, chat_history)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def iterative_enhance(
        self,
        original_prompt: str,
        previous_enhanced: str,
        current_prompt: str,
        conversation_history: str,
    ) -> dict:
        """Iteratively enhance an already-enhanced prompt, preserving user modifications."""
        iterative_prompt = ITERATIVE_ENHANCE_TEMPLATE.format(
            original_prompt=original_prompt,
            previous_enhanced=previous_enhanced,
            current_prompt=current_prompt,
        )

        if self._is_third_party():
            return self._call_third_party_api_raw(iterative_prompt, conversation_history)

        if not self.base_url:
            return {"enhanced_prompt": current_prompt, "note": "No API configured, returning current"}

        chat_history = parse_chat_history(conversation_history)

        if self.endpoint == "old":
            return self._call_old_endpoint_raw(iterative_prompt, chat_history)
        return self._call_new_endpoint_raw(iterative_prompt, chat_history)

    def _call_new_endpoint(self, prompt: str, chat_history: list[dict]) -> dict:
        """Call /prompt-enhancer endpoint (new)."""
        payload = {
            "nodes": [{"id": 0, "type": 0, "text_node": {"content": prompt}}],
            "chat_history": chat_history,
            "conversation_id": None,
            "model": DEFAULT_MODEL,
            "mode": "CHAT",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/prompt-enhancer",
                headers=self._get_headers(),
                json=payload,
            )
            self._check_auth_error(resp.status_code)
            resp.raise_for_status()
            data = resp.json()
            return {"enhanced_prompt": data.get("text", prompt)}

    def _call_new_endpoint_raw(self, raw_prompt: str, chat_history: list[dict]) -> dict:
        """Call /prompt-enhancer with pre-built prompt."""
        payload = {
            "nodes": [{"id": 0, "type": 0, "text_node": {"content": raw_prompt}}],
            "chat_history": chat_history,
            "conversation_id": None,
            "model": DEFAULT_MODEL,
            "mode": "CHAT",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/prompt-enhancer",
                headers=self._get_headers(),
                json=payload,
            )
            self._check_auth_error(resp.status_code)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", raw_prompt)
            enhanced = self._extract_enhanced_prompt(text)
            return {"enhanced_prompt": enhanced}

    def _build_old_payload(self, message: str, chat_history: list[dict], language_guideline: str) -> dict:
        """Build payload for old endpoint."""
        return {
            "model": DEFAULT_MODEL,
            "path": None,
            "prefix": None,
            "selected_code": None,
            "suffix": None,
            "message": message,
            "chat_history": chat_history,
            "lang": None,
            "blobs": {"checkpoint_id": None, "added_blobs": [], "deleted_blobs": []},
            "user_guided_blobs": [],
            "context_code_exchange_request_id": None,
            "external_source_ids": [],
            "disable_auto_external_sources": None,
            "user_guidelines": language_guideline,
            "workspace_guidelines": "",
            "feature_detection_flags": {"support_parallel_tool_use": None},
            "third_party_override": None,
            "tool_definitions": [],
            "nodes": [{"id": 1, "type": 0, "text_node": {"content": message}}],
            "mode": "CHAT",
            "agent_memories": None,
            "persona_type": None,
            "rules": [],
            "silent": None,
            "enable_parallel_tool_use": None,
            "conversation_id": None,
            "system_prompt": None,
        }

    def _call_old_endpoint(self, prompt: str, chat_history: list[dict]) -> dict:
        """Call /chat-stream endpoint (old, streaming)."""
        final_prompt = ENHANCE_PROMPT_TEMPLATE.replace("{original_prompt}", prompt)
        language_guideline = "Please respond in Chinese (Simplified Chinese). 请用中文回复。" if is_chinese_text(prompt) else ""
        payload = self._build_old_payload(final_prompt, chat_history, language_guideline)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat-stream",
                headers=self._get_headers(),
                json=payload,
            )
            self._check_auth_error(resp.status_code)
            resp.raise_for_status()
            raw_text = self._parse_streaming_response(resp.text)
            enhanced = self._extract_enhanced_prompt(raw_text)
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _call_old_endpoint_raw(self, raw_prompt: str, chat_history: list[dict]) -> dict:
        """Call /chat-stream with pre-built prompt."""
        language_guideline = "Please respond in Chinese (Simplified Chinese). 请用中文回复。" if is_chinese_text(raw_prompt) else ""
        payload = self._build_old_payload(raw_prompt, chat_history, language_guideline)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat-stream",
                headers=self._get_headers(),
                json=payload,
            )
            self._check_auth_error(resp.status_code)
            resp.raise_for_status()
            raw_text = self._parse_streaming_response(resp.text)
            enhanced = self._extract_enhanced_prompt(raw_text)
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _parse_streaming_response(self, body: str) -> str:
        """Parse streaming response from /chat-stream endpoint."""
        combined = []
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("data:"):
                line = line[5:].strip() if line.startswith("data:") else ""
            if not line or line == "[DONE]":
                continue
            try:
                data = json.loads(line)
                if text := data.get("text"):
                    combined.append(text)
            except json.JSONDecodeError:
                continue
        return "".join(combined) if combined else body

    def _extract_enhanced_prompt(self, text: str) -> str:
        """Extract enhanced prompt from XML-like response."""
        pattern = r"<augment-enhanced-prompt(?:\s+[^>]*)?>\s*(.*?)\s*</augment-enhanced-prompt\s*>"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            extracted = match.group(1).strip()
            if extracted:
                return extracted
        return text

    def _replace_tool_names(self, text: str) -> str:
        """Replace Augment-specific tool names with ace-tool names."""
        return text.replace("codebase-retrieval", "search_context").replace(
            "codebase_retrieval", "search_context"
        )

    def _call_third_party_api(self, prompt: str, conversation_history: str) -> dict:
        """Call third-party API (Claude/OpenAI/Gemini)."""
        if not self.third_party_base_url or not self.third_party_token:
            return {"error": f"PROMPT_ENHANCER_BASE_URL and PROMPT_ENHANCER_TOKEN required for '{self.endpoint}' endpoint"}

        chat_history = parse_chat_history(conversation_history)
        model = self._get_third_party_model()
        final_prompt = ENHANCE_PROMPT_TEMPLATE.replace("{original_prompt}", prompt)
        language_hint = "\n\n请用中文回复。" if is_chinese_text(prompt) else ""
        full_prompt = f"{final_prompt}{language_hint}"

        return self._dispatch_third_party(full_prompt, chat_history, model)

    def _call_third_party_api_raw(self, raw_prompt: str, conversation_history: str) -> dict:
        """Call third-party API with pre-built prompt."""
        if not self.third_party_base_url or not self.third_party_token:
            return {"error": f"PROMPT_ENHANCER_BASE_URL and PROMPT_ENHANCER_TOKEN required for '{self.endpoint}' endpoint"}

        chat_history = parse_chat_history(conversation_history)
        model = self._get_third_party_model()
        language_hint = "\n\n请用中文回复。" if is_chinese_text(raw_prompt) else ""
        full_prompt = f"{raw_prompt}{language_hint}"

        return self._dispatch_third_party(full_prompt, chat_history, model)

    def _dispatch_third_party(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Dispatch to appropriate third-party API."""
        if self.endpoint == "claude":
            return self._call_claude_api(prompt, chat_history, model)
        elif self.endpoint == "openai":
            return self._call_openai_api(prompt, chat_history, model)
        elif self.endpoint == "gemini":
            return self._call_gemini_api(prompt, chat_history, model)
        return {"error": f"Unknown endpoint: {self.endpoint}"}

    def _call_claude_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call Claude API."""
        messages = chat_history + [{"role": "user", "content": prompt}]
        payload = {"model": model, "max_tokens": 4096, "messages": messages}

        base = self.third_party_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = f"{base}/v1/messages"

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.third_party_token,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            self._check_auth_error(resp.status_code, "Claude")
            resp.raise_for_status()
            data = resp.json()
            text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
            enhanced = self._extract_enhanced_prompt(text) if text else prompt
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _call_openai_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call OpenAI API."""
        messages = chat_history + [{"role": "user", "content": prompt}]
        payload = {"model": model, "messages": messages, "max_tokens": 4096}

        base = self.third_party_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = f"{base}/v1/chat/completions"

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=self._get_headers(use_third_party=True), json=payload)
            self._check_auth_error(resp.status_code, "OpenAI")
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            enhanced = self._extract_enhanced_prompt(text) if text else prompt
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _call_gemini_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call Gemini API."""
        contents = []
        for msg in chat_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {"contents": contents, "generationConfig": {"maxOutputTokens": 4096}}

        base = self.third_party_base_url.rstrip("/")
        if base.endswith("/v1beta"):
            base = base[:-7]
        url = f"{base}/v1beta/models/{model}:generateContent"

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": self.third_party_token},
                json=payload,
            )
            self._check_auth_error(resp.status_code, "Gemini")
            resp.raise_for_status()
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            enhanced = self._extract_enhanced_prompt(text) if text else prompt
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _check_auth_error(self, status: int, provider: str = "API"):
        if status == 401:
            raise httpx.HTTPStatusError(
                f"{provider} token invalid or expired",
                request=None,
                response=httpx.Response(status),
            )
        if status == 403:
            raise httpx.HTTPStatusError(
                f"{provider} access denied, token may be disabled",
                request=None,
                response=httpx.Response(status),
            )

    def _local_search(self, project_root: str, query: str) -> dict:
        """Fallback local search using keyword matching."""
        results = []
        root = Path(project_root)
        keywords = [w.lower() for w in re.findall(r"\w+", query.lower()) if len(w) > 2]

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if any(p in EXCLUDE_PATTERNS for p in file_path.parts):
                continue
            if any(part.startswith(".") for part in file_path.parts[len(root.parts):]):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore").lower()
                score = sum(1 for kw in keywords if kw in content)
                if score > 0:
                    results.append({"file": str(file_path.relative_to(root)), "score": score})
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:10], "query": query, "mode": "local_fallback"}

    def get_config(self) -> dict:
        """Get current configuration."""
        return {
            "base_url": self.base_url or "(not configured)",
            "endpoint": self.endpoint,
            "token_configured": bool(self.token),
            "third_party_configured": bool(self.third_party_base_url and self.third_party_token),
        }
