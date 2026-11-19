"""Video decoding with the graphics card (1.1.16): Automatic leaves it to the
engine, On asks for it (experimental), Off turns it off; On falls back to
Automatic by itself when I.K.E. did not close normally while it was on."""

from ike import app


class Cfg(dict):
    saved = 0

    def save(self):
        self.saved += 1


def test_features_join_the_switches_the_engine_reads():
    flags = ["--enable-smooth-scrolling", "--enable-features=A,B", "--disable-features=C,AcceleratedVideoDecodeLinux"]
    out = app._feature_flags(flags, enable=app.VIDEO_ON)
    assert out[0] == "--enable-smooth-scrolling"
    assert [f for f in out if f.startswith("--enable-features=")] == [
        "--enable-features=A,B," + ",".join(app.VIDEO_ON)]
    assert [f for f in out if f.startswith("--disable-features=")] == ["--disable-features=C"]
    out = app._feature_flags(["--enable-features=AcceleratedVideoDecodeLinux"],
                             disable=("AcceleratedVideoDecodeLinux",))
    assert out == ["--disable-features=AcceleratedVideoDecodeLinux"]
    assert app._feature_flags(["--x"]) == ["--x"]


def test_each_choice_and_the_safety_net(tmp_path):
    trial = tmp_path / app.VIDEO_TRIAL
    cfg = Cfg(video_hw="auto", video_hw_fell_back=False)
    assert app._video_flags(["--x"], cfg, tmp_path) == ["--x"] and not trial.exists()
    cfg["video_hw"] = "off"
    assert app._video_flags([], cfg, tmp_path) == ["--disable-features=AcceleratedVideoDecodeLinux"]
    cfg["video_hw"] = "on"
    on = app._video_flags([], cfg, tmp_path)
    assert on == ["--enable-features=" + ",".join(app.VIDEO_ON)] and trial.exists()
    app._video_trial_done(tmp_path)                    # a normal exit
    assert not trial.exists()
    assert app._video_flags([], cfg, tmp_path) == on   # on again at the next start
    # ... and this time I.K.E. did not close normally: back to Automatic, said once
    assert app._video_flags([], cfg, tmp_path) == []
    assert cfg["video_hw"] == "auto" and cfg["video_hw_fell_back"] is True and cfg.saved == 1
    assert not trial.exists()


def test_in_the_browser(run_ike, tmp_path):
    marker = tmp_path / "home" / ".config" / "ike-browser" / app.VIDEO_TRIAL
    out = run_ike("""
        import os
        def steps(ike, qapp, out):
            yield 300
            out["flags"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            out["trial"] = os.path.exists(os.path.join(os.environ["XDG_CONFIG_HOME"], "ike-browser", "video-gpu-trial"))
            dlg = ike.show_settings(ike.windows[0])
            yield 200
            out["combo"] = [dlg.video_hw.itemData(i) for i in range(dlg.video_hw.count())]
            out["shown"] = dlg.video_hw.currentData()
            dlg.video_hw.setCurrentIndex(dlg.video_hw.findData("off"))
            dlg.apply()
            out["saved"] = ike.config["video_hw"]
            dlg.close()
    """, settings={"video_hw": "on"})
    assert "AcceleratedVideoDecodeLinuxGL" in out["flags"] and out["trial"] is True
    assert out["combo"] == ["auto", "on", "off"] and out["shown"] == "on" and out["saved"] == "off"
    assert not marker.exists()                          # closed normally

    # a start after one that ended badly while it was on
    marker.write_text("on\n")
    out = run_ike("""
        import os
        def steps(ike, qapp, out):
            yield 300
            out["flags"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            out["mode"] = ike.config["video_hw"]
            told = []
            ike._desktop_notify = lambda text: told.append(text)
            ike._healthy()
            out["told"] = told
            out["once"] = ike.config["video_hw_fell_back"]
    """, settings={"video_hw": "on"})
    assert "AcceleratedVideoDecodeLinux" not in out["flags"] and out["mode"] == "auto"
    assert len(out["told"]) == 1 and "Automatic" in out["told"][0] and out["once"] is False
