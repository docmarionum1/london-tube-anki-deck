#!/usr/bin/env python3
"""
Generate a comprehensive Anki flashcard deck for learning the London transport network.

Card types:
  Type 1 ("Lines"): Given a station with some lines hidden, recall the missing line(s).
  Type 2 ("Sequence"): Given a line and two neighbors, recall the station in between.
  Type 3 ("Branch"): Given a station on a branch, recall which line and branch it's on.

Uses TfL Unified API for data. Outputs london_transport.apkg.
"""

import json
import hashlib
import random
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import genanki
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

TFL_BASE = "https://api.tfl.gov.uk"

# Official TfL line colors and display names
LINE_INFO = {
    "bakerloo":             {"name": "Bakerloo",           "hex": "#B36305", "text": "white", "mode": "tube"},
    "central":              {"name": "Central",            "hex": "#E32017", "text": "white", "mode": "tube"},
    "circle":               {"name": "Circle",             "hex": "#FFD300", "text": "dark",  "mode": "tube"},
    "district":             {"name": "District",           "hex": "#00782A", "text": "white", "mode": "tube"},
    "hammersmith-city":     {"name": "Hammersmith & City", "hex": "#F3A9BB", "text": "dark",  "mode": "tube"},
    "jubilee":              {"name": "Jubilee",            "hex": "#A0A5A9", "text": "white", "mode": "tube"},
    "metropolitan":         {"name": "Metropolitan",       "hex": "#9B0056", "text": "white", "mode": "tube"},
    "northern":             {"name": "Northern",           "hex": "#000000", "text": "white", "mode": "tube"},
    "piccadilly":           {"name": "Piccadilly",         "hex": "#003688", "text": "white", "mode": "tube"},
    "victoria":             {"name": "Victoria",           "hex": "#0098D4", "text": "white", "mode": "tube"},
    "waterloo-city":        {"name": "Waterloo & City",    "hex": "#95CDBA", "text": "dark",  "mode": "tube"},
    "dlr":                  {"name": "DLR",                "hex": "#00A4A7", "text": "white", "mode": "dlr"},
    "elizabeth":            {"name": "Elizabeth line",     "hex": "#6950A1", "text": "white", "mode": "elizabeth-line"},
    "liberty":              {"name": "Liberty",            "hex": "#5D6061", "text": "white", "mode": "overground"},
    "lioness":              {"name": "Lioness",            "hex": "#FAA61A", "text": "dark",  "mode": "overground"},
    "mildmay":              {"name": "Mildmay",            "hex": "#0077AD", "text": "white", "mode": "overground"},
    "suffragette":          {"name": "Suffragette",        "hex": "#5BBD72", "text": "dark",  "mode": "overground"},
    "weaver":               {"name": "Weaver",             "hex": "#823A62", "text": "white", "mode": "overground"},
    "windrush":             {"name": "Windrush",           "hex": "#ED1B00", "text": "white", "mode": "overground"},
}

# Curriculum order for subdecks
LINE_ORDER = [
    "northern", "victoria", "jubilee", "central", "piccadilly",
    "bakerloo", "metropolitan", "circle", "district", "hammersmith-city",
    "waterloo-city", "liberty", "lioness", "mildmay", "suffragette",
    "weaver", "windrush", "dlr", "elizabeth",
]

# Canonical branch names for lines with branches.
# Each rule is (set_of_station_substrings, branch_label).
# For each segment, the first rule where ANY station name in the segment
# contains ANY of the substrings wins. Order matters — put specific rules first.
BRANCH_RULES = {
    "northern": [
        ({"High Barnet"}, "High Barnet branch"),
        ({"Edgware", "Burnt Oak"}, "Edgware branch"),
        ({"Mill Hill East"}, "Mill Hill East branch"),
        ({"Battersea Power", "Nine Elms"}, "Battersea Power Station branch"),
        ({"Morden", "South Wimbledon"}, "Morden branch"),
        # Bank vs Charing Cross: identified by unique intermediate stations
        ({"King\u2019s Cross", "Angel", "Old Street", "Moorgate", "Bank", "Borough"}, "Bank branch"),
        ({"Warren Street", "Goodge Street", "Leicester Square", "Charing Cross", "Embankment"}, "Charing Cross branch"),
        ({"Mornington Crescent"}, "Charing Cross branch"),
    ],
    "central": [
        ({"Epping", "Theydon Bois", "Debden", "Loughton", "Buckhurst Hill"}, "Epping branch"),
        ({"Hainault", "Fairlop", "Barkingside", "Newbury Park"}, "Hainault branch"),
        ({"Grange Hill", "Chigwell", "Roding Valley"}, "Hainault via Newbury Park"),
        ({"West Ruislip", "Northolt", "Greenford"}, "West Ruislip branch"),
        ({"Ealing Broadway"}, "Ealing Broadway branch"),
    ],
    "district": [
        ({"Richmond", "Kew Gardens"}, "Richmond branch"),
        ({"Ealing Broadway", "Ealing Common"}, "Ealing Broadway branch"),
        ({"Wimbledon", "Southfields"}, "Wimbledon branch"),
        ({"Upminster", "Upminster Bridge"}, "Upminster branch"),
        ({"Edgware Road"}, "Edgware Road branch"),
        ({"Kensington (Olympia)"}, "Kensington Olympia branch"),
    ],
    "metropolitan": [
        ({"Watford"}, "Watford branch"),
        ({"Chesham"}, "Chesham branch"),
        ({"Amersham"}, "Amersham branch"),
        ({"Uxbridge", "Hillingdon"}, "Uxbridge branch"),
    ],
    "piccadilly": [
        ({"Uxbridge", "Hillingdon", "Ickenham"}, "Uxbridge branch"),
        ({"Heathrow Terminal 5"}, "Heathrow Terminal 5 branch"),
        ({"Heathrow Terminal 4"}, "Heathrow Terminal 4 branch"),
        ({"Hatton Cross", "Hounslow"}, "Heathrow branch"),
    ],
    "hammersmith-city": [
        ({"Hammersmith"}, "Hammersmith branch"),
        ({"Barking"}, "Barking branch"),
    ],
    "circle": [
        ({"Hammersmith"}, "Hammersmith branch"),
    ],
    "weaver": [
        ({"Enfield Town"}, "Enfield Town branch"),
        ({"Cheshunt", "Theobalds Grove"}, "Cheshunt branch"),
        ({"Chingford", "Highams Park"}, "Chingford branch"),
    ],
    "windrush": [
        ({"West Croydon", "Norwood Junction"}, "West Croydon branch"),
        ({"Crystal Palace"}, "Crystal Palace branch"),
        ({"Clapham Junction"}, "Clapham Junction branch"),
        ({"New Cross ELL"}, "New Cross branch"),
        ({"London Bridge"}, "London Bridge branch"),
    ],
    "mildmay": [
        ({"Richmond"}, "Richmond branch"),
        ({"Clapham Junction"}, "Clapham Junction branch"),
    ],
    "suffragette": [
        ({"Barking Riverside"}, "Barking Riverside branch"),
    ],
    "dlr": [
        ({"Lewisham", "Elverson Road"}, "Lewisham branch"),
        ({"Beckton", "Gallions Reach"}, "Beckton branch"),
        ({"Woolwich Arsenal", "King George V"}, "Woolwich Arsenal branch"),
        ({"Stratford International"}, "Stratford International branch"),
        ({"Stratford High Street", "Abbey Road"}, "Stratford branch"),
        ({"Bank"}, "Bank branch"),
        ({"Tower Gateway"}, "Tower Gateway branch"),
    ],
    "elizabeth": [
        ({"Heathrow Terminal 4"}, "Heathrow Terminal 4 branch"),
        ({"Heathrow Terminal 5"}, "Heathrow Terminal 5 branch"),
        ({"Reading", "Maidenhead", "Slough"}, "Reading branch"),
        ({"Abbey Wood", "Woolwich"}, "Abbey Wood branch"),
        ({"Shenfield", "Brentwood"}, "Shenfield branch"),
    ],
}


def _label_segment(line_id, seg_stops, stations):
    """
    Determine the canonical branch label for a segment based on its station names.
    Returns a branch label string, or None for non-branching lines / shared sections.
    """
    rules = BRANCH_RULES.get(line_id)
    if not rules:
        return None

    # Collect all station names in this segment
    seg_names = set()
    for nid in seg_stops:
        name = stations.get(nid, {}).get("name", "")
        seg_names.add(name)

    for substrings, label in rules:
        for seg_name in seg_names:
            for sub in substrings:
                if sub in seg_name:
                    return label
    return None  # shared section — no specific branch


def _stable_id(name):
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)

TYPE1_MODEL_ID = _stable_id("LondonTransport_Type1_v4")
TYPE2_MODEL_ID = _stable_id("LondonTransport_Type2_v4")

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

SHARED_CSS = """
html { font-size: 16px; }
body {
    font-family: 'Johnston', 'P22 Underground', Arial, Helvetica, sans-serif;
    margin: 0; padding: 12px;
    background: #F5F5F5;
    color: #333;
}
.card { max-width: 400px; margin: 0 auto; }
.station-name {
    font-size: 1.4rem;
    font-weight: bold;
    text-align: center;
    margin: 8px 0 12px 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.line-flag {
    display: block;
    width: 100%;
    padding: 8px 16px;
    margin: 4px 0;
    color: #FFFFFF;
    font-weight: bold;
    font-size: 1rem;
    border-radius: 5px;
    text-align: center;
    box-sizing: border-box;
    line-height: 1.3;
}
/* Overground: white background with colored double-stripe at top */
.line-flag.overground-style {
    background: #FFFFFF;
    color: #1C3F94;
    border: 1px solid #DDDDDD;
}
.line-bakerloo        { background: #B36305; color: #FFFFFF; }
.line-central         { background: #E32017; color: #FFFFFF; }
.line-circle          { background: #FFD300; color: #1C3F94; }
.line-district        { background: #00782A; color: #FFFFFF; }
.line-hammersmith-city { background: #F3A9BB; color: #1C3F94; }
.line-jubilee         { background: #A0A5A9; color: #FFFFFF; }
.line-metropolitan    { background: #9B0056; color: #FFFFFF; }
.line-northern        { background: #000000; color: #FFFFFF; }
.line-piccadilly      { background: #003688; color: #FFFFFF; }
.line-victoria        { background: #0098D4; color: #FFFFFF; }
.line-waterloo-city   { background: #95CDBA; color: #1C3F94; }
.line-dlr             { background: #00A4A7; color: #FFFFFF; }
.line-elizabeth       { background: #6950A1; color: #FFFFFF; }
/* Overground lines: white bg, colored double-stripe top per line */
.line-flag.line-liberty    { background: #FFFFFF; color: #1C3F94; border-top: 6px double #5D6061; }
.line-flag.line-lioness    { background: #FFFFFF; color: #1C3F94; border-top: 6px double #FAA61A; }
.line-flag.line-mildmay    { background: #FFFFFF; color: #1C3F94; border-top: 6px double #0077AD; }
.line-flag.line-suffragette{ background: #FFFFFF; color: #1C3F94; border-top: 6px double #5BBD72; }
.line-flag.line-weaver     { background: #FFFFFF; color: #1C3F94; border-top: 6px double #823A62; }
.line-flag.line-windrush   { background: #FFFFFF; color: #1C3F94; border-top: 6px double #ED1B00; }
.line-national-rail   { background: #E21836; color: #FFFFFF; }
.line-flag.blank {
    background: #FFFFFF;
    color: #666;
    border: 2px dashed #333;
    font-style: italic;
}
.branch {
    font-weight: normal;
    font-size: 0.85em;
}
hr.divider {
    border: none;
    border-top: 2px solid #999;
    margin: 12px 0;
}
.line-header { margin-bottom: 12px; }
.sequence { text-align: center; margin: 8px 0; }
.sequence .station-name { font-size: 1.1rem; margin: 4px 0; }
.arrow {
    font-size: 1.4rem;
    color: #999;
    margin: 2px 0;
    line-height: 1;
}
.station-box {
    display: inline-block;
    padding: 8px 20px;
    margin: 4px 0;
    border-radius: 5px;
    font-weight: bold;
    font-size: 1.1rem;
}
.station-box.blank {
    background: #FFFFFF;
    color: #666;
    border: 2px dashed #333;
    font-style: italic;
}
.terminus {
    font-size: 1rem;
    color: #999;
    font-weight: bold;
    letter-spacing: 2px;
    margin: 4px 0;
}
.station-lines { margin-top: 4px; }
"""

# ---------------------------------------------------------------------------
# Anki Note Models
# ---------------------------------------------------------------------------

TYPE1_MODEL = genanki.Model(
    TYPE1_MODEL_ID,
    "London Transport - Which Lines",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "StationName"},
        {"name": "HiddenLines"},
        {"name": "Round"},
    ],
    templates=[{
        "name": "Which Lines",
        "qfmt": "{{Front}}",
        "afmt": "{{Back}}",
    }],
    css=SHARED_CSS,
)

TYPE2_MODEL = genanki.Model(
    TYPE2_MODEL_ID,
    "London Transport - Station Sequence",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "LineName"},
        {"name": "BranchName"},
        {"name": "AnswerStation"},
    ],
    templates=[{
        "name": "Station Sequence",
        "qfmt": "{{Front}}",
        "afmt": "{{Back}}",
    }],
    css=SHARED_CSS,
)

TYPE3_MODEL_ID = _stable_id("LondonTransport_Type3_v1")
TYPE3_MODEL = genanki.Model(
    TYPE3_MODEL_ID,
    "London Transport - Which Branch",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "StationName"},
    ],
    templates=[{
        "name": "Which Branch",
        "qfmt": "{{Front}}",
        "afmt": "{{Back}}",
    }],
    css=SHARED_CSS,
)


# ---------------------------------------------------------------------------
# TfL API Fetching (with caching)
# ---------------------------------------------------------------------------

def fetch_json(url, cache_name):
    cache_path = DATA_DIR / f"{cache_name}.json"
    if cache_path.exists():
        print(f"  [cache] {cache_name}")
        with open(cache_path) as f:
            return json.load(f)
    print(f"  [fetch] {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)
    time.sleep(1.5)
    return data


def fetch_all_lines():
    url = f"{TFL_BASE}/Line/Mode/tube,overground,dlr,elizabeth-line"
    return [l["id"] for l in fetch_json(url, "all_lines")]


def fetch_stop_points(line_id):
    url = f"{TFL_BASE}/Line/{line_id}/StopPoints"
    return fetch_json(url, f"stops_{line_id}")


def fetch_route_sequence(line_id, direction="inbound"):
    url = f"{TFL_BASE}/Line/{line_id}/Route/Sequence/{direction}"
    return fetch_json(url, f"route_{line_id}_{direction}")


# ---------------------------------------------------------------------------
# Station name cleaning
# ---------------------------------------------------------------------------

SUFFIXES_TO_STRIP = [
    " Underground Station",
    " DLR Station",
    " Rail Station",
    " (Underground)",
]

def clean_station_name(name):
    for suffix in SUFFIXES_TO_STRIP:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = name.replace("'", "\u2019")
    return name.strip()


# Tube/DLR stations with National Rail interchange, matched by exact clean name.
# The TfL per-line StopPoints endpoint only includes modes for that line, so tube
# stations don't get NR mode even when they're NR interchanges. This curated set
# supplements the API data.
NR_INTERCHANGE_EXACT_NAMES = {
    # Major termini
    "King\u2019s Cross St. Pancras",
    "Waterloo",
    "Victoria",
    "London Euston",
    "London Paddington",
    "London Liverpool Street",
    "London Bridge",
    "Moorgate",
    # Thameslink
    "Farringdon",
    "Blackfriars",
    "Elephant & Castle",
    "Kentish Town",
    "West Hampstead",
    # Other tube/NR interchanges
    "Old Street",
    "Finsbury Park",
    "Tottenham Hale",
    "West Ham",
    "Vauxhall",
    "Wimbledon",
    "Seven Sisters",
    "Lewisham",
    "Greenwich",
    "Kilburn High Road",
    "Queen\u2019s Park",
    "Gunnersbury",
    "Kew Gardens",
    "Ealing Broadway",
    "Richmond",
    "Richmond (London)",
    "Stratford",
    "Stratford (London)",
    "Barking",
    "Upminster",
    "Harrow & Wealdstone",
    "Wembley Central",
    "Willesden Junction",
    "Clapham Junction",
    "Hackney Central",
    "Hackney Downs",
    "Hackney Wick",
    "Homerton",
    "Kensington (Olympia)",
    "West Brompton",
    "Shepherds Bush",  # Shepherd's Bush Overground / NR
    "Kensal Rise",
    "Brondesbury",
    "Brondesbury Park",
    "South Acton",
    "Acton Central",
    "Gospel Oak",
    "Kentish Town West",
    "Highbury & Islington",
    "Charing Cross",
    "Blackhorse Road",
}


def _apply_nr_supplement(stations):
    """Mark stations with NR interchange based on curated exact name set."""
    for nid, sdata in stations.items():
        if sdata["national_rail"]:
            continue
        if sdata["name"] in NR_INTERCHANGE_EXACT_NAMES:
            sdata["national_rail"] = True


# ---------------------------------------------------------------------------
# Build Station Database with Graph-Based Routes
# ---------------------------------------------------------------------------

def build_database():
    """
    Fetch data from TfL API and build:
      stations:      {naptan_id: {name, lines: set, national_rail: bool}}
      line_graph:    {line_id: {nid: {"succ": set, "pred": set}}}
      line_segments: {line_id: [{"stops": [nid, ...], "name": str}, ...]}
    """
    print("Fetching line list...")
    api_line_ids = fetch_all_lines()
    print(f"  Found {len(api_line_ids)} lines: {api_line_ids}")

    stations = {}       # naptan_id -> {name, lines: set, national_rail}
    hub_map = {}        # naptan_id -> hubNaptanCode (for merging cross-mode stations)
    line_graph = {}     # line_id -> {nid: {"succ": set, "pred": set}}
    line_segments = {}  # line_id -> [{"stops": [nid, ...], "name": str}, ...]

    for line_id in LINE_ORDER:
        print(f"\nProcessing line: {LINE_INFO[line_id]['name']} ({line_id})")

        # Fetch stop points for station metadata (names, NR flag, line membership)
        try:
            stops = fetch_stop_points(line_id)
        except Exception as e:
            print(f"  [error] Could not fetch stops for {line_id}: {e}")
            continue

        for stop in stops:
            nid = stop.get("naptanId", stop.get("stationNaptan", stop.get("id", "")))
            if not nid:
                continue
            name = clean_station_name(stop.get("commonName", "Unknown"))
            modes = [m.strip() for m in stop.get("modes", [])]
            has_nr = "national-rail" in modes
            hub = stop.get("hubNaptanCode", "")

            if nid not in stations:
                stations[nid] = {"name": name, "lines": set(), "national_rail": has_nr}
            elif has_nr:
                stations[nid]["national_rail"] = True
            stations[nid]["lines"].add(line_id)

            if hub:
                hub_map[nid] = hub

        # Build directed graph from INBOUND segments only (consistent direction).
        # Also collect raw segments with names for Type 2 branch labeling.
        graph = defaultdict(lambda: {"succ": set(), "pred": set()})
        inbound_segments = []  # list of {"stops": [nid, ...], "name": str}

        for direction in ["inbound", "outbound"]:
            try:
                route_data = fetch_route_sequence(line_id, direction)
            except Exception as e:
                print(f"  [error] Could not fetch {direction} route for {line_id}: {e}")
                continue
            for seq in route_data.get("stopPointSequences", []):
                seg_stops = []
                for sp in seq.get("stopPoint", []):
                    nid = sp.get("id", sp.get("naptanId", ""))
                    if not nid:
                        continue
                    name = clean_station_name(sp.get("name", "Unknown"))
                    if nid not in stations:
                        stations[nid] = {"name": name, "lines": set(), "national_rail": False}
                    stations[nid]["lines"].add(line_id)
                    hub = sp.get("hubNaptanCode", "")
                    if hub:
                        hub_map[nid] = hub
                    seg_stops.append(nid)
                if len(seg_stops) >= 2:
                    if direction == "inbound":
                        seg_name = seq.get("name", "").strip()
                        inbound_segments.append({"stops": seg_stops, "name": seg_name})

        # If no inbound segments, fall back to outbound (reversed)
        if not inbound_segments:
            for direction in ["outbound"]:
                try:
                    route_data = fetch_route_sequence(line_id, direction)
                except Exception:
                    continue
                for seq in route_data.get("stopPointSequences", []):
                    seg_stops = []
                    for sp in seq.get("stopPoint", []):
                        nid = sp.get("id", sp.get("naptanId", ""))
                        if nid:
                            seg_stops.append(nid)
                    if len(seg_stops) >= 2:
                        seg_name = seq.get("name", "").strip()
                        inbound_segments.append({"stops": list(reversed(seg_stops)), "name": seg_name})

        for seg in inbound_segments:
            stops = seg["stops"]
            for i in range(len(stops) - 1):
                a, b = stops[i], stops[i + 1]
                graph[a]["succ"].add(b)
                graph[b]["pred"].add(a)

        # Ensure all stations on this line are in the graph
        for nid, sdata in stations.items():
            if line_id in sdata["lines"] and nid not in graph:
                graph[nid]

        line_graph[line_id] = dict(graph)
        line_segments[line_id] = inbound_segments

        # Stats
        graph_stations = {n for n in graph if graph[n]["succ"] or graph[n]["pred"]}
        print(f"  {len(graph_stations)} stations, {len(inbound_segments)} segments")

    # Merge stations that share a hubNaptanCode (same physical station,
    # different NaPTAN IDs for tube/DLR/overground/Elizabeth platforms)
    stations, line_graph, line_segments = _merge_hub_stations(
        stations, hub_map, line_graph, line_segments)

    # Supplement NR interchange flags
    _apply_nr_supplement(stations)
    nr_count = sum(1 for s in stations.values() if s["national_rail"])
    print(f"\n  National Rail interchanges: {nr_count}")

    # Print summary
    print("\n" + "=" * 60)
    print("DATABASE SUMMARY")
    print("=" * 60)
    print(f"Total unique stations: {len(stations)}")
    for lid in LINE_ORDER:
        if lid in line_segments:
            all_st = set()
            for seg in line_segments[lid]:
                all_st.update(seg["stops"])
            print(f"  {LINE_INFO[lid]['name']:25s}: {len(all_st):3d} stations, {len(line_segments[lid])} segments")

    by_line_count = defaultdict(int)
    for sdata in stations.values():
        by_line_count[len(sdata["lines"])] += 1
    print(f"\nStations by # of lines:")
    for n in sorted(by_line_count):
        print(f"  {n} line(s): {by_line_count[n]} stations")

    return stations, line_graph, line_segments


def _merge_hub_stations(stations, hub_map, line_graph, line_segments):
    """
    Merge stations that share a hubNaptanCode into a single station entry.
    This combines tube/DLR/overground/Elizabeth platforms at the same physical
    station (e.g. Bank tube + Bank DLR → one "Bank" station with all lines).

    Returns updated (stations, line_graph, line_segments) with merged IDs.
    """
    # Group naptanIds by hub
    hub_groups = defaultdict(set)
    for nid, hub in hub_map.items():
        if nid in stations:
            hub_groups[hub].add(nid)

    # Only process hubs with multiple IDs
    multi_hubs = {h: nids for h, nids in hub_groups.items() if len(nids) > 1}
    if not multi_hubs:
        return stations, line_graph, line_segments

    # Build remap: for each hub group, pick a canonical ID and remap all others
    remap = {}  # old_nid -> canonical_nid
    for hub, nids in multi_hubs.items():
        # Prefer tube ID (940GZZLU*), then DLR (940GZZDL*), then rail (910G*)
        sorted_nids = sorted(nids, key=lambda n: (
            0 if n.startswith("940GZZLU") else
            1 if n.startswith("940GZZDL") else
            2
        ))
        canonical = sorted_nids[0]
        for nid in sorted_nids[1:]:
            remap[nid] = canonical

    print(f"\n  Merging {len(remap)} station IDs into {len(multi_hubs)} hubs")

    # Merge station data: combine lines and NR flags into canonical
    for old_nid, canonical_nid in remap.items():
        if old_nid not in stations:
            continue
        old = stations[old_nid]
        if canonical_nid not in stations:
            stations[canonical_nid] = old
        else:
            canon = stations[canonical_nid]
            canon["lines"] |= old["lines"]
            if old["national_rail"]:
                canon["national_rail"] = True
            # Keep the shorter/cleaner name (prefer one without mode suffix)
            if len(old["name"]) < len(canon["name"]):
                canon["name"] = old["name"]
        del stations[old_nid]

    # Remap graph edges
    for line_id, graph in line_graph.items():
        new_graph = defaultdict(lambda: {"succ": set(), "pred": set()})
        for nid, adj in graph.items():
            canon_nid = remap.get(nid, nid)
            for s in adj["succ"]:
                canon_s = remap.get(s, s)
                if canon_s != canon_nid:  # avoid self-loops
                    new_graph[canon_nid]["succ"].add(canon_s)
            for p in adj["pred"]:
                canon_p = remap.get(p, p)
                if canon_p != canon_nid:
                    new_graph[canon_nid]["pred"].add(canon_p)
        # Ensure stations with no edges still appear
        for nid in list(graph.keys()):
            canon_nid = remap.get(nid, nid)
            if canon_nid not in new_graph:
                new_graph[canon_nid]
        line_graph[line_id] = dict(new_graph)

    # Remap segment stop IDs
    for line_id, segments in line_segments.items():
        for seg in segments:
            seg["stops"] = [remap.get(nid, nid) for nid in seg["stops"]]

    return stations, line_graph, line_segments


# ---------------------------------------------------------------------------
# HTML Generation Helpers
# ---------------------------------------------------------------------------

def flag_box_html(line_id, branch_label=None):
    info = LINE_INFO[line_id]
    css_class = f"line-flag line-{line_id}"
    if info["mode"] == "overground":
        css_class += " overground-style"
    content = info["name"]
    if branch_label:
        content += f' <span class="branch">({branch_label})</span>'
    return f'<div class="{css_class}">{content}</div>'


def blank_box_html():
    return '<div class="line-flag blank">?</div>'


def national_rail_html():
    return '<div class="line-flag line-national-rail">\u21d4 National Rail</div>'


CANONICAL_LINE_ORDER = [
    "northern", "victoria", "jubilee", "central", "piccadilly",
    "bakerloo", "metropolitan", "circle", "district", "hammersmith-city",
    "waterloo-city", "dlr", "elizabeth",
    "liberty", "lioness", "mildmay", "suffragette", "weaver", "windrush",
]


def sorted_lines_for_station(line_ids):
    order_map = {lid: i for i, lid in enumerate(CANONICAL_LINE_ORDER)}
    return sorted(line_ids, key=lambda x: order_map.get(x, 999))


# ---------------------------------------------------------------------------
# Card Generation: Type 1 — "Lines"
# ---------------------------------------------------------------------------

def generate_type1_cards(stations):
    """
    Generate Type 1 ("Lines") cards. Given a station with some lines hidden,
    recall the missing ones. All cards in a shared deck, randomly ordered
    within each round so the hidden line can't be predicted.
    """
    line_order_map = {lid: i for i, lid in enumerate(LINE_ORDER)}

    # Collect cards with sort keys
    raw_cards = []  # (sort_key, subdeck, note)

    for nid, sdata in stations.items():
        line_ids = sorted_lines_for_station(list(sdata["lines"]))
        n_lines = len(line_ids)
        has_nr = sdata["national_rail"]
        station_name = sdata["name"]

        if n_lines == 0:
            continue

        # Curriculum position: earliest line this station is on
        station_order = min(line_order_map.get(l, 999) for l in line_ids)

        # Round 1: hide 1 line at a time
        for hidden_line in line_ids:
            visible = [l for l in line_ids if l != hidden_line]
            front_html = _type1_front_html(station_name, visible, 1, has_nr)
            back_html = _type1_back_html(station_name, visible, [hidden_line], has_nr)

            subdeck = "London Transport::1 Lines::1 Missing"
            # Sort: by hidden line's curriculum position, then station name
            sort_key = (1, line_order_map.get(hidden_line, 999), station_name)

            note = genanki.Note(
                model=TYPE1_MODEL,
                fields=[front_html, back_html, station_name, hidden_line, "1"],
                guid=genanki.guid_for(f"t1_r1_{nid}_{hidden_line}"),
            )
            raw_cards.append((sort_key, subdeck, note))

        if n_lines == 1:
            continue

        # "Hide all" card for stations with 2+ lines
        front_html = _type1_front_html(station_name, [], n_lines, has_nr)
        back_html = _type1_back_html(station_name, [], line_ids, has_nr)
        subdeck = "London Transport::1 Lines::All Missing"
        sort_key = (99, station_order, station_name)
        note = genanki.Note(
            model=TYPE1_MODEL,
            fields=[front_html, back_html, station_name, "all", "all"],
            guid=genanki.guid_for(f"t1_rall_{nid}"),
        )
        raw_cards.append((sort_key, subdeck, note))

        # Rounds 2..N-1: hide k lines
        for k in range(2, n_lines):
            for hidden_combo in combinations(line_ids, k):
                visible = [l for l in line_ids if l not in hidden_combo]
                front_html = _type1_front_html(station_name, visible, k, has_nr)
                back_html = _type1_back_html(
                    station_name, visible, list(hidden_combo), has_nr)

                subdeck = f"London Transport::1 Lines::{k} Missing"
                # Sort by earliest hidden line, then station
                earliest_hidden = min(line_order_map.get(l, 999) for l in hidden_combo)
                sort_key = (k, earliest_hidden, station_name)
                combo_key = "_".join(sorted(hidden_combo))
                note = genanki.Note(
                    model=TYPE1_MODEL,
                    fields=[front_html, back_html, station_name, combo_key, str(k)],
                    guid=genanki.guid_for(f"t1_r{k}_{nid}_{combo_key}"),
                )
                raw_cards.append((sort_key, subdeck, note))

    # Shuffle within each round (sort key's first element is the round)
    random.seed(42)  # deterministic shuffle for reproducible builds
    random.shuffle(raw_cards)
    # Stable sort by round only — keeps random order within each round
    raw_cards.sort(key=lambda x: x[0][0])
    return [(subdeck, note) for _, subdeck, note in raw_cards]


def _type1_front_html(station_name, visible_lines, num_hidden, has_nr):
    parts = [f'<div class="station-name">{station_name}</div>']
    if visible_lines or has_nr:
        parts.append('<div class="lines-given">')
        for lid in visible_lines:
            parts.append(flag_box_html(lid))
        if has_nr:
            parts.append(national_rail_html())
        parts.append('</div>')
    parts.append('<hr class="divider">')
    parts.append('<div class="lines-blank">')
    for _ in range(num_hidden):
        parts.append(blank_box_html())
    parts.append('</div>')
    return "\n".join(parts)


def _type1_back_html(station_name, visible_lines, hidden_lines, has_nr):
    parts = [f'<div class="station-name">{station_name}</div>']
    if visible_lines or has_nr:
        parts.append('<div class="lines-given">')
        for lid in visible_lines:
            parts.append(flag_box_html(lid))
        if has_nr:
            parts.append(national_rail_html())
        parts.append('</div>')
    parts.append('<hr class="divider">')
    parts.append('<div class="lines-answer">')
    for lid in hidden_lines:
        parts.append(flag_box_html(lid))
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Card Generation: Type 2 — "Station Sequence"
# ---------------------------------------------------------------------------

def generate_type2_cards(stations, line_graph, line_segments):
    """
    Generate Type 2 ("Sequence") cards from raw API segments. Each segment is
    one branch section with correct neighbor context. At segment boundaries,
    stitch to connecting segments. Branch labels shown only at ambiguous
    branch points where prev/next don't uniquely identify the route.
    """
    cards = []
    seen = set()

    for line_id in LINE_ORDER:
        segments = line_segments.get(line_id, [])
        graph = line_graph.get(line_id, {})
        if not segments:
            continue
        line_name = LINE_INFO[line_id]["name"]
        subdeck = f"London Transport::2 Sequence::{line_name}"
        has_branches = len(segments) > 1

        # Build segment connection map: which segments connect at endpoints
        # seg_end -> list of (seg_idx, position_in_that_seg) for stitching
        end_to_seg = defaultdict(list)  # nid -> [(seg_idx, "first"/"last")]
        for si, seg in enumerate(segments):
            stops = seg["stops"]
            end_to_seg[stops[0]].append((si, "first"))
            end_to_seg[stops[-1]].append((si, "last"))

        for si, seg in enumerate(segments):
            stops = seg["stops"]
            if len(stops) < 2:
                continue

            # Derive canonical branch label from segment stations.
            # Shared trunk sections (no unique branch stations) get no label.
            branch_label = _label_segment(line_id, stops, stations)

            for i, nid in enumerate(stops):
                sdata = stations.get(nid)
                if not sdata:
                    continue

                # Previous station
                if i > 0:
                    prev_nid = stops[i - 1]
                else:
                    # First station in segment — stitch to connecting segment
                    prev_nid = _find_stitched_neighbor(
                        nid, si, "before", segments, end_to_seg, graph)

                # Next station
                if i < len(stops) - 1:
                    next_nid = stops[i + 1]
                else:
                    # Last station in segment — stitch to connecting segment
                    next_nid = _find_stitched_neighbor(
                        nid, si, "after", segments, end_to_seg, graph)

                dedup_key = (line_id,
                             prev_nid or "TERMINUS",
                             nid,
                             next_nid or "TERMINUS")
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                prev_name = stations[prev_nid]["name"] if prev_nid and prev_nid in stations else None
                next_name = stations[next_nid]["name"] if next_nid and next_nid in stations else None
                answer_name = sdata["name"]

                # Only show branch label when the context is ambiguous:
                # prev, target, or next is at a branch point (degree > 1).
                card_label = None
                if branch_label:
                    target_adj = graph.get(nid, {})
                    prev_succs = len(graph.get(prev_nid, {}).get("succ", set())) if prev_nid else 0
                    next_preds = len(graph.get(next_nid, {}).get("pred", set())) if next_nid else 0
                    target_preds = len(target_adj.get("pred", set()))
                    target_succs = len(target_adj.get("succ", set()))
                    if prev_succs > 1 or next_preds > 1 or target_preds > 1 or target_succs > 1:
                        card_label = branch_label

                front_html = _type2_front_html(line_id, card_label, prev_name, next_name)
                back_html = _type2_back_html(
                    line_id, card_label, prev_name, next_name,
                    answer_name, sdata, stations
                )

                guid_key = f"t2_{line_id}_{prev_nid or 'T'}_{nid}_{next_nid or 'T'}"
                note = genanki.Note(
                    model=TYPE2_MODEL,
                    fields=[front_html, back_html, line_name, branch_label or "", answer_name],
                    guid=genanki.guid_for(guid_key),
                )
                cards.append((subdeck, note))

    return cards


def _find_stitched_neighbor(nid, seg_idx, direction, segments, end_to_seg, graph):
    """
    At a segment boundary, find the neighbor from a connecting segment.

    For direction="before": nid is the first station of seg_idx.
    Look for another segment whose last station == nid, and return
    that segment's second-to-last station.

    For direction="after": nid is the last station of seg_idx.
    Look for another segment whose first station == nid, and return
    that segment's second station.

    Falls back to the graph adjacency if no connecting segment found.
    Returns None for true termini.
    """
    connections = end_to_seg.get(nid, [])

    if direction == "before":
        # Find a segment that ENDS at nid (and isn't our own segment)
        for other_idx, pos in connections:
            if other_idx != seg_idx and pos == "last":
                other_stops = segments[other_idx]["stops"]
                if len(other_stops) >= 2:
                    return other_stops[-2]  # second-to-last
        # Fall back to graph predecessor
        preds = graph.get(nid, {}).get("pred", set())
        seg_stops = set(segments[seg_idx]["stops"])
        external_preds = preds - seg_stops
        if external_preds:
            return sorted(external_preds)[0]
        return None  # true terminus

    else:  # direction == "after"
        # Find a segment that STARTS at nid (and isn't our own segment)
        for other_idx, pos in connections:
            if other_idx != seg_idx and pos == "first":
                other_stops = segments[other_idx]["stops"]
                if len(other_stops) >= 2:
                    return other_stops[1]  # second station
        # Fall back to graph successor
        succs = graph.get(nid, {}).get("succ", set())
        seg_stops = set(segments[seg_idx]["stops"])
        external_succs = succs - seg_stops
        if external_succs:
            return sorted(external_succs)[0]
        return None  # true terminus


# ---------------------------------------------------------------------------
# Card Generation: Type 3 — "Which Branch?"
# ---------------------------------------------------------------------------

def generate_type3_cards(stations, line_segments):
    """
    Generate Type 3 cards for stations on branch-specific sections.
    Front: station name + "Which line & branch?"
    Back: line flag boxes with branch labels for each branch the station is on.

    Only generates cards for stations that appear on at least one named branch
    (not shared trunk sections).
    """
    cards = []

    # Build mapping: station nid -> set of (line_id, branch_label)
    station_branches = defaultdict(set)
    for line_id in LINE_ORDER:
        for seg in line_segments.get(line_id, []):
            branch_label = _label_segment(line_id, seg["stops"], stations)
            if not branch_label:
                continue  # skip shared trunk sections
            for nid in seg["stops"]:
                station_branches[nid].add((line_id, branch_label))

    # Generate one card per station that has branch info
    for nid, branches in sorted(station_branches.items(),
                                 key=lambda x: stations.get(x[0], {}).get("name", "")):
        sdata = stations.get(nid)
        if not sdata:
            continue
        station_name = sdata["name"]

        # Group branches by line for display
        line_to_branches = defaultdict(list)
        for line_id, branch_label in sorted(branches,
                key=lambda x: CANONICAL_LINE_ORDER.index(x[0]) if x[0] in CANONICAL_LINE_ORDER else 999):
            line_to_branches[line_id].append(branch_label)

        # Front: station name + prompt
        front_parts = [f'<div class="station-name">{station_name}</div>']
        front_parts.append('<div class="lines-blank">')
        front_parts.append('<div class="line-flag blank">Which line &amp; branch?</div>')
        front_parts.append('</div>')
        front_html = "\n".join(front_parts)

        # Back: station name + line flag boxes with branch labels
        back_parts = [f'<div class="station-name">{station_name}</div>']
        back_parts.append('<div class="lines-answer">')
        for line_id, branch_labels in line_to_branches.items():
            for bl in branch_labels:
                back_parts.append(flag_box_html(line_id, bl))
        back_parts.append('</div>')
        back_html = "\n".join(back_parts)

        subdeck = "London Transport::3 Branch"
        note = genanki.Note(
            model=TYPE3_MODEL,
            fields=[front_html, back_html, station_name],
            guid=genanki.guid_for(f"t3_{nid}"),
        )
        cards.append((subdeck, note))

    return cards


def _type2_front_html(line_id, branch_label, prev_name, next_name):
    parts = ['<div class="line-header">']
    parts.append(flag_box_html(line_id, branch_label))
    parts.append('</div>')
    parts.append('<div class="sequence">')
    if prev_name is None:
        parts.append('<div class="terminus">\u2550 TERMINUS \u2550</div>')
    else:
        parts.append(f'<div class="station-name prev">{prev_name}</div>')
    parts.append('<div class="arrow">\u25bc</div>')
    parts.append('<div class="station-box blank">?</div>')
    parts.append('<div class="arrow">\u25bc</div>')
    if next_name is None:
        parts.append('<div class="terminus">\u2550 TERMINUS \u2550</div>')
    else:
        parts.append(f'<div class="station-name next">{next_name}</div>')
    parts.append('</div>')
    return "\n".join(parts)


def _type2_back_html(line_id, branch_label, prev_name, next_name,
                     answer_name, answer_station_data, all_stations):
    parts = ['<div class="line-header">']
    parts.append(flag_box_html(line_id, branch_label))
    parts.append('</div>')
    parts.append('<div class="sequence">')
    if prev_name is None:
        parts.append('<div class="terminus">\u2550 TERMINUS \u2550</div>')
    else:
        parts.append(f'<div class="station-name prev">{prev_name}</div>')
    parts.append('<div class="arrow">\u25bc</div>')

    # Answer station name (plain text, same style as prev/next) + its line list
    parts.append(f'<div class="station-name">{answer_name}</div>')
    parts.append('<div class="station-lines">')
    station_lines = sorted_lines_for_station(list(answer_station_data["lines"]))
    for lid in station_lines:
        parts.append(flag_box_html(lid))
    if answer_station_data.get("national_rail"):
        parts.append(national_rail_html())
    parts.append('</div>')

    parts.append('<div class="arrow">\u25bc</div>')
    if next_name is None:
        parts.append('<div class="terminus">\u2550 TERMINUS \u2550</div>')
    else:
        parts.append(f'<div class="station-name next">{next_name}</div>')
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Deck Assembly
# ---------------------------------------------------------------------------

def build_deck(type1_cards, type2_cards, type3_cards):
    decks = {}

    def get_deck(path):
        if path not in decks:
            deck_id = _stable_id(f"deck_{path}") % (2**31)
            decks[path] = genanki.Deck(deck_id, path)
        return decks[path]

    all_cards = type1_cards + type2_cards + type3_cards
    for subdeck, note in all_cards:
        get_deck(subdeck).add_note(note)

    # Log counts
    print("\n" + "=" * 60)
    print("CARD GENERATION SUMMARY")
    print("=" * 60)
    deck_counts = defaultdict(int)
    for subdeck, _ in all_cards:
        deck_counts[subdeck] += 1

    total = 0
    for path in sorted(deck_counts):
        count = deck_counts[path]
        total += count
        depth = path.count("::")
        indent = "  " * depth
        short = path.split("::")[-1]
        print(f"  {indent}{short}: {count}")
    print(f"\n  TOTAL CARDS: {total}")

    pkg = genanki.Package(list(decks.values()))
    output_path = Path(__file__).parent / "london_transport.apkg"
    pkg.write_to_file(str(output_path))
    print(f"\nExported to: {output_path}")
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("LONDON TRANSPORT ANKI DECK GENERATOR")
    print("=" * 60)

    print("\n--- STEP 1: Fetching data from TfL API ---")
    stations, line_graph, line_segments = build_database()

    print("\n--- STEP 2: Generating Lines cards ---")
    type1_cards = generate_type1_cards(stations)
    print(f"  Generated {len(type1_cards)} cards")

    print("\n--- STEP 3: Generating Sequence cards ---")
    type2_cards = generate_type2_cards(stations, line_graph, line_segments)
    print(f"  Generated {len(type2_cards)} cards")

    print("\n--- STEP 4: Generating Branch cards ---")
    type3_cards = generate_type3_cards(stations, line_segments)
    print(f"  Generated {len(type3_cards)} cards")

    print("\n--- STEP 5: Building Anki deck ---")
    total = build_deck(type1_cards, type2_cards, type3_cards)

    print("\nDone!")
    return total


if __name__ == "__main__":
    main()
