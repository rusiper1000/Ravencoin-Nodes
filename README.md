# Raven Network Nodes

ravennodes.com을 거치지 않고, 레이븐코인 P2P 네트워크에 직접 접속해 측정한
국가별/ISP별/클라이언트버전별 노드 분포를 보여주는 사이트입니다.

- `crawler.py` — GitHub Actions가 몇 시간마다 자동으로 실행하는 크롤러
- `.github/workflows/crawl.yml` — 자동 실행 스케줄 설정
- `docs/index.html` — GitHub Pages로 배포되는 대시보드
- `docs/data/latest.json` — 크롤러가 생성하는 최신 결과 (자동 갱신됨)

## 처음 설정하는 방법 (한 번만 하면 됨)

1. GitHub에서 새 저장소를 만듭니다 (Public 이어야 무료로 Pages를 쓸 수 있어요).
2. 이 폴더 안의 모든 파일/폴더 구조를 그대로 저장소에 올립니다 (git push, 또는
   GitHub 웹사이트에서 "Add file → Upload files"로 폴더째 드래그).
3. 저장소의 **Settings → Actions → General → Workflow permissions** 에서
   **"Read and write permissions"** 를 선택하고 저장합니다.
   (이게 없으면 크롤러가 결과를 커밋하지 못합니다.)
4. 저장소의 **Settings → Pages** 에서 Source를 **"Deploy from a branch"**,
   Branch를 **main / docs** 폴더로 선택하고 저장합니다.
5. 저장소의 **Actions** 탭 → "Crawl Ravencoin Network" 워크플로우 → **Run workflow**
   버튼을 눌러 수동으로 한 번 실행해봅니다 (첫 데이터를 바로 만들기 위함).
6. 몇 분 뒤 `https://[사용자이름].github.io/[저장소이름]/` 주소로 들어가면
   사이트가 뜹니다.

이후로는 `.github/workflows/crawl.yml` 에 설정된 대로 4시간마다 자동으로
새로 측정되고 사이트에 반영됩니다. 주기를 바꾸고 싶으면 그 파일의
`cron: "0 */4 * * *"` 부분을 수정하면 됩니다 (숫자 4를 원하는 시간 간격으로).
