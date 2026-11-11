import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

username = os.environ["NETPULSE_USERNAME"]
password = os.environ["NETPULSE_PASSWORD"]
failures = []

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
base_url = f"http://127.0.0.1:{port}"


def call(method, path, body=None, token=None, form=False):
    headers = {}
    data = None
    if form:
        data = urlencode(body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=3) as response:
            status, raw = response.status, response.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
        exc.close()
    return status, json.loads(raw) if raw else None


def check(label, actual_status, expected_status, body=None, detail=None, valid=True):
    passed = actual_status == expected_status and valid
    if detail is not None:
        passed = passed and body == {"detail": detail}
    print(f"{'PASS' if passed else 'FAIL'} {label}: {actual_status} (expected {expected_status})")
    if not passed:
        failures.append(label)


server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT,
)
try:
    for _ in range(50):
        try:
            call("GET", "/devices")
            break
        except (URLError, TimeoutError):
            if server.poll() is not None:
                raise RuntimeError("API server exited before becoming ready")
            time.sleep(0.1)
    else:
        raise RuntimeError("API server did not become ready")

    full = {"name": "Audit Router", "device_type": "router", "status": "online", "location": "Delhi"}
    fields = set(full) | {"id"}
    status, body = call("GET", "/devices")
    check("public list", status, 200, valid=isinstance(body, list) and len(body) >= 2 and all(fields <= set(item) for item in body))
    status, body = call("GET", "/devices/1")
    check("public existing device", status, 200, valid=isinstance(body, dict) and body.get("id") == 1 and fields <= set(body))
    status, body = call("GET", "/devices/999999")
    check("public missing device", status, 404, body, detail="Device not found")

    writes = [
        ("POST", "/devices", full),
        ("PUT", "/devices/999999", full),
        ("PATCH", "/devices/999999", {"status": "offline"}),
        ("DELETE", "/devices/999999", None),
    ]
    for method, path, payload in writes:
        status, body = call(method, path, payload)
        check(f"{method} without token", status, 401, body, detail="Invalid or missing bearer token")
        status, body = call(method, path, payload, token="invalid-token")
        check(f"{method} invalid token", status, 401, body, detail="Invalid or missing bearer token")

    status, body = call("POST", "/auth/token", {"username": username, "password": password + "-wrong"}, form=True)
    check("invalid login", status, 401, body, detail="Invalid credentials")
    status, body = call("POST", "/auth/token", {"username": username, "password": password}, form=True)
    token_ok = isinstance(body, dict) and isinstance(body.get("access_token"), str) and body.get("token_type") == "bearer"
    check("valid login", status, 200, valid=token_ok)
    if not token_ok:
        raise RuntimeError("Cannot continue authenticated checks without a token")
    token = body["access_token"]

    for method, path, payload in writes[1:]:
        status, body = call(method, path, payload, token)
        check(f"{method} missing device", status, 404, body, detail="Device not found")

    status, created = call("POST", "/devices", full, token)
    created_ok = isinstance(created, dict) and fields <= set(created) and all(created.get(key) == value for key, value in full.items()) and isinstance(created.get("id"), int)
    check("create device", status, 201, valid=created_ok)
    if not created_ok:
        raise RuntimeError("Cannot continue device lifecycle without a created ID")
    device_id = created["id"]
    path = f"/devices/{device_id}"
    status, body = call("GET", path)
    check("read created device", status, 200, valid=body == created)
    replacement = {"name": "Updated Audit Router", "device_type": "router", "status": "maintenance", "location": "Mumbai"}
    status, body = call("PUT", path, replacement, token)
    check("replace device", status, 200, valid=body == {**replacement, "id": device_id})
    status, body = call("PATCH", path, {"status": "online"}, token)
    check("partial update", status, 200, valid=body == {**replacement, "status": "online", "id": device_id})
    status, body = call("DELETE", path, token=token)
    check("delete device", status, 204, valid=body is None)
    status, body = call("GET", path)
    check("deleted device missing", status, 404, body, detail="Device not found")
    status, body = call("PATCH", "/devices/1", {}, token)
    check("empty patch rejected", status, 422)
    status, body = call("PATCH", "/devices/1", {"status": None}, token)
    check("null patch rejected", status, 422)
finally:
    server.terminate()
    server.wait(timeout=5)

print(f"RESULT: {len(failures)} failure(s)")
if failures:
    raise SystemExit(1)
