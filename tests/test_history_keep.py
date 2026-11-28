"""The history kept for a chosen time (Settings -> Privacy, "Keep the history").

"Always" is the default and deletes nothing (as 1.1.30 and earlier); with
1 month, 3 or 6 months, 1 or 2 years the pages and the downloads older than
that go by themselves (at the start, every hour and when the setting is
applied), the newer ones and the bookmarks stay.
"""

STEPS = r'''
import time

def steps(ike, qapp, out):
    yield 300
    st = ike.storage
    now = time.time()
    day = 86400
    rows = [("https://old.example/", "old", int(now - 400 * day), 3),
            ("https://months.example/", "months", int(now - 100 * day), 1),
            ("https://recent.example/", "recent", int(now - 2 * day), 5)]
    st.import_history(rows)
    st.add_bookmark("https://old.example/", "kept bookmark")
    st.db.execute("INSERT INTO downloads(name,path,url,size,state,time,host,note) VALUES(?,?,?,?,?,?,?,?)",
                  ("old.zip", "/tmp/old.zip", "https://old.example/old.zip", 1, "done",
                   int(now - 400 * day), "old.example", ""))
    st.db.execute("INSERT INTO downloads(name,path,url,size,state,time,host,note) VALUES(?,?,?,?,?,?,?,?)",
                  ("new.zip", "/tmp/new.zip", "https://recent.example/new.zip", 1, "done",
                   int(now - day), "recent.example", ""))
    st.db.commit()
    def urls():
        return sorted(u for (u,) in st.db.execute("SELECT url FROM history"))
    def downloads():
        return sorted(n for (n,) in st.db.execute("SELECT name FROM downloads"))
    out["default"] = [ike.config["history_keep_days"], ike.expire_history(), urls()]
    ike.config["history_keep_days"] = 365
    out["year"] = [ike.expire_history(), urls(), downloads()]
    ike.config["history_keep_days"] = 91
    out["three_months"] = [ike.expire_history(), urls()]
    out["bookmark"] = st.is_bookmarked("https://old.example/")
    ike.config["history_keep_days"] = 17          # an edited settings file: kept always
    out["odd"] = [ike.history_keep_days(), ike.expire_history(now + 1000 * day), urls()]
    # Settings -> Privacy: the choices, and Apply deletes at once
    ike.config["history_keep_days"] = 0
    st.import_history([("https://old2.example/", "old2", int(now - 40 * day), 1)])
    dlg = ike.show_settings(ike.windows[0])
    yield 300
    box = dlg.history_keep
    out["choices"] = [box.itemData(i) for i in range(box.count())]
    out["current"] = box.currentData()
    box.setCurrentIndex(box.findData(30))
    dlg.apply()
    yield 300
    out["applied"] = [ike.config["history_keep_days"], urls()]
    dlg.close()
'''


def test_history_kept_for_the_chosen_time(run_ike):
    out = run_ike(STEPS, timeout=120)
    assert out["default"] == [0, 0, ["https://months.example/", "https://old.example/",
                                     "https://recent.example/"]]
    assert out["year"] == [1, ["https://months.example/", "https://recent.example/"], ["new.zip"]]
    assert out["three_months"] == [1, ["https://recent.example/"]]
    assert out["bookmark"] is True
    assert out["odd"] == [0, 0, ["https://recent.example/"]]
    assert out["choices"] == [0, 30, 91, 182, 365, 730] and out["current"] == 0
    assert out["applied"] == [30, ["https://recent.example/"]]
