import datetime as dt
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("TM_DATA_DIR", os.path.join(ROOT, "data"))
RAW = os.path.join(DATA, "raw")
PUBLIC = os.path.join(DATA, "public")
SHARDS = 64

with open(os.path.join(ROOT, "scraper", "config.json"), encoding="utf-8") as fh:
    CFG = json.load(fh)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def g(d, *keys, default=None):
    """Erstes vorhandenes Feld aus mehreren möglichen Pfaden (a.b.c) – robust gegen API-Änderungen."""
    for k in keys:
        cur, ok = d, True
        for part in k.split("."):
            if isinstance(cur, dict) and cur.get(part) is not None:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def current_season(today=None):
    t = today or dt.date.today()
    return t.year if t.month >= 7 else t.year - 1


def parse_date(v):
    if not v:
        return None
    s = str(v).strip()
    try:
        return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    for f in ("%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y"):
        try:
            return dt.datetime.strptime(s.split("(")[0].strip(), f).date().isoformat()
        except ValueError:
            continue
    return None


def money(v):
    """Zahl in Euro aus 1234567 | '€94.00m' | '€500k' | '94,00 Mio. €' – sonst None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace("€", "").replace("eur", "").strip()
    mult = 1.0
    for suf, m in (("bn", 1e9), ("mrd.", 1e9), ("mio.", 1e6), ("m", 1e6), ("tsd.", 1e3), ("th.", 1e3), ("k", 1e3)):
        if s.endswith(suf):
            mult, s = m, s[: -len(suf)].strip()
            break
    s = s.replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9.]", "", s)
    try:
        return float(s) * mult
    except ValueError:
        return None


def shard_of(pid):
    return int(pid) % SHARDS
