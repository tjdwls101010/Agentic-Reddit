# Implementation kickoff prompt (paste into a fresh session)

Open a new Claude Code session **in the `Agentic Reddit` repo** and paste the box below.

---

```
agentic-reddit v0.1 (Reddit 리더)를 구현해줘. 이건 구현 세션이야 (계획은 지난 세션에 끝났고,
계획과 구현을 분리하기 위한 것).

먼저 계획 문서를 순서대로 정독해 (docs/plan/):
- 00-overview.md             ← 목적/비목적, "Reddit은 접근이 어렵고 데이터는 깨끗하다"
- 01-decisions.md            ← 합의된 결정 로그 (D1~D16) + 폐기된 OAuth 결정 + Phase 0 질문
- 02-recon-findings.md       ← 라이브 실측 전량 (anti-bot, OAuth 차단, 무로그인 검증, 레이트 모델)
- 03-architecture.md         ← 모듈 구조, 전송 seam, pacing, 저장소, 데이터 모델
- 04-cli-spec.md             ← 명령 표면, 플래그, exit code, 출력 계약
- 05-testing-and-ci.md       ← 테스트/픽스처/CI/배포/PII/DISCLAIMER 요구사항
- 06-implementation-phases.md ← verify 게이트가 달린 단계별 로드맵 (메인)
- 07-skill-plan.md           ← 스킬은 PyPI 배포 후 별도 세션 (지금은 X)

배경: agentic-reddit은 agentic-facebook / agentic-x / agentic-threads의 넷째다. 하지만
Reddit은 "무로그인이라 쉬운" 형제가 아니라 접근 경로가 가장 까다로운 형제다. 실측 결과:
(1) 브라우저가 아닌 HTTP는 전부 403 JS 챌린지 (residential IP, 어떤 UA든),
(2) 공식 OAuth Data API는 승인제로 막힘 (계정 2개로 확인, 게다가 승인은 사용자별이라
    배포용 패키지엔 애초에 부적합),
(3) 그러나 실제 브라우저 안에서 same-origin fetch('/....json')를 호출하면 OAuth와 완전히
    동일한 정제 Listing JSON이 200으로 나오고, 이는 로그아웃 상태에서도 전 엔드포인트 검증됨.
따라서 전송은 "브라우저가 anti-bot 클리어런스를 들고 있고, 그 페이지 안에서 JSON을 부른다".
HTML 파싱이 아니다. model/parse/retrieve/cli 계층은 형제들과 거의 동일하게 간다.

반드시 지킬 제약:
- 최소 코드, 수술적 변경, 투기적 추상화·미요청 기능 금지. 스코프 밖(쓰기, 로그인/계정/자격증명,
  개인화 데이터, OAuth, duplicates/wiki/trophies/multireddit/live, crawl/batch/daemon) 금지.
- 전송은 브라우저 전용. httpx 없음, 쿠키/자격증명 저장소 없음, login 명령 없음.
  session.get_json() 위쪽은 전송을 몰라야 한다(나중에 OAuth 교체 가능하도록).
- TLS 지문 위조(curl_cffi 등) 금지. scrapling 기본을 넘는 공격적 stealth 레이어도 금지.
  Phase 0에서 그게 필요해 보이면 먼저 물어봐.
- /api/morechildren 사용 금지 — HTML 렌더 형태만 반환함이 실측으로 확인됨.
  댓글 확장은 퍼머링크 서브트리 GET(/r/<sub>/comments/<post>/_/<comment>.json)으로.
- 페이싱은 우회 불가: 1.0s floor + x-ratelimit-* 헤더 기반 예산 governor.
  무로그인 예산은 약 600초당 100요청(실측)이다. 429에서 재시도 루프 금지.
- scrapling은 lazy import. --version/--help/catalog/schema는 브라우저 없이 즉시 동작해야 함.
- PII: scratch/, *.raw.json, output/, profiles/, browsers/ gitignore. 픽스처는 합성.
- DISCLAIMER 톤 약화 금지(승인 없는 접근임을 명시). NSFW는 무로그인으로 접근되므로 숨기지 말고
  문서화할 것.
- 산출물은 전부 영어(코드/주석/README/CLI 출력).

진행 방식 (각 Phase의 verify 게이트를 통과할 때까지 loop):
0) Phase 0 필수 — 데이터 계층은 계획 단계에서 이미 전부 검증됐다. 남은 단 하나의 관문은
   "완전히 새 scrapling 프로필이 콜드 스타트로 JS 챌린지를 통과하는가"(Q-1). 여기에 더해
   headless 여부(Q-2), top-level more 처리(Q-3), 레이트 윈도우 확인(Q-4), over_18/over18
   매핑(Q-5), 비존재/비공개 응답 형태(Q-6)를 확정. Q-1이 실패하면 멈추고 사용자와 상의.
1) 스캐폴드 + 패키징 + 오프라인 명령(catalog/schema) + CI + publish.yml 하드닝.
2) BrowserSession + pacing + setup/status/doctor.
3) 수직 슬라이스 하나(`subreddit`)를 라이브로 관통.
4) 나머지 프리미티브(post 댓글트리/user/search 3종/subreddits/subreddit-info).
5) 하드닝 + README/wiki/CHANGELOG/DISCLAIMER + 버전.
6) PR → main 머지 → GitHub Release(→ publish.yml → PyPI Trusted Publishing). 설치 검증.
7) 스킬은 별도 세션(07-skill-plan.md).

시작 전에: 계획 문서를 읽고 → Phase 0 실행 계획을 짧게 제시하고 진행. 계획을 벗어나는 스코프
변경이 필요하면 먼저 물어봐.
```

---

**Notes for you (not part of the paste):**

- Repo remote is `github.com/tjdwls101010/Agentic-Reddit`. The PyPI trusted publisher is **already working** (the `0.0.1` placeholder shipped through it): workflow **`publish.yml`**, environment **`pypi`** — keep both names, just harden the workflow's contents.
- **Naming triple**: dist `agentic-reddit` / import `agentic_reddit` / command `agentic-reddit`. Env override `AGENTIC_REDDIT_PROFILE_DIR`.
- **scrapling docs are cached locally** at `../.tmp/docs_scrapling/` (including a Korean README at `docs_scrapling/README_KR.md`). crawl4ai is also cached there but is **not** used by this project.
- Recon was performed with Claude-in-Chrome on the `rararat` profile — first logged in, then **logged out** for the anonymous verification pass. The account (`Horror-Highway1207`) plays **no runtime role**; the shipped tool never logs in.
- The single riskiest item is Phase 0 Q-1 (cold-start challenge under a fresh scrapling profile). Everything else was verified during planning. Do Q-1 first, before writing much code.
- If `setup` ends up needing a headed browser (Q-2), that is a real UX regression for a distributed CLI — raise it with the user rather than silently defaulting to a visible window per command.
