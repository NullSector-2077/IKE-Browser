"""How old the system's web engine is (1.1.18, security audit F4).

The notice that the engine's security fixes are behind came only at five
Chrome versions (about five months); now at three (two is normal between two
Qt releases, see ike/chromever.py). The
comparison is between the Chrome version up to which Qt WebEngine has its
security fixes (qWebEngineChromiumSecurityPatchVersion) and the current
stable Chrome (Google's version list, or a calendar estimate that may lag but
is never ahead). Help -> About names the reference version and says whether
it was checked or only estimated.
"""

STEPS = r'''
def steps(ike, qapp, out):
    from ike import chromever
    notes = []
    ike._desktop_notify = lambda text, *a, **k: notes.append(text)
    real = chromever.security_major
    ike.config["chrome_major"] = 157
    for fixes in (157, 156, 155, 154):
        chromever.security_major = lambda f=fixes: f
        ike._engine_warned = False
        out[str(fixes)] = [ike._engine_security_notice(), len(notes)]
    out["about_checked"] = ike.windows[0].about_text(media={})
    ike.config["chrome_major"] = 0                  # never checked: the estimate
    out["about_estimated"] = ike.windows[0].about_text(media={})
    chromever.security_major = real
    yield 10
'''


def test_the_notice_comes_at_three_versions_behind(run_ike):
    out = run_ike(STEPS, settings={"language": "en"}, timeout=60)
    assert out["157"] == [0, 0] and out["156"] == [1, 0], out      # up to date, one behind: no notice
    assert out["155"] == [2, 0], out                              # two: between two Qt releases, no notice
    assert out["154"] == [3, 1], out                              # three: a Qt update was missed
    assert "Current stable Chrome: 157 (checked with Google's version list)" in out["about_checked"]
    assert "Security fixes: 3 Chrome versions behind" in out["about_checked"]
    assert "(estimated from the calendar" in out["about_estimated"], out["about_estimated"]
