"""常量定义"""
import json
import os

DOMAIN = "longyan_water"

BASE_URL = "https://service.fjlyzls.com"
LOGIN_URL = "/iwater/nt/wt/login.json"
CAPTCHA_URL = "/iwater/nt/validateCode.json"
METER_LIST_URL = "/iwater/v1/watermeter/queryUserMeterList/v1.json"

APP_VERSION = "1.0.2"
UPDATE_INTERVAL_HOURS = 6

def _fixed_params(token=None):
    return {
        "token": token,
        "waterCorpId": 3,
        "UNID": "",
        "areaId": 0,
        "accountType": "XJ",
        "apiType": "PC",
        "appVersion": APP_VERSION,
    }

FIXED_PARAMS = _fixed_params

# 验证码字符模板
_TMPL_PATH = os.path.join(os.path.dirname(__file__), "captcha_templates.json")
with open(_TMPL_PATH, encoding="utf-8") as _f:
    _TMPL = json.load(_f)
TMPL_SIZE = tuple(_TMPL["size"])
TEMPLATES = _TMPL["templates"]
