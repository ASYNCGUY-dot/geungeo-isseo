import argparse
from datetime import UTC, datetime
from pathlib import Path

from build_extension_review import ReviewBuildError, load_products
from pydantic import ValidationError

from claimledger.functional_role import load_functional_role_registry
from claimledger.functional_role_review import (
    DEFAULT_GENERAL_AUDIT_SIZE,
    DEFAULT_POSITIVE_AUDIT_SIZE,
    FunctionalRoleBuildError,
    write_functional_role_review_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a functional-role review pack")
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--product-review-pack", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--general-size", type=int, default=DEFAULT_GENERAL_AUDIT_SIZE)
    parser.add_argument("--positive-size", type=int, default=DEFAULT_POSITIVE_AUDIT_SIZE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(UTC)
    try:
        products = load_products(args.source_export)
        registry = load_functional_role_registry(
            args.rules,
            evaluated_at=generated_at,
        )
        write_functional_role_review_pack(
            args.output_dir,
            products=products,
            source_export_path=args.source_export,
            product_review_pack_dir=args.product_review_pack,
            rules_path=args.rules,
            registry=registry,
            generated_at=generated_at,
            base_seed=args.seed,
            general_size=args.general_size,
            positive_size=args.positive_size,
        )
    except (FunctionalRoleBuildError, ReviewBuildError, ValidationError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
