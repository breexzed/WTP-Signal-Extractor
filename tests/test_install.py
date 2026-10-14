"""Installed-tool behaviour: config locations, version, update decisions.
No network: GitHub is mocked."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from wtp import cli, install
from wtp.contract import EXIT_DEGRADED, EXIT_OK, EXIT_SOURCE_FAILED


class Config(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wtp-install-"))
        (self.tmp / "cfg").mkdir()
        (self.tmp / "work").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_precedence_env_then_cwd_then_user_file(self):
        (self.tmp / "cfg" / ".env").write_text("A=user\nB=user\nC=user\n")
        (self.tmp / "work" / ".env").write_text("A=cwd\nB=cwd\n")
        env = {"WTP_CONFIG_DIR": str(self.tmp / "cfg"), "A": "real"}
        cwd = os.getcwd()
        try:
            os.chdir(self.tmp / "work")
            with patch.dict(os.environ, env, clear=True):
                loaded = install.load_config()
                self.assertEqual((os.environ["A"], os.environ["B"], os.environ["C"]),
                                 ("real", "cwd", "user"))
        finally:
            os.chdir(cwd)
        self.assertEqual(len(loaded), 2)

    def test_data_dir_follows_xdg(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/x/share"}, clear=True):
            self.assertEqual(install.data_dir(), Path("/x/share/wtp"))
        with patch.dict(os.environ, {"WTP_DATA_DIR": "/y"}, clear=True):
            self.assertEqual(install.data_dir(), Path("/y"))


class Updates(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_version_compare(self):
        self.assertGreater(install.version_tuple("v0.10.0"), install.version_tuple("0.9.3"))
        self.assertEqual(install.version_tuple("0.0.0+source"), (0, 0, 0))

    def test_update_available_exits_1_with_upgrade_command(self):
        with patch("wtp.install.current_version", return_value="0.5.0"), \
                patch("wtp.install.latest_release", return_value={"tag": "v0.6.0", "url": "u", "published_at": None}):
            code, out, _ = self.run_cli(["--check-update"])
        info = json.loads(out)
        self.assertEqual((code, info["update_available"]), (EXIT_DEGRADED, True))
        self.assertIn("@v0.6.0", info["upgrade_command"])

    def test_up_to_date_and_no_releases(self):
        with patch("wtp.install.current_version", return_value="0.6.0"):
            for release in ({"tag": "v0.6.0", "url": "u", "published_at": None}, None):
                with patch("wtp.install.latest_release", return_value=release):
                    code, out, _ = self.run_cli(["--check-update"])
                self.assertEqual((code, json.loads(out)["update_available"]), (EXIT_OK, False))

    def test_github_unreachable(self):
        with patch("wtp.install.latest_release", side_effect=OSError("timed out")):
            code, out, err = self.run_cli(["--check-update"])
        self.assertEqual((code, out), (EXIT_SOURCE_FAILED, ""))
        self.assertIn("could not reach GitHub", err)

    def test_self_update_refuses_outside_uv_tool_install(self):
        with patch("wtp.install.current_version", return_value="0.5.0"), \
                patch("wtp.install.latest_release", return_value={"tag": "v0.6.0", "url": "u", "published_at": None}), \
                patch("wtp.install.installed_as_uv_tool", return_value=False), \
                patch("wtp.install.subprocess.run") as run:
            info = install.self_update()
        self.assertFalse(info["updated"])
        run.assert_not_called()

    def test_self_update_reinstalls_the_latest_tag(self):
        with patch("wtp.install.current_version", return_value="0.5.0"), \
                patch("wtp.install.latest_release", return_value={"tag": "v0.6.0", "url": "u", "published_at": None}), \
                patch("wtp.install.installed_as_uv_tool", return_value=True), \
                patch("wtp.install.shutil.which", return_value="/usr/bin/uv"), \
                patch("wtp.install.subprocess.run") as run:
            run.return_value.returncode = 0
            info = install.self_update()
        self.assertTrue(info["updated"])
        self.assertEqual(run.call_args.args[0][-1], f"{install.INSTALL_SOURCE}@v0.6.0")

    def test_version_flag(self):
        code, out, _ = self.run_cli(["--version"])
        self.assertEqual((code, out.strip()), (EXIT_OK, cli.contract.TOOL_VERSION))


if __name__ == "__main__":
    unittest.main()
