"""Smoke test: call the router with your real keys and see who answers.

    cd backend
    python -m scripts.smoke_test              # uses MODE from .env
    python -m scripts.smoke_test path/to/plan.png   # also tests vision
"""
import sys
from pathlib import Path

from app.router.model_router import AllProvidersFailed, get_router


def main():
    r = get_router()
    print(f"MODE = {r.s.mode}")

    try:
        print("ask():", r.ask("Say hello in five words.")[:200])
        print("  answered by:", r.last_provider)
        print("ask_json():", r.ask_json('Return {"rooms": ["kitchen", "bedroom"]}'))
        print("  answered by:", r.last_provider)
    except AllProvidersFailed as e:
        print("Chat failed on every provider:\n ", e)
        sys.exit(1)

    if len(sys.argv) > 1:
        img = Path(sys.argv[1])
        mime = "image/jpeg" if img.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        try:
            out = r.see("List the rooms you can see as {\"rooms\": [names]}.",
                        img.read_bytes(), mime)
            print("see():", out, "\n  answered by:", r.last_provider)
        except AllProvidersFailed as e:
            print("Vision failed on every provider:\n ", e)

    print("Done.")


if __name__ == "__main__":
    main()
