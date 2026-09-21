"""龙岩水发网厅 API 客户端"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

import aiohttp

from .const import (
    APP_VERSION,
    BASE_URL,
    CAPTCHA_URL,
    FIXED_PARAMS,
    LOGIN_URL,
    METER_LIST_URL,
)
from .ocr import solve_captcha

_LOGGER = logging.getLogger(__name__)


class LongyanWaterError(Exception):
    """基础异常"""


class CaptchaError(LongyanWaterError):
    """验证码错误（可重试）"""


class AuthError(LongyanWaterError):
    """账号密码错误或 token 失效"""


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


class LongyanWaterClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _post(self, path: str, params: dict, token: str | None = None) -> dict:
        p = dict(params)
        p.update(FIXED_PARAMS(token))
        body = "requestPara=" + json.dumps(p, ensure_ascii=False)
        body = body.replace("+", "%2B").replace("&", "%26")
        async with self._session.post(
            BASE_URL + path,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": BASE_URL + "/",
                "Origin": BASE_URL,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            return await resp.json(content_type=None)

    async def get_captcha(self) -> tuple[bytes, str]:
        """获取验证码图片和时间戳"""
        ts = str(int(time.time() * 1000))
        async with self._session.get(
            BASE_URL + CAPTCHA_URL,
            params={"timestamp": ts},
            headers={"Referer": BASE_URL + "/"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            data = await resp.read()
            if resp.status != 200 or len(data) < 100:
                raise LongyanWaterError(f"获取验证码失败: HTTP {resp.status}")
            return data, ts

    async def login(self, mobile: str, password: str, code: str, ts: str) -> str:
        """登录返回 token，密码需先 md5"""
        r = await self._post(LOGIN_URL, {
            "userName": mobile,
            "password": md5(password),
            "code": code,
            "timestamp": ts,
        })
        status = r.get("status")
        if status == 0:
            token = ((r.get("data") or {}).get("userInfo") or {}).get("token")
            if token:
                return str(token)
        if status == 3:
            raise CaptchaError(r.get("message") or "验证码错误")
        if status == 5:
            raise AuthError(r.get("message") or "用户名或密码错误")
        raise LongyanWaterError(f"登录失败({status}): {r.get('message')}")

    async def login_auto(self, mobile: str, password: str, retries: int = 12) -> str:
        """自动识别验证码登录"""
        last: Exception | None = None
        for _ in range(retries):
            try:
                jpeg, ts = await self.get_captcha()
                code = await asyncio.get_running_loop().run_in_executor(
                    None, solve_captcha, jpeg
                )
                if not code:
                    continue
                return await self.login(mobile, password, code, ts)
            except CaptchaError as e:
                last = e
            except AuthError:
                raise
            except aiohttp.ClientError as e:
                last = LongyanWaterError(f"网络错误: {e}")
        raise last or LongyanWaterError("自动登录失败")

    async def meter_list(self, token: str) -> list[dict]:
        """查询户号列表（含余额/欠费/账单）"""
        r = await self._post(METER_LIST_URL, {}, token)
        status = r.get("status")
        if status == 11:
            raise AuthError("token 已失效")
        if status != 0:
            raise LongyanWaterError(f"查询户号失败({status}): {r.get('message')}")
        data = r.get("data")
        return data if isinstance(data, list) else []

    async def validate(self, mobile: str, password: str) -> list[dict]:
        """完整验证：自动登录 + 查询户号"""
        token = await self.login_auto(mobile, password)
        meters = await self.meter_list(token)
        return meters
