"""A minimal OpenAI-compatible chat client for the Meta Model API, stdlib only.

Also talks to any OpenAI-compatible local endpoint (LiteLLM, Ollama, vLLM) for testing without a key:
    Client(base_url="http://127.0.0.1:11435/v1", model="qwen3.8:27b", provider="local")

Key resolution for the Meta provider: explicit arg > $META_API_KEY > the key file (default ~/.config/colophon/meta.env,
one KEY=VALUE line per key, chmod 600, written by the owner — never by this code).
"""
import base64, json, os, random, time, urllib.error, urllib.request

META_BASE = "https://api.meta.ai/v1"
PRICES = {  # USD per 1M tokens: input, cached input, output  (dev.meta.ai/docs/pricing-rate-limits, 2026-11-02)
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
}


def read_key_file(path):
    vals = {}
    try:
        with open(os.path.expanduser(path)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return vals


def image_part(path=None, data=None, mime="image/jpeg"):
    if data is None:
        with open(path, "rb") as f:
            data = f.read()
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def text_part(text):
    return {"type": "text", "text": text}


class ChatError(Exception):
    pass


class Client:
    def __init__(self, provider="meta", base_url=None, api_key=None, model=None,
                 key_file="~/.config/colophon/meta.env", timeout=240):
        self.provider = provider
        env = read_key_file(key_file) if provider == "meta" else {}
        self.base_url = (base_url or os.environ.get("META_API_BASE") or env.get("META_API_BASE")
                         or (META_BASE if provider == "meta" else None))
        self.api_key = api_key or os.environ.get("META_API_KEY") or env.get("META_API_KEY") or ""
        self.model = model or os.environ.get("META_MODEL") or env.get("META_MODEL") or "muse-spark-1.3"
        self.timeout = timeout
        if not self.base_url:
            raise ChatError("no base URL")
        if provider == "meta" and not self.api_key:
            raise ChatError(f"no META_API_KEY (env or {key_file})")

    def chat(self, messages, schema=None, schema_name="Result", reasoning="minimal", max_tokens=4000,
             prompt_cache_key=None, retries=6, temperature=None):
        body = {"model": self.model, "messages": messages, "max_completion_tokens": max_tokens}
        if schema is not None:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema_name, "schema": schema, "strict": True}}
        if self.provider == "meta":
            body["reasoning_effort"] = reasoning          # "none" is refused on Muse Spark; minimal is the floor
            if prompt_cache_key:
                body["prompt_cache_key"] = prompt_cache_key
        else:
            body["max_tokens"] = max_tokens               # older local servers
            if temperature is not None:
                body["temperature"] = temperature
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/chat/completions"
        delay = 2.0
        t0 = time.time()
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = json.loads(r.read().decode())
                break
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:500]
                if e.code == 429 or e.code >= 500:
                    if attempt == retries:
                        raise ChatError(f"HTTP {e.code} after {retries} retries: {text}")
                    ra = e.headers.get("Retry-After")
                    wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay
                    time.sleep(wait + random.uniform(0, 1))
                    delay = min(delay * 2, 60)
                    continue
                raise ChatError(f"HTTP {e.code}: {text}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == retries:
                    raise ChatError(f"network: {e}")
                time.sleep(delay + random.uniform(0, 1))
                delay = min(delay * 2, 60)
        elapsed = time.time() - t0
        msg = raw["choices"][0]["message"]
        content = msg.get("content") or ""
        parsed = None
        if schema is not None:
            parsed = parse_json(content)
        usage = raw.get("usage") or {}
        return {"content": content, "json": parsed, "usage": usage, "cost_usd": self.cost(usage),
                "elapsed_s": round(elapsed, 2), "model": raw.get("model", self.model),
                "finish_reason": raw["choices"][0].get("finish_reason")}

    def cost(self, usage):
        p = PRICES.get(self.model)
        if not p or not usage:
            return None
        pt = usage.get("prompt_tokens", 0) or 0
        cached = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        ct = usage.get("completion_tokens", 0) or 0
        return round(((pt - cached) * p[0] + cached * p[1] + ct * p[2]) / 1e6, 6)


def parse_json(text):
    """The content should be JSON; local models sometimes wrap it in fences or think-tags. Be forgiving."""
    t = text.strip()
    if "</think>" in t:
        t = t.split("</think>", 1)[1].strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                return None
        return None
