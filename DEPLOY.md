# 웹 배포 가이드 (해커톤 발표용)

이 프로젝트는 **프론트(Next.js) → Vercel**, **백엔드(FastAPI+Whisper) → Railway** 조합을 권장합니다.

> Vercel만으로는 Whisper 전사·PDF 처리 백엔드를 돌릴 수 없습니다. 프론트 URL만 제출하면 API가 동작하지 않습니다.

---

## 1. GitHub에 코드 올리기

```bash
cd hackerton/lecture-script-matcher
git init
git add .
git commit -m "Lecture Script Matcher - hackathon demo"
# GitHub에서 새 repo 생성 후:
git remote add origin https://github.com/YOUR_USER/lecture-script-matcher.git
git branch -M main
git push -u origin main
```

`.env` 파일은 올라가지 않습니다. API 키는 각 플랫폼 환경변수에만 넣으세요.

---

## 2. 백엔드 배포 (Railway)

1. [railway.app](https://railway.app) 로그인 → **New Project** → **Deploy from GitHub repo**
2. 저장소 선택 후 **Root Directory**를 `backend`로 설정
3. **Variables**에 아래 추가:

| 변수 | 예시 |
|------|------|
| `OPENAI_API_KEY` | `sk-...` |
| `OPENAI_TEXT_MODEL` | `gpt-4o-mini` |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` |
| `WHISPER_MODEL` | `base` |
| `WHISPER_BEAM_SIZE` | `3` (발표용 속도 우선) |

4. 배포 완료 후 **Public URL** 복사 (예: `https://lecture-matcher-production.up.railway.app`)
5. 헬스체크: `https://YOUR-BACKEND.up.railway.app/health` → `{"status":"ok"}`

**무료 플랜 참고:** CPU 전사는 5~10분 강의도 수 분 걸릴 수 있습니다. 발표 전 **짧은 샘플(1~2분 오디오)** 로 한 번 돌려 보세요.

---

## 3. 프론트 배포 (Vercel)

1. [vercel.com](https://vercel.com) 로그인 → **Add New Project** → GitHub repo 연결
2. 설정:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js
3. **Environment Variables**:

| 변수 | 값 |
|------|-----|
| `NEXT_PUBLIC_API_URL` | Railway 백엔드 URL (슬래시 없이) |

4. **Deploy** 클릭
5. 배포 URL 예: `https://lecture-script-matcher.vercel.app`

### CLI로 배포 (선택)

```bash
cd frontend
npx vercel login
npx vercel --prod
# 환경변수는 Vercel 대시보드에서 NEXT_PUBLIC_API_URL 설정
```

---

## 4. CORS (백엔드)

`*.vercel.app` 도메인은 자동 허용됩니다. 커스텀 도메인을 쓰면 Railway Variables에 추가:

```
CORS_ORIGINS=https://your-app.vercel.app,https://www.your-domain.com
```

---

## 5. 발표용 데모 링크

| 용도 | URL |
|------|-----|
| **운영진 제출용 (메인)** | Vercel URL |
| 샘플 결과 미리보기 | `https://YOUR-VERCEL.vercel.app/result/demo` |
| 실제 업로드 시연 | Vercel 메인 페이지에서 PDF+오디오 업로드 |

`/result/demo` 는 서버 없이 샘플 JSON으로 UI만 보여 줍니다.

---

## 6. 로컬과 동일하게 테스트

```bash
# 터미널 1 - 백엔드
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 터미널 2 - 프론트 (프로덕션 모드 시뮬레이션)
cd frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build && npm start -p 3010
```

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| 업로드 시 CORS 에러 | `NEXT_PUBLIC_API_URL` 확인, Railway `CORS_ORIGINS`에 Vercel URL 추가 |
| 이미지 안 보임 | 백엔드 URL이 맞는지, `apiUrl`이 적용됐는지 확인 |
| 전사가 너무 느림 | `WHISPER_BEAM_SIZE=1`, 짧은 오디오 샘플 사용 |
| Railway 빌드 실패 | `backend` 루트 디렉터리·Dockerfile 경로 확인 |
