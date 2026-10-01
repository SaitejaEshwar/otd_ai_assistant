import uvicorn
from .config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("otd_assistant.main:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
