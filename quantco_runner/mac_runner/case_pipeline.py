"""Decrypt a staged QuantCo case, analyze it, and prepare internal prices."""

import argparse
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

import pymupdf
import pyzipper
from pyzipper.zipfile import BadZipFile

from invoice_rows import DEFAULT_VAT_RATE, invoice_manifest
from pricing import DEFAULT_SPREAD_BPS, price_payload


DOCUMENTS = {"policy": "policy.txt", "damage": "description.txt", "invoice": "invoices.pdf"}
MAX_CASE_BYTES = 100 * 1024 * 1024
MAX_DOC_CHARS = 30_000


def extract_case(archive, destination, password, *, require_encrypted=False):
    """Decrypt a ZIP in temporary storage and move it into place on success."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"extraction destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with pyzipper.AESZipFile(archive) as source:
        members = source.infolist()
        if not members or len(members) > 1000 or sum(m.file_size for m in members) > MAX_CASE_BYTES:
            raise ValueError("archive is empty or exceeds case size limits")
        names = set()
        for member in members:
            name = PurePosixPath(member.filename)
            if (
                not name.parts or name.is_absolute() or ".." in name.parts
                or "\\" in member.filename or ":" in member.filename
                or stat.S_ISLNK(member.external_attr >> 16) or name in names
            ):
                raise ValueError("archive contains an unsafe or duplicate path")
            names.add(name)
        files = [member for member in members if not member.is_dir()]
        if require_encrypted and (not files or any(not member.flag_bits & 1 for member in files)):
            raise ValueError("expected an encrypted organizer archive")
        if any(m.flag_bits & 1 for m in members) and not password:
            raise ValueError("the case is encrypted; supply the released password")
        with tempfile.TemporaryDirectory(prefix=".case-", dir=destination.parent) as scratch:
            unpacked = Path(scratch) / "files"
            unpacked.mkdir()
            try:
                source.extractall(path=unpacked, pwd=password)
            except (RuntimeError, BadZipFile, NotImplementedError) as exc:
                raise ValueError("could not decrypt ZIP: verify the released password and archive") from exc
            unpacked.rename(destination)


def _case_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"case file is missing or outside the extracted directory: {relative}")
    return path


def _find_case_file(root, filename):
    matches = [path for path in root.rglob(filename) if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"expected one case file named {filename}; found {len(matches)}")
    return _case_file(root, matches[0].relative_to(root))


def case_manifest(root, game_id, *, vat_rate=DEFAULT_VAT_RATE):
    root = root.resolve()
    paths = {role: _find_case_file(root, filename) for role, filename in DOCUMENTS.items()}
    return invoice_manifest(paths["invoice"], game_id, vat_rate=vat_rate)


def _read_document(role, path, max_chars=MAX_DOC_CHARS):
    if path.suffix.lower() == ".pdf":
        pages = []
        with pymupdf.open(path) as pdf:
            for index, page in enumerate(pdf, start=1):
                text = page.get_text(sort=True).strip()
                if len(text) < 12:
                    text += "\n[Little or no text; review the original page locally]"
                pages.append(f"[Page {index}]\n{text}")
        text = "\n\n".join(pages)
    elif path.suffix.lower() in {".txt", ".md", ".csv"}:
        text = path.read_text(encoding="utf-8-sig")
    else:
        raise ValueError(f"unsupported document format for {role}: {path.suffix}")
    if len(text) > max_chars:
        return text[:max_chars] + "\n[Document excerpt ends here]"
    return text


def inspection_input(manifest, root, *, max_doc_chars=MAX_DOC_CHARS):
    root = root.resolve()
    documents = {}
    overrides = manifest.get("documents", {})
    for role, filename in DOCUMENTS.items():
        path = _case_file(root, overrides[role]) if role in overrides else _find_case_file(root, filename)
        documents[role] = _read_document(role, path, max_doc_chars)
    photos = manifest.get("photos")
    if photos is None:
        photos = [
            path.relative_to(root) for path in sorted(root.rglob("*"))
            if path.is_file() and path.stem.lower().startswith(("image", "photo"))
            and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
    images = []
    for relative in photos:
        path = _case_file(root, relative)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("case photos must be PNG or JPEG")
        images.append(str(path.relative_to(root)))
    rows = []
    for index, item in enumerate(manifest["items"]):
        row = {field: item[field] for field in ("item_id", "quantity", "unit", "vat_rate")}
        row["description"] = item.get("description", "")
        rows.append({"row_index": index, **row})
    return {"documents": documents, "images": images, "rows": rows}


def _assessment_rows(manifest, analysis):
    count = len(manifest["items"])
    by_index = {}
    for row in analysis["items"]:
        index = row["row_index"]
        if type(index) is not int or index not in range(count) or index in by_index:
            raise ValueError("local assessment has a duplicate or unknown invoice row")
        band = row["unit_price_band_net_cents"]
        if (
            not isinstance(band, list) or len(band) != 3
            or any(type(value) is not int or value < 0 for value in band)
            or band != sorted(band)
        ):
            raise ValueError("local assessment has an invalid net unit price band")
        eligible = row["eligible_samples"]
        if type(eligible) is not int or not 0 <= eligible <= 100:
            raise ValueError("local assessment has invalid eligibility")
        if not isinstance(row["evidence"], str) or not row["evidence"].strip():
            raise ValueError("local assessment omitted evidence")
        by_index[index] = {key: row[key] for key in (
            "coverage", "relevance", "eligible_samples", "unit_price_band_net_cents", "evidence"
        )}
    if len(by_index) != count:
        raise ValueError("local assessment omitted invoice rows")
    valuation = []
    for index, item in enumerate(manifest["items"]):
        # Only join model estimates; the runner owns IDs, quantity and VAT.
        record = {key: item[key] for key in ("item_id", "quantity", "unit", "vat_rate")}
        valuation.append({**record, **by_index[index]})
    return {**manifest, "items": valuation}


def _save(directory, name, data):
    fd, temporary_name = tempfile.mkstemp(dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(directory / name)
    finally:
        temporary.unlink(missing_ok=True)


def process_case(manifest, output, *, analysis_file=None, spread_bps=DEFAULT_SPREAD_BPS):
    """Save a complete baseline first and keep any local candidate separate."""
    if not 1 <= spread_bps <= 10000:
        raise ValueError("spread must be between 1 and 10000 basis points")
    start = time.monotonic()
    output.mkdir(parents=True, exist_ok=False)
    result = {"game_id": manifest["game_id"], "payloads": {}}
    try:
        payload = price_payload(manifest, spread_bps=spread_bps)
        _save(output, "baseline.json", payload)
        result["payloads"]["baseline"] = "baseline.json"
        result["baseline_ms"] = round((time.monotonic() - start) * 1000)
    except (KeyError, TypeError, ValueError) as exc:
        result["baseline_error"] = str(exc)

    if analysis_file is not None:
        analysis_start = time.monotonic()
        try:
            analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
            valuation = _assessment_rows(manifest, analysis)
            payload = price_payload(valuation, spread_bps=spread_bps)
            name = "refined" if "baseline" in result["payloads"] else "candidate"
            _save(output, "analysis.json", valuation)
            _save(output, f"{name}.json", payload)
            result["payloads"][name] = f"{name}.json"
        except (KeyError, TypeError, ValueError, OSError) as exc:
            result["analysis_error"] = str(exc)
        result["analysis_ms"] = round((time.monotonic() - analysis_start) * 1000)
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    _save(output, "run.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="decrypt a staged ZIP")
    extract.add_argument("archive", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("--password-file", type=Path, help="otherwise read FDN_CASE_PASSWORD")
    inspect = commands.add_parser("inspect", help="print case evidence as JSON for local analysis")
    inspect.add_argument("case_dir", type=Path)
    inspect.add_argument("manifest", type=Path)
    run = commands.add_parser("run", help="price locally from a runner's invoice manifest")
    run.add_argument("manifest", type=Path)
    run.add_argument("output", type=Path, help="a fresh output directory")
    run.add_argument("--analysis-file", type=Path, help="import a local assessment JSON file")
    run.add_argument("--spread-bps", type=int, default=DEFAULT_SPREAD_BPS)
    args = parser.parse_args()
    try:
        if args.command == "extract":
            password = (args.password_file.read_bytes().rstrip(b"\r\n") if args.password_file
                        else os.getenv("FDN_CASE_PASSWORD", "").encode())
            extract_case(args.archive, args.destination, password)
            print(args.destination)
            return 0
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.command == "inspect":
            print(json.dumps(inspection_input(manifest, args.case_dir), ensure_ascii=False, indent=2))
            return 0
        result = process_case(manifest, args.output,
                              analysis_file=args.analysis_file, spread_bps=args.spread_bps)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["payloads"] else 1
    except (BadZipFile, KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(2, f"case pipeline: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
