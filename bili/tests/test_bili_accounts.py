"""accounts.py 单元测试（纯函数 + 临时目录，不触真实 ~/.config）。"""

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import accounts as acc  # noqa: E402

# SESSDATA 形如 值,过期时间戳,md5；用 4102444800（2100-01-01）代表远期有效
FUTURE = 4102444800
PAST = 1600000000


def make_session(mid="42", expires=FUTURE, **extra):
    return {
        "cookies": f"SESSDATA=val%2C{expires}%2Cdeadbeef; bili_jct=csrf; DedeUserID={mid};",
        "mid": mid,
        "room_id": "1234567",
        "csrf_token": "csrf",
        **extra,
    }


def write_account(directory: Path, name: str, session: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
    return path


class SandboxTest(unittest.TestCase):
    """把 accounts_dir 指向临时目录，并放一个可回落的 legacy 文件。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "accounts"
        self.legacy = self.root / ".bilibili_session.json"
        patcher = mock.patch.dict(os.environ, {"BILI_ACCOUNTS_DIR": str(self.dir)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def resolve(self, explicit=None, account=None, tool="live"):
        return acc.resolve_session(explicit, account, tool, self.legacy)


class NameValidationTest(unittest.TestCase):
    def test_accepts_plain_names(self):
        for name in ("live", "upload", "acc2", "a_b-c", "A1"):
            self.assertEqual(acc.validate_account_name(name), name)

    def test_rejects_traversal_and_empty(self):
        for name in ("../evil", "a/b", "..", "", "x" * 65, "acc.json", "a b"):
            with self.assertRaises(acc.AccountError, msg=name):
                acc.validate_account_name(name)


class ResolveSessionTest(SandboxTest):
    def test_explicit_path_wins_over_everything(self):
        write_account(self.dir, "live", make_session())
        explicit = self.root / "custom.json"
        self.assertEqual(self.resolve(explicit=explicit, account="live"), explicit)

    def test_account_flag_picks_named_profile(self):
        write_account(self.dir, "live", make_session())
        write_account(self.dir, "upload", make_session(mid="99"))
        self.assertEqual(self.resolve(account="upload", tool="upload"), self.dir / "upload.json")

    def test_tool_defaults_differ(self):
        write_account(self.dir, "live", make_session())
        self.assertEqual(self.resolve(tool="live"), self.dir / "live.json")
        # upload 账号不存在时返回它自己的目标路径（而不是回落到 live）
        self.assertEqual(self.resolve(tool="upload"), self.dir / "upload.json")

    def test_falls_back_to_legacy_when_profile_missing(self):
        self.legacy.write_text(json.dumps(make_session()), encoding="utf-8")
        # profiles 目录整个不存在 + legacy 在 -> 回落
        self.assertEqual(self.resolve(tool="upload"), self.legacy)

    def test_profile_beats_legacy(self):
        self.legacy.write_text(json.dumps(make_session(mid="1")), encoding="utf-8")
        write_account(self.dir, "upload", make_session(mid="99"))
        self.assertEqual(self.resolve(tool="upload"), self.dir / "upload.json")

    def test_explicit_account_overrides_tool_default(self):
        write_account(self.dir, "live", make_session())
        write_account(self.dir, "other", make_session(mid="7"))
        self.assertEqual(self.resolve(account="other", tool="upload"), self.dir / "other.json")

    def test_invalid_account_name_raises(self):
        with self.assertRaises(acc.AccountError):
            self.resolve(account="../evil")


class DefaultsTest(SandboxTest):
    def test_builtin_defaults(self):
        self.assertEqual(acc.tool_default_account("live"), "live")
        self.assertEqual(acc.tool_default_account("upload"), "upload")
        self.assertEqual(acc.tool_default_account("unknown-tool"), "live")

    def test_set_tool_default_requires_existing_profile(self):
        with self.assertRaises(acc.AccountError):
            acc.set_tool_default_account("upload", "ghost")
        self.assertFalse((self.dir / "defaults.json").exists())

    def test_set_tool_default_persists_and_is_independent(self):
        write_account(self.dir, "upload", make_session(mid="99"))
        target = acc.set_tool_default_account("live", "upload")
        self.assertEqual(target, self.dir / "upload.json")
        self.assertEqual(acc.tool_default_account("live"), "upload")
        self.assertEqual(acc.tool_default_account("upload"), "upload")  # 内置默认不受影响

    def test_defaults_file_is_0600(self):
        write_account(self.dir, "upload", make_session())
        acc.set_tool_default_account("live", "upload")
        self.assertEqual(oct((self.dir / "defaults.json").stat().st_mode & 0o777), "0o600")

    def test_corrupt_defaults_falls_back_to_builtin(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "defaults.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(acc.tool_default_account("upload"), "upload")

    def test_defaults_file_with_wrong_shape_ignored(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "defaults.json").write_text('["live"]', encoding="utf-8")
        self.assertEqual(acc.tool_default_account("live"), "live")


class SessionExpiryTest(SandboxTest):
    def test_parses_expiry_from_sessdata(self):
        got = acc.session_expiry(make_session(expires=FUTURE))
        self.assertEqual(got, datetime.fromtimestamp(FUTURE))

    def test_missing_sessdata_returns_none(self):
        self.assertIsNone(acc.session_expiry({"cookies": "bili_jct=x"}))

    def test_malformed_expiry_returns_none(self):
        self.assertIsNone(acc.session_expiry(make_session(expires="not-a-number")))

    def test_single_segment_returns_none(self):
        self.assertIsNone(acc.session_expiry({"cookies": "SESSDATA=onlyvalue"}))


class ListAccountsTest(SandboxTest):
    def test_empty_dir_returns_empty(self):
        self.assertEqual(acc.list_accounts(), [])

    def test_lists_profiles_and_skips_defaults_file(self):
        write_account(self.dir, "live", make_session(mid="1", title="旧房间", rtmp_code="x"))
        write_account(self.dir, "expired", make_session(mid="2", expires=PAST))
        (self.dir / "defaults.json").write_text("{}", encoding="utf-8")
        rows = {r["name"]: r for r in acc.list_accounts()}
        self.assertEqual(set(rows), {"live", "expired"})
        self.assertEqual(rows["live"]["mid"], "1")
        self.assertEqual(rows["live"]["room_id"], "1234567")
        self.assertEqual(rows["live"]["title"], "旧房间")
        self.assertTrue(rows["live"]["has_push_code"])
        self.assertFalse(rows["live"]["expired"])
        self.assertTrue(rows["expired"]["expired"])
        self.assertLess(rows["expired"]["expires"].timestamp(), time.time())

    def test_unparsable_file_still_listed_with_empty_fields(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "broken.json").write_text("{not json", encoding="utf-8")
        rows = acc.list_accounts()
        self.assertEqual([r["name"] for r in rows], ["broken"])
        self.assertEqual(rows[0]["mid"], "")
        self.assertIsNone(rows[0]["expires"])


class MigrateLegacyTest(SandboxTest):
    def test_migrates_once_and_backs_up(self):
        self.legacy.write_text(json.dumps(make_session(mid="1")), encoding="utf-8")
        note = acc.migrate_legacy(self.legacy)
        self.assertIn("已迁移", note)
        self.assertTrue((self.dir / "live.json").exists())
        self.assertEqual(acc.read_session(self.dir / "live.json")["mid"], "1")
        self.assertFalse(self.legacy.exists())
        self.assertTrue(self.legacy.with_suffix(".json.bak").exists())

    def test_is_idempotent(self):
        self.legacy.write_text(json.dumps(make_session()), encoding="utf-8")
        acc.migrate_legacy(self.legacy)
        self.assertIsNone(acc.migrate_legacy(self.legacy))  # 第二次无事发生

    def test_does_not_overwrite_existing_profile(self):
        self.legacy.write_text(json.dumps(make_session(mid="1")), encoding="utf-8")
        write_account(self.dir, "live", make_session(mid="99"))
        self.assertIsNone(acc.migrate_legacy(self.legacy))
        self.assertEqual(acc.read_session(self.dir / "live.json")["mid"], "99")
        self.assertTrue(self.legacy.exists())

    def test_skips_legacy_without_cookies(self):
        self.legacy.write_text('{"mid": "1"}', encoding="utf-8")
        self.assertIsNone(acc.migrate_legacy(self.legacy))
        self.assertTrue(self.legacy.exists())

    def test_skips_when_legacy_absent(self):
        self.assertIsNone(acc.migrate_legacy(self.legacy))

    def test_migrated_file_is_0600_and_dir_0700(self):
        self.legacy.write_text(json.dumps(make_session()), encoding="utf-8")
        acc.migrate_legacy(self.legacy)
        self.assertEqual(oct((self.dir / "live.json").stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.dir.stat().st_mode & 0o777), "0o700")


if __name__ == "__main__":
    unittest.main()
