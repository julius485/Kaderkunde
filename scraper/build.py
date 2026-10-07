"""Erzeugt aus data/raw/ die kompakten Dateien, die die App lädt (data/public/)."""
import datetime as dt
import glob
import json
import os
import re

from common import CFG, PUBLIC, RAW, current_season, load, save

NAT = {"Germany": "Deutschland", "Spain": "Spanien", "Italy": "Italien", "France": "Frankreich", "Netherlands": "Niederlande", "Belgium": "Belgien",
       "Brazil": "Brasilien", "Argentina": "Argentinien", "Colombia": "Kolumbien", "Croatia": "Kroatien", "Serbia": "Serbien", "Switzerland": "Schweiz",
       "Austria": "Österreich", "Poland": "Polen", "Denmark": "Dänemark", "Sweden": "Schweden", "Norway": "Norwegen", "Scotland": "Schottland",
       "Northern Ireland": "Nordirland", "Ireland": "Irland", "Cote d'Ivoire": "Elfenbeinküste", "Cameroon": "Kamerun", "Morocco": "Marokko",
       "Algeria": "Algerien", "Tunisia": "Tunesien", "Egypt": "Ägypten", "DR Congo": "DR Kongo", "Korea, South": "Südkorea", "Turkey": "Türkei",
       "Türkiye": "Türkei", "Greece": "Griechenland", "Czech Republic": "Tschechien", "Czechia": "Tschechien", "Slovakia": "Slowakei",
       "Slovenia": "Slowenien", "Hungary": "Ungarn", "Romania": "Rumänien", "Russia": "Russland", "Georgia": "Georgien", "Albania": "Albanien",
       "Bosnia-Herzegovina": "Bosnien-Herzegowina", "North Macedonia": "Nordmazedonien", "Bulgaria": "Bulgarien", "Finland": "Finnland",
       "Iceland": "Island", "Mexico": "Mexiko", "United States": "USA", "Canada": "Kanada", "Australia": "Australien", "New Zealand": "Neuseeland",
       "Jamaica": "Jamaika", "Gabon": "Gabun", "The Gambia": "Gambia", "Cape Verde": "Kap Verde", "Zambia": "Sambia", "Armenia": "Armenien",
       "Luxembourg": "Luxemburg", "Equatorial Guinea": "Äquatorialguinea", "Congo": "Kongo", "Curacao": "Curaçao", "Saudi Arabia": "Saudi-Arabien",
       "Qatar": "Katar", "Cyprus": "Zypern", "Lithuania": "Litauen", "Latvia": "Lettland", "Estonia": "Estland", "Moldova": "Moldau",
       "Azerbaijan": "Aserbaidschan", "Kazakhstan": "Kasachstan", "South Africa": "Südafrika", "Kenya": "Kenia", "Zimbabwe": "Simbabwe",
       "Bolivia": "Bolivien", "Uzbekistan": "Usbekistan", "Ukraine": "Ukraine", "Japan": "Japan", "Portugal": "Portugal", "England": "England"}
SUB = {"Goalkeeper": "Torwart", "Centre-Back": "Innenverteidiger", "Left-Back": "Linker Verteidiger", "Right-Back": "Rechter Verteidiger",
       "Defensive Midfield": "Defensives Mittelfeld", "Central Midfield": "Zentrales Mittelfeld", "Attacking Midfield": "Offensives Mittelfeld",
       "Left Midfield": "Linkes Mittelfeld", "Right Midfield": "Rechtes Mittelfeld", "Left Winger": "Linksaußen", "Right Winger": "Rechtsaußen",
       "Second Striker": "Hängende Spitze", "Centre-Forward": "Mittelstürmer"}
GROUP_OF_SUB = {"Goalkeeper": "TW", "Centre-Back": "AB", "Left-Back": "AB", "Right-Back": "AB", "Defensive Midfield": "MF", "Central Midfield": "MF",
                "Attacking Midfield": "MF", "Left Midfield": "MF", "Right Midfield": "MF", "Left Winger": "ST", "Right Winger": "ST",
                "Second Striker": "ST", "Centre-Forward": "ST"}
GROUP = {"Goalkeeper": "TW", "Defender": "AB", "Midfielder": "MF", "Midfield": "MF", "Striker": "ST", "Attack": "ST", "Forward": "ST"}
YOUTH = re.compile(r"(U\d{2}|Yth\.?|Youth|Jgd|Sub-?\d|\bJV\b|Juv\.|Academy|Under ?\d|Primavera|\bB$|\bC$|\bII$|Reserves?|U-\d)", re.I)
SKIP = re.compile(r"^(Without Club|Vereinslos|Retired|Karriereende|Career break|Unknown|Unbekannt|Ban|---)$", re.I)
CHUNK = 20000


def ym(d):
    y, m = d.split("-")[:2]
    return int(y) * 12 + int(m) - 1


def foot(f):
    f = (f or "").lower()
    return "right" if f.startswith("r") else "left" if f.startswith("l") else "both" if f.startswith("b") else ""


def mio(v):
    return round(v / 1e4) / 100 if v else None


def stints_from_transfers(tr, club_names):
    tr = sorted(tr, key=lambda t: t[0])
    st = []
    for date, fid, fname, tid, tname, fee, ttype in tr:
        if st:
            st[-1][2] = ym(date)
        if not tid or YOUTH.search(tname or "") or SKIP.match(tname or ""):
            st.append([None, ym(date), 0, "x"])
            continue
        club_names.setdefault(str(tid), tname)
        code = (-3 if ttype == "loan" else -4 if ttype == "endOfLoan" else -5 if ttype == "internal" or YOUTH.search(fname or "") and not fee
                else -2 if ttype == "freeTransfer" or fee == 0 else mio(fee) if fee else -1)
        st.append([int(tid), ym(date), 0, code])
    st = [s for s in st if s[3] != "x"]
    merged = []
    for s in st:
        if merged and merged[-1][0] == s[0] and merged[-1][2] == s[1]:
            merged[-1][2] = s[2]
        else:
            merged.append(s)
    return merged


def stints_from_squads(seasons):
    out = []
    for s, cid in sorted(seasons):
        if out and out[-1][0] == cid and out[-1][2] == s * 12 + 6:
            out[-1][2] = (s + 1) * 12 + 6
        else:
            out.append([cid, s * 12 + 6, (s + 1) * 12 + 6, -1])
    return out


def main():
    cur = current_season()
    squads, club_comp, club_names, member = {}, {}, {}, {}
    for f in sorted(glob.glob(os.path.join(RAW, "squads", "*.json"))):
        season = int(os.path.basename(f)[:-5])
        data = load(f, {})
        squads[season] = {cid: v["p"] for cid, v in data.items()}
        for cid, v in data.items():
            club_comp[cid] = v["c"]
            if v.get("n"):
                club_names[cid] = v["n"]
            for pid in v["p"]:
                member.setdefault(str(pid), []).append((season, int(cid)))

    players = []
    for f in sorted(glob.glob(os.path.join(RAW, "players", "*.json"))):
        for pid, r in load(f, {}).items():
            if not r.get("name"):
                continue
            seasons = member.get(pid, [])
            last = max([s for s, _ in seasons] + [r.get("seen") or 0])
            st = stints_from_transfers(r.get("transfers") or [], club_names) if r.get("transfers") else []
            if not st:
                st = stints_from_squads(seasons)
            if st and last >= cur - 1 and not r.get("retired"):
                st[-1][2] = 0
            elif st and st[-1][2] == 0:
                st[-1][2] = (last + 1) * 12 + 6
            cur_club = r.get("club") or (sorted(seasons)[-1][1] if seasons else 0)
            sub = r.get("sub") or ""
            pos = GROUP.get(r.get("group") or "", GROUP_OF_SUB.get(sub, "MF"))
            nat = r.get("nat") or ""
            height = r.get("height")
            if isinstance(height, str):
                digits = re.sub(r"[^0-9]", "", height)
                height = int(digits) if digits else 0
            if height and height < 3:
                height = int(height * 100)
            players.append([int(pid), r["name"], NAT.get(nat, nat), pos, SUB.get(sub, sub), r.get("dob") or "", foot(r.get("foot")), height or 0,
                            mio(r.get("mv")), mio(r.get("peak") or r.get("mv")) or 0, int(cur_club or 0), club_comp.get(str(cur_club), ""),
                            r.get("img") or "", int(r.get("caps") or 0), last, st])

    clubs = {cid: [club_names.get(cid, "Unbekannt"), club_comp.get(cid, "")] for cid in set(club_names) | set(club_comp)}
    comps = {k: [v[0], v[1]] for k, v in CFG["competitions"].items()}
    os.makedirs(PUBLIC, exist_ok=True)
    for old in glob.glob(os.path.join(PUBLIC, "players-*.json")):
        os.remove(old)
    players.sort(key=lambda p: -(p[9] or 0))
    files = []
    for i in range(0, len(players), CHUNK):
        name = f"players-{i // CHUNK + 1}.json"
        save(os.path.join(PUBLIC, name), players[i:i + CHUNK])
        files.append(name)
    save(os.path.join(PUBLIC, "clubs.json"), clubs)
    save(os.path.join(PUBLIC, "comps.json"), comps)
    save(os.path.join(PUBLIC, "squads.json"), {str(s): v for s, v in squads.items()})
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    save(os.path.join(PUBLIC, "manifest.json"), {"version": now, "date": now[:10], "curSeason": cur, "players": len(players), "clubs": len(clubs),
                                                  "seasons": sorted(squads), "files": {"players": files, "clubs": "clubs.json", "comps": "comps.json", "squads": "squads.json"}})
    print(f"Export: {len(players)} Spieler, {len(clubs)} Vereine, {len(squads)} Saisons")


if __name__ == "__main__":
    main()
