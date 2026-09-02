"""교정 모델 비교 스크립트 (멀티 프로바이더 · 실험용)

저장된 전사본(chunks.json)에 여러 모델을 돌려 교정 결과를 나란히 비교한다.
Whisper는 다시 안 돌린다 — 이미 전사된 golden set을 재사용한다.
OpenAI / DeepSeek / Claude 를 같은 방식(OpenAI 호환)으로 호출한다.

실행:
    cd ~/Desktop/lecture-script-matcher/backend && source .venv/bin/activate
    cd ~/Desktop/lecture-script-matcher && python test_correction_compare.py

필요한 키 (backend/.env). 있는 것만 자동으로 돌고, 없으면 건너뜀:
    OPENAI_API_KEY    → terra, luna, gpt-4.1-mini, gpt-4.1-nano
    DEEPSEEK_API_KEY  → deepseek  (※ 잔액 충전 필요)
    ANTHROPIC_API_KEY → claude-haiku, claude-sonnet

결과:
    - 콘솔: 앞 6개 조각 비교 + 모델별 시간/토큰/대략 원가
    - correction_compare.md : 전체 비교 저장 (모든 모델 끝나야 저장됨)
"""

import json
import os
import sys
import time

BASE = os.path.expanduser("~/Desktop/lecture-script-matcher/backend")
sys.path.insert(0, BASE)

# ---------------- 설정 ----------------
JOB_ID = "f0e0c0c3-87a4-4dde-a6ab-70e6e1f8a3e9"  # 골든셋 강의 (RTA)
N_CHUNKS = 40            # 앞에서 몇 조각 교정할지
FX = 1460               # 원/달러 (2026년 7월 기준, 대략)
TIMEOUT = 120           # 모델 하나가 이 초 넘게 멈추면 에러 처리하고 넘어감
OUT_MD = os.path.expanduser("~/Desktop/lecture-script-matcher/correction_compare.md")
# --------------------------------------

env = {}
for line in open(os.path.join(BASE, ".env"), encoding="utf-8"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v.strip()

reference_model = env.get("OPENAI_TEXT_MODEL", "gpt-5.6-terra")  # 정답지(현재 모델)

# 비교 모델 목록. price = (입력,출력) $/1M 토큰. 싼 것부터 배치.
PROVIDERS = [
    {"label": f"{reference_model} (정답지)", "key_env": "OPENAI_API_KEY", "base_url": None,
     "model": reference_model, "token_param": "max_completion_tokens", "max_out": 16000,
     "json": True, "price": (2.5, 15.0)},          # gpt-5.6-terra 공식가
    {"label": "gpt-5.6-luna", "key_env": "OPENAI_API_KEY", "base_url": None,
     "model": "gpt-5.6-luna", "token_param": "max_completion_tokens", "max_out": 16000,
     "json": True, "price": (1.0, 6.0)},
    {"label": "gpt-4.1-mini", "key_env": "OPENAI_API_KEY", "base_url": None,
     "model": "gpt-4.1-mini", "token_param": "max_completion_tokens", "max_out": 16000,
     "json": True, "price": (0.40, 1.60)},
    {"label": "gpt-4.1-nano", "key_env": "OPENAI_API_KEY", "base_url": None,
     "model": "gpt-4.1-nano", "token_param": "max_completion_tokens", "max_out": 16000,
     "json": True, "price": (0.10, 0.40)},
    {"label": "deepseek-v4-flash", "key_env": "DEEPSEEK_API_KEY", "base_url": "https://api.deepseek.com",
     "model": "deepseek-v4-flash", "token_param": "max_tokens", "max_out": 8000,
     "json": True, "price": (0.14, 0.28)},
    {"label": "deepseek-v4-pro", "key_env": "DEEPSEEK_API_KEY", "base_url": "https://api.deepseek.com",
     "model": "deepseek-v4-pro", "token_param": "max_tokens", "max_out": 8000,
     "json": True, "price": (0.435, 0.87)},
    {"label": "claude-haiku-4-5", "key_env": "ANTHROPIC_API_KEY", "base_url": "https://api.anthropic.com/v1/",
     "model": "claude-haiku-4-5", "token_param": "max_tokens", "max_out": 8000,
     "json": False, "price": (1.0, 5.0)},
    {"label": "claude-sonnet-4-6", "key_env": "ANTHROPIC_API_KEY", "base_url": "https://api.anthropic.com/v1/",
     "model": "claude-sonnet-4-6", "token_param": "max_tokens", "max_out": 8000,
     "json": False, "price": (3.0, 15.0)},
    {"label": "gemini-3.5-flash-lite", "key_env": "GEMINI_API_KEY", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "model": "gemini-3.5-flash-lite", "token_param": "max_tokens", "max_out": 8000,
     "json": True, "price": (0.30, 2.50)},
    {"label": "gemini-3.6-flash", "key_env": "GEMINI_API_KEY", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "model": "gemini-3.6-flash", "token_param": "max_tokens", "max_out": 8000,
     "json": True, "price": (1.50, 7.50)},
]

from openai import OpenAI
from app.services.correction import (
    build_glossary,
    CORRECTION_BATCH_SYSTEM_PROMPT,
    _format_glossary_snippet,
    _parse_corrected_json,
)

job_dir = os.path.join(BASE, "storage/jobs", JOB_ID)
all_chunks = json.load(open(os.path.join(job_dir, "chunks.json"), encoding="utf-8"))
total_chunks = len(all_chunks)
chunks = all_chunks[:N_CHUNKS]
pages = json.load(open(os.path.join(job_dir, "pages.json"), encoding="utf-8"))

glossary = build_glossary(pages)
originals = [c["text"] for c in chunks]
numbered = "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(originals))
user_prompt = (
    f"참고 용어집: {_format_glossary_snippet(glossary, limit=300)}\n\n"
    "아래는 한 강의 전사의 연속된 구간 전체다. 전체 흐름과 용어집을 참고해 "
    "발음 오인식으로 잘못 적힌 부분을 교정하라. 각 구간의 번호는 그대로 유지하고, "
    '교정된 문장만 담아 JSON으로 반환하라. 형식: {"1": "...", "2": "..."}\n\n'
    f"{numbered}"
)

results: dict[str, list[str]] = {}
stats: dict[str, str] = {}
labels: list[str] = []

for p in PROVIDERS:
    label = p["label"]
    key = env.get(p["key_env"], "")
    if not key:
        print(f"\n### {label} — 키({p['key_env']}) 없음 → 건너뜀")
        continue
    labels.append(label)
    print(f"\n### {label} 교정 중 ({N_CHUNKS}조각)...")
    client = OpenAI(api_key=key, base_url=p["base_url"]) if p["base_url"] else OpenAI(api_key=key)
    kwargs = {p["token_param"]: p["max_out"], "timeout": TIMEOUT}
    if p["json"]:
        kwargs["response_format"] = {"type": "json_object"}
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=p["model"],
            messages=[
                {"role": "system", "content": CORRECTION_BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            **kwargs,
        )
        corrected = _parse_corrected_json(
            resp.choices[0].message.content or "", len(chunks), originals
        )
        dt = time.time() - t0
        results[label] = corrected
        u = resp.usage
        pin = getattr(u, "prompt_tokens", 0) or 0
        pout = getattr(u, "completion_tokens", 0) or 0
        line = f"{dt:.1f}s · 입력 {pin} / 출력 {pout} 토큰"
        if p["price"]:
            cost_run = pin / 1e6 * p["price"][0] + pout / 1e6 * p["price"][1]
            scale = total_chunks / max(N_CHUNKS, 1)
            won_lecture = cost_run * scale * FX
            line += f" · 강의당 ~{won_lecture:,.0f}원 · 120강의/월 ~{won_lecture * 120:,.0f}원"
        stats[label] = line
        print(f"  완료 — {stats[label]}")
    except Exception as e:
        results[label] = ["(에러)"] * len(chunks)
        stats[label] = f"에러: {type(e).__name__}: {str(e)[:200]}"
        print(f"  {stats[label]}")

print("\n" + "=" * 60)
print("앞 6개 조각 비교")
print("=" * 60)
for i in range(min(6, len(originals))):
    print(f"\n[{i + 1}] 원문 : {originals[i][:110]}")
    for m in labels:
        print(f"    {m} : {str(results[m][i])[:110]}")

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(f"# 교정 모델 비교 — {JOB_ID[:8]} (앞 {N_CHUNKS}조각)\n\n")
    for m in labels:
        f.write(f"- **{m}**: {stats.get(m, '')}\n")
    f.write("\n---\n\n")
    for i in range(len(originals)):
        f.write(f"## [{i + 1}]\n\n")
        f.write(f"**원문**\n\n> {originals[i]}\n\n")
        for m in labels:
            f.write(f"**{m}**\n\n> {results[m][i]}\n\n")
        f.write("\n")

print(f"\n전체 비교 저장됨 → {OUT_MD}")
