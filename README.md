# 1Q / Lecture Script Matcher

교수님 수업 녹음본과 강의록 PDF를 업로드하면, AI가 페이지별로 관련 스크립트를 자동 매칭해 보여주는 해커톤 MVP 웹앱입니다.

**한 번의 클릭으로 완성되는 필기** — 왼쪽에는 PDF 페이지 미리보기, 오른쪽에는 해당 페이지와 매칭된 교수님 발화 스크립트가 표시됩니다.

> 해커톤 MVP에서는 로컬 파일 저장을 사용합니다. 실제 서비스에서는 object storage와 DB가 필요합니다.

## 기능

- 로컬 **faster-whisper**로 음성 전사 (timestamp 포함)
- **PyMuPDF**로 PDF 페이지별 텍스트 + PNG 이미지 추출
- PDF 용어집 **fuzzy 교정** + **LLM 문맥 교정** (전사 오류 수정)
- **GPT Vision caption**으로 그림 위주 슬라이드 설명 생성 → embedding 보강
- **OpenAI Embedding** + BM25 + anchor term으로 페이지-스크립트 매칭
- chunk **전역 exclusivity** (최대 2개 연속 페이지), **저신뢰 carry-over** (score < 0.35)
- 시간 순서 제약(greedy monotonic selection) 적용
- 가독성 모드(문어체 변환), 중요 키워드 하이라이트
- Markdown / JSON 다운로드

## 프로젝트 구조

```
lecture-script-matcher/
├── backend/          # FastAPI + faster-whisper
├── frontend/         # Next.js + Tailwind
└── README.md
```

## 실행 방법

### 1. Backend 설정

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 설정
```

### 2. Backend 실행

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:3000 접속

## Backend .env 설정

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 키 (embedding, polishing) | (필수) |
| `OPENAI_EMBEDDING_MODEL` | Embedding 모델 | `text-embedding-3-small` |
| `OPENAI_TEXT_MODEL` | 교정·가독성 모드용 텍스트 모델 | `gpt-4o-mini` |
| `OPENAI_VISION_MODEL` | 슬라이드 vision caption 모델 | `gpt-4o-mini` |
| `WHISPER_MODEL` | faster-whisper 모델 | `small` |
| `WHISPER_DEVICE` | `cpu` 또는 `cuda` | `cpu` |
| `WHISPER_COMPUTE_TYPE` | `int8` (cpu) / `float16` (cuda) | `int8` |
| `JOB_STORAGE_DIR` | 작업 파일 저장 경로 | `./storage/jobs` |

> `OPENAI_API_KEY`는 backend `.env`에서만 사용됩니다. 프론트엔드에 노출되지 않습니다.

## API

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/jobs` | audio + PDF 업로드, job 생성 |
| `GET` | `/api/jobs/{job_id}/status` | 처리 상태 polling |
| `GET` | `/api/jobs/{job_id}/result` | 매칭 결과 JSON |
| `GET` | `/api/jobs/{job_id}/pages/{n}.png` | PDF 페이지 이미지 |
| `GET` | `/api/jobs/{job_id}/download.md` | Markdown 다운로드 |
| `GET` | `/api/jobs/{job_id}/download.json` | JSON 다운로드 |

### POST /api/jobs (multipart/form-data)

- `audio_file`: mp3, m4a, wav, mp4, webm
- `pdf_file`: pdf
- `readability_mode`: boolean
- `highlight_mode`: boolean
- `background_color`, `text_color`, `text_size`: optional

## Mock UI 테스트

백엔드 없이 프론트엔드 UI만 확인하려면:

1. `npm run dev` 실행
2. 결과 페이지에서 오류 시 **Mock 결과 보기** 클릭
3. 또는 `/result/sample` 접속 후 Mock 버튼 사용

`frontend/public/sample_result.json`에 샘플 데이터가 있습니다.

## Known Limitations

- **이미지 기반 PDF**는 OCR 없이 텍스트 추출이 안 될 수 있습니다.
- 교수님이 **페이지 순서와 다르게** 설명하면 매칭이 틀릴 수 있습니다.
- **faster-whisper 모델 크기**에 따라 속도와 정확도가 달라집니다.
- PDF 위 텍스트 **overlay**는 현재 MVP 범위에서 제외되었습니다.
- Celery, Redis, DB, 로그인, OCR, 결제 기능은 포함되지 않습니다.

## 기술 스택

**Frontend:** Next.js, TypeScript, Tailwind CSS  
**Backend:** FastAPI, faster-whisper, PyMuPDF, OpenAI SDK, rank-bm25, numpy
