from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sys
from typing import Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, ValidationError


SILVER_ICON = "\U0001f948"
WARNING_ICON = "\u26a0\ufe0f"
SUCCESS_ICON = "\u2705"
SUMMARY_ICON = "\U0001f4ca"

ProcessStatus = Literal["processed", "skipped"]


class JobListing(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    description: str = Field(min_length=1)


@dataclass(frozen=True)
class ProcessResult:
    source_path: Path
    output_path: Path | None
    status: ProcessStatus
    reason: str | None = None


def _configure_stdout() -> None:
    if not hasattr(sys.stdout, "reconfigure"):
        return

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except OSError:
        return
    except ValueError:
        return


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _iter_html_files(input_path: Path) -> list[Path]:
    if not input_path.exists() or not input_path.is_dir():
        return []

    return sorted(
        (
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".html"
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def _extract_source_id(soup: BeautifulSoup) -> str:
    source_url = _get_soup_value(
        soup,
        attrs={"property": "og:url"},
        attribute="content",
    )
    url_path = urlparse(source_url).path.rstrip("/")
    return _clean_text(url_path.split("/")[-1]) if url_path else ""


def _get_soup_value(
    soup: BeautifulSoup,
    attrs: dict[str, str],
    attribute: str | None = None,
    normalize: bool = True,
) -> str:
    element = soup.find(attrs=attrs)
    if element is None:
        return ""

    if attribute is not None:
        return _clean_text(str(element.get(attribute, "")))

    text = element.get_text(separator=" ", strip=True)
    return _clean_text(text) if normalize else text


def _extract_text_by_automation(
    soup: BeautifulSoup,
    automation_name: str,
    normalize: bool = True,
) -> str:
    return _get_soup_value(
        soup,
        attrs={"data-automation": automation_name},
        normalize=normalize,
    )


def _missing_fields(values: dict[str, str]) -> list[str]:
    return [
        field_name for field_name, value in values.items() if not _clean_text(value)
    ]


def _validation_missing_fields(error: ValidationError) -> list[str]:
    fields: list[str] = []
    for error_detail in error.errors():
        location = error_detail.get("loc", ())
        if location:
            fields.append(str(location[0]))
    return fields


def _extract_listing_values(html_path: Path) -> dict[str, str]:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    return {
        "source_id": _extract_source_id(soup),
        "job_title": _extract_text_by_automation(soup, "job-detail-title"),
        "company": _extract_text_by_automation(soup, "advertiser-name"),
        "description": _extract_text_by_automation(
            soup,
            "jobAdDetails",
            normalize=False,
        ),
    }


def process_html(html_path: Path, output_dir: Path) -> ProcessResult:
    output_path = output_dir / html_path.with_suffix(".json").name

    try:
        values = _extract_listing_values(html_path)
    except Exception as error:
        return ProcessResult(html_path, None, "skipped", f"read_error: {error}")

    missing_fields = _missing_fields(values)
    if missing_fields:
        return ProcessResult(html_path, None, "skipped", ", ".join(missing_fields))

    try:
        listing = JobListing(**values)
    except ValidationError as error:
        validation_fields = _validation_missing_fields(error)
        reason = ", ".join(validation_fields) if validation_fields else "validation"
        return ProcessResult(html_path, None, "skipped", reason)

    output_path.write_text(
        json.dumps(listing.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ProcessResult(html_path, output_path, "processed")


def _log_result(result: ProcessResult) -> None:
    if result.status == "processed":
        logging.info("%s Processed: %s", SUCCESS_ICON, result.source_path.name)
        return

    reason = result.reason or "unknown reason"
    if reason.startswith("read_error:"):
        logging.warning(
            "%s Skipped: %s (%s)",
            WARNING_ICON,
            result.source_path.name,
            reason,
        )
    else:
        logging.warning(
            "%s Missing %s in: %s",
            WARNING_ICON,
            reason,
            result.source_path.name,
        )


def _print_summary(results: list[ProcessResult]) -> None:
    total = len(results)
    processed = sum(result.status == "processed" for result in results)
    skipped = total - processed

    print(f"\n{SUMMARY_ICON} Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")


def process_all_html(input_dir, output_dir) -> None:
    _configure_stdout()

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"{SILVER_ICON} Silver: Processing HTML files...")

    if not input_path.exists():
        logging.warning("%s Source directory not found: %s", WARNING_ICON, input_path)
    elif not input_path.is_dir():
        logging.warning("%s Source path is not a directory: %s", WARNING_ICON, input_path)

    results: list[ProcessResult] = []
    for html_path in _iter_html_files(input_path):
        result = process_html(html_path, output_path)
        results.append(result)
        _log_result(result)

    _print_summary(results)
