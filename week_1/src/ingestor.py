from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
import logging
from pathlib import Path
import quopri
import sys
from typing import Literal


SUPPORTED_MHTML_SUFFIXES = {".mhtml", ".mht"}

BRONZE_ICON = "\U0001f949"
WARNING_ICON = "\u26a0\ufe0f"
SUCCESS_ICON = "\u2705"
FAILED_ICON = "\u274c"
SUMMARY_ICON = "\U0001f4ca"

IngestStatus = Literal["extracted", "no_html", "failed"]


@dataclass(frozen=True)
class IngestResult:
    source_path: Path
    output_path: Path | None
    status: IngestStatus
    error: str | None = None


def _configure_stdout() -> None:
    if not hasattr(sys.stdout, "reconfigure"):
        return

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except OSError:
        return
    except ValueError:
        return


def _iter_mhtml_files(input_path: Path) -> list[Path]:
    if not input_path.exists() or not input_path.is_dir():
        return []

    return sorted(
        (
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_MHTML_SUFFIXES
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def _payload_to_bytes(payload: bytes | str | None, charset: str) -> bytes:
    if isinstance(payload, bytes):
        return payload

    if isinstance(payload, str):
        return payload.encode(charset, errors="replace")

    return b""


def _decode_html_part(part: Message) -> str:
    charset = part.get_content_charset() or "utf-8"
    payload_bytes = part.get_payload(decode=True)

    if payload_bytes is None:
        transfer_encoding = part.get("Content-Transfer-Encoding", "").lower()
        raw_payload = _payload_to_bytes(part.get_payload(decode=False), charset)
        if transfer_encoding == "quoted-printable":
            payload_bytes = quopri.decodestring(raw_payload)
        else:
            payload_bytes = raw_payload

    return payload_bytes.decode(charset, errors="replace")


def _extract_html_from_mhtml(source_path: Path) -> str | None:
    message = BytesParser(policy=policy.default).parsebytes(source_path.read_bytes())

    for part in message.walk():
        if not part.is_multipart() and part.get_content_type() == "text/html":
            return _decode_html_part(part)

    return None


def ingest_mhtml(source_path: Path, output_dir: Path) -> IngestResult:
    output_path = output_dir / source_path.with_suffix(".html").name

    try:
        html = _extract_html_from_mhtml(source_path)
        if html is None:
            return IngestResult(source_path, None, "no_html")

        output_path.write_text(html, encoding="utf-8")
        return IngestResult(source_path, output_path, "extracted")
    except Exception as error:
        return IngestResult(source_path, None, "failed", str(error))


def _log_result(result: IngestResult) -> None:
    if result.status == "extracted":
        logging.info("%s Extracted: %s", SUCCESS_ICON, result.source_path.name)
    elif result.status == "no_html":
        logging.warning(
            "%s No HTML content found in: %s",
            WARNING_ICON,
            result.source_path.name,
        )
    else:
        reason = result.error or "unknown error"
        logging.error("%s Failed: %s (%s)", FAILED_ICON, result.source_path.name, reason)


def _print_summary(results: list[IngestResult]) -> None:
    total = len(results)
    extracted = sum(result.status == "extracted" for result in results)
    failed = total - extracted

    print(f"\n{SUMMARY_ICON} Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")


def ingest_all_mhtml(input_dir, output_dir) -> None:
    _configure_stdout()

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"{BRONZE_ICON} Bronze: Extracting MHTML files...")

    if not input_path.exists():
        logging.warning("%s Source directory not found: %s", WARNING_ICON, input_path)
    elif not input_path.is_dir():
        logging.warning("%s Source path is not a directory: %s", WARNING_ICON, input_path)

    results: list[IngestResult] = []
    for source_path in _iter_mhtml_files(input_path):
        result = ingest_mhtml(source_path, output_path)
        results.append(result)
        _log_result(result)

    _print_summary(results)
