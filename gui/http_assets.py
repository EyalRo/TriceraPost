type AssetInfo = tuple[str, str]


def asset_info(path: str) -> AssetInfo | None:
    match path:
        case "/assets/style.css":
            return ("style.css", "text/css; charset=utf-8")
        case "/assets/icon.png":
            return ("icon.png", "image/png")
        case "/assets/app.js":
            return ("app.js", "text/javascript; charset=utf-8")
        case "/assets/settings.js":
            return ("settings.js", "text/javascript; charset=utf-8")
        case _:
            return None
