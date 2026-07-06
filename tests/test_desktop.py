import struct

from selfscribe import desktop, startup
from selfscribe.assets import ICO_SIZES, icon_path, render_icon, write_ico
from selfscribe.links import _ps_quote


def test_render_icon_is_square_rgba():
    img = render_icon(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    # not blank: the mic + tile paint a chunk of opaque pixels
    alpha = img.getchannel("A")
    opaque = sum(1 for a in alpha.tobytes() if a > 0)
    assert opaque > 64 * 64 * 0.3


def test_write_ico_produces_multi_size_icon(tmp_path):
    path = write_ico(tmp_path / "selfscribe.ico")
    assert path.exists()
    data = path.read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"  # ICO magic
    count = struct.unpack("<H", data[4:6])[0]
    assert count == len(ICO_SIZES)


def test_icon_path_under_config_dir():
    assert icon_path().name == "selfscribe.ico"
    assert icon_path().parent.name == ".selfscribe"


def test_desktop_install_uninstall_roundtrip(tmp_path, monkeypatch):
    # keep the generated .ico out of the real home dir
    monkeypatch.setattr(desktop, "write_ico", lambda: tmp_path / "icon.ico")
    (tmp_path / "icon.ico").write_bytes(b"\x00\x00\x01\x00")
    link = desktop.install(tmp_path)
    assert link.exists()
    assert desktop.is_installed(tmp_path)
    assert desktop.uninstall(tmp_path) is True
    assert not desktop.is_installed(tmp_path)
    assert desktop.uninstall(tmp_path) is False


def test_desktop_shortcut_carries_icon(tmp_path, monkeypatch):
    icon = tmp_path / "icon.ico"
    write_ico(icon)
    monkeypatch.setattr(desktop, "write_ico", lambda: icon)
    link = desktop.install(tmp_path)
    # a .lnk that references the .ico path contains its bytes (UTF-16) somewhere
    blob = link.read_bytes()
    assert b"selfscribe" in blob.lower() or icon.name.encode("utf-16-le") in blob


def test_startup_and_desktop_share_the_shortcut_helper():
    # both modules build on links.create_shortcut / venv_pythonw (no duplication)
    import selfscribe.links as links

    assert startup._ps_quote is _ps_quote
    assert startup.StartupError is links.ShortcutError
