"""Minimal OpenAI-compatible chat client (stdlib only), pointed at the LMS gateway's model endpoint."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

DEFAULT_MODEL = "cx/gpt-6-luna"


class LLMClient:
	def __init__(self, base_url: str, api_key: str, model: str = DEFAULT_MODEL, timeout: int = 180):
		self.base_url = base_url.rstrip("/")
		self.api_key = api_key
		self.model = model or DEFAULT_MODEL
		self.timeout = timeout

	def chat(self, system: str, user: str) -> str:
		payload = {
			"model": self.model,
			"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
		}
		request = urllib.request.Request(
			f"{self.base_url}/chat/completions",
			data=json.dumps(payload).encode(),
			headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
			method="POST",
		)
		with urllib.request.urlopen(request, timeout=self.timeout) as response:
			body = json.loads(response.read().decode())
		return str(body["choices"][0]["message"].get("content") or "")


def parse_json(text: str) -> Any:
	"""Accept a bare JSON document or one wrapped in a markdown fence."""
	cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.I)
	return json.loads(cleaned)
