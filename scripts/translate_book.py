#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "en" / "index.qmd"
PROTECTED_INLINE_RE = re.compile(r"(`[^`]*`|\$[^$]*\$|\[.*?\]\(.*?\))")
SKIP_RE = re.compile(r"^[\s\d#>*\-`~:;,.!\[\](){}+=_/\\|]+$")


@dataclass
class Counter:
    total: int
    done: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def tick(self) -> None:
        with self.lock:
            self.done += 1
            if self.done % 10 == 0 or self.done == self.total:
                logging.info("chunks %d/%d (%.1f%%)", self.done, self.total, self.done / self.total * 100)


@dataclass
class RateLimiter:
    interval_s: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    next_ts: float = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now < self.next_ts:
                time.sleep(self.next_ts - now)
                now = time.monotonic()
            self.next_ts = now + self.interval_s


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Translate QMD/Markdown with chunking, parallelism, and detailed progress logs")
    p.add_argument("--source-lang", default="en")
    p.add_argument("--target-lang", default="ja")
    p.add_argument("--source", default=str(DEFAULT_SOURCE.relative_to(ROOT)))
    p.add_argument("--output", default="")
    p.add_argument("--chunk-size", type=int, default=2600)
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--rate-limit", type=float, default=6.0)
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S")


def split_chunks(text: str, size: int) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        j = min(len(text), i + size)
        if j < len(text):
            cut = max(text.rfind("\n\n", i, j), text.rfind("\n", i, j))
            if cut > i + 120:
                j = cut + (2 if text[cut:cut+2] == "\n\n" else 1)
        out.append(text[i:j])
        i = j
    return out


def protect_inline(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = f"__KEEP_{len(mapping)}__"
        mapping[token] = match.group(0)
        return token

    return PROTECTED_INLINE_RE.sub(repl, text), mapping


def restore_inline(text: str, mapping: dict[str, str]) -> str:
    for token, val in mapping.items():
        text = text.replace(token, val)
    return text


def translate_one(idx: int, chunk: str, translator: GoogleTranslator, limiter: RateLimiter, retries: int, counter: Counter) -> tuple[int, str]:
    if not chunk.strip() or SKIP_RE.fullmatch(chunk):
        counter.tick()
        return idx, chunk

    protected, mapping = protect_inline(chunk)

    for attempt in range(1, retries + 1):
        try:
            limiter.wait()
            translated = translator.translate(protected) or protected
            counter.tick()
            return idx, restore_inline(translated, mapping)
        except Exception as exc:
            sleep_s = min(8, attempt * 1.5)
            logging.warning("chunk %d failed (%d/%d): %s; retry %.1fs", idx, attempt, retries, exc, sleep_s)
            time.sleep(sleep_s)

    logging.error("chunk %d exhausted retries; fallback to source", idx)
    counter.tick()
    return idx, chunk


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    src = ROOT / args.source
    dst = ROOT / (args.output or f"{args.target_lang.split('-')[0].lower()}/index.qmd")
    text = src.read_text(encoding="utf-8")

    chunks = split_chunks(text, args.chunk_size)
    logging.info("start %s -> %s | file=%s | chunks=%d | workers=%d | rate=%.1f/s", args.source_lang, args.target_lang, src.relative_to(ROOT), len(chunks), args.max_workers, args.rate_limit)

    translator = GoogleTranslator(source=args.source_lang, target=args.target_lang)
    limiter = RateLimiter(interval_s=1.0 / max(0.2, args.rate_limit))
    counter = Counter(total=len(chunks))

    started = time.time()
    out = [""] * len(chunks)
    with cf.ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [pool.submit(translate_one, i, c, translator, limiter, args.retries, counter) for i, c in enumerate(chunks)]
        for fut in cf.as_completed(futures):
            i, translated = fut.result()
            out[i] = translated

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(out), encoding="utf-8")
    logging.info("done %s -> %s in %.1fs", src.relative_to(ROOT), dst.relative_to(ROOT), time.time() - started)


if __name__ == "__main__":
    main()
