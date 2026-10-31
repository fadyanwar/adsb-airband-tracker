# ADS-B Aircraft Tracker + Airband Correlator

A receive-only tool that decodes ADS-B signals from an RTL-SDR via `dump1090-mutability`, enriches each aircraft with online metadata, and displays a live table in the terminal. Type a callsign fragment you hear on airband to highlight the matching aircraft for correlation.

## Requirements

### Hardware
- **RTL-SDR dongle** (e.g. Nooelec NESDR SMArt v5 or any RTL2832U-based receiver)
- **1090 MHz antenna** recommended for ADS-B. The default RTL-SDR dipole antenna works but range is limited (typically 50-150 nm). A dedicated 1090 MHz antenna significantly improves reception.
- USB port (the SDR draws ~300mA)

### Software
- `dump1090-mutability` (`sudo apt install dump1090-mutability`)
- Python 3.9+ with `requests` (`pip install requests`)
- Optional: `rtl_fm` (included with `rtl-sdr` package) for airband monitoring

## Design

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  RTL-SDR    │────▶│ dump1090-mut.    │────▶│ aircraft.json│
│  (1090 MHz) │     │ (ADS-B decoder)  │     │ (JSON poll)  │
└─────────────┘     └──────────────────┘     └──────┬───────┘
                                                    │
                                                    ▼
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  hexdb.io   │────▶│  Enrichment      │────▶│  Live Table  │
│  (reg/type) │     │  (cached)        │     │  (terminal)  │
└─────────────┘     └──────────────────┘     └──────────────┘
┌─────────────┐     ┌──────────────────┐
│  OpenSky    │────▶│  Route (opt.)    │
│  (from/to)  │     │  (env creds)     │
└─────────────┘     └──────────────────┘
```

- **dump1090-mutability** runs as a subprocess and writes aircraft data to JSON files every second.
- The Python script polls `aircraft.json` at a configurable interval.
- Each aircraft's ICAO hex is looked up on **hexdb.io** for registration, type code, and registered owner/operator (cached in memory).
- If `OPENSKY_USER` and `OPENSKY_PASS` environment variables are set, the script queries OpenSky Network's flights endpoint for origin/destination airports.
- An optional airband monitor (`rtl_fm`) runs in parallel for activity correlation; the user types a callsign fragment to highlight matching aircraft.

## Installation

```bash
cd adsb_tool
sudo bash install.sh   # or: pkexec bash install.sh
```

This installs the `adsb` command to `/usr/local/bin/adsb`.

## Usage

```bash
adsb [--freq 118.5] [--json-dir /tmp/dump1090] [--interval 2] [--lat 53.4] [--lon -6.2]
```

| Flag | Description |
|------|-------------|
| `--freq` | Airband frequency (MHz) to monitor for activity correlation |
| `--json-dir` | Directory for dump1090 JSON output (default `/tmp/dump1090`) |
| `--interval` | Refresh interval in seconds (default 2) |
| `--lat` / `--lon` | Receiver location (auto-detected from aircraft if omitted) |

While running, type a callsign fragment + Enter to highlight matching aircraft. Type `clear` to reset. Press Ctrl+C to stop.

## Sample Output

```
ADS-B Aircraft Tracker  |  22:26:50 UTC  |  RTL-SDR + hexdb.io + OpenSky
Receiver: 53.37, -6.33  |  Aircraft seen: 5
Highlight filter: 'RYR'
======================================================================================================================
ICAO    Callsign   Reg       Type    Operator            From  To     Alt(ft) Spd(kt)   Hdg Dist(nm)  Seen
----------------------------------------------------------------------------------------------------------------------
4D23FC  RYR9SA     9H-QET    B738    Malta Air           -     -         8550     324    18     13.4   8.4
4CAD10  RYR6JN     EI-HGX    B38M    Ryanair             -     -         6950     345    39     15.9   7.4
4CADFC  RYR58MR    EI-IHP    B38M    Ryanair             -     -        34000     399   217     15.6   0.0
407CF7  DHK051     G-DHLX    B77L    DHL Air             -     -        35000     497   115      8.0   0.0
```

With OpenSky credentials (`OPENSKY_USER`/`OPENSKY_PASS`), the From/To columns populate with ICAO airport codes (e.g. `EIDW` → `EGSS`).

## Notes

- Receive-only. No transmission is performed.
- Aircraft metadata is fetched from hexdb.io (free, no auth required).
- Origin/destination columns require OpenSky Network credentials via environment variables; without them, columns show `-`.
- For best results, use a 1090 MHz-tuned antenna; the default RTL-SDR antenna works but range is limited.
