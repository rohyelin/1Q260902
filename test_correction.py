import json
import os

from openai import OpenAI

BASE = os.path.expanduser("~/Desktop/lecture-script-matcher/backend")

# .env 읽기
env = {}
for line in open(os.path.join(BASE, ".env"), encoding="utf-8"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v.strip()

key = env["OPENAI_API_KEY"]
model = env.get("OPENAI_TEXT_MODEL", "gpt-5.6-terra")
print("모델:", model)

# base whisper 전사본(교정 전) + 슬라이드 불러오기
job = os.path.join(BASE, "storage/jobs/f0e0c0c3-87a4-4dde-a6ab-70e6e1f8a3e9")
chunks = json.load(open(os.path.join(job, "chunks.json"), encoding="utf-8"))
pages = json.load(open(os.path.join(job, "pages.json"), encoding="utf-8"))
slide_terms = " ".join(p.get("text", "") for p in pages)[:3000]

sample = chunks[:25]
originals = [c["text"] for c in sample]
numbered = "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(originals))

system_prompt = (
    "당신은 의학 강의 음성 전사 교정 전문가입니다. 여러 구간으로 나뉜 한 강의의 전사 전체가 주어집니다. "
    "강의 전체 맥락과 아래 슬라이드 용어를 참고해 발음 오인식으로 잘못 적힌 단어를 교정하세요. "
    "문맥상 명백한 의학 용어는 적극적으로 바로잡되, 없는 내용을 새로 지어내지 마세요. "
    "각 구간 번호를 유지하고 교정된 문장만 JSON으로 반환하세요."
)
user_prompt = (
    f"슬라이드 용어(발췌): {slide_terms}\n\n"
    f"교정할 전사(구간별):\n{numbered}\n\n"
    '형식: {"1": "...", "2": "..."}'
)

client = OpenAI(api_key=key)
try:
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=8000,
        response_format={"type": "json_object"},
    )
    data = json.loads(r.choices[0].message.content or "{}")
    print("\n=== 교정 결과 (앞 8개) ===\n")
    for i in range(min(8, len(originals))):
        print("원문:", originals[i][:100])
        print("교정:", str(data.get(str(i + 1), "(없음)"))[:100])
        print()
    print("성공 — gpt-5.6-terra가 새 파라미터로 정상 작동합니다.")
except Exception as e:
    print("에러:", type(e).__name__, str(e)[:400])
