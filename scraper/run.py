"""Sammelt Kader und Spielerprofile über eine lokal laufende transfermarkt-api (github.com/felipeall/transfermarkt-api).

Ablauf pro Lauf (bis das Zeitbudget aufgebraucht ist):
  1. Kader der laufenden Saison aller konfigurierten Ligen (einmal pro Tag)
  2. Nachholen älterer Saisons, neueste zuerst (jede Liga+Saison nur einmal)
  3. Profile, Transfers und Marktwert-Verlauf: erst neue Spieler, dann veraltete aktive Spieler
Der Fortschritt liegt in data/raw/ – ein abgebrochener Lauf macht beim nächsten Mal weiter.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import threading
import time

import requests

from common import CFG, RAW, current_season, g, load, money, parse_date, save, shard_of

API = os.environ.get("TM_API", "http://localhost:8000").rstrip("/")


class Client:
    def __init__(self, rps):
        self.gap = 1.0 / max(rps, 0.1)
        self.lock = threading.Lock()
        self.last = 0.0
        self.local = threading.local()
        self.calls = 0
        self.errors = 0

    def session(self):
        if not hasattr(self.local, "s"):
            self.local.s = requests.Session()
        return self.local.s

    def get(self, path, params=None, tries=4):
        for attempt in range(tries):
            with self.lock:
                wait = self.last + self.gap - time.time()
                if wait > 0:
                    time.sleep(wait)
                self.last = time.time()
            try:
                r = self.session().get(API + path, params=params, timeout=90)
                self.calls += 1
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (400, 404, 422):
                    return None
            except (requests.RequestException, ValueError):
                pass
            self.errors += 1
            time.sleep(min(120, 5 * (attempt + 1) ** 2))
        return None


class Store:
    def __init__(self):
        self.shards = {}
        self.dirty = set()
        self.lock = threading.Lock()

    def shard(self, i):
        if i not in self.shards:
            self.shards[i] = load(os.path.join(RAW, "players", f"{i:02d}.json"), {})
        return self.shards[i]

    def get(self, pid):
        return self.shard(shard_of(pid)).get(str(pid))

    def put(self, pid, rec):
        with self.lock:
            i = shard_of(pid)
            self.shard(i)[str(pid)] = rec
            self.dirty.add(i)

    def all_ids(self):
        from common import SHARDS
        ids = []
        for i in range(SHARDS):
            ids.extend(self.shard(i).keys())
        return ids

    def flush(self):
        with self.lock:
            for i in sorted(self.dirty):
                save(os.path.join(RAW, "players", f"{i:02d}.json"), self.shards[i])
            self.dirty.clear()


def stub_from_squad(p, season):
    nat = g(p, "nationality", "citizenship", default=[])
    return {
        "name": g(p, "name"),
        "dob": parse_date(g(p, "dateOfBirth", "birthDate")),
        "nat": nat[0] if isinstance(nat, list) and nat else (nat or None),
        "sub": g(p, "position", "position.main"),
        "foot": g(p, "foot"),
        "height": g(p, "height"),
        "img": g(p, "imageUrl", "portraitUrl"),
        "mv": money(g(p, "marketValue")),
        "seen": season,
        "fetched": None,
    }


def fetch_squads(c, store, comp, season, squads):
    res = c.get(f"/competitions/{comp}/clubs", {"season_id": season})
    clubs = g(res or {}, "clubs", default=[]) or []
    if not clubs:
        return False

    def one(club):
        cid = str(g(club, "id"))
        sq = c.get(f"/clubs/{cid}/players", {"season_id": season})
        return cid, g(club, "name"), g(sq or {}, "players", default=[]) or []

    with cf.ThreadPoolExecutor(max_workers=CFG.get("workers", 3)) as ex:
        for cid, cname, players in ex.map(one, clubs):
            ids = []
            for p in players:
                pid = g(p, "id")
                if not pid:
                    continue
                ids.append(int(pid))
                cur = store.get(pid)
                if cur is None:
                    store.put(pid, stub_from_squad(p, season))
                elif (cur.get("seen") or 0) < season:
                    cur["seen"] = season
                    if cur.get("fetched") is None and money(g(p, "marketValue")) is not None:
                        cur["mv"] = money(g(p, "marketValue"))
                    store.put(pid, cur)
            squads[cid] = {"n": cname, "c": comp, "p": ids}
    return True


def fetch_player(c, pid, old):
    prof = c.get(f"/players/{pid}/profile")
    if prof is None:
        return None
    tr = c.get(f"/players/{pid}/transfers") or {}
    mvh = c.get(f"/players/{pid}/market_value") if CFG.get("fetch_market_value_history", True) else None
    nat = g(prof, "citizenship", "nationality", default=[])
    hist = g(mvh or {}, "marketValueHistory", "history", default=[]) or []
    values = [money(g(h, "marketValue", "value")) for h in hist]
    mv = money(g(prof, "marketValue")) or money(g(mvh or {}, "marketValue"))
    peak = max([v for v in values if v] + [mv or 0]) or None
    transfers = []
    for t in g(tr, "transfers", default=[]) or []:
        if g(t, "upcoming", default=False):
            continue
        fee_raw = g(t, "fee")
        ttype = g(t, "transferType", "type")
        if not ttype and isinstance(fee_raw, str):
            low = fee_raw.lower()
            ttype = "endOfLoan" if "end of loan" in low else "loan" if "loan" in low else "freeTransfer" if "free" in low else None
        transfers.append([
            parse_date(g(t, "date")),
            g(t, "clubFrom.id", "from.clubId", "fromClubId"), g(t, "clubFrom.name", "from.clubName", "fromClubName"),
            g(t, "clubTo.id", "to.clubId", "toClubId"), g(t, "clubTo.name", "to.clubName", "toClubName"),
            money(fee_raw) if not isinstance(fee_raw, str) or any(ch.isdigit() for ch in fee_raw) else None,
            ttype,
        ])
    return {
        "name": g(prof, "name", default=old.get("name") if old else None),
        "dob": parse_date(g(prof, "dateOfBirth")) or (old or {}).get("dob"),
        "nat": nat[0] if isinstance(nat, list) and nat else (nat or (old or {}).get("nat")),
        "group": g(prof, "position.group"),
        "sub": g(prof, "position.main", default=(old or {}).get("sub")),
        "foot": g(prof, "foot", default=(old or {}).get("foot")),
        "height": g(prof, "height", default=(old or {}).get("height")),
        "img": g(prof, "imageUrl", default=(old or {}).get("img")),
        "caps": g(prof, "nationalTeam.caps", "internationalCaps", "nationalTeam.matches", default=0),
        "club": g(prof, "club.id"),
        "clubName": g(prof, "club.name"),
        "retired": bool(g(prof, "isRetired", default=False)),
        "mv": mv,
        "peak": peak,
        "transfers": [t for t in transfers if t[0]],
        "seen": (old or {}).get("seen"),
        "fetched": dt.date.today().isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-minutes", type=float, default=320)
    ap.add_argument("--selftest", action="store_true", help="Beispielantworten ausgeben und beenden")
    args = ap.parse_args()
    c = Client(CFG.get("requests_per_second", 2))

    if args.selftest:
        for path, params in (("/competitions/L1/clubs", {"season_id": current_season()}), ("/clubs/35/players", {"season_id": 2005}),
                             ("/players/28003/profile", None), ("/players/28003/transfers", None), ("/players/28003/market_value", None)):
            print("==", path, json.dumps(c.get(path, params), ensure_ascii=False)[:1500])
        return

    start = time.time()
    deadline = start + args.budget_minutes * 60
    squad_deadline = start + args.budget_minutes * 60 * 0.45
    store = Store()
    prog = load(os.path.join(RAW, "progress.json"), {"done": [], "current_day": None})
    done = set(prog["done"])
    cur = current_season()
    today = dt.date.today().isoformat()
    comps = list(CFG["competitions"].keys())

    def squads_file(s):
        return os.path.join(RAW, "squads", f"{s}.json")

    if prog.get("current_day") != today:
        sq = load(squads_file(cur), {})
        for comp in comps:
            fetch_squads(c, store, comp, cur, sq)
        save(squads_file(cur), sq)
        prog["current_day"] = today
        store.flush()
        print(f"Aktuelle Saison {cur}: {len(sq)} Vereine")

    for season in range(cur - 1, CFG["from_season"] - 1, -1):
        if time.time() > squad_deadline:
            break
        sq = None
        for comp in comps:
            key = f"{comp}-{season}"
            if key in done:
                continue
            if time.time() > squad_deadline:
                break
            sq = sq if sq is not None else load(squads_file(season), {})
            fetch_squads(c, store, comp, season, sq)
            done.add(key)
            save(squads_file(season), sq)
            prog["done"] = sorted(done)
            save(os.path.join(RAW, "progress.json"), prog)
            store.flush()
            print(f"Kader {key}: fertig ({c.calls} Abrufe)")

    refresh = dt.date.today() - dt.timedelta(days=CFG.get("refresh_days_active", 7))
    ids = store.all_ids()
    new = [p for p in ids if not store.get(p).get("fetched")]
    new.sort(key=lambda p: -(store.get(p).get("seen") or 0))
    stale = [p for p in ids if store.get(p).get("fetched") and (store.get(p).get("seen") or 0) >= cur - 1
             and not store.get(p).get("retired") and store.get(p)["fetched"] < refresh.isoformat()]
    queue = new + stale
    print(f"Spieler: {len(ids)} bekannt, {len(new)} neu, {len(stale)} zu aktualisieren")

    n = 0
    with cf.ThreadPoolExecutor(max_workers=CFG.get("workers", 3)) as ex:
        it = iter(queue)
        while time.time() < deadline - 300:
            batch = [p for _, p in zip(range(30), it)]
            if not batch:
                break
            for pid, rec in zip(batch, ex.map(lambda p: fetch_player(c, p, store.get(p)), batch)):
                if rec:
                    store.put(pid, rec)
                    n += 1
            if n % 300 < 30:
                store.flush()
    store.flush()
    save(os.path.join(RAW, "progress.json"), prog)
    print(f"Fertig: {n} Profile aktualisiert, {c.calls} Abrufe, {c.errors} Fehlversuche, {round((time.time() - start) / 60)} Min.")


if __name__ == "__main__":
    main()
