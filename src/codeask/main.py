"""Console entry point: `codeask` runs uvicorn."""

import uvicorn

from codeask.settings import Settings


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "codeask.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
