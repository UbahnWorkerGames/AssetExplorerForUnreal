from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

import httpx


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
_THROTTLE_LOCK = threading.Lock()
_LAST_REQUEST: Dict[str, float] = {}

DEFAULT_TEMPLATE = (
    "Generate up to 10 relevant asset tags (single words, lowercase, no duplicates) in {language}. "
    "Also infer an optional era (short lowercase phrase, e.g. medieval, victorian, sci-fi) if obvious. "
    "Return ONLY a JSON object with 'tags' array and 'era' string. "
    "Name: {name}\n"
    "Class: {asset_class}\n"
    "Description: {description}\n"
    "Existing tags: {existing_tags}"
)

TRANSLATE_TEMPLATE = (
    "Translate these asset tags into {language}. Keep order. Use short single words if possible, lowercase, no duplicates. "
    "Return ONLY JSON in this shape: {\"tags\": [\"...\", ...]}.\n"
    "Tags: {tags}"
)


def render_template(
    template: str,
    name: str,
    description: str,
    existing: List[str],
    language: str,
    asset_class: str,
) -> str:
    existing_text = ", ".join(existing) if existing else ""
    language_text = language.strip() if language else "english"
    return (
        template.replace("{name}", name)
        .replace("{asset_class}", asset_class)
        .replace("{description}", description)
        .replace("{existing_tags}", existing_text)
        .replace("{language}", language_text)
    )


def build_chat_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1/chat/completions"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


def _as_bool(value: Optional[object]) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _as_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize_payload(payload: Dict[str, object]) -> Dict[str, object]:
    cleaned = dict(payload)
    messages = cleaned.get("messages")
    if isinstance(messages, list):
        safe_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                safe_messages.append(msg)
                continue
            content = msg.get("content")
            if isinstance(content, list):
                safe_content = []
                for part in content:
                    if not isinstance(part, dict):
                        safe_content.append(part)
                        continue
                    if part.get("type") == "image_url" and isinstance(part.get("image_url"), dict):
                        url = part["image_url"].get("url", "")
                        safe_content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "[omitted]",
                                    "length": len(url) if isinstance(url, str) else 0,
                                },
                            }
                        )
                    else:
                        safe_content.append(part)
                msg = dict(msg)
                msg["content"] = safe_content
            safe_messages.append(msg)
        cleaned["messages"] = safe_messages
    return cleaned




def _log_llm_request_full(url: str, headers: Dict[str, str], payload: Dict[str, object], label: str) -> None:
    safe_headers = dict(headers)
    if "Authorization" in safe_headers:
        safe_headers["Authorization"] = "Bearer ***"
    try:
        logger.info("LLM %s FULL request url=%s headers=%s payload=%s", label, url, json.dumps(safe_headers), json.dumps(payload))
        logging.getLogger("uvicorn.error").info(
            "LLM %s FULL request url=%s headers=%s payload=%s", label, url, json.dumps(safe_headers), json.dumps(payload)
        )
    except Exception as exc:
        logger.warning("LLM full request logging failed: %s", exc)


def _extract_tags_and_era(content: str) -> Tuple[List[str], str]:
    tags_out: List[str] = []
    era_out = ""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            tags_out = parsed
        elif isinstance(parsed, dict):
            tags_out = parsed.get("tags", [])
            era_out = str(parsed.get("era") or "").strip()
        if tags_out:
            return tags_out, era_out
    except json.JSONDecodeError:
        pass

    # Try to extract a JSON object containing "tags"
    for match in re.finditer(r"\{[\s\S]*?\}", content):
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict) and "tags" in parsed:
                tags_out = parsed.get("tags", [])
                era_out = str(parsed.get("era") or "").strip()
                return tags_out, era_out
        except json.JSONDecodeError:
            continue

    # Try to extract a JSON array
    match = re.search(r"\[[\s\S]*\]", content)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed, ""
            if isinstance(parsed, dict):
                return parsed.get("tags", []), str(parsed.get("era") or "").strip()
        except json.JSONDecodeError:
            pass

    return [], ""


def _extract_tags_from_content(content: str) -> List[str]:
    tags, _era = _extract_tags_and_era(content)
    return tags
def _get_throttle_interval(settings: Dict[str, str], provider: str) -> float:
    raw = settings.get("llm_min_interval_seconds") or ""
    try:
        value = float(raw)
        if value >= 0:
            return value
    except (TypeError, ValueError):
        value = None
    if provider == "groq":
        return 2.0
    return 0.5


def _rate_limit_key(provider: str, model: str) -> str:
    return f"{provider}:{model}".lower()


def _throttle_wait(settings: Dict[str, str], provider: str, model: str) -> None:
    interval = _get_throttle_interval(settings, provider)
    if interval <= 0:
        return
    key = _rate_limit_key(provider, model)
    with _THROTTLE_LOCK:
        last = _LAST_REQUEST.get(key, 0.0)
    now = time.monotonic()
    wait = interval - (now - last)
    if wait > 0:
        time.sleep(wait)


def _note_request(provider: str, model: str) -> None:
    key = _rate_limit_key(provider, model)
    with _THROTTLE_LOCK:
        _LAST_REQUEST[key] = time.monotonic()




def _log_llm_response(provider: str, model: str, response: httpx.Response) -> None:
    try:
        request_id = response.headers.get("x-request-id") or response.headers.get("x-requestid") or ""
        content_type = response.headers.get("content-type", "")
        body = response.text
        preview = body[:2000]
        logger.info(
            "LLM response meta provider=%s model=%s status=%s request_id=%s content_type=%s bytes=%s",
            provider,
            model,
            response.status_code,
            request_id,
            content_type,
            len(body),
        )
        logger.info("LLM response body preview: %s", preview)
    except Exception as exc:
        logger.warning("LLM response logging failed: %s", exc)


def _extract_retry_delay(detail: str, headers: Dict[str, str], fallback: float) -> float:
    retry_after = headers.get("Retry-After") or headers.get("retry-after") or ""
    if retry_after.strip().isdigit():
        return float(retry_after.strip())
    match = re.search(r"try again in (\d+)s", detail, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return fallback


def _post_with_throttle(
    settings: Dict[str, str],
    provider: str,
    model: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, object],
    timeout: httpx.Timeout,
) -> Tuple[httpx.Response, bool]:
    _throttle_wait(settings, provider, model)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        _note_request(provider, model)
        if response.status_code == 429:
            detail = response.text
            delay = _extract_retry_delay(detail, dict(response.headers), _get_throttle_interval(settings, provider))
            if delay > 0:
                time.sleep(delay)
            response = client.post(url, headers=headers, json=payload)
            _note_request(provider, model)
            return response, True
    return response, False


def generate_tags(
    settings: Dict[str, str],
    name: str,
    description: str,
    existing: List[str],
    image_data_url: Optional[str] = None,
    asset_class: str = "",
    return_era: bool = False,
) -> List[str] | Tuple[List[str], str]:
    provider = (settings.get("provider") or "").strip().lower()
    base_url = settings.get(f"{provider}_base_url") or settings.get("base_url")
    api_key = settings.get("api_key")
    if provider == "openai":
        api_key = settings.get("openai_api_key") or api_key
    elif provider == "openrouter":
        api_key = settings.get("openrouter_api_key") or api_key
    elif provider == "groq":
        api_key = settings.get("groq_api_key") or api_key
    model = settings.get("tag_model") or settings.get(f"{provider}_model") or settings.get("model")
    if not base_url or not model:
        raise ValueError("LLM settings are incomplete")

    language = settings.get("tag_language") or "english"
    provider = (settings.get("provider") or "").strip().lower()
    template = (settings.get(f"tag_prompt_template_{provider}") or settings.get("tag_prompt_template") or DEFAULT_TEMPLATE)
    prompt = render_template(template, name, description, existing, language, asset_class)
    if "json" not in prompt.lower():
        prompt = f"{prompt}\n\nReturn ONLY JSON like {{\"tags\":[\"...\"],\"era\":\"...\"}}."
    url = build_chat_url(base_url)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    user_content: object = prompt
    if image_data_url:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You generate tags for 3D/asset libraries."},
            {"role": "user", "content": user_content},
        ],
    }
    if provider in {"openai", "openrouter", "groq"}:
        payload["response_format"] = {"type": "json_object"}
    elif provider == "ollama":
        payload["format"] = "json"
    use_temperature = _as_bool(settings.get("use_temperature"))
    temperature = _as_float(settings.get("temperature"))
    if use_temperature and temperature is not None:
        payload["temperature"] = temperature

    payload_log = _sanitize_payload(payload)
    logger.info("LLM request url=%s payload=%s", url, json.dumps(payload_log))
    _log_llm_request_full(url, headers, payload, "tag_test")
    _log_llm_request_full(url, headers, payload, "tag")

    timeout = httpx.Timeout(90.0, connect=30.0, read=90.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.error("LLM request failed: %s", detail)
        raise ValueError(f"LLM request failed: {detail}") from exc
    _log_llm_response(provider, model, response)
    try:
        logger.info("LLM translation FULL response: %s", response.text)
        logging.getLogger("uvicorn.error").info("LLM translation FULL response: %s", response.text)
    except Exception as exc:
        logger.warning("LLM translation full response logging failed: %s", exc)
    data = response.json()
    try:
        logger.info("LLM translation response json: %s", json.dumps(data, ensure_ascii=False))
        logging.getLogger("uvicorn.error").info("LLM translation response json: %s", json.dumps(data, ensure_ascii=False))
    except Exception as exc:
        logger.warning("LLM translation json log failed: %s", exc)

    content = data["choices"][0]["message"]["content"]
    tags, era = _extract_tags_and_era(content)
    if not tags:
        text = re.sub(r"```[\s\S]*?```", " ", content)
        text = re.sub(r"https?://\S+", " ", text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        keyword_lines = []
        for line in lines:
            if re.search(r"\b(tags?|keywords?)\b", line, re.IGNORECASE):
                keyword_lines.append(line)
        if keyword_lines:
            blob = " ".join(keyword_lines)
            parts = re.split(r"[,\n;]", blob)
            tags = [re.sub(r"^\d+[\).\s-]*", "", part).strip() for part in parts]

    cleaned = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    if not cleaned:
        raise ValueError("LLM did not return valid tags")
    if return_era:
        return cleaned, era
    return cleaned




def generate_tags_debug(
    settings: Dict[str, str],
    name: str,
    description: str,
    existing: List[str],
    image_data_url: Optional[str] = None,
    asset_class: str = "",
) -> Dict[str, object]:
    provider = (settings.get("provider") or "").strip().lower()
    base_url = settings.get(f"{provider}_base_url") or settings.get("base_url")
    api_key = settings.get("api_key")
    if provider == "openai":
        api_key = settings.get("openai_api_key") or api_key
    elif provider == "openrouter":
        api_key = settings.get("openrouter_api_key") or api_key
    elif provider == "groq":
        api_key = settings.get("groq_api_key") or api_key
    model = settings.get("tag_model") or settings.get(f"{provider}_model") or settings.get("model")
    if not base_url or not model:
        raise ValueError("LLM settings are incomplete")

    language = settings.get("tag_language") or "english"
    template = (settings.get(f"tag_prompt_template_{provider}") or settings.get("tag_prompt_template") or DEFAULT_TEMPLATE)
    prompt = render_template(template, name, description, existing, language, asset_class)
    if "json" not in prompt.lower():
        prompt = f"{prompt}\n\nReturn ONLY JSON like {{\"tags\":[\"...\"],\"era\":\"...\"}}."
    url = build_chat_url(base_url)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    user_content: object = prompt
    if image_data_url:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You generate tags for 3D/asset libraries."},
            {"role": "user", "content": user_content},
        ],
    }
    if provider in {"openai", "openrouter", "groq"}:
        payload["response_format"] = {"type": "json_object"}
    elif provider == "ollama":
        payload["format"] = "json"
    use_temperature = _as_bool(settings.get("use_temperature"))
    temperature = _as_float(settings.get("temperature"))
    if use_temperature and temperature is not None:
        payload["temperature"] = temperature

    payload_log = _sanitize_payload(payload)
    logger.info("LLM request url=%s payload=%s", url, json.dumps(payload_log))

    timeout = httpx.Timeout(90.0, connect=30.0, read=90.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.error("LLM request failed: %s", detail)
        raise ValueError(f"LLM request failed: {detail}") from exc
    _log_llm_response(provider, model, response)

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = None
    tags = []
    era = ""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            tags = parsed
        elif isinstance(parsed, dict):
            tags = parsed.get("tags", [])
            era = str(parsed.get("era") or "").strip()
    except json.JSONDecodeError:
        parsed = None
    cleaned = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    output = parsed if parsed is not None else content
    if isinstance(output, dict) and "tags" in output:
        output = {k: v for k, v in output.items() if k != "tags"}
    return {
        "tags": cleaned,
        "era": era,
        "output": output,
        "prompt": prompt,
    }


def translate_tags(settings: Dict[str, str], tags: List[str], language: str) -> List[str]:
    if not tags:
        return []
    provider = (settings.get("provider") or "").strip().lower()
    base_url = settings.get(f"{provider}_base_url") or settings.get("base_url")
    api_key = settings.get("api_key")
    if provider == "openai":
        api_key = settings.get("openai_api_key") or api_key
    elif provider == "openrouter":
        api_key = settings.get("openrouter_api_key") or api_key
    elif provider == "groq":
        api_key = settings.get("groq_api_key") or api_key
    model = settings.get(f"{provider}_translate_model") or settings.get("translate_model") or settings.get(f"{provider}_model") or settings.get("model")
    if not base_url or not model:
        raise ValueError("LLM settings are incomplete")

    language_text = language.strip() if language else ""
    if not language_text:
        raise ValueError("Translation language is required")

    tag_text = ", ".join([str(t).strip() for t in tags if str(t).strip()])
    if not tag_text:
        return []
    prompt = TRANSLATE_TEMPLATE.replace("{language}", language_text).replace("{tags}", tag_text)
    if "json" not in prompt.lower():
        prompt = f"{prompt}\n\nReturn ONLY a JSON object with a 'tags' array of strings."
    logger.info("LLM translation prompt: %s", json.dumps({"prompt": prompt}, ensure_ascii=False))
    logging.getLogger("uvicorn.error").info("LLM translation prompt: %s", json.dumps({"prompt": prompt}, ensure_ascii=False))
    url = build_chat_url(base_url)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate tags for 3D/asset libraries."},
            {"role": "user", "content": prompt},
        ],
    }
    if provider in {"openai", "openrouter", "groq"}:
        payload["response_format"] = {"type": "json_object"}
    elif provider == "ollama":
        payload["format"] = "json"
    use_temperature = _as_bool(settings.get("use_temperature"))
    temperature = _as_float(settings.get("temperature"))
    if use_temperature and temperature is not None:
        payload["temperature"] = temperature

    payload_log = _sanitize_payload(payload)
    logger.info("LLM translation request url=%s payload=%s", url, json.dumps(payload_log))
    logging.getLogger("uvicorn.error").info("LLM translation request url=%s payload=%s", url, json.dumps(payload_log))
    _log_llm_request_full(url, headers, payload, "translate")

    timeout = httpx.Timeout(90.0, connect=30.0, read=90.0)
    try:
        response, retried = _post_with_throttle(settings, provider, model, url, headers, payload, timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.error("LLM translation failed: %s", detail)
        raise ValueError(f"LLM translation failed: {detail}") from exc
    if retried:
        logger.info("LLM translation retried after rate limit.")
    _log_llm_response(provider, model, response)
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    logger.info("LLM translation raw content: %s", content)
    logging.getLogger("uvicorn.error").info("LLM translation raw content: %s", content)
    tags_out = _extract_tags_from_content(content)

    cleaned = []
    for tag in tags_out:
        tag = str(tag).strip().lower()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    if not cleaned:
        logger.warning("LLM translation returned empty tags. Raw content=%s", content)
        raise ValueError("LLM did not return valid translated tags")
    return cleaned


def translate_tags_debug(settings: Dict[str, str], tags: List[str], language: str) -> Dict[str, object]:
    if not tags:
        return {"tags": [], "prompt": "", "response_text": "", "response_json": None}
    provider = (settings.get("provider") or "").strip().lower()
    base_url = settings.get(f"{provider}_base_url") or settings.get("base_url")
    api_key = settings.get("api_key")
    if provider == "openai":
        api_key = settings.get("openai_api_key") or api_key
    elif provider == "openrouter":
        api_key = settings.get("openrouter_api_key") or api_key
    elif provider == "groq":
        api_key = settings.get("groq_api_key") or api_key
    model = settings.get(f"{provider}_translate_model") or settings.get("translate_model") or settings.get(f"{provider}_model") or settings.get("model")
    if not base_url or not model:
        raise ValueError("LLM settings are incomplete")

    language_text = language.strip() if language else ""
    if not language_text:
        raise ValueError("Translation language is required")

    tag_text = ", ".join([str(t).strip() for t in tags if str(t).strip()])
    if not tag_text:
        return {"tags": [], "prompt": "", "response_text": "", "response_json": None}
    prompt = TRANSLATE_TEMPLATE.replace("{language}", language_text).replace("{tags}", tag_text)
    if "json" not in prompt.lower():
        prompt = f"{prompt}\n\nReturn ONLY a JSON object with a 'tags' array of strings."

    url = build_chat_url(base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate tags for 3D/asset libraries."},
            {"role": "user", "content": prompt},
        ],
    }
    if provider in {"openai", "openrouter", "groq"}:
        payload["response_format"] = {"type": "json_object"}
    elif provider == "ollama":
        payload["format"] = "json"
    use_temperature = _as_bool(settings.get("use_temperature"))
    temperature = _as_float(settings.get("temperature"))
    if use_temperature and temperature is not None:
        payload["temperature"] = temperature

    payload_log = _sanitize_payload(payload)
    logger.info("LLM translation DEBUG request url=%s payload=%s", url, json.dumps(payload_log))
    logging.getLogger("uvicorn.error").info("LLM translation DEBUG request url=%s payload=%s", url, json.dumps(payload_log))
    _log_llm_request_full(url, headers, payload, "translate_debug")

    timeout = httpx.Timeout(90.0, connect=30.0, read=90.0)
    response, _ = _post_with_throttle(settings, provider, model, url, headers, payload, timeout)
    response.raise_for_status()
    _log_llm_response(provider, model, response)
    response_text = response.text
    try:
        response_json = response.json()
    except Exception:
        response_json = None
    try:
        logger.info("LLM translate_debug response_text: %s", response_text)
        logging.getLogger("uvicorn.error").info("LLM translate_debug response_text: %s", response_text)
        logger.info("LLM translate_debug response_json: %s", json.dumps(response_json, ensure_ascii=False))
        logging.getLogger("uvicorn.error").info("LLM translate_debug response_json: %s", json.dumps(response_json, ensure_ascii=False))
    except Exception as exc:
        logger.warning("LLM translate_debug response log failed: %s", exc)

    content = ""
    if response_json and isinstance(response_json, dict):
        content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        content = response_text

    parsed = None
    tags_out: List[str] = _extract_tags_from_content(content)

    cleaned = []
    for tag in tags_out:
        tag = str(tag).strip().lower()
        if tag and tag not in cleaned:
            cleaned.append(tag)

    return {
        "tags": cleaned,
        "prompt": prompt,
        "response_text": response_text,
        "response_json": response_json,
    }
