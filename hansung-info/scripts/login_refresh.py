#!/usr/bin/env python3
"""Refresh Hansung info portal cookies by logging in (no 2FA).

Env:
  HANSUNG_INFO_ID
  HANSUNG_INFO_PASSWORD

Writes:
  /home/ubuntu/.openclaw/workspace/secrets/hansung_info_storage.json
"""

from __future__ import annotations

import json
import os
import pathlib

import requests

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
OUT = WORKSPACE / "secrets" / "hansung_info_storage.json"

LOGIN_PAGE = "https://info.hansung.ac.kr/index.jsp"
LOGIN_POST = "https://info.hansung.ac.kr/servlet/s_gong.gong_login_ssl"


def env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"Missing env var: {name}")
    return v


def main() -> None:
    sid = env("HANSUNG_INFO_ID")
    pw = env("HANSUNG_INFO_PASSWORD")

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    s.get(LOGIN_PAGE, timeout=20)
    data = {"id": sid, "passwd": pw, "changePass": "", "return_url": "null"}

    r = s.post(LOGIN_POST, data=data, timeout=20, allow_redirects=True, headers={"Referer": LOGIN_PAGE})
    r.raise_for_status()

    cookies = []
    for c in s.cookies:
        expires = c.expires if c.expires is not None else -1
        cookies.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expires": expires,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False), encoding="utf-8")
    os.chmod(OUT, 0o600)

    print(f"OK: logged in, wrote {OUT}")


if __name__ == "__main__":
    main()
