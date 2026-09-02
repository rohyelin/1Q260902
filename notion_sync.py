"""노션 강의 DB ↔ 필기조 AI 자동 동기화.

하루에 한 번 이걸 돌리면:
  1. 노션에서 `상태=전사완료` 이고 `필기조=시작 전`(또는 `오류`) 인 강의를 찾아
  2. 전사본·강의록을 내려받고
  3. 필기조 백엔드로 처리한 뒤
  4. 결과 PDF 2개를 (필요하면 압축해서) 노션 `필기조PDF` 칸에 올리고
  5. `필기조`를 `완료`로 바꾼다.

실행:
    ./sync.sh                     (권장 — 백엔드까지 알아서 띄움)
    python notion_sync.py         (백엔드가 이미 떠 있을 때)
    python notion_sync.py --dry-run   (뭘 처리할지 보기만 하고 아무것도 안 바꿈)

backend/.env 에 필요한 값:
    NOTION_TOKEN=ntn_...                  (notion.so/my-integrations 에서 발급)
    NOTION_DATA_SOURCE_ID=3b778f31-...    (기본값이 이미 들어 있음)
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
BACKEND_DIR = BASE / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------- 설정
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
# 각자 자기 노션 DB를 backend/.env 의 NOTION_DATA_SOURCE_ID 에 넣어 쓴다.
# (여기에 특정 DB를 박아두면 다른 사람이 남의 DB를 건드릴 수 있다)
DEFAULT_DATA_SOURCE_ID = ""

BACKEND_URL = "http://localhost:8000"

# 노션 속성 이름 (노션에서 이름을 바꾸면 여기도 바꿔야 한다)
P_TRANSCRIPT = "전사본"
P_LECTURE = "강의록"
P_OUTPUT = "필기조PDF"
P_STATUS = "상태"
P_NOTE = "필기조"
P_NAME = "이름"

STATUS_READY = "전사완료"
NOTE_TODO = "시작 전"
NOTE_RUNNING = "진행중"
NOTE_DONE = "완료"
NOTE_ERROR = "오류"

# 이 상태인 행을 집어간다.
#   오류   → 다음 실행 때 자동 재시도
#   진행중 → 지난번에 도중에 끊긴 행 (맥이 잠들거나 전원이 나간 경우). 하루 한 번
#            혼자 돌리는 용도라 두 번 겹칠 일이 없어서 그냥 다시 처리한다.
PICKUP = {NOTE_TODO, NOTE_ERROR, NOTE_RUNNING}

# 처리 옵션
NOTE_MODE = "summary"
READABILITY = True
HIGHLIGHT = True

# 노션 단일 업로드 한도는 20MB. 살짝 여유를 둔다.
MAX_UPLOAD_MB = 19.0

POLL_SECONDS = 5
JOB_TIMEOUT_SECONDS = 45 * 60

WORK_DIR = BASE / ".sync_tmp"


# ---------------------------------------------------------------- 유틸
def log(msg: str = "") -> None:
    print(msg, flush=True)


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def safe_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', "-", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "강의"


# ---------------------------------------------------------------- 노션
class Notion:
    def __init__(self, token: str, data_source_id: str):
        self.h = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
        }
        self.hj = {**self.h, "Content-Type": "application/json"}
        self.ds = data_source_id

    def _check(self, r: requests.Response, what: str) -> dict:
        if r.status_code >= 300:
            raise RuntimeError(f"{what} 실패 [{r.status_code}] {r.text[:400]}")
        return r.json()

    def rows(self) -> list[dict]:
        """처리 대상 행을 모두 가져온다 (페이지네이션 포함)."""
        out: list[dict] = []
        cursor = None
        while True:
            payload: dict = {
                "filter": {
                    "and": [
                        {"property": P_STATUS, "select": {"equals": STATUS_READY}},
                        {
                            "or": [
                                {"property": P_NOTE, "select": {"equals": s}}
                                for s in sorted(PICKUP)
                            ]
                        },
                    ]
                },
                "page_size": 100,
            }
            if cursor:
                payload["start_cursor"] = cursor
            r = requests.post(
                f"{NOTION_API}/data_sources/{self.ds}/query",
                headers=self.hj,
                json=payload,
                timeout=60,
            )
            data = self._check(r, "노션 조회")
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return out

    def set_select(self, page_id: str, prop: str, value: str) -> None:
        r = requests.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=self.hj,
            json={"properties": {prop: {"select": {"name": value}}}},
            timeout=60,
        )
        self._check(r, f"{prop} → {value}")

    def comment(self, page_id: str, text: str) -> None:
        try:
            requests.post(
                f"{NOTION_API}/comments",
                headers=self.hj,
                json={
                    "parent": {"page_id": page_id},
                    "rich_text": [{"text": {"content": text[:1900]}}],
                },
                timeout=60,
            )
        except Exception:
            pass  # 코멘트는 실패해도 본 작업을 막지 않는다.

    def upload(self, path: Path) -> str:
        """파일 하나를 노션에 올리고 file_upload id를 돌려준다."""
        created = self._check(
            requests.post(
                f"{NOTION_API}/file_uploads",
                headers=self.hj,
                json={"filename": path.name, "content_type": "application/pdf"},
                timeout=60,
            ),
            "업로드 생성",
        )
        upload_id = created["id"]
        with path.open("rb") as f:
            self._check(
                requests.post(
                    created.get("upload_url")
                    or f"{NOTION_API}/file_uploads/{upload_id}/send",
                    headers=self.h,
                    files={"file": (path.name, f, "application/pdf")},
                    timeout=600,
                ),
                "파일 전송",
            )
        return upload_id

    def attach(self, page_id: str, prop: str, uploads: list[tuple[str, str]]) -> None:
        """uploads = [(file_upload_id, 표시이름), ...] 를 파일 속성에 붙인다(덮어쓰기)."""
        files = [
            {"type": "file_upload", "file_upload": {"id": uid}, "name": name}
            for uid, name in uploads
        ]
        r = requests.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=self.hj,
            json={"properties": {prop: {"type": "files", "files": files}}},
            timeout=120,
        )
        self._check(r, "결과 첨부")


def prop_text(page: dict, name: str) -> str:
    p = (page.get("properties") or {}).get(name) or {}
    kind = p.get("type")
    value = p.get(kind)
    if kind in ("rich_text", "title") and isinstance(value, list):
        return "".join(i.get("plain_text", "") for i in value).strip()
    if kind == "select" and isinstance(value, dict):
        return (value.get("name") or "").strip()
    return ""


def prop_files(page: dict, name: str) -> list[tuple[str, str]]:
    """파일 속성에서 (표시이름, 다운로드 URL) 목록을 뽑는다."""
    p = (page.get("properties") or {}).get(name) or {}
    out: list[tuple[str, str]] = []
    for f in p.get("files") or []:
        url = (f.get("file") or {}).get("url") or (f.get("external") or {}).get("url")
        if url:
            out.append((f.get("name") or "file", url))
    return out


# ---------------------------------------------------------------- 백엔드
def backend_alive() -> bool:
    try:
        return requests.get(BACKEND_URL + "/", timeout=3).status_code < 500
    except Exception:
        return False


def run_job(transcript: Path, lecture: Path) -> str:
    with transcript.open("rb") as tf, lecture.open("rb") as pf:
        r = requests.post(
            f"{BACKEND_URL}/api/jobs",
            files={
                "transcript_file": (transcript.name, tf),
                "pdf_file": (lecture.name, pf, "application/pdf"),
            },
            data={
                "readability_mode": str(READABILITY).lower(),
                "highlight_mode": str(HIGHLIGHT).lower(),
                "summary_mode": "true",
                "note_mode": NOTE_MODE,
            },
            timeout=300,
        )
    if r.status_code >= 300:
        raise RuntimeError(f"작업 생성 실패 [{r.status_code}] {r.text[:300]}")
    return r.json()["job_id"]


def wait_job(job_id: str) -> None:
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    last = ""
    while time.time() < deadline:
        try:
            s = requests.get(
                f"{BACKEND_URL}/api/jobs/{job_id}/status", timeout=30
            ).json()
        except Exception:
            time.sleep(POLL_SECONDS)
            continue
        note = f"      {s.get('progress', 0):3d}%  {s.get('message', '')}"
        if note != last:
            log(note)
            last = note
        if s.get("status") == "done":
            return
        if s.get("status") == "error":
            raise RuntimeError(s.get("error") or s.get("message") or "처리 중 오류")
        time.sleep(POLL_SECONDS)
    raise RuntimeError("시간 초과 (45분)")


def fetch_pdf(
    job_id: str,
    layout: str | None,
    dest: Path,
    readability: bool = True,
    cover: dict[str, str] | None = None,
) -> None:
    # style=print → 웹 화면의 인쇄물과 같은 레이아웃 (백엔드에서 직접 렌더)
    params: dict[str, str] = {
        "readability": "true" if readability else "false",
        "style": "print",
    }
    if layout:
        params["layout"] = layout
    for k, v in (cover or {}).items():
        if v:
            params[f"cover_{k}"] = v
    with requests.get(
        f"{BACKEND_URL}/api/jobs/{job_id}/download.pdf",
        params=params,
        stream=True,
        timeout=600,
    ) as r:
        if r.status_code >= 300:
            raise RuntimeError(f"PDF 내려받기 실패 [{r.status_code}] {r.text[:200]}")
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


# ---------------------------------------------------------------- 본체
def process(notion: Notion, page: dict, idx: int, total: int) -> bool:
    page_id = page["id"]
    name = prop_text(page, P_NAME) or prop_text(page, "전사 담당") or "이름 없는 강의"

    log(f"\n[{idx}/{total}] {name}")

    transcripts = prop_files(page, P_TRANSCRIPT)
    lectures = prop_files(page, P_LECTURE)
    if not transcripts or not lectures:
        missing = []
        if not transcripts:
            missing.append(P_TRANSCRIPT)
        if not lectures:
            missing.append(P_LECTURE)
        msg = f"{' · '.join(missing)} 이(가) 비어 있어요."
        log(f"      건너뜀 — {msg}")
        notion.set_select(page_id, P_NOTE, NOTE_ERROR)
        notion.comment(page_id, f"[필기조 AI] {msg}")
        return False

    work = WORK_DIR / page_id.replace("-", "")
    work.mkdir(parents=True, exist_ok=True)

    try:
        notion.set_select(page_id, P_NOTE, NOTE_RUNNING)

        t_name, t_url = transcripts[0]
        l_name, l_url = lectures[0]
        # 결과 파일명은 강의록 파일명을 그대로 따른다.
        stem = safe_filename(Path(l_name).stem) or safe_filename(name)
        t_path = work / f"transcript{Path(t_name).suffix.lower() or '.txt'}"
        l_path = work / "lecture.pdf"

        log("      전사본·강의록 내려받는 중...")
        download(t_url, t_path)
        download(l_url, l_path)

        log("      필기조 AI 처리 중...")
        job_id = run_job(t_path, l_path)
        wait_job(job_id)

        # 같은 작업 결과에서 세 가지로 뽑는다 (AI는 한 번만 돌린다).
        #   _스크립트                  — 슬라이드 + 스크립트만 (전사본 그대로)
        #   _스크립트+핵심정리 (문어체) — 문어체로 다듬은 스크립트 + 핵심정리
        #   _스크립트+핵심정리 (원문)   — 업로드한 전사본 그대로 + 핵심정리
        outputs: list[tuple[str, str]] = []
        targets = [
            ("script_side", False, f"{stem}_스크립트.pdf"),
            ("summary_script", True, f"{stem}_스크립트+핵심정리 (문어체).pdf"),
            ("summary_script", False, f"{stem}_스크립트+핵심정리 (원문).pdf"),
        ]
        # 표지에 들어갈 정보 — 노션 행에서 가져온다
        cover = {
            "session": prop_text(page, "블록") or "",
            "title": name,
            "professor": prop_text(page, "교수님") or "",
        }

        for layout, readable, filename in targets:
            pdf = work / filename
            fetch_pdf(job_id, layout, pdf, readability=readable, cover=cover)

            size = pdf.stat().st_size / 1_000_000
            if size > MAX_UPLOAD_MB:
                from app.services.pdf_compress import compress_in_place

                report = compress_in_place(pdf, max_mb=MAX_UPLOAD_MB)
                log(f"      압축: {filename} — {report}")
                size = pdf.stat().st_size / 1_000_000
                if size > 20:
                    raise RuntimeError(
                        f"{filename} 이(가) 압축 후에도 {size:.1f}MB 라 노션에 못 올려요."
                    )

            log(f"      업로드: {filename} ({size:.1f}MB)")
            outputs.append((notion.upload(pdf), filename))

        notion.attach(page_id, P_OUTPUT, outputs)
        notion.set_select(page_id, P_NOTE, NOTE_DONE)
        log("      ✅ 완료")
        return True

    except Exception as exc:
        log(f"      ❌ 실패 — {exc}")
        try:
            notion.set_select(page_id, P_NOTE, NOTE_ERROR)
            notion.comment(page_id, f"[필기조 AI] 실패: {exc}")
        except Exception:
            pass
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="노션 ↔ 필기조 AI 동기화")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="처리 대상만 보여주고 아무것도 바꾸지 않는다",
    )
    ap.add_argument("--limit", type=int, default=0, help="최대 몇 개만 처리")
    args = ap.parse_args()

    env = load_env()
    token = env.get("NOTION_TOKEN", "")
    if not token:
        log("NOTION_TOKEN 이 backend/.env 에 없어요.")
        log("  1) https://www.notion.so/my-integrations 에서 통합을 만들고 토큰 복사")
        log("  2) 노션 DB 페이지 → ··· → 연결 → 만든 통합 추가")
        log("  3) backend/.env 에  NOTION_TOKEN=ntn_...  추가")
        return 1

    ds = env.get("NOTION_DATA_SOURCE_ID") or DEFAULT_DATA_SOURCE_ID
    if not ds:
        log("NOTION_DATA_SOURCE_ID 가 backend/.env 에 없어요.")
        log("  노션 DB를 연 뒤 주소창의 링크를 Claude에게 주거나,")
        log("  통합 연결 후 데이터 소스 ID(collection 뒤 UUID)를 넣어주세요.")
        return 1

    notion = Notion(token, ds)

    log("노션에서 처리할 강의를 찾는 중...")
    try:
        rows = notion.rows()
    except Exception as exc:
        log(f"조회 실패 — {exc}")
        return 1

    if not rows:
        log(f"처리할 강의가 없어요. ({P_STATUS}={STATUS_READY} 이고 {P_NOTE}가 "
            f"{' 또는 '.join(sorted(PICKUP))} 인 행이 대상이에요.)")
        return 0

    if args.limit:
        rows = rows[: args.limit]

    log(f"{len(rows)}개 발견:")
    for p in rows:
        log(f"  · {prop_text(p, P_NAME) or '(이름 없음)'}")

    if args.dry_run:
        log("\n--dry-run 이라 여기까지만 합니다.")
        return 0

    if not backend_alive():
        log(f"\n백엔드({BACKEND_URL})가 응답하지 않아요. ./sync.sh 로 실행하거나,")
        log("따로 uvicorn 을 띄운 뒤 다시 시도해 주세요.")
        return 1

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    ok = 0
    done_ids: set[str] = set()
    try:
        for i, page in enumerate(rows, start=1):
            if process(notion, page, i, len(rows)):
                ok += 1
            done_ids.add(page["id"])
    except KeyboardInterrupt:
        # 중단해도 `진행중`으로 멈춘 행이 남지 않게 되돌려 놓는다.
        log("\n\n중단됨 — 처리 중이던 강의를 되돌리는 중...")
        for page in rows:
            if page["id"] in done_ids:
                continue
            try:
                notion.set_select(page["id"], P_NOTE, NOTE_TODO)
            except Exception:
                pass
        log("되돌렸어요. 다시 실행하면 이어서 처리합니다.")
        return 130

    mins = (time.time() - started) / 60
    log(f"\n{'─' * 40}")
    log(f"완료 {ok}개 / 실패 {len(rows) - ok}개 · {mins:.0f}분 걸림")
    if ok < len(rows):
        log(f"실패한 건 노션에서 {P_NOTE}={NOTE_ERROR} 로 표시했고, 사유는 코멘트에 있어요.")
        log("다음에 다시 돌리면 자동으로 재시도합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
