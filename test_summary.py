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
print("핵심정리 모델:", model)

SUMMARY_SYSTEM_PROMPT = (
    "당신은 의대생을 위한 강의 노트 정리 도우미입니다. "
    "특정 강의 슬라이드와, 그 슬라이드를 설명하는 동안 교수님이 실제로 말한 전사문이 주어집니다. "
    "전사문에서 이 슬라이드의 개념과 관련해 교수님이 강조·설명·비교·예시로 든 내용을 "
    "복습용 개조식 노트로 풍부하게 정리하세요. "
    "각 항목은 명사형 종결체로 끝내고, 5~10개 항목으로 작성하세요. "
    '출력은 반드시 JSON 형식: {"points": ["...", "..."]}'
)

# 방금 완료된 작업 데이터 재사용 (전사·매칭 이미 돼 있음)
job = os.path.join(BASE, "storage/jobs/65f53675-ab07-461c-901f-659813df40e6")
result = json.load(open(os.path.join(job, "result.json"), encoding="utf-8"))

# 스크립트가 있는 페이지 2개만 테스트
tested = 0
client = OpenAI(api_key=key)
for page in result["pages"]:
    scripts = page.get("matched_scripts", [])
    if not scripts:
        continue
    script_text = "\n".join(
        f"[{s.get('start_time', '')}] {s.get('corrected_text') or s.get('clean_text') or s.get('raw_text', '')}"
        for s in scripts
    ).strip()
    slide_info = f"슬라이드 텍스트:\n{page.get('page_text', '').strip()}"
    if page.get("page_caption"):
        slide_info += f"\n\n슬라이드 시각 설명:\n{page['page_caption'].strip()}"
    user_prompt = (
        f"{slide_info}\n\n"
        f"이 슬라이드를 설명할 때 교수님의 전사문:\n{script_text}\n\n"
        "위 전사문에서 이 슬라이드 개념과 관련된 핵심 내용을 개조식으로 정리하세요."
    )
    print(f"\n===== 슬라이드 {page.get('page')} =====")
    try:
        r = client.chat.completions.create(
            model=model,
            max_completion_tokens=16000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = r.choices[0].message.content or "{}"
        points = json.loads(content).get("points", [])
        if points:
            for p in points[:6]:
                print(" -", p)
            print(f"  → 항목 {len(points)}개 생성됨 ✅")
        else:
            print("  → 여전히 빈 결과 (points 없음) ⚠️  finish_reason:", r.choices[0].finish_reason)
    except Exception as e:
        print("  에러:", type(e).__name__, str(e)[:300])
    tested += 1
    if tested >= 2:
        break

print("\n완료 — 항목이 나오면 핵심정리 수정 성공입니다.")
