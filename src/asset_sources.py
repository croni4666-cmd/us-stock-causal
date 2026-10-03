"""Official public asset evidence. Downloads are explicit; calculations never fetch.

Issuer material stays in the caller's local store. A download time is never
backdated to pretend an historical observation was available to a strategy.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import uuid
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import requests


SOURCE_SPECS = {
    "QQQ": ("Invesco", "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/46090E103/holdings/fund?idType=cusip&productType=ETF"),
    "IEF": ("iShares", "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf/latest-holdings.csv"),
    "TLT": ("iShares", "https://www.ishares.com/us/products/239454/ishares-20%2B-year-treasury-bond-etf/latest-holdings.csv"),
    "GLD": ("SPDR", "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"),
}
MAX_BYTES = 20 * 1024 * 1024
_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_EQUITY_TYPES = {"Common Stock", "American Depository Receipt", "American Depository Receipt - NY"}


def _number(value, *, optional=False, nonnegative=False):
    if value is None or str(value).strip() in ("", "-", "N/A", "AWAITED"):
        if optional:
            return None
        raise ValueError("missing numeric field")
    try:
        number = float(str(value).replace(",", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid numeric field: {value!r}") from exc
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise ValueError("non-finite or negative numeric field")
    return number


def _iso_day(value):
    return date.fromisoformat(str(value)).isoformat()


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("capture timestamp must be a timezone-aware string")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("capture timestamp requires timezone")
    return stamp.astimezone(timezone.utc)


def portfolio_weight_complete(rows: list[dict]) -> bool:
    """Allow per-record issuer rounding, without rescaling or inventing cash.

    iShares publishes weights at 0.01 percentage-point precision. The bound
    allows half a rounding unit per row plus a small floating-point margin.
    This checksum detects material truncation; it cannot prove every tiny
    holding is present without an independent published row count.
    """
    if not rows or any(row.get("weight") is None for row in rows):
        return False
    total = sum(_number(row["weight"]) for row in rows)
    tolerance = max(.0002, len(rows) * .00005 + .0001)
    return abs(total - 1) <= tolerance


def _validate_rows(rows):
    if not rows:
        raise ValueError("empty holdings")
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate security identifier")
    equity_tickers = [r['ticker'] for r in rows if r['asset_class'] == 'Equity' and r.get('ticker')]
    if len(equity_tickers) != len(set(equity_tickers)):
        raise ValueError("duplicate equity ticker with conflicting security identity")
    for row in rows:
        weight = row["weight"]
        if weight is not None and abs(weight) > 1.5:
            raise ValueError("weight outside supported portfolio range")
        if row["asset_class"] == "Equity" and weight is not None and weight < 0:
            raise ValueError("negative equity weight not supported")
    if all(row["weight"] is not None for row in rows) and not portfolio_weight_complete(rows):
        raise ValueError("portfolio weight coverage incomplete or inconsistent")
    return [f"unknown weight: {row['id']}" for row in rows if row["weight"] is None]


def parse_invesco(raw: bytes) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("cusip") != "46090E103":
        raise ValueError("wrong Invesco fund identity")
    as_of = _iso_day(data.get("effectiveBusinessDate"))
    effective = _iso_day(data.get("effectiveDate"))
    if effective < as_of:
        raise ValueError("publication date precedes business date")
    holdings = data.get("holdings")
    if not isinstance(holdings, list) or data.get("totalNumberOfHoldings") != len(holdings):
        raise ValueError("incomplete Invesco holdings")
    rows = []
    for item in holdings:
        if not isinstance(item, dict):
            raise ValueError("invalid holding object")
        security_type = item.get("securityTypeName") or "Unknown"
        identity = item.get("cusip") or item.get("ticker") or item.get("issuerName")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("holding without identifier")
        identity = identity.strip().upper()
        ticker = item.get('ticker')
        if ticker is not None:
            if not isinstance(ticker, str):
                raise ValueError("invalid holding ticker")
            ticker = ticker.strip().upper() or None
        weight = _number(item.get("percentageOfTotalNetAssets"), optional=True)
        # Type labels must not let a single equity CUSIP evade duplication.
        # Cash/derivative identities retain their explicit instrument type.
        security_id = str(identity) if security_type in _EQUITY_TYPES else f"{identity}:{security_type}"
        rows.append({"id": security_id, "ticker": ticker,
                     "name": item.get("issuerName") or str(identity),
                     "asset_class": "Equity" if security_type in _EQUITY_TYPES else security_type,
                     "security_type": security_type, "weight": None if weight is None else weight / 100,
                     "duration_years": None, "yield_pct": None, "maturity": item.get("maturityDate")})
    return {"kind": "holdings", "as_of": as_of, "effective_date": effective,
            "rows": rows, "warnings": _validate_rows(rows), "classification": "issuer security types; no sector mapping"}


def parse_ishares(raw: bytes, symbol: str) -> dict:
    names = {"TLT": "iShares 20+ Year Treasury Bond ETF", "IEF": "iShares 7-10 Year Treasury Bond ETF"}
    if symbol not in names:
        raise ValueError("unsupported iShares fund")
    records = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    if not records or records[0] != [names[symbol]]:
        raise ValueError("wrong iShares fund identity")
    metadata = next((r for r in records if r and r[0] == "Fund Holdings as of"), None)
    if metadata is None or len(metadata) != 2:
        raise ValueError("missing holdings date")
    as_of = datetime.strptime(metadata[1], "%b %d, %Y").date().isoformat()
    start = next((i for i, r in enumerate(records) if r and r[0] == "Name" and "Weight (%)" in r), None)
    if start is None:
        raise ValueError("missing holdings header")
    header = records[start]
    required = {"Name", "Asset Class", "Weight (%)", "CUSIP", "Duration", "YTM (%)", "Maturity"}
    if not required.issubset(header) or len(header) != len(set(header)):
        raise ValueError("invalid holdings columns")
    rows = []
    for record in records[start + 1:]:
        if not record or not any(record):
            break  # issuer legal text follows the blank line after the table
        if len(record) != len(header):
            raise ValueError("truncated holdings record")
        item = dict(zip(header, record))
        identity = item["CUSIP"]
        if identity in ("", "-"):
            if item["Asset Class"] == "Cash" and item["Name"]:
                identity = "Cash:" + item["Name"]
            else:
                raise ValueError("missing security identifier")
        weight = _number(item["Weight (%)"], optional=True)
        rows.append({"id": identity, "ticker": None, "name": item["Name"],
                     "asset_class": item["Asset Class"], "security_type": item["Asset Class"],
                     "weight": None if weight is None else weight / 100,
                     "duration_years": _number(item["Duration"], optional=True, nonnegative=True),
                     "yield_pct": _number(item["YTM (%)"], optional=True), "maturity": item["Maturity"]})
    return {"kind": "holdings", "as_of": as_of, "rows": rows,
            "warnings": _validate_rows(rows), "classification": "issuer asset classes"}


def _xlsx_rows(raw):
    """Read the named issuer sheet with ZIP/XML; no Excel runtime dependency."""
    with ZipFile(io.BytesIO(raw)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_BYTES * 5:
            raise ValueError("expanded XLSX too large")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next((s for s in workbook.findall("s:sheets/s:sheet", _NS)
                      if s.get("name") == "US GLD Historical Archive"), None)
        if sheet is None:
            raise ValueError("missing GLD archive sheet")
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next((r.get("Target") for r in relations if r.get("Id") == rid), None)
        if not target:
            raise ValueError("missing archive sheet relationship")
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in PurePosixPath(path).parts or not path.startswith("xl/"):
            raise ValueError("unsafe sheet path")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = [''.join(si.itertext()) for si in root.findall("s:si", _NS)]
        root = ET.fromstring(archive.read(path))
        rows = []
        for row in root.findall("s:sheetData/s:row", _NS):
            values = {}
            for cell in row.findall("s:c", _NS):
                ref = cell.get("r", "")
                column = 0
                for ch in ref:
                    if ch.isdigit():
                        break
                    column = column * 26 + ord(ch) - 64
                if not 1 <= column <= 100:
                    raise ValueError("invalid archive cell reference")
                kind = cell.get("t")
                value = cell.findtext("s:v", default="", namespaces=_NS)
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = ''.join(cell.find("s:is", _NS).itertext())
                values[column - 1] = value
            rows.append([values.get(i, "") for i in range(max(values, default=-1) + 1)])
        return rows


def parse_spdr(raw: bytes) -> dict:
    records = _xlsx_rows(raw)
    fields = {"Date": "date", "Closing Price": "close", "Ounces of Gold per Share": "ounces_per_share",
              "NAV/Share at 10:30am NYT": "nav_1030", "Indicative Price per Share at 4:15pm NYT": "indicative_1615",
              "Mid point of bid/ask spread at 4:15pm NYT": "midpoint_1615",
              "Premium/Discount of GLD Mid Point vs Indicative Value of GLD at 4:15pm NYT": "premium_pct_1615"}
    if not records or not set(fields).issubset(records[0]):
        raise ValueError("invalid GLD archive header")
    columns = {records[0].index(key): value for key, value in fields.items()}
    rows = []
    for record in records[1:]:
        if not record or not any(record):
            continue
        day = datetime.strptime(record[0], "%d-%b-%Y").date().isoformat()
        if len(record) <= max(columns):
            raise ValueError("truncated GLD archive row")
        # Holidays are explicit missing observations, never carried forward.
        if "Holiday" in record[1]:
            continue
        row = {"date": day}
        for i, key in columns.items():
            if key != "date":
                row[key] = _number(record[i], optional=True, nonnegative=(key != "premium_pct_1615"))
        rows.append(row)
    days = [r["date"] for r in rows]
    if not days or len(days) != len(set(days)) or days != sorted(days):
        raise ValueError("empty, duplicate or unordered GLD dates")
    return {"kind": "gold_archive", "as_of": days[-1], "rows": rows,
            "warnings": ["independent licensed LBMA benchmark absent; NAV and close have different pricing times"]}


def _parse(symbol, raw):
    if symbol == "QQQ":
        return parse_invesco(raw)
    if symbol in ("IEF", "TLT"):
        return parse_ishares(raw, symbol)
    if symbol == "GLD":
        return parse_spdr(raw)
    raise ValueError(f"unsupported official source: {symbol}")


def _atomic_write(path, data):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def store_source(symbol: str, raw: bytes, parsed: dict, root: Path, *, retrieved_at: str | None = None) -> Path:
    if symbol not in SOURCE_SPECS:
        raise ValueError(f"unsupported official source: {symbol}")
    if not raw or len(raw) > MAX_BYTES or _parse(symbol, raw) != parsed:
        raise ValueError("invalid raw/normalized source pair")
    captured = _timestamp(retrieved_at or datetime.now(timezone.utc).isoformat())
    if _iso_day(parsed["as_of"]) > captured.date().isoformat():
        raise ValueError("source observation is in the future")
    provider, url = SOURCE_SPECS[symbol]
    digest = hashlib.sha256(raw).hexdigest()
    doc = {**parsed, "schema_version": 1, "symbol": symbol, "provider": provider,
           "source_url": url, "sha256": digest, "retrieved_at": captured.isoformat(),
           "available_at": captured.isoformat()}
    folder = Path(root) / symbol
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}-{uuid.uuid4().hex}.json"
    _atomic_write(path.with_suffix(".raw"), raw)
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    return path


def load_sources(symbol: str, root: Path) -> list[dict]:
    if symbol not in SOURCE_SPECS:
        raise ValueError(f"unsupported official source: {symbol}")
    documents = []
    for path in sorted((Path(root) / symbol).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("source metadata must be an object")
        if doc.get("schema_version") != 1 or doc.get("symbol") != symbol:
            raise ValueError("unsupported source schema or symbol")
        provider, url = SOURCE_SPECS[symbol]
        if doc.get("provider") != provider or doc.get("source_url") != url:
            raise ValueError("invalid source provenance")
        raw = path.with_suffix(".raw").read_bytes()
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != doc.get("sha256"):
            raise ValueError("source hash mismatch")
        parsed = _parse(symbol, raw)
        if any(doc.get(key) != value for key, value in parsed.items()):
            raise ValueError("normalized source differs from raw")
        captured = _timestamp(doc["retrieved_at"])
        if doc.get("available_at") != doc["retrieved_at"] or parsed["as_of"] > captured.date().isoformat():
            raise ValueError("invalid source availability")
        documents.append(doc)
    return documents


def eligible_snapshot(doc: dict, start: str, mode: str = "point_in_time") -> bool:
    if mode not in ("point_in_time", "retrospective"):
        raise ValueError("mode must be point_in_time or retrospective")
    start_day = date.fromisoformat(start)
    if date.fromisoformat(doc["as_of"]) > start_day:
        return False
    if mode == "retrospective":
        return True
    cutoff = datetime.combine(start_day, time(9, 30), ZoneInfo("America/New_York"))
    return _timestamp(doc["available_at"]) <= cutoff


def capture_source(symbol: str, root: Path, *, session=None) -> Path:
    if symbol not in SOURCE_SPECS:
        raise ValueError(f"unsupported official source: {symbol}")
    # Importing this existing module activates the user's configured proxy only
    # when the explicit download function is called, not on report imports.
    from src import proxy  # noqa: F401
    client = session or requests.Session()
    try:
        with client.get(SOURCE_SPECS[symbol][1], timeout=(10, 40), stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("source response too large")
                chunks.append(chunk)
            raw = b''.join(chunks)
        return store_source(symbol, raw, _parse(symbol, raw), root)
    finally:
        if session is None:
            client.close()
