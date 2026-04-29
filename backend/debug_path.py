import os
from pathlib import Path

# Simulate main.py logic
FILE_PATH = Path("c:/Users/Lenovo/OneDrive/Desktop/CapstoneSEM8/Project/backend/app/main.py")
FRONTEND_DIR = FILE_PATH.resolve().parent.parent.parent / "frontend"

print(f"FILE_PATH: {FILE_PATH}")
print(f"FILE_PATH.resolve(): {FILE_PATH.resolve()}")
print(f"FRONTEND_DIR: {FRONTEND_DIR}")
print(f"FRONTEND_DIR exists: {FRONTEND_DIR.exists()}")

if FRONTEND_DIR.exists():
    print("Contents of FRONTEND_DIR:")
    for f in os.listdir(FRONTEND_DIR):
        print(f" - {f}")
        if f == "index.html":
            with open(FRONTEND_DIR / f, 'r', encoding='utf-8') as h:
                content = h.read()
                print(f"   [index.html Title]: {content.split('<title>')[1].split('</title>')[0] if '<title>' in content else 'No title'}")
