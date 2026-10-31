# ADS-B Aircraft Tracker + Airband Correlator

A receive-only tool that decodes ADS-B signals from an RTL-SDR via `dump1090-mutability`, enriches each aircraft with online metadata (hexdb.io for registration/type/operator, OpenSky Network for live states), and displays a live table in the terminal. Type a callsign fragment you hear on airband to highlight the matching aircraft for correlation.

## Requirements

- RTL-SDR (e.g. Nooelec NESDR SMArt v5)
- `dump1090-mutability` installed (`sudo apt install dump1090-mutability`)
- Python 3.9+ with `requests` (`pip install requests`)
- Optional: `rtl_fm` for airband monitoring

## Usage

```bash
python3 adsb_tracker.py [--freq 118.5] [--json-dir /tmp/dump1090] [--interval 2] [--lat 53.4] [--lon -6.2]
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
ADS-B Aircraft Tracker  |  22:15:32 UTC  |  RTL-SDR + hexdb.io + OpenSky
Receiver: 53.47, -6.12  |  Aircraft seen: 3
Highlight filter: 'RYR'
======================================================================================================================
ICAO    Callsign   Reg       Type    Operator                 Alt(ft) Spd(kt)   Hdg Dist(nm)  Seen
----------------------------------------------------------------------------------------------------------------------
4CA894  RYR3XZ    EI-DWS    B738    Ryanair                  9425    299     88     12.3    0.2
4CA9D3  RYR449    EI-EKK    B738    Ryanair                   625    137    276     18.7   33.0
4A1265  DNA508    EI-DAA    A320    Aer Lingus              13525    372    100     45.1    7.2

Legend: ICAO=Mode-S hex | Reg=tail number | Type=ICAO aircraft type | Dist=nm from receiver
Airband monitor: 118.5 MHz  (activity -> /tmp/airband_activity.log)
Type callsign fragment + Enter to highlight. 'clear' to reset. Ctrl+C to stop.
```

## Notes

- Receive-only. No transmission is performed.
- Aircraft metadata is fetched from hexdb.io and OpenSky Network (free, rate-limited).
- Distance is calculated from the receiver location (auto-detected or manually set).
- For best results, use a 1090 MHz-tuned antenna; the default RTL-SDR antenna works but range is limited.
