"""阿里云 TranslateGeneral 客户端（标准库，不记录凭据或签名请求）。"""
import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import subtitle_config


def credentials():
    key = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    if not key or not secret:
        values = subtitle_config.read_credentials()
        key, secret = (values.get(name, "") for name in subtitle_config.CREDENTIAL_NAMES)
    if not key or not secret:
        raise ValueError("缺少阿里云 AccessKey 环境变量")
    return key, secret


def translate(text, timeout=5):
    key, secret = credentials()
    params = {
        "Action": "TranslateGeneral", "Version": "2018-10-12",
        "Format": "JSON", "AccessKeyId": key,
        "SignatureMethod": "HMAC-SHA1", "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "FormatType": "text", "SourceLanguage": "ja", "TargetLanguage": "zh",
        "SourceText": text, "Scene": "general",
    }
    encode = lambda value: quote(str(value), safe="~")
    canonical = "&".join(encode(k) + "=" + encode(v) for k, v in sorted(params.items()))
    signature = hmac.new((secret + "&").encode(),
                         ("POST&%2F&" + encode(canonical)).encode(), hashlib.sha1)
    params["Signature"] = base64.b64encode(signature.digest()).decode()
    request = Request("https://mt.cn-hangzhou.aliyuncs.com/",
                      data=urlencode(params).encode(),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"阿里云翻译 HTTP {error.code}") from None
    if str(result.get("Code")) != "200":
        raise RuntimeError(f"阿里云翻译失败 Code={result.get('Code')}")
    translated = (result.get("Data") or {}).get("Translated")
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError("阿里云翻译未返回有效译文")
    return translated.replace("\n", " ").strip()
