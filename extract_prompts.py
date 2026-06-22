import json
import re

log_path = r"C:\Users\HP\.gemini\antigravity-ide\brain\49d41bdc-7caa-40f7-b9cc-8b6efcc1b460\.system_generated\logs\transcript.jsonl"
output_path = r"C:\Users\HP\.gemini\antigravity-ide\scratch\crime-intel-platform\frontend_prompts.md"

prompts = []

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("source") == "USER_EXPLICIT" and data.get("type") == "USER_INPUT":
                content = data.get("content", "")
                if "Prompt F" in content or "F1" in content or "Phase F" in content:
                    prompts.append(content)
        except Exception as e:
            pass

print(f"Found {len(prompts)} matches.")

with open(output_path, "w", encoding="utf-8") as out:
    out.write("# Extracted Frontend Prompts\n\n")
    for i, p in enumerate(prompts):
        out.write(f"## Match {i+1}\n\n")
        out.write(p)
        out.write("\n\n---\n\n")

print(f"Written prompts to {output_path}")
