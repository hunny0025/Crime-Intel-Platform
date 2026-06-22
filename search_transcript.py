import json

log_path = r"C:\Users\HP\.gemini\antigravity-ide\brain\49d41bdc-7caa-40f7-b9cc-8b6efcc1b460\.system_generated\logs\transcript.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if "prompt f" in line.lower() or "phase f" in line.lower():
            print(f"Line {idx+1}: len={len(line)}")
            try:
                data = json.loads(line)
                print(f"  source={data.get('source')} type={data.get('type')}")
                content = data.get("content", "")
                print(f"  content preview: {content[:200]}")
            except Exception as e:
                print(f"  parse error: {e}")
