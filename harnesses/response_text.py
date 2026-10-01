"""Extract final answer text from actual JSON or SSE Responses, never reasoning."""
import json


def response_text(raw):
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = None
    if isinstance(body, dict) and "output" in body:
        return from_body(body)
    if isinstance(body, dict) and body.get("choices"):
        content = body["choices"][0].get("message", {}).get("content")
        return content if isinstance(content, str) else None
    completed, snippets = [], []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        payload = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if event.get("type") in ("response.completed", "response.incomplete"):
            completed.append(event.get("response", {}))
        elif event.get("type") == "response.output_text.done":
            snippets.append(event.get("text", ""))
    for body in reversed(completed):
        text = from_body(body)
        if text is not None:
            return text
    return "\n".join(snippets) if snippets else None


def from_body(body):
    texts, finishes = [], []
    for item in body.get("output", []):
        if item.get("type") == "message":
            texts += [content["text"] for content in item.get("content", [])
                      if content.get("type") == "output_text" and isinstance(content.get("text"), str)]
        elif item.get("type") == "function_call" and item.get("name") == "finish":
            try:
                message = json.loads(item["arguments"]).get("message")
                if isinstance(message, str):
                    finishes.append(message)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return "\n".join(texts) if texts else finishes[-1] if finishes else None
