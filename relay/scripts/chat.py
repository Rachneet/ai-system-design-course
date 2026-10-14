"""Chat with a running Relay API from the terminal: uv run python -m scripts.chat --customer c_77

Needs RELAY_AUTH_MODE=dev and RELAY_DEV_JWT_SECRET on both the API and this script.
"""

import argparse
import json

import httpx

from scripts.dev_token import mint


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", default="c_77")
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()
    session_id = None
    token = mint(args.customer)
    with httpx.Client(timeout=120) as client:
        while True:
            try:
                message = input("\nyou> ").strip()
            except EOFError:
                break
            if not message:
                continue
            body = {"message": message} | ({"session_id": session_id} if session_id else {})
            print("relay> ", end="", flush=True)
            with client.stream(
                "POST", f"{args.url}/chat", json=body, headers={"Authorization": f"Bearer {token}"}
            ) as r:
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    print(event.get("text", ""), end="", flush=True)
                    session_id = event.get("session_id", session_id)
                    if "error" in event:
                        print(event["error"])
            print()


if __name__ == "__main__":
    main()
