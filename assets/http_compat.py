"""requests가 있으면 그것을, 없으면 표준 라이브러리(urllib)로 만든 같은 모양의 대체품을 내준다.

    from http_compat import requests

MCP 서버는 Claude Desktop 등이 아무 python3로나 띄운다. 그 python3에 requests가 없어도 도구가 죽지 않게 하려고 둔다.
대체품은 이 스킬이 쓰는 만큼만 흉내 낸다: get·post·Session().get, 응답의 status_code·content·text·json()·raise_for_status(),
예외 RequestException·HTTPError. 테스트가 mock.patch("requests.get")을 쓰므로 requests가 있으면 반드시 진짜를 돌려준다.
"""
from __future__ import annotations

import json as _json
import socket
import types
import urllib.error
import urllib.parse
import urllib.request

try:
    import requests  # noqa: F401  (있으면 이것을 그대로 쓴다)
except ImportError:
    class RequestException(OSError):
        """requests.RequestException 자리. OSError라서 기존 `except OSError` 처리도 그대로 탄다."""

    class HTTPError(RequestException):
        pass

    class Response:
        def __init__(self, status: int, content: bytes, url: str, charset: str | None) -> None:
            self.status_code, self.content, self.url = status, content, url
            self.encoding = charset or "utf-8"

        @property
        def text(self) -> str:
            return self.content.decode(self.encoding, errors="replace")

        def json(self):
            return _json.loads(self.content)     # 깨진 본문은 ValueError (requests와 같은 처리)

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise HTTPError(f"{self.status_code} for url: {self.url}")

    def _send(method: str, url: str, params=None, data=None, headers=None, timeout=None) -> Response:
        params = {k: v for k, v in (params or {}).items() if v is not None}   # requests처럼 None 값은 보내지 않는다
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        body = urllib.parse.urlencode(data, doseq=True).encode() if isinstance(data, dict) else data
        req = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return Response(r.status, r.read(), r.geturl(), r.headers.get_content_charset())
        except urllib.error.HTTPError as e:      # 4xx·5xx도 응답으로 돌려준다 (raise_for_status가 판단)
            return Response(e.code, e.read() or b"", url, None)
        except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
            raise RequestException(str(e)) from None

    class Session:
        def get(self, url, params=None, headers=None, timeout=None):
            return _send("GET", url, params=params, headers=headers, timeout=timeout)

    requests = types.SimpleNamespace(
        get=lambda url, params=None, headers=None, timeout=None: _send("GET", url, params, None, headers, timeout),
        post=lambda url, data=None, headers=None, timeout=None: _send("POST", url, None, data, headers, timeout),
        Session=Session, RequestException=RequestException, HTTPError=HTTPError, Response=Response,
        __name__="http_compat.requests",
    )
