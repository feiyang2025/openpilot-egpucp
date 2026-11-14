import time
from openpilot.cereal import messaging

sm = messaging.sub_sock("smallObjectTracks", timeout=200)
time.sleep(0.4)
messaging.drain_sock(sm)
best = None
nmsg = 0
t0 = time.monotonic()
while time.monotonic() - t0 < 8:
    for mm in messaging.drain_sock(sm):
        m = mm.smallObjectTracks
        if m is not None:
            best = m
            nmsg += 1
    time.sleep(0.05)
print("msgs:", nmsg)
if best:
    rows = [(round(t.score, 2), int(t.cls), bool(t.confirmed), round(t.x, 1), round(t.y, 1),
             int(t.detPxH), [round(v, 2) for v in t.bbox][:2]) for t in best.tracks]
    rows.sort(reverse=True)
    print("tracks:", len(rows))
    for r in rows[:14]:
        print(r)
