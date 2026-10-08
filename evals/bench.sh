#!/bin/sh
# 채점 → 집계 → 새 버전을 앞에 두도록 정렬. 사용: sh evals/bench.sh output/skill-eval/iteration-N "<skill-creator 경로>"
set -e
IT="$(cd "$1" && pwd)"; SC="$2"
python3 "$(dirname "$0")/grade.py" "$IT"
(cd "$SC" && python3 -m scripts.aggregate_benchmark "$IT" --skill-name dart >/dev/null)
python3 - "$IT" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]) / "benchmark.json"
b = json.loads(p.read_text())
b["metadata"]["executor_model"] = "claude-opus-5-5"
b["metadata"]["runs_per_configuration"] = 1
rs = b["run_summary"]
new = next(k for k in rs if k.startswith("with_skill"))
base = next(k for k in rs if k != new and k != "delta")
b["run_summary"] = {new: rs[new], base: rs[base]}
d = {}
for m in ("pass_rate", "time_seconds", "tokens"):
    a, c = rs[new][m]["mean"], rs[base][m]["mean"]
    d[m] = f"{a - c:+.2f}" if m == "pass_rate" else f"{a - c:+.1f}" if m == "time_seconds" else f"{a - c:+.0f}"
b["run_summary"]["delta"] = d
b["runs"].sort(key=lambda r: (r["eval_id"], r["configuration"] != new))
p.write_text(json.dumps(b, ensure_ascii=False, indent=2))
s = b["run_summary"]
f = lambda k, m: s[k][m]["mean"]
print(f"pass_rate  {new} {f(new,'pass_rate'):.0%}  vs  {base} {f(base,'pass_rate'):.0%}  (delta {d['pass_rate']})")
print(f"time       {f(new,'time_seconds'):.0f}s vs {f(base,'time_seconds'):.0f}s   tokens {f(new,'tokens'):.0f} vs {f(base,'tokens'):.0f}")
PY
# benchmark.md도 새 버전이 앞에 오도록 json에서 다시 쓴다
(cd "$SC" && python3 -c "
import json, sys
from scripts.aggregate_benchmark import generate_markdown
b = json.load(open(sys.argv[1] + '/benchmark.json'))
open(sys.argv[1] + '/benchmark.md', 'w').write(generate_markdown(b))
" "$IT")
