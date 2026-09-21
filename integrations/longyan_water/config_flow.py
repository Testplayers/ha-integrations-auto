"""配置流程：自动识别验证码，失败时显示验证码图片让人工输入"""
from __future__ import annotations

import base64
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthError, CaptchaError, LongyanWaterClient, LongyanWaterError
from .const import DOMAIN

STEP_USER_SCHEMA = vol.Schema({
    vol.Required("username"): cv.string,
    vol.Required("password"): cv.string,
})
STEP_CAPTCHA_SCHEMA = vol.Schema({
    vol.Required("code"): cv.string,
})


class LongyanWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._captcha_jpeg: bytes | None = None
        self._captcha_ts: str | None = None

    async def _auto_login(self) -> dict[str, Any]:
        """OCR 自动登录；需人工验证码时返回待显示的图片"""
        client = LongyanWaterClient(async_get_clientsession(self.hass))
        try:
            await client.login_auto(self._username, self._password)
            return {"ok": True}
        except CaptchaError:
            jpeg, ts = await client.get_captcha()
            self._captcha_jpeg, self._captcha_ts = jpeg, ts
            return {"ok": False, "error": "captcha"}
        except AuthError:
            return {"ok": False, "error": "invalid_auth"}
        except LongyanWaterError as e:
            return {"ok": False, "error": str(e)}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            result = await self._auto_login()
            if result["ok"]:
                return self.async_create_entry(
                    title=f"龙岩自来水 {self._username}",
                    data={"username": self._username, "password": self._password},
                )
            if result["error"] == "captcha":
                return await self.async_step_captcha()
            errors["base"] = result["error"] if result["error"] in ("invalid_auth",) else "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_captcha(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """显示验证码图片等人工输入；提交后验证"""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = LongyanWaterClient(async_get_clientsession(self.hass))
            try:
                await client.login(
                    self._username, self._password, user_input["code"], self._captcha_ts
                )
                return self.async_create_entry(
                    title=f"龙岩自来水 {self._username}",
                    data={"username": self._username, "password": self._password},
                )
            except CaptchaError:
                errors["base"] = "captcha"
                jpeg, ts = await client.get_captcha()
                self._captcha_jpeg, self._captcha_ts = jpeg, ts
            except AuthError:
                return await self.async_step_user()

        b64 = base64.b64encode(self._captcha_jpeg or b"").decode()
        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_SCHEMA,
            description_placeholders={
                "captcha_image": f"![captcha](data:image/jpeg;base64,{b64})",
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LongyanWaterOptionsFlow(config_entry)


class LongyanWaterOptionsFlow(config_entries.OptionsFlow):
    """暂无配置项"""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        return self.async_abort(reason="not_supported")
