import os
import re

router_dir = r"C:\Users\HP\.gemini\antigravity-ide\scratch\crime-intel-platform\app\routers"
endpoints = []

for filename in os.listdir(router_dir):
    if filename.endswith(".py") and filename != "__init__.py":
        filepath = os.path.join(router_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r'@router\.(get|post|put|delete)\("([^"]+)"', line)
                if match:
                    method, path = match.groups()
                    endpoints.append((filename, method.upper(), path))

for fn, m, p in sorted(endpoints):
    print(f"{fn:20} | {m:6} | {p}")
