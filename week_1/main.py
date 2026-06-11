import logging
import sys
from pathlib import Path

from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html
from src.loader import load_all_jsons
from src.profiler import run_data_profile


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "data" / "0_source"
BRONZE_DIR = BASE_DIR / "data" / "1_bronze"
SILVER_DIR = BASE_DIR / "data" / "2_silver"
GOLD_DIR = BASE_DIR / "data" / "3_gold"
DB_NAME = "jobs.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s |%(levelname)s |%(message)s",
)


def run_profile():
    db_path = GOLD_DIR / DB_NAME
    run_data_profile(db_path)


def run_gold():
    input_dir = SILVER_DIR
    output_dir = GOLD_DIR
    load_all_jsons(input_dir, output_dir)


def run_silver():
    input_dir = BRONZE_DIR
    output_dir = SILVER_DIR
    process_all_html(input_dir, output_dir)


def run_bronze():
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)


def run_all():
    run_bronze()
    run_silver()
    run_gold()
    run_profile()


stages = {
    "ingest": run_bronze,
    "process": run_silver,
    "load": run_gold,
    "profile": run_profile,
    "all": run_all,
}


def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py [ingest|process|load|profile|all]")
    else:
        stages.get(
            sys.argv[1],
            lambda: print(
                f"Invalid argument {sys.argv[1]}\n"
                "Valid arguments are: ingest, process, load, profile, all"
            ),
        )()


if __name__ == "__main__":
    main()
