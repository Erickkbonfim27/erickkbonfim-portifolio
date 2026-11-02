"""Build the app the way the deploy does, with production dependencies only.

`make runtime` runs this in an isolated environment without the dev group, so an
import that only works on a developer machine (type stubs, test tools), a missing
driver or a URL in a shape the code does not accept fails here, not in production.
Nothing connects: the values only have the shape of the real ones.
"""

import os

SHAPES = {
    # As Easypanel hands it out: plain postgres://, no driver, libpq's sslmode.
    "DATABASE_URL": "postgres://user:password@portifolio_postgres:5432/portfolio?sslmode=disable",
    # The public domain: the S3 client rejects internal names with '_'.
    "S3_ENDPOINT_URL": "https://s3.example.dev",
    "S3_ACCESS_KEY": "access",
    "S3_SECRET_KEY": "secret",
    "S3_BUCKET": "portfolio",
    "PUBLIC_FILES_BASE_URL": "https://files.example.dev/portfolio",
    "PUBLIC_SITE_URL": "https://example.dev",
    "PUBLIC_API_URL": "https://api.example.dev",
    "QDRANT_URL": "http://portifolio_qdrant:6333",
    "OPENROUTER_API_KEY": "sk-or-shape-only",
    "IP_HASH_SECRET": "x" * 32,
}


def main() -> None:
    os.environ.update(SHAPES)
    from portfolio import cli, worker  # noqa: F401, PLC0415 - imported for the check
    from portfolio.main import create_app  # noqa: PLC0415

    app = create_app()
    print(f"ok: {app.title} builds with production dependencies only")


if __name__ == "__main__":
    main()
