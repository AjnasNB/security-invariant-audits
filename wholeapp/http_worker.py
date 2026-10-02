"""Trusted in-network HTTP client. Inputs only, no expected access specification."""
import hashlib
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

BASE = "http://ajnas-wholeapp-server-20261002:8000"


class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = None

    def request(self, method, route, value=None, token=None):
        content = json.dumps(value).encode() if value is not None else None
        headers = {"Content-Type": "application/json", "X-Frappe-Site-Name": "audit.local"}
        if self.csrf:
            headers["X-Frappe-CSRF-Token"] = self.csrf
        if token:
            headers["Authorization"] = "token " + token["api_key"] + ":" + token["api_secret"]
        request = urllib.request.Request(BASE + route, data=content, headers=headers, method=method)
        opener = urllib.request.build_opener() if token else self.opener
        try:
            with opener.open(request, timeout=15) as response:
                code, raw = response.status, response.read(1_000_001)
                cache_control = response.headers.get("Cache-Control")
        except urllib.error.HTTPError as error:
            code, raw = error.code, error.read(1_000_001)
            cache_control = error.headers.get("Cache-Control")
        except (OSError, TimeoutError) as error:
            return {"http_status": None, "body": "", "bytes": 0, "transport_error": type(error).__name__}
        if len(raw) > 1_000_000:
            return {"http_status": code, "body": "", "bytes": len(raw), "transport_error": "OutputLimitExceeded"}
        return {"http_status": code, "body": raw.decode("utf-8", errors="replace"),
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "cache_control": cache_control}

    def login(self, user, password):
        if user == "Guest":
            return True
        response = self.request("POST", "/api/method/login", {"usr": user, "pwd": password})
        if response["http_status"] != 200:
            return False
        token = self.request("GET", "/api/method/frappe.sessions.get_csrf_token")
        try:
            self.csrf = json.loads(token["body"]).get("message")
        except (ValueError, TypeError):
            pass
        result = self.request("GET", "/api/method/frappe.auth.get_logged_user")
        try:
            return json.loads(result["body"]).get("message") == user
        except (ValueError, TypeError):
            return False


payload = json.load(sys.stdin)
sessions, observations = {}, []
for case in payload["requests"]:
    user = case["user"]
    if user not in sessions:
        session = Session()
        sessions[user] = session if session.login(user, payload["login_password"]) else None
    session = sessions[user]
    token = payload.get("credentials", {}).get(user) if case["method"] in ("PUT", "POST", "DELETE") else None
    token_identity = True
    if token:
        check = Session().request("GET", "/api/method/frappe.auth.get_logged_user", token=token)
        try:
            token_identity = json.loads(check["body"]).get("message") == user
        except (TypeError, ValueError):
            token_identity = False
    response = session.request(case["method"], case["route"], case.get("payload"),
        token=token) if session and token_identity else {
        "http_status": None, "transport_error": "LoginIdentityNotConfirmed", "body": "", "bytes": 0}
    observations.append({"id": case["id"], **response})
print(json.dumps(observations))
