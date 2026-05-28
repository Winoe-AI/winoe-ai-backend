from app.config import CorsSettings, Settings, _normalize_sync_url, _to_async_url


def production_secret_kwargs() -> dict[str, str]:
    return {
        "ADMIN_API_KEY": "a" * 40,
        "AUTH0_DOMAIN": "example.auth0.com",
        "AUTH0_ISSUER": "https://example.auth0.com/",
        "AUTH0_API_AUDIENCE": "https://api.example.com",
        "AUTH0_CLIENT_ID": "prod-client-id",
        "AUTH0_CLIENT_SECRET": "c" * 40,
        "AUTH0_SESSION_SECRET": "s" * 40,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
