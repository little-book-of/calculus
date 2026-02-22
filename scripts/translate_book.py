#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC_FILES = [ROOT / "en" / "index.qmd", ROOT / "index.qmd"]
PROTECTED_RE = re.compile(r"(`[^`]*`|\$[^$]*\$)")


@dataclass
class RateLimiter:
    interval_s: float
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _next_ts: float = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_ts:
                time.sleep(self._next_ts - now)
                now = time.monotonic()
            self._next_ts = now + self.interval_s


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Translate book qmd files into target language")
    p.add_argument("--source-lang", default="en")
    p.add_argument("--target-lang", default="zh-CN")
    p.add_argument("--output-dir", default="")
    p.add_argument("--files", default=os.environ.get("TRANSLATE_FILES", ""))
    p.add_argument("--chunk-size", type=int, default=2200)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--rate-limit", type=float, default=4.0)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_files(files_arg: str) -> list[Path]:
    if files_arg.strip():
        return [ROOT / path.strip() for path in files_arg.split(",") if path.strip()]
    return DEFAULT_SRC_FILES


def chunk_text(s: str, size: int) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(s):
        j = min(len(s), i + size)
        if j < len(s):
            k = s.rfind("\n", i, j)
            if k > i + 80:
                j = k + 1
        out.append(s[i:j])
        i = j
    return out


def translate_chunk(
    idx: int,
    chunk: str,
    translator: GoogleTranslator,
    limiter: RateLimiter,
) -> tuple[int, str]:
    if not chunk.strip() or re.fullmatch(r"[\s\d#>*\-`~:;,.!\[\](){}+=_/\\|]+", chunk):
        return idx, chunk

    limiter.wait()
    try:
        return idx, translator.translate(chunk) or chunk
    except Exception as exc:
        logging.warning("chunk %s failed: %s", idx, exc)
        return idx, chunk


def translate_segment(
    segment: str,
    translator: GoogleTranslator,
    limiter: RateLimiter,
    chunk_size: int,
    max_workers: int,
) -> str:
    chunks = chunk_text(segment, chunk_size)
    if len(chunks) == 1:
        return translate_chunk(0, chunks[0], translator, limiter)[1]

    out = [""] * len(chunks)
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(translate_chunk, idx, chunk, translator, limiter)
            for idx, chunk in enumerate(chunks)
        ]
        for future in cf.as_completed(futures):
            idx, txt = future.result()
            out[idx] = txt
    return "".join(out)


def translate_line(
    line: str,
    translator: GoogleTranslator,
    limiter: RateLimiter,
    chunk_size: int,
    max_workers: int,
) -> str:
    parts = PROTECTED_RE.split(line)
    translated_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if (part.startswith("`") and part.endswith("`")) or (part.startswith("$") and part.endswith("$")):
            translated_parts.append(part)
        else:
            translated_parts.append(
                translate_segment(part, translator, limiter, chunk_size, max_workers)
            )
    return "".join(translated_parts)


def post_process_qmd(text: str, output_dir: str) -> str:
    text = text.replace("lang: en", f"lang: {output_dir}")
    text = text.replace("[English version](en/index.qmd)", "[英文版](en/index.qmd)")
    text = text.replace("[Phiên bản tiếng Việt](vi/index.qmd)", "[越南语版](vi/index.qmd)")
    text = text.replace("[Chinese version](zh/index.qmd)", "[中文版](zh/index.qmd)")
    return text


def translate_file(
    src: Path,
    dst: Path,
    translator: GoogleTranslator,
    limiter: RateLimiter,
    chunk_size: int,
    max_workers: int,
    output_dir: str,
) -> None:
    lines = src.read_text(encoding="utf-8").splitlines(True)
    in_code = False
    in_math = False
    out: list[str] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if stripped == "$$":
            in_math = not in_math
            out.append(line)
            continue

        if in_code or in_math:
            out.append(line)
        else:
            translated = translate_line(line.rstrip("\n"), translator, limiter, chunk_size, max_workers)
            if line.endswith("\n"):
                translated += "\n"
            out.append(translated)

        if i % 250 == 0:
            logging.info("%s: %d/%d lines", src.relative_to(ROOT), i, len(lines))

    dst.parent.mkdir(parents=True, exist_ok=True)
    rendered = post_process_qmd("".join(out), output_dir)
    dst.write_text(rendered, encoding="utf-8")
    logging.info("DONE %s -> %s", src.relative_to(ROOT), dst.relative_to(ROOT))


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)
    output_dir = (args.output_dir.strip() or args.target_lang.split("-")[0]).lower()

    files = resolve_files(args.files)
    translator = GoogleTranslator(source=args.source_lang, target=args.target_lang)
    limiter = RateLimiter(interval_s=1.0 / max(args.rate_limit, 0.2))

    for src in files:
        rel = src.relative_to(ROOT)
        if rel == Path("index.qmd"):
            dst = ROOT / rel
        else:
            dst = ROOT / output_dir / rel.name
        translate_file(src, dst, translator, limiter, args.chunk_size, args.max_workers, output_dir)


if __name__ == "__main__":
    main()
