"""Generate ~100 Synthea patients (FHIR R4) with a fixed seed.

Usage:
  uv run python -m scripts.generate_patients --download   # fetch the Synthea jar once
  uv run python -m scripts.generate_patients              # generate into data/synthea/

Needs Java 17+ on PATH (or JAVA_HOME). The jar is stored in tools/ (gitignored).
Flags follow the Synthea README (-s seed, -cs clinician seed, -p population, -r reference date);
verify against the README of the pinned release before first run.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

SYNTHEA_VERSION = "v3.3.0"
JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/download/"
    f"{SYNTHEA_VERSION}/synthea-with-dependencies.jar"
)
ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / "tools" / f"synthea-{SYNTHEA_VERSION}.jar"
OUT = ROOT / "data" / "synthea"
SEED = 20261114
REFERENCE_DATE = "20261001"


def find_java() -> str:
    java = shutil.which("java")
    if java:
        return java
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / "java.exe").exists():
        return str(Path(home) / "bin" / "java.exe")
    for base in (Path("C:/Program Files/Eclipse Adoptium"),):
        for p in sorted(base.glob("jdk-*/bin/java.exe"), reverse=True):
            return str(p)
    sys.exit("Java 17+ not found. Install a JDK or set JAVA_HOME.")


def download() -> None:
    JAR.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {JAR_URL}")
    with httpx.stream("GET", JAR_URL, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with JAR.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    print(f"saved {JAR} ({JAR.stat().st_size // 1_000_000} MB)")


def generate(population: int, seed: int) -> None:
    if not JAR.exists():
        sys.exit(f"{JAR} missing. Run with --download first.")
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        find_java(), "-jar", str(JAR),
        "-s", str(seed), "-cs", str(seed), "-p", str(population), "-r", REFERENCE_DATE,
        f"--exporter.baseDirectory={OUT}",
        "--exporter.fhir.export=true",
        "--exporter.fhir.transaction_bundle=true",
        "--exporter.hospital.fhir.export=true",
        "--exporter.practitioner.fhir.export=true",
        "--exporter.csv.export=false",
        "--exporter.ccda.export=false",
    ]  # fmt: skip
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="download the Synthea jar")
    ap.add_argument("-p", "--population", type=int, default=100)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    if args.download:
        download()
    else:
        generate(args.population, args.seed)


if __name__ == "__main__":
    main()
