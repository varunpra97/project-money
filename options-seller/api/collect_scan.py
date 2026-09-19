"""Portable server-side scanner collector; requires only the Pulse Python dependencies."""
import argparse
import importlib.util
from pathlib import Path
import re
from options_seller.paths import data_dir
from options_seller.portfolio.scanner_feed import scanner_json_path


def collect(symbols=None):
    source = Path(__file__).resolve().parents[2]/"stock-data-scanner"/"scan.py"
    spec = importlib.util.spec_from_file_location("pulse_server_scan", source)
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    # Explicit deployment paths win; otherwise keep generated data outside tracked snapshots.
    import os
    target = scanner_json_path() if os.environ.get("SCANNER_JSON_PATH") else data_dir()/"scan-latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    result = scanner.build_scan(symbols, max_workers=4)
    if not any(isinstance(row.get("price"), (int, float)) and row["price"] > 0 for row in result["results"]):
        raise RuntimeError("Scanner provider returned no usable prices; previous file was retained.")
    import json
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated tickers; defaults to the server scanner universe")
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    if symbols and (len(symbols) > 100 or any(not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}", s) for s in symbols)):
        parser.error("Use 1–100 valid ticker symbols")
    result = collect(symbols)
    print(f"Collected {len(result['results'])} scanner rows at {result['asOf']}")


if __name__ == "__main__":
    main()
