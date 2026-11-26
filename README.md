# 클래스카드 매크로 (Liquid Glass Edition)

클래스카드(`classcard.net`) 단어장 및 문장(본문) 세트의 **암기 / 리콜 / 스펠 / 테스트**를 자동으로 풀어주는 프로그램입니다. **Windows 및 macOS를 모두 지원합니다.**

Apple `DESIGN.md` 및 **Liquid Glass** 디자인 언어를 반영한 순수 Tkinter UI로 개편되었으며, 원본 저장소(`v2.0.1`)의 구간 이어풀기·자동 재응시·마이크로 지연 안정화 기능과 포크 저장소의 탐지 방지·통계 대시보드 기능을 하나로 통합했습니다.

---

## ✨ 주요 특징

- **Apple DESIGN.md & Liquid Glass UI**:
  - 캡슐(`pill`) 버튼, 18px 라운드 카드, 헤어라인 보더, 상단 스페큘러 하이라이트 림, 라이트(`#FFFFFF`/`#F5F5F7`) 및 다크(`#1D1D1F`/`#272729`) 타일 테마, 시스템 테마 자동 감지(`☾`/`☀` 즉시 전환).
- **실시간 4대 KPI & LIVE 진행 바**:
  - 암기·리콜·스펠 평균 진도와 테스트 통과율을 상단 KPI 카드에 1초마다 갱신.
  - 하단 플로팅 Dock에 실시간 카드 진행률(`n/m`), 탐지 방지 휴식 카운트다운, 경과 시간 표시.
- **세트 검색·필터·빠른 선택**:
  - 이름 검색 바, 상태 필터 칩(`전체` / `미완료` / `테스트 미달` / `단어` / `문장`), 원클릭 선택(`모두 선택` / `미완료만` / `미달만` / `모두 해제`), 목표 % 일괄 적용.
- **선택형 모드 & 일시정지/재개**:
  - 하단 Dock의 모드 칩(`암기` / `리콜` / `스펠` / `테스트`)으로 원하는 단계만 골라 실행 가능.
  - 학습 진행 중에도 상태를 잃지 않고 **일시정지 / 재개** 지원.
- **클래스별 테스트 커트라인 & 자동 재응시**:
  - 클래스마다 통과 기준 점수(기본 `85점`, 5점 단위)를 개별 설정 가능하며, 미달 시 최대 3회까지 자동 재응시.
- **고급 탐지 방지 옵션 (`설정` / `ANTICHEAT`)**:
  - `ANTICHEAT` 토글: 인간형 미세 클릭 지연(`0.1~0.7초`) 및 모드 간 랜덤 전환 대기(`1~3초`).
  - 세트 간 랜덤 휴식(`min~max`초, 카운트다운 표시).
  - 테스트 일부러 틀리기(`min~max`개 랜덤 오답 제출로 100점 회피).
- **문장(본문) 세트 대응 & 구간 이어풀기**:
  - 영작 연습, 듣고 배열, 어순배열, `/` 끊어읽기 토막 및 다중 구간 연속 풀이를 안정적으로 처리.
- **모달 시트**:
  - `옵션 설정`, `학습 통계 대시보드`(모드별 달성도·성적 분포 차트), `실시간 활동 로그`(레벨별 필터·복사), `수동 모드`, `자동 로그인`(Windows DPAPI / macOS·Linux HMAC-SHA256 로컬 암호화).

---

## 📥 설치 및 실행

> **공통 필수 조건**: **Google Chrome**이 설치되어 있어야 합니다.

### 🍎 macOS

1. 이 폴더의 **`run_mac.command`** 를 더블 클릭하거나 터미널에서 실행합니다:
   ```bash
   pip install -r requirements.txt
   python3 main.py
   ```

### 🪟 Windows

1. [**Releases**](../../releases)에서 **`Classcard_Setup.exe`** 를 내려받아 설치합니다.
2. 또는 소스에서 직접 실행할 수 있습니다:
   ```bash
   pip install -r requirements.txt
   python main.py
   ```

---

## 🛠 구조 (모듈화 아키텍처)

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점 및 Windows DPI 인식 초기화 |
| `config_store.py` | 스레드 세이프(`RLock`) 원자적 설정/진도 캐시 저장(`config.json`, `rates.json`) 및 자격 증명 암호화(`login.dat`) |
| `chrome_bridge.py` | Chrome 원격 디버깅(`9333`) 연결, 페이지 각성(CDP), 클래스/세트/리포트 조회, 로그인·DOM 제어 |
| `study_engine.py` | Tkinter 비의존 자동/수동 학습 워커 엔진, 문장 스크램블 매칭, 일시정지/재개, 구조화 로그 |
| `glass_ui.py` | Apple `DESIGN.md` & Liquid Glass 순수 Tkinter 컴포넌트 및 메인/모달 UI |
| `setup.iss` | Windows Inno Setup 설치 스크립트 |

### PyInstaller 빌드 (Windows)

```bash
pyinstaller --onefile --windowed --name "암기" --collect-all selenium main.py
```

---

## License

이 프로젝트는 [LICENSE](LICENSE) 파일에 명시된 라이선스(Apache License 2.0)를 따릅니다.
