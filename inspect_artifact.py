from pathlib import Path
import re


html = Path(r"artifacts\erro-20260515-210010.html").read_text(encoding="utf-8")

patterns = re.findall(
    r'<(?:button|span|i)[^>]+class="[^"]*(?:close|fa-times)[^"]*"[^>]*>',
    html,
    re.I,
)

for pattern in patterns[:80]:
    print(pattern)

print("COUNT=", len(patterns))
