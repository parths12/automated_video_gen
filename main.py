#!/usr/bin/env python3
"""NCERT Math Shorts Video Generator CLI."""

import argparse
import sys
from pathlib import Path

# Ensure package root on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from agents.orchestrator import run_pipeline
from agents.pdf_parser import parse_ncert_pdf
from agents.segmenter import save_concept_cards, segment_chapter
from utils.logger import get_logger
from utils.schemas import ConceptCard

logger = get_logger(__name__)


def cmd_parse(args: argparse.Namespace) -> None:
    pdf = Path(args.pdf)
    if not pdf.exists():
        pdf = config.SOURCE_PDF
    print(f"Parsing {pdf}...")
    text = parse_ncert_pdf(str(pdf), parsed_dir=config.PARSED_DIR)
    subject = getattr(args, "subject", "math")
    if hasattr(config, "SUBJECT"):
        import os
        os.environ["SUBJECT"] = subject

    cards = segment_chapter(
        chapter_text=text,
        grade=args.grade,
        chapter_name=args.chapter,
        chapter_number=args.chapter_num,
        subject=subject,
    )
    cards_dir = getattr(args, "cards_dir", None)
    output_dir = Path(cards_dir) if cards_dir else config.CARDS_DIR / f"class{args.grade}_ch{args.chapter_num}"
    if subject == "physics":
        output_dir = Path(cards_dir) if cards_dir else config.CARDS_DIR / "physics_ch2"
    paths = save_concept_cards(cards, output_dir)
    print(f"\nSaved {len(paths)} concept cards to {output_dir}")
    for card in cards:
        print(f"  [{card.difficulty.value}] {card.topic}")


def cmd_generate(args: argparse.Namespace) -> None:
    if getattr(args, "subject", None):
        import os
        os.environ["SUBJECT"] = args.subject

    cards_dir = Path(args.cards)
    card_files = sorted(cards_dir.glob("*.json"))
    if not card_files:
        print(f"No concept cards in {cards_dir}")
        sys.exit(1)

    if args.concept is not None:
        if args.concept >= len(card_files):
            print(f"Concept index {args.concept} out of range (0-{len(card_files)-1})")
            sys.exit(1)
        card_files = [card_files[args.concept]]

    for idx, card_file in enumerate(card_files):
        print(f"\n{'='*60}\nProcessing: {card_file.name}\n{'='*60}")
        card = ConceptCard.model_validate_json(card_file.read_text(encoding="utf-8"))
        run = run_pipeline(
            concept_card=card,
            output_dir=args.output,
            language=args.language,
            concept_index=args.concept if args.concept is not None else idx,
        )
        if run.status == "done":
            print(f"Output: {run.output_video_path}")
            if run.quiz_result:
                print(f"TeachQuiz: {'PASS' if run.quiz_result.passed else 'FAIL'} ({run.quiz_result.score})")
        else:
            print(f"FAILED: {run.errors}")


def cmd_run(args: argparse.Namespace) -> None:
    cmd_parse(args)
    cards_dir = config.CARDS_DIR / f"class{args.grade}_ch{args.chapter_num}"
    gen_args = argparse.Namespace(
        cards=str(cards_dir),
        output=args.output,
        language=args.language,
        concept=args.concept,
    )
    cmd_generate(gen_args)


def main() -> None:
    parser = argparse.ArgumentParser(description="NCERT Math Shorts Video Generator")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("parse", help="Parse NCERT PDF into concept cards")
    p.add_argument("--pdf", default=str(config.SOURCE_PDF))
    p.add_argument("--grade", type=int, required=True)
    p.add_argument("--chapter", required=True)
    p.add_argument("--chapter-num", type=int, default=2, dest="chapter_num")
    p.add_argument("--subject", default="math", choices=["math", "physics"])
    p.add_argument("--cards-dir", default=None, help="Where to save concept cards")

    g = sub.add_parser("generate", help="Generate videos from concept cards")
    g.add_argument("--cards", required=True)
    g.add_argument("--output", default=str(config.OUTPUT_DIR))
    g.add_argument("--language", default="en", choices=["en", "hi", "en-hi"])
    g.add_argument("--concept", type=int, default=None, help="Concept index (0-based)")
    g.add_argument("--subject", default=None, choices=["math", "physics"])

    r = sub.add_parser("run", help="Full pipeline: parse + generate")
    r.add_argument("--pdf", default=str(config.SOURCE_PDF))
    r.add_argument("--grade", type=int, required=True)
    r.add_argument("--chapter", required=True)
    r.add_argument("--chapter-num", type=int, default=2, dest="chapter_num")
    r.add_argument("--output", default=str(config.OUTPUT_DIR))
    r.add_argument("--language", default="en", choices=["en", "hi", "en-hi"])
    r.add_argument("--concept", type=int, default=0)
    r.add_argument("--subject", default="math", choices=["math", "physics"])
    r.add_argument("--cards-dir", default=None)

    args = parser.parse_args()
    if getattr(args, "subject", None):
        import os
        os.environ["SUBJECT"] = args.subject
    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
