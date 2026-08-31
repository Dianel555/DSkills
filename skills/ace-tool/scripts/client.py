"""ACE-Tool API client for semantic search and prompt enhancement."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

try:
    from .templates import (
        USER_AGENT, DEFAULT_MODEL,
        DEFAULT_CLAUDE_MODEL, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL,
        DEFAULT_CODEX_MODEL,
        ENV_ENHANCER_ENDPOINT, ENV_ENHANCER_ENDPOINT_LEGACY,
        ENV_ENHANCER_INCLUDE_SEARCH_CONTEXT,
        ENV_ENHANCER_REASONING_EFFORT,
        SEARCH_CONTEXT_CHAR_LIMIT, NO_RELEVANT_CODE_CONTEXT,
        ENHANCE_PROMPT_TEMPLATE, ITERATIVE_ENHANCE_TEMPLATE,
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS, RETRIEVAL_TIMEOUT, ENCODING_CHAIN,
    )
    from .utils import build_api_url, get_session_id, is_chinese_text, parse_chat_history, detect_and_read, load_session_auth
    from .indexer import Indexer
except ImportError:
    from templates import (
        USER_AGENT, DEFAULT_MODEL,
        DEFAULT_CLAUDE_MODEL, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL,
        DEFAULT_CODEX_MODEL,
        ENV_ENHANCER_ENDPOINT, ENV_ENHANCER_ENDPOINT_LEGACY,
        ENV_ENHANCER_INCLUDE_SEARCH_CONTEXT,
        ENV_ENHANCER_REASONING_EFFORT,
        SEARCH_CONTEXT_CHAR_LIMIT, NO_RELEVANT_CODE_CONTEXT,
        ENHANCE_PROMPT_TEMPLATE, ITERATIVE_ENHANCE_TEMPLATE,
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS, RETRIEVAL_TIMEOUT, ENCODING_CHAIN,
    )
    from utils import build_api_url, get_session_id, is_chinese_text, parse_chat_history, detect_and_read, load_session_auth
    from indexer import Indexer

import logging

log = logging.getLogger(__name__)

_ENHANCED_PROMPT_RE = re.compile(
    r"<augment-enhanced-prompt(?:\s+[^>]*)?>\s*(.*?)\s*</augment-enhanced-prompt\s*>",
    re.DOTALL,
)
_THIRD_PARTY_ENDPOINTS = frozenset({"claude", "openai", "gemini", "codex"})
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


class AceToolClient:
    """Client for ACE-Tool API endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        endpoint: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ):
        # Determine auth source priority: constructor params > session auth
        if base_url is not None or token is not None:
            # Constructor params provided (full or partial override)
            self.auth_source = "constructor"
            loaded_base_url, loaded_token, _ = load_session_auth()
            self.base_url = (base_url if base_url is not None else loaded_base_url or "").rstrip("/")
            self.token = token if token is not None else loaded_token or ""
        else:
            # No constructor params, use load_session_auth()
            loaded_base_url, loaded_token, auth_source = load_session_auth()
            self.base_url = (loaded_base_url or "").rstrip("/")
            self.token = loaded_token or ""
            self.auth_source = auth_source

        # Endpoint resolution: PROMPT_ENHANCER_ENDPOINT > ACE_ENHANCER_ENDPOINT > constructor arg > "new"
        env_endpoint = (
            os.getenv(ENV_ENHANCER_ENDPOINT, "")
            or os.getenv(ENV_ENHANCER_ENDPOINT_LEGACY, "")
        )
        resolved = env_endpoint or endpoint or "new"
        self.endpoint = resolved.lower()

        self.timeout = httpx.Timeout(180.0, connect=30.0)

        self.third_party_base_url = os.getenv("PROMPT_ENHANCER_BASE_URL", "").rstrip("/")
        self.third_party_token = os.getenv("PROMPT_ENHANCER_TOKEN", "")
        self.third_party_model = os.getenv("PROMPT_ENHANCER_MODEL", "")
        # Reasoning control: default none (enhancement needs no deep reasoning);
        # empty string sends no reasoning parameter at all.
        env_val = os.environ.get(ENV_ENHANCER_REASONING_EFFORT)
        if reasoning_effort is not None:
            self.reasoning_effort = reasoning_effort.strip().lower()
        elif env_val is not None:
            self.reasoning_effort = env_val.strip().lower()
        else:
            self.reasoning_effort = "none"

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
        return self.endpoint in _THIRD_PARTY_ENDPOINTS

    def _should_include_search_context(self) -> bool:
        """Check if search context injection is enabled via env var."""
        val = os.environ.get(ENV_ENHANCER_INCLUDE_SEARCH_CONTEXT, "").strip().lower()
        return val in _TRUE_ENV_VALUES

    @staticmethod
    def _normalize_search_context(text: str) -> str:
        """Normalize search context: placeholder for empty, truncate if over limit."""
        stripped = text.strip()
        if not stripped or stripped == NO_RELEVANT_CODE_CONTEXT:
            return NO_RELEVANT_CODE_CONTEXT
        if len(stripped) > SEARCH_CONTEXT_CHAR_LIMIT:
            return stripped[:SEARCH_CONTEXT_CHAR_LIMIT] + "\n\n[codebase_context truncated for length]"
        return stripped

    @staticmethod
    def _build_prompt_with_search_context(original: str, ctx: str) -> str:
        """Wrap original prompt with codebase context in XML tags."""
        return (
            f"<codebase_context>\n{ctx}\n</codebase_context>\n\n"
            f"<original_request>\n{original}\n</original_request>"
        )

    def _maybe_inject_search_context(self, endpoint: str, prompt: str, project_root: Optional[str]) -> str:
        """Inject search context into prompt if enabled and applicable."""
        if not self._is_third_party() or not self._should_include_search_context():
            return prompt
        if not project_root:
            raise ValueError("project_root is required when search context injection is enabled")
        if not self.base_url or not self.token:
            raise ValueError("No authentication configured for search context injection. Set up session.json, AUGMENT_SESSION_AUTH, or ACE_API_URL/ACE_API_TOKEN")
        result = self._remote_search(project_root, prompt)
        raw_ctx = result.get("results", "")
        ctx = self._normalize_search_context(raw_ctx)
        return self._build_prompt_with_search_context(prompt, ctx)

    def _get_third_party_model(self) -> str:
        if self.third_party_model:
            return self.third_party_model
        return {
            "claude": DEFAULT_CLAUDE_MODEL,
            "openai": DEFAULT_OPENAI_MODEL,
            "gemini": DEFAULT_GEMINI_MODEL,
            "codex": DEFAULT_CODEX_MODEL,
        }.get(self.endpoint, DEFAULT_MODEL)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def search_context(self, project_root: str, query: str) -> dict:
        """Search codebase: remote via ACE API if available, else local fallback."""
        if self.base_url and self.token:
            try:
                return self._remote_search(project_root, query)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    log.error("Auth failed (%d) for remote search: %s", e.response.status_code, e)
                else:
                    log.warning("Remote search failed, falling back to local: %s", e)
            except Exception as e:
                log.warning("Remote search failed, falling back to local: %s", e)
        return self._local_search(project_root, query)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_not_exception_type(ValueError))
    def enhance_prompt(
        self,
        prompt: str,
        conversation_history: str,
        project_root: Optional[str] = None,
    ) -> dict:
        """Enhance prompt with codebase context and conversation history."""
        if self._is_third_party():
            return self._call_third_party_api(prompt, conversation_history, project_root)

        if not self.base_url:
            return {"enhanced_prompt": prompt, "note": "No API configured, returning original"}

        chat_history = parse_chat_history(conversation_history)

        if self.endpoint == "old":
            return self._call_old_endpoint(prompt, chat_history, project_root)
        return self._call_new_endpoint(prompt, chat_history, project_root)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_not_exception_type(ValueError))
    def iterative_enhance(
        self,
        original_prompt: str,
        previous_enhanced: str,
        current_prompt: str,
        conversation_history: str,
        project_root: Optional[str] = None,
    ) -> dict:
        """Iteratively enhance an already-enhanced prompt, preserving user modifications."""
        iterative_prompt = ITERATIVE_ENHANCE_TEMPLATE.format(
            original_prompt=original_prompt,
            previous_enhanced=previous_enhanced,
            current_prompt=current_prompt,
        )

        if self._is_third_party():
            return self._call_third_party_api_raw(iterative_prompt, conversation_history, project_root)

        if not self.base_url:
            return {"enhanced_prompt": current_prompt, "note": "No API configured, returning current"}

        chat_history = parse_chat_history(conversation_history)

        if self.endpoint == "old":
            return self._call_old_endpoint_raw(iterative_prompt, chat_history, project_root)
        return self._call_new_endpoint_raw(iterative_prompt, chat_history, project_root)

    def _call_new_endpoint(self, prompt: str, chat_history: list[dict], project_root: Optional[str] = None) -> dict:
        """Call /prompt-enhancer endpoint (new)."""
        context = self._get_retrieval_context(project_root, prompt)
        enriched_prompt = f"{context}{prompt}" if context else prompt
        payload = {
            "nodes": [{"id": 0, "type": 0, "text_node": {"content": enriched_prompt}}],
            "chat_history": chat_history,
            "conversation_id": None,
            "model": DEFAULT_MODEL,
            "mode": "CHAT",
        }

        data = self._post_json(
            build_api_url(self.base_url, "/prompt-enhancer"),
            payload, headers=self._get_headers(),
        )
        return {"enhanced_prompt": data.get("text", prompt)}

    def _call_new_endpoint_raw(self, raw_prompt: str, chat_history: list[dict], project_root: Optional[str] = None) -> dict:
        """Call /prompt-enhancer with pre-built prompt."""
        context = self._get_retrieval_context(project_root, raw_prompt)
        enriched_prompt = f"{context}{raw_prompt}" if context else raw_prompt
        payload = {
            "nodes": [{"id": 0, "type": 0, "text_node": {"content": enriched_prompt}}],
            "chat_history": chat_history,
            "conversation_id": None,
            "model": DEFAULT_MODEL,
            "mode": "CHAT",
        }

        data = self._post_json(
            build_api_url(self.base_url, "/prompt-enhancer"),
            payload, headers=self._get_headers(),
        )
        text = data.get("text", raw_prompt)
        return {"enhanced_prompt": self._extract_enhanced_prompt(text)}

    def _build_old_payload(self, message: str, chat_history: list[dict], language_guideline: str, blob_names: list[str] | None = None) -> dict:
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
            "blobs": {"checkpoint_id": None, "added_blobs": blob_names or [], "deleted_blobs": []},
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

    def _get_blob_names(self, project_root: Optional[str]) -> list[str] | None:
        """Get blob_names from indexer if API and project_root are available."""
        if not project_root or not self.base_url or not self.token:
            return None
        try:
            indexer = Indexer(project_root, self.base_url, self.token)
            return indexer.get_blob_names()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                log.error("Auth failed (%d) getting blob names: %s", e.response.status_code, e)
            else:
                log.warning("Failed to get blob names: %s", e)
            return None
        except Exception as e:
            log.warning("Failed to get blob names: %s", e)
            return None

    def _get_retrieval_context(self, project_root: Optional[str], query: str) -> str:
        """Get cloud retrieval context to inject into prompts for non-old endpoints."""
        if not project_root or not self.base_url or not self.token:
            return ""
        try:
            result = self._remote_search(project_root, query)
            context = result.get("results", "")
            if context:
                return f"\n\n<codebase-context>\n{context}\n</codebase-context>\n\n"
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                log.error("Auth failed (%d) for cloud retrieval: %s", e.response.status_code, e)
            else:
                log.warning("Cloud retrieval failed, proceeding without context: %s", e)
        except Exception as e:
            log.warning("Cloud retrieval failed, proceeding without context: %s", e)
        return ""

    def _call_old_endpoint(self, prompt: str, chat_history: list[dict], project_root: Optional[str] = None) -> dict:
        """Call /chat-stream endpoint (old, streaming)."""
        final_prompt = ENHANCE_PROMPT_TEMPLATE.replace("{original_prompt}", prompt)
        language_guideline = "Please respond in Chinese (Simplified Chinese). 请用中文回复。" if is_chinese_text(prompt) else ""
        blob_names = self._get_blob_names(project_root)
        payload = self._build_old_payload(final_prompt, chat_history, language_guideline, blob_names)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                build_api_url(self.base_url, "/chat-stream"),
                headers=self._get_headers(),
                json=payload,
            )
            self._check_auth_error(resp.status_code)
            resp.raise_for_status()
            raw_text = self._parse_streaming_response(resp.text)
            enhanced = self._extract_enhanced_prompt(raw_text)
            enhanced = self._replace_tool_names(enhanced)
            return {"enhanced_prompt": enhanced}

    def _call_old_endpoint_raw(self, raw_prompt: str, chat_history: list[dict], project_root: Optional[str] = None) -> dict:
        """Call /chat-stream with pre-built prompt."""
        language_guideline = "Please respond in Chinese (Simplified Chinese). 请用中文回复。" if is_chinese_text(raw_prompt) else ""
        blob_names = self._get_blob_names(project_root)
        payload = self._build_old_payload(raw_prompt, chat_history, language_guideline, blob_names)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                build_api_url(self.base_url, "/chat-stream"),
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
        match = _ENHANCED_PROMPT_RE.search(text)
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

    def _post_json(
        self,
        url: str,
        payload: dict,
        *,
        headers: dict,
        provider: str = "API",
        timeout: httpx.Timeout | None = None,
    ) -> dict:
        with httpx.Client(timeout=timeout or self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            self._check_auth_error(resp.status_code, provider)
            resp.raise_for_status()
            return resp.json()

    def _enhanced_prompt_from_text(self, text: str, fallback: str) -> dict:
        enhanced = self._extract_enhanced_prompt(text) if text else fallback
        return {"enhanced_prompt": self._replace_tool_names(enhanced)}

    def _call_third_party_api(self, prompt: str, conversation_history: str, project_root: Optional[str] = None) -> dict:
        """Call third-party API (Claude/OpenAI/Gemini/Codex)."""
        if not self.third_party_base_url or not self.third_party_token:
            raise ValueError(
                f"PROMPT_ENHANCER_BASE_URL and PROMPT_ENHANCER_TOKEN required for '{self.endpoint}' endpoint"
            )

        chat_history = parse_chat_history(conversation_history)
        model = self._get_third_party_model()
        injected_prompt = self._maybe_inject_search_context(self.endpoint, prompt, project_root)
        final_prompt = ENHANCE_PROMPT_TEMPLATE.replace("{original_prompt}", injected_prompt)
        language_hint = "\n\n请用中文回复。" if is_chinese_text(prompt) else ""
        full_prompt = f"{final_prompt}{language_hint}"

        return self._dispatch_third_party(full_prompt, chat_history, model)

    def _call_third_party_api_raw(self, raw_prompt: str, conversation_history: str, project_root: Optional[str] = None) -> dict:
        """Call third-party API with pre-built prompt."""
        if not self.third_party_base_url or not self.third_party_token:
            raise ValueError(
                f"PROMPT_ENHANCER_BASE_URL and PROMPT_ENHANCER_TOKEN required for '{self.endpoint}' endpoint"
            )

        chat_history = parse_chat_history(conversation_history)
        model = self._get_third_party_model()
        injected_prompt = self._maybe_inject_search_context(self.endpoint, raw_prompt, project_root)
        language_hint = "\n\n请用中文回复。" if is_chinese_text(raw_prompt) else ""
        full_prompt = f"{injected_prompt}{language_hint}"

        return self._dispatch_third_party(full_prompt, chat_history, model)

    def _dispatch_third_party(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Dispatch to appropriate third-party API."""
        if self.endpoint == "claude":
            return self._call_claude_api(prompt, chat_history, model)
        elif self.endpoint == "openai":
            return self._call_openai_api(prompt, chat_history, model)
        elif self.endpoint == "gemini":
            return self._call_gemini_api(prompt, chat_history, model)
        elif self.endpoint == "codex":
            return self._call_codex_api(prompt, chat_history, model)
        return {"error": f"Unknown endpoint: {self.endpoint}"}

    @staticmethod
    def _extract_codex_output_text(api_response: dict) -> str:
        outputs = api_response.get("output", [])
        final = [o for o in outputs if o.get("type") == "message" and o.get("phase") == "final_answer"]
        candidates = final or [o for o in outputs if o.get("type") == "message"]
        text_parts, refusal_parts = [], []
        for msg in candidates:
            for part in (msg.get("content") or []):
                t = part.get("type")
                if t == "output_text":
                    txt = (part.get("text") or "").strip()
                    if txt:
                        text_parts.append(txt)
                elif t == "refusal":
                    rf = (part.get("refusal") or "").strip()
                    if rf:
                        refusal_parts.append(rf)
        if text_parts:
            return "\n".join(text_parts)
        if refusal_parts:
            raise RuntimeError(f"Codex API refusal: {chr(10).join(refusal_parts)}")
        raise RuntimeError("Codex API returned no output_text content")

    def _call_codex_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        input_items = []
        for msg in chat_history:
            input_items.append({"role": msg["role"], "content": msg["content"]})
        input_items.append({"role": "user", "content": prompt})

        payload = {"model": model, "input": input_items}
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        url = build_api_url(self.third_party_base_url, "/v1/responses")

        data = self._post_json(url, payload, headers=self._get_headers(use_third_party=True), provider="Codex")
        text = self._extract_codex_output_text(data)
        return self._enhanced_prompt_from_text(text, prompt)

    def _call_claude_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call Claude API."""
        messages = chat_history + [{"role": "user", "content": prompt}]
        payload = {"model": model, "max_tokens": 4096, "messages": messages}
        # ponytail: adaptive only; legacy thinking-enabled/budget models unmapped —
        # unset effort if such an endpoint rejects adaptive.
        if self.reasoning_effort:
            if self.reasoning_effort == "none":
                payload["thinking"] = {"type": "disabled"}
            else:
                payload["thinking"] = {"type": "adaptive"}
                payload["output_config"] = {"effort": self.reasoning_effort}

        url = build_api_url(self.third_party_base_url, "/v1/messages")

        data = self._post_json(
            url, payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.third_party_token,
                "anthropic-version": "2023-06-01",
            },
            provider="Claude",
        )
        text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
        return self._enhanced_prompt_from_text(text, prompt)

    def _call_openai_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call OpenAI API."""
        messages = chat_history + [{"role": "user", "content": prompt}]
        payload = {"model": model, "messages": messages, "max_tokens": 4096}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        url = build_api_url(self.third_party_base_url, "/v1/chat/completions")

        data = self._post_json(url, payload, headers=self._get_headers(use_third_party=True), provider="OpenAI")
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._enhanced_prompt_from_text(text, prompt)

    def _call_gemini_api(self, prompt: str, chat_history: list[dict], model: str) -> dict:
        """Call Gemini API."""
        contents = []
        for msg in chat_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {"contents": contents, "generationConfig": {"maxOutputTokens": 4096}}
        # Gemini 3 has no "none" thinking level; "minimal" is its lowest.
        if self.reasoning_effort:
            level = "minimal" if self.reasoning_effort == "none" else self.reasoning_effort
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": level}

        url = build_api_url(self.third_party_base_url, f"/v1beta/models/{model}:generateContent")

        data = self._post_json(
            url, payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.third_party_token},
            provider="Gemini",
        )
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return self._enhanced_prompt_from_text(text, prompt)

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

    def _remote_search(self, project_root: str, query: str) -> dict:
        """Search via ACE codebase-retrieval API."""
        indexer = Indexer(project_root, self.base_url, self.token)
        blob_names = indexer.get_blob_names()

        url = build_api_url(self.base_url, "/agents/codebase-retrieval")
        payload = {
            "information_request": query,
            "blobs": {"checkpoint_id": None, "added_blobs": blob_names, "deleted_blobs": []},
            "dialog": [],
            "max_output_length": 0,
            "disable_codebase_retrieval": False,
            "enable_commit_retrieval": False,
        }
        timeout = httpx.Timeout(RETRIEVAL_TIMEOUT, connect=15.0)

        try:
            data = self._post_json(url, payload, headers=self._get_headers(), timeout=timeout)
        except httpx.HTTPStatusError as e:
            # Server lost blobs the local index marked as uploaded: rebuild, re-upload, retry once.
            if e.response.status_code != 400 or "unknown blob" not in e.response.text.lower():
                raise
            log.warning("Server reports unknown blobs; rebuilding index and retrying once")
            blob_names = indexer.force_rebuild()
            payload["blobs"]["added_blobs"] = blob_names
            data = self._post_json(url, payload, headers=self._get_headers(), timeout=timeout)

        return {
            "results": data.get("formatted_retrieval", ""),
            "query": query,
            "mode": "remote",
            "blob_count": len(blob_names),
        }

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
                content = detect_and_read(file_path, ENCODING_CHAIN)
                if content is None:
                    continue
                content = content.lower()
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
            "endpoint_effective": self.endpoint,
            "endpoint_env_ready": bool(self.third_party_base_url and self.third_party_token) if self._is_third_party() else bool(self.base_url and self.token),
            "token_configured": bool(self.token),
            "third_party_configured": bool(self.third_party_base_url and self.third_party_token),
            "auth_source": self.auth_source,
            "search_context_injection": self._should_include_search_context(),
        }
