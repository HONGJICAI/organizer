"""smb.py: mounting SMB shares with mount.cifs (faked: no CIFS here)."""
import asyncio
import io
import os

import pytest
from sqlmodel import Session

import smb
from model import MediaSource


def share_row(id=1, **kw) -> MediaSource:
    fields = dict(
        id=id, media="comic", kind="smb", path=os.path.join(smb.MOUNT_ROOT, f"share{id}"),
        smbShare="//nas/media", smbUsername="me", smbPassword="p@ss,word",
    )
    fields.update(kw)
    return MediaSource(**fields)


class TestNormalize:
    @pytest.mark.parametrize("given, expected", [
        ("//nas/media", "//nas/media"),
        (r"\\nas\media\manga", "//nas/media/manga"),
        ("smb://nas/media/", "//nas/media"),
        ("  //nas//media///a  ", "//nas/media/a"),
    ])
    def test_share(self, given, expected):
        assert smb.normalize_share(given) == expected

    @pytest.mark.parametrize("given", ["", "nas/media", "//nas", "//nas/a,b", "//nas/a\nb", None])
    def test_bad_share(self, given):
        with pytest.raises(smb.SmbError):
            smb.normalize_share(given)

    def test_options(self):
        assert smb.normalize_options(" vers=2.0 , noserverino,") == "vers=2.0,noserverino"
        assert smb.normalize_options(None) == ""

    @pytest.mark.parametrize("given, message", [
        ("vers=2.0;rm", "Invalid mount option"),
        ("password=x", "user name, password and domain"),
        ("Guest", "user name, password and domain"),
    ])
    def test_bad_options(self, given, message):
        with pytest.raises(smb.SmbError, match=message):
            smb.normalize_options(given)

    def test_credential(self):
        assert smb.check_credential(None, "x") == ""
        assert smb.check_credential("a b", "x") == "a b"
        with pytest.raises(smb.SmbError, match="line breaks"):
            smb.check_credential("a\nb", "password")


class TestExplain:
    def test_known_error(self):
        out = "mount error(13): Permission denied\nRefer to the mount.cifs(8) manual page (e.g. man mount.cifs)\n"
        assert smb.explain(out) == (
            "Permission denied: check the user name and password (mount error(13): Permission denied)"
        )

    def test_unknown_error(self):
        assert smb.explain("mount error(999): Odd\n") == "mount error(999): Odd"

    def test_no_output(self):
        assert smb.explain("") == "mount.cifs failed"


class TestUnsupported:
    def test_without_mount_cifs(self, monkeypatch):
        monkeypatch.setattr(smb.shutil, "which", lambda name: None)
        assert "cifs-utils" in smb.unsupported()

    def test_without_root(self, monkeypatch):
        monkeypatch.setattr(smb.shutil, "which", lambda name: "/sbin/mount.cifs")
        monkeypatch.setattr(smb.os, "geteuid", lambda: 1000)
        assert "SYS_ADMIN" in smb.unsupported()

    def test_without_capability(self, monkeypatch):
        monkeypatch.setattr(smb.shutil, "which", lambda name: "/sbin/mount.cifs")
        monkeypatch.setattr(smb.os, "geteuid", lambda: 0)
        monkeypatch.setattr(smb, "_has_sys_admin", lambda: False)
        assert "cap_add" in smb.unsupported()

    def test_supported(self, monkeypatch):
        monkeypatch.setattr(smb.shutil, "which", lambda name: "/sbin/mount.cifs")
        monkeypatch.setattr(smb.os, "geteuid", lambda: 0)
        monkeypatch.setattr(smb, "_has_sys_admin", lambda: None)
        assert smb.unsupported() is None

    @pytest.mark.parametrize("status, expected", [
        ("Name:\tx\nCapEff:\t000001ffffffffff\n", True),
        ("CapEff:\t00000000a80425fb\n", False),
        ("Name:\tx\n", None),
        ("CapEff:\tzz\n", None),
    ])
    def test_has_sys_admin(self, monkeypatch, status, expected):
        monkeypatch.setattr(smb, "open", lambda path: io.StringIO(status), raising=False)
        assert smb._has_sys_admin() is expected

    def test_has_sys_admin_unreadable(self, monkeypatch):
        def fail(path):
            raise OSError("no /proc")

        monkeypatch.setattr(smb, "open", fail, raising=False)
        assert smb._has_sys_admin() is None


class TestMount:
    def test_with_credentials(self, mounts):
        row = share_row(smbDomain="WORK", smbOptions="vers=2.0")
        assert smb.connect(row) is None
        assert row.path in mounts.mounted
        [args] = mounts.calls
        assert args[:3] == ["mount.cifs", "//nas/media", row.path]
        options = args[4].split(",")
        assert options[:2] == ["iocharset=utf8", "soft"] and options[-1] == "vers=2.0"
        # The password never reaches the command line...
        assert "p@ss" not in " ".join(args)
        # ...but a root-only file that is gone afterwards.
        assert mounts.credentials == [("username=me\npassword=p@ss,word\ndomain=WORK\n", "0o600")]
        cred = next(o[12:] for o in options if o.startswith("credentials="))
        assert not os.path.exists(cred)

    def test_guest(self, mounts):
        row = share_row(smbUsername=None, smbPassword=None, smbDomain="WORK")
        assert smb.connect(row) is None
        options = mounts.calls[0][4].split(",")
        assert "guest" in options and "domain=WORK" in options
        assert mounts.credentials == []

    def test_already_mounted(self, mounts):
        row = share_row()
        mounts.mounted.add(row.path)
        assert smb.connect(row) is None
        assert mounts.calls == []

    def test_failure_is_remembered_until_it_works(self, mounts):
        row = share_row()
        mounts.fail["//nas/media"] = (32, "mount error(112): Host is down\n")
        error = smb.connect(row)
        assert error.startswith("Can't reach the server (it's down)")
        assert smb.last_error(1) == error
        del mounts.fail["//nas/media"]
        assert smb.connect(row) is None
        assert smb.last_error(1) is None

    def test_timeout(self, mounts):
        mounts.raise_on = "mount.cifs"
        assert "Timed out" in smb.connect(share_row())

    def test_unsupported(self, mounts, monkeypatch):
        monkeypatch.setattr(smb, "unsupported", lambda: "nope")
        assert smb.connect(share_row()) == "nope"

    def test_mount_point_not_creatable(self, mounts, tmp_path, monkeypatch):
        (tmp_path / "file").write_text("x")
        row = share_row(path=str(tmp_path / "file" / "1"))
        assert "Can't create the mount point" in smb.connect(row)

    def test_remount(self, mounts):
        row = share_row()
        mounts.mounted.add(row.path)
        assert smb.connect(row, remount=True) is None
        assert [c[0] for c in mounts.calls] == ["umount", "mount.cifs"]


class TestUnmount:
    def test_not_mounted(self, mounts):
        assert smb.unmount("/x") is None
        assert mounts.calls == []

    def test_busy_falls_back_to_lazy(self, mounts):
        mounts.mounted.add("/x")
        mounts.umount_fail = 1
        assert smb.unmount("/x") is None
        assert mounts.calls == [["umount", "/x"], ["umount", "-l", "/x"]]

    def test_fails(self, mounts):
        mounts.mounted.add("/x")
        mounts.umount_fail = 2
        assert smb.unmount("/x") == "Couldn't unmount /x"

    def test_times_out(self, mounts):
        mounts.mounted.add("/x")
        mounts.raise_on = "umount"
        assert smb.unmount("/x") == "Couldn't unmount /x"

    def test_disconnect_removes_mount_point(self, mounts):
        row = share_row()
        smb.connect(row)
        mounts.fail["//nas/media"] = (32, "x")
        smb._errors[1] = "old"
        smb.disconnect(row)
        assert row.path not in mounts.mounted
        assert not os.path.exists(row.path)
        assert smb.last_error(1) is None
        smb.disconnect(row)  # gone already: nothing to do


class TestConnectAll:
    def test_connects_every_share(self, mounts, task_engine):
        with Session(task_engine) as s:
            s.add(share_row(id=1))
            s.add(share_row(id=2, smbShare="//other/x"))
            s.add(MediaSource(id=3, media="comic", path="/local"))
            s.commit()
        mounts.fail["//other/x"] = (32, "mount error(13): Permission denied")
        assert smb.connect_all() == 1
        assert os.path.join(smb.MOUNT_ROOT, "share1") in mounts.mounted
        assert smb.last_error(2).startswith("Permission denied")

    def test_reconnect_loop(self, monkeypatch):
        calls = []

        def connect_all():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("db is busy")
            return 0

        monkeypatch.setattr(smb, "connect_all", connect_all)
        monkeypatch.setattr(smb, "RECONNECT_SECONDS", 0)

        async def run():
            task = asyncio.create_task(smb.reconnect_loop())
            while len(calls) < 2:
                await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(run())
        assert len(calls) >= 2
