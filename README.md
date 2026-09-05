# Raven Network Nodes

ravennodes.com을 거치지 않고, 레이븐코인(Ravencoin) P2P 네트워크에 **직접 접속해서
측정한** 국가별·ISP별·클라이언트 버전별 노드 분포와 네트워크 건강도를 보여주는
실시간 대시보드입니다.

- 라이브 사이트 (GitHub Pages): `https://[사용자이름].github.io/[저장소이름]/`
- 라이브 사이트 (Vercel): `https://[프로젝트이름].vercel.app`

---

## 1. 이게 무엇을 하는 사이트인가

- 자체 제작한 P2P 크롤러가 레이븐코인 네트워크에 직접 `getaddr` 요청을 보내서
  **도달 가능한 노드**를 찾아냅니다 (ravennodes.com이 쓰는 것과 같은 방식이지만,
  독립적으로 직접 측정합니다).
- 각 노드의 국가, ISP, 클라이언트 버전, 블록 높이까지 함께 수집합니다.
- 이 데이터를 GeoIP(ip-api.com, 무료·비인증)로 위치 정보를 붙여 JSON으로 저장하고,
  정적 웹페이지가 그 JSON을 읽어 화면에 그립니다.
- 전체 과정이 **GitHub Actions**로 자동화되어 있어서, 사람이 개입할 필요 없이
  하루 5~6회 자동으로 새로 측정됩니다.

### 주요 기능
| 기능 | 설명 |
|---|---|
| 국가/ISP/버전별 분포 | 전체 노드를 여러 기준으로 집계 (국가는 "더보기"로 전체 확인 가능) |
| 네트워크 건강도 | 동기화 완료 / 지연 중 / 정지된 노드 3단계 분류 (아래 4번 항목 참고) |
| 세계지도 | 위경도 기반 실시간 노드 위치 + 국가 하이라이트 + 신호 애니메이션 |
| 추이 그래프 | 측정할 때마다 총 노드 수를 기록해 시간에 따른 변화를 보여줌 |
| 내 노드 확인하기 | IP를 검색해서 내 노드가 이번 측정에 잡혔는지, 신뢰도는 어떤지 확인 |
| 데이터 & API | `data/*.json`을 누구나 받아갈 수 있음, CSV 다운로드 버튼 제공 |
| 측정 지연 경고 | 마지막 측정이 너무 오래됐으면 화면에 경고 배너 표시 |
| 한/영 언어 전환 | 우측 상단 버튼으로 전환, 브라우저에 저장돼 다음에도 유지됨 |

---

## 2. 폴더 구조

```
ravenweb/
├── crawler.py                     ← 크롤러 본체 (GitHub Actions가 실행)
├── README.md                      ← 이 문서
├── .github/workflows/crawl.yml    ← 자동 실행 스케줄/방법 설정
└── docs/                          ← 실제 배포되는 웹사이트 (GitHub Pages/Vercel 둘 다 이 폴더를 봄)
    ├── index.html                 ← 대시보드 화면 전체 (HTML+CSS+JS 한 파일)
    ├── og-image.png               ← SNS 공유 시 뜨는 미리보기 이미지
    ├── assets/
    │   └── raven-logo.png         ← 헤더에 쓰이는 레이븐코인 공식 커뮤니티 로고
    └── data/
        ├── latest.json            ← 가장 최근 측정 결과 (크롤러가 매번 덮어씀)
        ├── history.json           ← 측정 시각별 총 노드 수 기록 (최근 약 2개월치 누적)
        └── node_stats.json        ← 노드별 "처음 발견 시각/신뢰도" 내부 추적용 (사이트에 직접 노출 안 됨)
```

---

## 3. 처음 설정하는 방법

### 3-1. GitHub Pages로 배포

1. GitHub에서 새 저장소를 만듭니다 (**Public**이어야 무료로 Pages를 쓸 수 있어요).
2. 이 폴더 안의 모든 파일/폴더 구조를 그대로 저장소에 올립니다.
3. 저장소의 **Settings → Actions → General → Workflow permissions**에서
   **"Read and write permissions"**를 선택하고 저장합니다.
   (이게 없으면 크롤러가 결과를 커밋하지 못합니다.)
4. 저장소의 **Settings → Pages**에서 Source를 **"Deploy from a branch"**,
   Branch를 **main / docs** 폴더로 선택하고 저장합니다.
5. **Actions** 탭 → "Crawl Ravencoin Network" → **Run workflow**로 수동 실행 (첫 데이터 생성용).
6. 몇 분 뒤 `https://[사용자이름].github.io/[저장소이름]/`으로 접속하면 사이트가 뜹니다.

### 3-2. Vercel로도 배포 (선택, GitHub Pages와 동시에 운영 가능)

1. https://vercel.com 에서 **GitHub 계정으로 가입**
2. **Add New → Project** → 이 저장소 Import
3. **Root Directory**를 반드시 **`docs`**로 지정 (Edit 버튼으로 설정)
4. Framework Preset은 **Other**로, Build Command/Output Directory는 비워둠
5. Deploy → `프로젝트이름.vercel.app` 주소 발급됨
6. 이후로는 저장소에 새 커밋이 올라올 때마다 자동으로 재배포됨 (설정 불필요)

> GitHub에 Vercel 앱 자체가 설치 안 되어 있으면 저장소 목록이 안 보일 수 있습니다.
> 그럴 땐 `github.com/apps/vercel`에서 직접 설치 → 저장소 접근 허용을 해주세요.

---

## 4. 자동 실행 방식 — 클라우드 vs 자체 러너

`.github/workflows/crawl.yml`의 `runs-on` 값으로 둘 중 하나를 고를 수 있습니다.

| 방식 | 설정값 | 특징 |
|---|---|---|
| GitHub 클라우드 서버 | `runs-on: ubuntu-latest` | 설정 간편, PC 필요 없음. 다만 클라우드/데이터센터 IP라 일부 노드가 접속을 덜 받아줘서 **노드 수가 실제보다 적게 잡힐 수 있음** |
| 자체 러너(권장) | `runs-on: self-hosted` | 가정용 PC의 인터넷 회선으로 크롤링하므로 노드들이 더 잘 받아줌. **PC가 항상 켜져 있어야 함** |

### 자체 러너 설정 방법 (Windows 기준)

1. 상시 가동하는 PC에서 **Python**과 **Git**이 설치돼 있는지 확인
   (`python --version`, `git --version`으로 확인. 없으면 각각 python.org, git-scm.com에서 설치)
2. 저장소 **Settings → Actions → Runners → New self-hosted runner** → OS는 **Windows** 선택
3. 화면에 뜨는 명령어를 그 PC에서 순서대로 실행 (다운로드 → 압축해제 → `config.cmd`)
4. **반드시 서비스로 등록**해야 창을 닫아도 계속 작동합니다. 관리자 권한 명령 프롬프트에서
   러너 설치 폴더로 이동한 뒤:
   ```
   .\svc.cmd install
   .\svc.cmd start
   ```
5. **Settings → Actions → Runners**에서 초록점(Idle) 상태면 완료

**러너가 죽었을 때(Actions가 "Queued"에서 안 넘어갈 때) 복구법**:
```
.\svc.cmd stop
.\svc.cmd uninstall
.\svc.cmd install
.\svc.cmd start
```

> **참고**: GitHub의 예약 실행(cron)은 부하가 많을 때 몇 시간씩 지연될 수 있다는 게
> GitHub 공식 문서에도 명시된 특성입니다. 정각에 딱 맞춰 안 돌아도 정상이니 걱정 안 하셔도 됩니다.

---

## 5. 설정값 바꾸는 방법

### 크롤링 주기
`.github/workflows/crawl.yml`의 `cron: "0 */4 * * *"`에서 `4`를 원하는 시간 간격으로.
(UTC 기준이라 한국시간과 9시간 차이가 있다는 점 참고)

### 네트워크 건강도 판정 기준
`crawler.py` 상단 근처:
```python
SYNC_TOLERANCE_BLOCKS = 50       # 기준 높이 ±이만큼은 "동기화 완료"
STALLED_THRESHOLD_BLOCKS = 500   # 기준 높이보다 이만큼 이상 뒤처지면 "정지된 노드"
MIN_SAMPLE_FOR_REFERENCE = 3     # 기준 버전으로 인정하려면 최소 이 노드 수는 있어야 함
```
기준 높이는 전체 노드의 단순 평균/중앙값이 아니라, **"표본이 충분하고 버전 번호가
가장 높은(최신) 클라이언트"** 노드들만의 높이로 계산합니다. 롤백 이후 방치된
구버전이 아무리 많아도, 최신 버전 쪽을 기준으로 삼아 착시를 방지하기 위함입니다.

### 크롤링 강도(라운드 수, 동시 접속 수 등)
```python
MAX_ROUNDS = 8         # 탐색 라운드 수
MAX_WORKERS = 60        # 동시 접속 시도 수
CONNECT_TIMEOUT = 20    # 개별 접속 타임아웃(초)
```

### 측정 지연 경고 기준
`docs/index.html`의 `STALE_THRESHOLD_HOURS = 9` (4시간 주기 기준 1회 정도는 놓쳐도 괜찮게 여유를 둔 값)

---

## 6. 데이터 스키마 (`docs/data/*.json`)

전부 공개 데이터라 누구나 직접 받아갈 수 있습니다 (인증 불필요).

### `latest.json` — 이번 측정의 전체 결과
```jsonc
{
  "generated_at": "2026-08-30T05:00:00+00:00",
  "total_nodes": 91,
  "network_health": {
    "reference_height": 4523050,
    "reference_version": "/Ravencoin:4.8.0/",
    "synced": 66, "lagging": 5, "stalled": 20, "unknown": 0,
    "stalled_versions": [{"name": "/Ravencoin:4.6.0/", "count": 12, "pct": 60.0}]
  },
  "countries": [{"name": "United States", "code": "us", "count": 23, "pct": 25.3}],
  "isps": [{"name": "OVH SAS", "count": 10, "pct": 11.0}],
  "versions": [{"name": "/Ravencoin:4.8.0/", "count": 66, "pct": 72.5}],
  "nodes": [
    {
      "ip": "154.38.163.235", "port": 8767,
      "country": "United States", "country_code": "us", "isp": "OVH SAS",
      "version": "/Ravencoin:4.8.0/", "height": 4523051, "sync_status": "synced",
      "lat": 37.4, "lon": -122.1,
      "age_label": "14일 전 처음 발견", "reachability_pct": 95.8, "checks": 24
    }
  ]
}
```
`sync_status`는 `"synced"` / `"lagging"` / `"stalled"` / `"unknown"` 중 하나입니다.

### `history.json` — 측정 시각별 총 노드 수
```jsonc
[{"t": "2026-08-29T05:00:00+00:00", "total": 88}, {"t": "2026-08-29T21:00:00+00:00", "total": 91}]
```

### `node_stats.json` — 내부 추적용 (사이트에 직접 노출되지 않음)
각 노드가 처음 발견된 시점과 그동안 몇 번 잡혔는지를 기록해서, `latest.json`의
`age_label`(처음 발견 시점)과 `reachability_pct`(신뢰도)를 계산하는 데 씁니다.

---

## 7. 자주 발생하는 문제

| 증상 | 원인 / 해결 |
|---|---|
| Actions가 "Queued"에서 안 넘어감 | 자체 러너 PC가 꺼져있거나 러너 서비스가 죽음 → 4번 항목의 복구법 참고 |
| GitHub Pages는 반영되는데 화면이 예전 그대로 | 브라우저 캐시 문제 → `Ctrl+Shift+R`로 강력 새로고침 |
| `docs/index.html`을 새로 올렸는데 반영 안 됨 | 저장소 **루트**가 아니라 **`docs` 폴더 안에** 정확히 올렸는지 확인 |
| 노드 수가 어느 날 갑자기 확 줄어듦 | 일시적인 네트워크 변동일 수 있음. 자체 러너를 쓰고 있다면 그 PC의 인터넷/전원 상태 확인 |
| 워크플로우 커밋 단계에서 에러 | Windows 자체 러너는 기본 셸이 PowerShell이라 `||` 같은 bash 문법이 안 먹힘 → `crawl.yml`은 이미 PowerShell 문법(`$LASTEXITCODE`)으로 작성돼 있음 |
| 내 노드가 검색이 안 됨 | 그 노드의 8767 포트가 공유기에서 포트포워딩 안 돼있을 가능성 큼 → yougetsignal.com 등에서 포트 열림 여부 확인 |

---

## 8. 크레딧

- 데이터: 자체 제작 크롤러 (Ravencoin P2P 프로토콜 직접 구현)
- GeoIP: [ip-api.com](https://ip-api.com) (무료, 비인증)
- 세계지도: Al MacDonald (Wikimedia Commons), edited by Fritz Lekschas — CC BY-SA 3.0
- 레이븐 로고: [Ravencoin-Marketing](https://github.com/underdarkskies/Ravencoin-Marketing) (커뮤니티 공용 자산)
- Made by 타락천사 ([@rusiper1000](https://github.com/rusiper1000))
