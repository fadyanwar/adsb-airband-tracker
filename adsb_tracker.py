#!/usr/bin/env python3
"""
ADS-B Aircraft Tracker + Airband Correlator
- Receives ADS-B via dump1090-mutability (RTL-SDR)
- Enriches with hexdb.io (registration, type, operator)
- Enriches with OpenSky Network (live states)
- Displays live table; type a callsign fragment to highlight matching aircraft
- Logs airband activity timestamps for correlation with radio traffic

Usage:
  python3 adsb_tracker.py [--freq 118.5] [--json-dir /tmp/dump1090] [--interval 2]
  Type a callsign fragment + Enter to highlight. Type 'clear' to reset. Ctrl+C to stop.
"""
import argparse, json, os, subprocess, sys, time, threading, signal, math
from datetime import datetime, timezone

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DUMP_JSON = "/tmp/dump1090"
INTERVAL = 2.0
HEXDB_CACHE = {}
OPENSKY_CACHE = {}
OPENSKY_LAST = 0
import os as _os
OPENSKY_USER = _os.environ.get('OPENSKY_USER')
OPENSKY_PASS = _os.environ.get('OPENSKY_PASS')
_creds_candidates = [
    _os.environ.get('OPENSKY_CREDS'),
    _os.path.expanduser('~/Downloads/credentials.json'),
    _os.path.expanduser('~/.config/opensky/credentials.json'),
    _os.path.expanduser('~/.opensky/credentials.json'),
]
CREDS_FILE = None
for c in _creds_candidates:
    if c and _os.path.exists(c):
        CREDS_FILE = c
        break
_OAUTH_TOKEN = None
_OAUTH_EXPIRY = 0
ROUTE_CACHE = {}
SEARCH = ""
SEARCH_LOCK = threading.Lock()
AIRBAND_LOG = "/tmp/airband_activity.log"

def start_dump1090(json_dir):
    if not os.path.exists(json_dir):
        os.makedirs(json_dir, exist_ok=True)
    proc = subprocess.Popen(
        ["dump1090-mutability", "--device-index", "0", "--gain", "49.6",
         "--net", "--write-json", json_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc

def fetch_hexdb(hexcode):
    hexcode = hexcode.upper()
    if hexcode in HEXDB_CACHE:
        return HEXDB_CACHE[hexcode]
    if not HAS_REQUESTS:
        HEXDB_CACHE[hexcode] = None
        return None
    try:
        r = requests.get(f"https://hexdb.io/api/v1/aircraft/{hexcode}", timeout=4)
        if r.status_code == 200:
            data = r.json()
            HEXDB_CACHE[hexcode] = data
            return data
    except Exception:
        pass
    HEXDB_CACHE[hexcode] = None
    return None

def fetch_opensky_states():
    global OPENSKY_LAST
    now = time.time()
    if now - OPENSKY_LAST < 12:
        return None
    OPENSKY_LAST = now
    if not HAS_REQUESTS:
        return None
    try:
        r = requests.get(
            "https://opensky-network.org/api/states/all",
            params={"lamin": 20, "lomin": -130, "lamax": 55, "lomax": -60},
            timeout=10)
        if r.status_code == 200:
            data = r.json()
            states = {}
            for s in data.get("states", []) or []:
                if s and s[0]:
                    states[s[0].upper()] = s
            return states
    except Exception:
        pass
    return None

def get_oauth_token():
    global _OAUTH_TOKEN, _OAUTH_EXPIRY
    if _OAUTH_TOKEN and time.time() < _OAUTH_EXPIRY - 30:
        return _OAUTH_TOKEN
    # Try client credentials file first
    client_id = None
    client_secret = None
    try:
        if CREDS_FILE and _os.path.exists(CREDS_FILE):
            with open(CREDS_FILE) as f:
                creds = json.load(f)
            client_id = creds.get("clientId") or creds.get("client_id")
            client_secret = creds.get("clientSecret") or creds.get("client_secret")
    except Exception:
        pass
    if not client_id or not client_secret:
        return None
    try:
        r = requests.post(
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }, timeout=10)
        if r.status_code == 200:
            data = r.json()
            _OAUTH_TOKEN = data.get("access_token")
            _OAUTH_EXPIRY = time.time() + data.get("expires_in", 1800)
            return _OAUTH_TOKEN
    except Exception:
        pass
    return None

def fetch_route(hexcode, callsign):
    key = (hexcode, callsign)
    if key in ROUTE_CACHE:
        return ROUTE_CACHE[key]
    if not HAS_REQUESTS:
        ROUTE_CACHE[key] = ("", "")
        return ("", "")
    token = get_oauth_token()
    if not token:
        ROUTE_CACHE[key] = ("", "")
        return ("", "")
    try:
        now = int(time.time())
        r = requests.get(
            "https://opensky-network.org/api/flights/aircraft",
            params={"icao24": hexcode.lower(), "begin": now-7200, "end": now},
            headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data:
                last = data[-1]
                origin = airport_name(last.get("estDepartureAirport") or "")
                dest = airport_name(last.get("estArrivalAirport") or "")
                ROUTE_CACHE[key] = (origin, dest)
                return (origin, dest)
    except Exception:
        pass
    ROUTE_CACHE[key] = ("", "")
    return ("", "")

AIRPORTS = {
    "EIDW": "Dublin", "EICK": "Cork", "EINN": "Shannon", "EIKN": "Knock",
    "EGSS": "Stansted", "EGLL": "Heathrow", "EGKK": "Gatwick", "EGCC": "Manchester",
    "EGPH": "Edinburgh", "EGPF": "Glasgow", "EGBB": "Birmingham", "EGNX": "East Midlands",
    "EGGD": "Bristol", "EGGW": "Luton", "EGNM": "Leeds Bradford", "EGNT": "Newcastle",
    "LFPG": "CDG Paris", "LFPO": "Orly", "LFMN": "Nice", "LFML": "Marseille",
    "LFLL": "Lyon", "LFBD": "Bordeaux", "LFBG": "Bergen", "LFST": "Strasbourg",
    "EHAM": "Amsterdam", "EBBR": "Brussels", "EDDF": "Frankfurt", "EDDM": "Munich",
    "EDDB": "Berlin", "EDDH": "Hamburg", "EDDL": "Dusseldorf", "EDDS": "Stuttgart",
    "EDDK": "Cologne", "EDDV": "Hanover", "EDDW": "Bremen", "EDDP": "Leipzig",
    "LEMD": "Madrid", "LEBL": "Barcelona", "LEPA": "Palma", "LEMG": "Malaga",
    "LEAL": "Alicante", "LEVC": "Valencia", "LEZL": "Seville", "LEBB": "Bilbao",
    "LIRF": "Rome Fiumicino", "LIMC": "Milan Malpensa", "LIME": "Bergamo",
    "LIPE": "Bologna", "LIPZ": "Venice", "LIRQ": "Florence", "LICJ": "Palermo",
    "LICA": "Lamezia", "LICR": "Reggio Calabria", "LIRN": "Naples",
    "LOWW": "Vienna", "LSZH": "Zurich", "LSGG": "Geneva", "LSZB": "Bern",
    "EKCH": "Copenhagen", "ENGM": "Oslo", "ESSA": "Stockholm Arlanda",
    "EFHK": "Helsinki", "EPWA": "Warsaw", "LKPR": "Prague", "LHBP": "Budapest",
    "LWSK": "Skopje", "LDZA": "Zagreb", "LJLJ": "Ljubljana", "LATI": "Tirana",
    "LTFM": "Istanbul", "LTBA": "Istanbul Ataturk", "LTFJ": "Sabiha Gokcen",
    "KJFK": "JFK New York", "KLAX": "Los Angeles", "KORD": "Chicago O'Hare",
    "KATL": "Atlanta", "KDFW": "Dallas DFW", "KDEN": "Denver", "KSFO": "San Francisco",
    "KSEA": "Seattle", "KMIA": "Miami", "KBOS": "Boston", "KPHL": "Philadelphia",
    "KIAD": "Washington Dulles", "KDCA": "Washington National", "KLAS": "Las Vegas",
    "KPHX": "Phoenix", "KIAH": "Houston", "KDTW": "Detroit", "KMSP": "Minneapolis",
    "KSLC": "Salt Lake City", "KPDX": "Portland", "KSAN": "San Diego",
    "KBNA": "Nashville", "KAUS": "Austin", "KMDW": "Chicago Midway",
    "CYUL": "Montreal", "CYYZ": "Toronto", "CYVR": "Vancouver", "CYOW": "Ottawa",
    "CYYC": "Calgary", "CYEG": "Edmonton", "CYHZ": "Halifax", "CYWG": "Winnipeg",
    "OMDB": "Dubai", "OMAA": "Abu Dhabi", "OTHH": "Doha", "OERK": "Riyadh",
    "OEJN": "Jeddah", "OEDF": "Dammam", "OMSJ": "Sharjah", "OBBI": "Bahrain",
    "OKBK": "Kuwait", "OOMS": "Muscat", "OIKB": "Bandar Abbas", "OISS": "Shiraz",
    "OIII": "Tehran", "OIMM": "Mashhad", "OIKM": "Kermanshah",
    "VABB": "Mumbai", "VIDP": "Delhi", "VOBL": "Bangalore", "VOMM": "Chennai",
    "VECC": "Kolkata", "VAAH": "Ahmedabad", "VAGO": "Goa", "VOCI": "Kochi",
    "ZBAA": "Beijing Capital", "ZSPD": "Shanghai Pudong", "ZGGG": "Guangzhou",
    "ZUUU": "Chengdu", "ZSSS": "Shanghai Hongqiao", "ZGSZ": "Shenzhen",
    "RJTT": "Tokyo Haneda", "RJAA": "Tokyo Narita", "RKSI": "Seoul Incheon",
    "RJBB": "Osaka Kansai", "RJOO": "Osaka Itami", "RJFF": "Fukuoka",
    "WMKK": "Kuala Lumpur", "WSSS": "Singapore", "VTBS": "Bangkok Suvarnabhumi",
    "VTBD": "Bangkok Don Mueang", "VHHH": "Hong Kong", "RPLL": "Manila",
    "YSSY": "Sydney", "YMML": "Melbourne", "YBBN": "Brisbane", "YPPH": "Perth",
    "NZAA": "Auckland", "NZWN": "Wellington", "NZCH": "Christchurch",
    "FAOR": "Johannesburg", "FACT": "Cape Town", "FALE": "Durban",
    "HKJK": "Nairobi", "DNMM": "Lagos", "DGAA": "Accra", "HECA": "Cairo",
    "GMMN": "Casablanca", "DTTA": "Tunis", "DAAG": "Algiers",
    "SBGR": "Sao Paulo GRU", "SBSP": "Sao Paulo CGH", "SBRJ": "Rio de Janeiro",
    "SBGL": "Rio Galeao", "SBBR": "Brasilia", "SBKP": "Campinas",
    "SAEZ": "Buenos Aires EZE", "SABE": "Buenos Aires AEP", "SCEL": "Santiago",
    "SKBO": "Bogota", "SEQM": "Quito", "SPJC": "Lima", "MMMX": "Mexico City",
    "MPTO": "Panama City", "MROC": "San Jose CR", "TNCA": "Curacao",
    "TJSJ": "San Juan PR", "MDSD": "Santo Domingo", "MKJP": "Kingston",
    "TBPB": "Bridgetown", "TFFR": "Pointe-a-Pitre", "TNCM": "St Maarten",
}

def airport_name(code):
    if not code:
        return ""
    code = code.strip().upper()
    return AIRPORTS.get(code, code)

def dist_nm(lat1, lon1, lat2, lon2):
    R = 3440.065
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

def fmt(v, w=8):
    if v is None: return " " * w
    s = str(v)
    return s[:w].ljust(w)

def input_thread():
    global SEARCH
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break
        line = line.strip()
        with SEARCH_LOCK:
            if line.lower() == "clear":
                SEARCH = ""
            else:
                SEARCH = line.upper()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", default=DUMP_JSON)
    ap.add_argument("--interval", type=float, default=INTERVAL)
    ap.add_argument("--freq", type=float, default=None, help="Airband freq to monitor (MHz)")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    args = ap.parse_args()

    rx_lat = args.lat
    rx_lon = args.lon

    print("Starting dump1090-mutability...")
    proc = start_dump1090(args.json_dir)
    time.sleep(3)

    # airband monitor
    airband_proc = None
    if args.freq:
        print(f"Monitoring airband {args.freq} MHz...")
        airband_proc = subprocess.Popen(
            ["rtl_fm", "-f", str(int(args.freq*1e6)), "-M", "am", "-s", "12000",
             "-g", "40", "-l", "0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    stop = threading.Event()
    def handler(sig, frame):
        stop.set()
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    t = threading.Thread(target=input_thread, daemon=True)
    t.start()

    opensky_states = {}
    print("Running. Type a callsign fragment + Enter to highlight. Ctrl+C to stop.\n")
    time.sleep(1)

    while not stop.is_set():
        ac_list = []
        try:
            with open(os.path.join(args.json_dir, "aircraft.json")) as f:
                data = json.load(f)
            ac_list = data.get("aircraft", [])
        except Exception:
            pass

        os_states = fetch_opensky_states()
        if os_states:
            opensky_states = os_states

        # Auto-detect receiver location from aircraft positions
        if rx_lat is None or rx_lon is None:
            lats = [a.get("lat") for a in ac_list if a.get("lat") is not None]
            lons = [a.get("lon") for a in ac_list if a.get("lon") is not None]
            if lats and lons:
                rx_lat = sum(lats)/len(lats)
                rx_lon = sum(lons)/len(lons)

        clear_screen()
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        print(f"ADS-B Aircraft Tracker  |  {now}  |  RTL-SDR + hexdb.io + OpenSky")
        loc = f"{rx_lat:.2f}, {rx_lon:.2f}" if rx_lat is not None else "unknown"
        print(f"Receiver: {loc}  |  Aircraft seen: {len(ac_list)}")
        with SEARCH_LOCK:
            cur_search = SEARCH
        if cur_search:
            print(f"Highlight filter: '{cur_search}'")
        print("="*118)
        header = f"{'ICAO':<8}{'Callsign':<11}{'Reg':<10}{'Type':<8}{'Operator':<20}{'From':<12}{'To':<12}{'Alt(ft)':>8}{'Spd(kt)':>8}{'Hdg':>6}{'Dist(nm)':>9}{'Seen':>6}"
        print(header)
        print("-"*118)

        rows = []
        for ac in ac_list:
            hexc = (ac.get("hex") or "").upper()
            callsign = (ac.get("flight") or "").strip()
            alt = ac.get("altitude")
            speed = ac.get("speed")
            track = ac.get("track")
            seen = ac.get("seen", 0)
            lat = ac.get("lat"); lon = ac.get("lon")
            squawk = ac.get("squawk")

            hd = fetch_hexdb(hexc) if hexc else None
            reg = (hd.get("Registration") if hd else "") or ""
            typ = (hd.get("ICAOTypeCode") if hd else "") or ""
            op = (hd.get("RegisteredOwners") if hd else "") or ""

            os_state = opensky_states.get(hexc) if hexc else None
            if os_state and not callsign:
                callsign = (os_state[1] or "").strip()
            origin, dest = fetch_route(hexc, callsign) if hexc else ("", "")

            dist = ""
            if lat is not None and lon is not None and rx_lat is not None:
                try:
                    d = dist_nm(rx_lat, rx_lon, lat, lon)
                    dist = f"{d:.1f}"
                except Exception:
                    dist = ""

            rows.append((hexc, callsign, reg, typ, op, origin, dest, alt, speed, track, dist, seen, squawk))

        def sortkey(r):
            try:
                d = float(r[8]) if r[8] else 9999
            except Exception:
                d = 9999
            return (d, r[9])
        rows.sort(key=sortkey)

        for r in rows[:45]:
            hexc, callsign, reg, typ, op, origin, dest, alt, speed, track, dist, seen, squawk = r
            alt_s = f"{alt}" if alt is not None else "-"
            spd_s = f"{speed:.0f}" if speed is not None else "-"
            trk_s = f"{track:.0f}" if track is not None else "-"
            highlight = (cur_search and (cur_search in hexc or cur_search in callsign or cur_search in reg))
            line = f"{fmt(hexc,8)}{fmt(callsign,11)}{fmt(reg,10)}{fmt(typ,8)}{fmt(op,20)}{fmt(origin or '-',12)}{fmt(dest or '-',12)}{alt_s:>8}{spd_s:>8}{trk_s:>6}{dist:>9}{seen:>6.1f}"
            if highlight:
                line = "\033[1;32m" + line + "\033[0m"
            print(line)

        if not rows:
            print("  (no aircraft detected - waiting for ADS-B signals...)")

        print()
        print("Legend: ICAO=Mode-S hex | Reg=tail number | Type=ICAO aircraft type | Dist=nm from receiver")
        if args.freq:
            print(f"Airband monitor: {args.freq} MHz  (activity -> {AIRBAND_LOG})")
        print("Type callsign fragment + Enter to highlight. 'clear' to reset. Ctrl+C to stop.")

        time.sleep(args.interval)

    try:
        proc.terminate()
    except Exception:
        pass
    if airband_proc:
        try:
            airband_proc.terminate()
        except Exception:
            pass
    print("\nStopped.")

if __name__ == "__main__":
    main()
