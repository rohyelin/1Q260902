# 설치 안내

강의록 PDF + 전사본을 넣으면, 슬라이드마다 해당 부분의 교수님 말이 붙은 PDF를 만들어 주는 프로그램이에요.

한 번만 설치해 두면 그다음부터는 터미널 두 줄로 켤 수 있어요. 처음 설치는 20~30분쯤 걸려요.

---

## 0. 미리 준비할 것

**OpenAI API 키** (필수)

이 프로그램은 OpenAI를 사용하고, **비용은 키 주인에게 청구돼요.** 그래서 본인 키가 꼭 필요해요.

1. https://platform.openai.com 가입
2. Billing에서 카드 등록 후 $5~10 정도 충전
3. API keys → Create new secret key → 복사 (`sk-proj-...`)

> 강의 1개당 대략 300~400원이에요. 처음엔 $5만 넣고 몇 강 돌려보면서 감을 잡으세요.

**개발 도구**

터미널(응용 프로그램 → 유틸리티 → 터미널)을 열고 아래를 하나씩 붙여넣어 확인해요.

```bash
python3 --version    # 3.11 이상
node --version       # 18 이상
git --version
```

`command not found`가 뜨면 없는 거예요. Mac이면 [Homebrew](https://brew.sh) 설치 후:

```bash
brew install python node git
```

---

## 1. 코드 받기

```bash
cd ~/Desktop
git clone https://github.com/jelee2008-prog/lecture-script-matcher-personal.git
cd lecture-script-matcher-personal
```

## 2. 백엔드 설치

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`pip install`이 몇 분 걸려요. 오류 없이 끝나면 성공이에요.

## 3. API 키 넣기

```bash
cp .env.example .env
open -e .env
```

메모장 같은 창이 열리면 맨 위 `OPENAI_API_KEY=sk-...` 의 `sk-...` 자리에 아까 복사한 키를 붙여넣고 저장(⌘S)해요. `=` 양옆에 띄어쓰기나 따옴표는 넣지 마세요.

## 4. 프론트엔드 설치

터미널에서:

```bash
cd ../frontend
npm install
```

---

## 실행하기 (매번 이렇게)

터미널 **두 개**가 필요해요. (⌘T로 새 탭을 열면 돼요.)

**터미널 1 — 백엔드**

```bash
cd ~/Desktop/lecture-script-matcher-personal/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**터미널 2 — 화면**

```bash
cd ~/Desktop/lecture-script-matcher-personal/frontend
npm run dev
```

브라우저에서 **http://localhost:3000** 접속.

끌 때는 각 터미널에서 `Ctrl+C`.

---

## 쓰는 법

### 여러 강의 한꺼번에

첫 화면 오른쪽 위 **"여러 강의 한번에"** 를 눌러요.

1. 강의별로 **전사본**(txt·docx·pdf)과 **강의록 PDF**를 한 줄씩 고르기
2. 위쪽에서 정리본 형식과 옵션 선택
   - **가독성 (문어체 변환)** — 말한 그대로("그니까 이게요…") 대신 글말로 다듬어요
   - **핵심 하이라이트** — 중요한 부분 강조
3. **전체 시작**

강의 하나에 5~10분쯤 걸려요. 창을 닫아도 백그라운드에서 계속되고, 다시 열면 목록이 그대로 있어요. **단, 터미널(백엔드)은 켜져 있어야 해요.**

완료되면 **결과 보기** → 원하는 형태로 PDF 다운로드.

### 녹음 파일로 하기

첫 화면에서 녹음 파일을 올리면 음성 인식부터 해줘요. 다만 이때 음성 인식 모델(약 3GB)을 처음 한 번 자동으로 받아요. 그게 부담되면 `.env`에서 `WHISPER_MODEL=large-v3`를 `base`로 바꾸면 훨씬 가벼워요 (대신 정확도는 떨어져요).

전사본을 직접 올리는 방식이면 이 모델은 아예 받지 않아요.

---

## 잘 안 될 때

**`localhost:3000`이 안 열려요**
터미널 2에서 `npm run dev`가 돌고 있는지 확인. 포트가 이미 쓰이는 중이면 3001 같은 다른 번호로 열리니 터미널에 찍힌 주소를 보세요.

**"업로드에 실패했습니다"**
터미널 1(백엔드)이 꺼져 있을 때 나요. 다시 켜 주세요.

**처리 중 갑자기 멈춰요**
백엔드 터미널에 빨간 글씨가 있는지 보세요. `insufficient_quota`면 OpenAI 잔액이 떨어진 거예요.

**`command not found: python3`**
0번 항목의 개발 도구 설치를 안 한 거예요.

---

## 참고

`notion_sync.py`와 `sync.sh`는 노션 데이터베이스와 연동하는 별도 기능이라 신경 쓰지 않아도 돼요. 웹 화면 사용과는 무관하고, 설정하지 않으면 그냥 동작하지 않아요.
