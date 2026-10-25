"""Refresh all catalogue data without changing any Telegram messages."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for script in ("fetch_channel.py", "build_catalog.py"):
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script)], cwd=ROOT, check=True)
    print("Готово. Каталог обновлён локально. Публикация: git add, git commit, git push.")


if __name__ == "__main__":
    main()
