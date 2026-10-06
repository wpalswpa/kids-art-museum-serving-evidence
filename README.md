# 우리 아이 미술관 · 작업 처리 규칙과 실행 검증

[![ci](https://github.com/wpalswpa/kids-art-museum-serving-evidence/actions/workflows/ci.yml/badge.svg)](https://github.com/wpalswpa/kids-art-museum-serving-evidence/actions/workflows/ci.yml)

**무엇을 만들었나.** 아이 그림을 움직임·입체로 바꾸는 팀 서비스(교육 과정 4인 팀, 원본 비공개)에서 내가 맡은 작업 처리 규칙을, 실제로 돌아가는 API·워커·MariaDB 서비스로 다시 세웠다. 원본 팀 코드의 사본이 아니라 공개용 재현이다.

**무엇이 바뀌나.** 변경이 올라오면 GitHub Actions가 ruff → 규칙 단위 검사 16개 → OpenAPI 문서 검증 → 컨테이너 빌드 → 계약 검사·장애 주입 시험 11개를 차례로 돌린다. 모든 API 응답은 OpenAPI 스키마로 검증되고, 모델 시간 초과·503·계약 위반 응답·DB 중지에서 규칙이 지켜지는지 확인한다.

**어떻게 아나.** [CI 실행 기록](https://github.com/wpalswpa/kids-art-museum-serving-evidence/actions/workflows/ci.yml)(로그·지표 보관), [장애 주입 시험](tests/integration/test_service.py), 음성 대조: CI가 워커 시간 제한을 1초에서 5초로 늘려 시간 초과 시나리오 2개가 실제로 실패하는지 확인하고, 되돌려 다시 통과시킨다(시험이 고장을 잡지 못하면 CI가 실패).

**재현.**

```bash
docker compose up -d --build --wait
pip install pytest jsonschema pyyaml requests
API_URL=http://localhost:8000 COMPOSE=1 python -m pytest tests/integration -v
```

| 장애 주입 | 지켜야 할 것 | 확인 |
|---|---|---|
| 모델 시간 초과 1회 → 정상 | 같은 단계 재시도, 원인은 인프라 실패 | 시험 3 |
| 시간 초과 3회 · 503 3회 | 결과 미도달, 벽에는 원본 액자, 다른 결과로 확인 거절 | 시험 4·6 |
| 계약 위반 응답(JSON 아님·필드 다름) | 낮춤이 아니라 재시도([결정 004](docs/decisions/004-invalid-response.md)) | 시험 5 |
| 품질 미달 | 재시도 없이 한 단계 낮춤 | 시험 2 |
| DB 중지 | API 503 + request_id, 재시작 뒤 앞서 올린 작품이 끝까지 처리 | 시험 11 |
| 모든 시나리오 | 확인 전 원본 액자만 전시, 단계별 시도 3회 이하, 워커 지표 = 실제 결과 수 | 공통 검사·시험 10 |

설계는 구현 전에 커밋한 [docs/platform.md](docs/platform.md)에 있다. 서비스 코드·컨테이너·CI는 2026-10-06에 추가했다. 처리 규칙과 결정 기록 001~003은 원본 팀 프로젝트(2026-09)에서 정한 것이고, 원본에서 돌린 시험 기록은 [evidence/README.md](evidence/README.md)에 있다. 코드 작성에는 AI 코딩 도구(Claude Code)를 썼다.

| 구성 | 파일 |
|---|---|
| 처리 규칙(원본 액자 먼저·품질 미달 낮춤·장애 재시도·원인 5분류) | [fallback.py](fallback.py) |
| 계약 | [contracts/openapi.yaml](contracts/openapi.yaml), [contracts/model_response.schema.json](contracts/model_response.schema.json) |
| API · 워커(응답 분류 한 곳) · 가짜 모델 서버 | [service/](service/) |
| 로그·지표 | 한 줄 JSON 로그(request_id·job_id·분류·지연), Prometheus `jobs_total`·`job_retries_total`·`job_attempts_total`·`job_duration_seconds` |

---

## 서비스 소개

> 작은 손이 남긴 선이, 우리 가족의 한 장면으로.

아이의 작품과 그날의 말을 가족이 함께 간직하고, 시간이 흐른 뒤에도 다시 만나는 기록으로 잇는 가족용 미술관입니다.
보호자가 휴대폰으로 찍은 아이 그림 한 장을 올리면, 그림은 제목 · 그린 날 · 그때 나이가 적힌 명패와 함께 아이의 미술관 벽에 걸립니다.
가족은 나이별 전시실을 함께 걸으며 아이가 자라 온 시간을 다시 꺼내 봅니다.

**기술은 기억을 꾸며내는 주체가 아니라, 다시 꺼내 보는 수단입니다.**

![견본 미술관 7살 전시실](evidence/sample-museum.jpg)

## 누구에게 무엇을 주나

| 누구 | 무엇을 |
|---|---|
| 지금의 아이 | 자기 그림이 미술관에 걸리고, 원하면 움직이거나 도톰한 입체로 떠오르는 모습을 보호자와 함께 본다. 원본의 선과 색은 그대로 알아볼 수 있다 |
| 지금의 보호자 | 사진 한 장만 올리면 작품만 오려 내 전시하고, 어울리는 감상 방식을 제안받는다. 고르는 것은 보호자다 |
| 성장한 아이 | 자기 작품과 그날의 말로 어린 시절을 돌아본다. 장기 보존이 필요한 후속 가치이며 아직 보장한 것이 아니다 |

## 지키는 원칙

- 작품과 아이의 실제 말이 먼저 보인다. 움직임 · 입체는 보호자가 고를 때만 만든다.
- 원본을 덮어쓰지 않는다. 원본 액자도 완성된 작품으로 대한다.
- AI는 제안까지만 한다. 점수를 보여 주지 않고, 제안과 다른 선택을 막지 않는다.
- 없었던 일 · 감정 · 발달 평가를 만들지 않는다. 그림 점수나 아이 비교 기능을 만들지 않는다.
- 실명 대신 별칭과 그린 때의 나이만 받는다. 아이 그림을 외부 AI 서비스로 보내지 않고 팀 서버 안에서만 처리한다.

## 지금 상태

- 과정 서버에서 견본 미술관을 걷고, 작품을 크게 보며 해설을 듣는 흐름이 동작한다(2026-10-01).
- 모델은 새로 학습하지 않고 공개 사전학습 모델(그림 오려내기 · 종류 제안 · 움직이는 그림 · 깊이)을 이어 붙였다.
- 실제 가족의 사용 · 만족 · 수요는 아직 검증하지 않았다.

원본은 MLOps 과정의 팀 프로젝트(비공개)입니다.

## 내가 맡은 일

| 구분 | 내용 |
|---|---|
| 맡은 일(팀 역할 분담 기준) | API 서버, 작업 DB와 큐, 결과를 만드는 단계의 처리 규칙(낮춤 · 재시도 · 원인 분류), 작품 삭제, 운영 지표 |
| 팀이 함께 정한 것 | 아래 규칙. 팀 결정 기록과 설계서에서 확정했다 |
| 다른 팀원이 맡은 것 | 모델 어댑터와 워커, 모델 평가, 보호자 화면 |

## 이 저장소에 담은 것

팀 코드의 사본이 아니라, 맡은 일의 핵심 규칙을 공개 가능한 최소 코드와 검사로 다시 쓴 것입니다.

| 보호자가 겪을 일 | 규칙 | 결정 기록 |
|---|---|---|
| 움직이는 그림은 한 장에 수십 초에서 몇 분이 걸린다 | 올리는 즉시 원본 액자로 건다. 새 결과는 보호자가 확인해야 바꿔 건다 | [001](docs/decisions/001-original-first.md) |
| 그림에 따라 움직임이 잘 안 나온다 | 품질이 모자라면 한 단계 낮춘다(움직임 → 입체 → 원본 액자). 서버 장애는 같은 단계를 최대 3번 다시 한다 | [002](docs/decisions/002-downgrade-vs-retry.md) |
| 왜 이 결과가 걸렸는지 알아야 고칠 수 있다 | 보호자 선택 · 모델 낮춤 · 보호자 전환 · 인프라 실패 · 결과 미도달을 섞지 않고 기록한다 | [003](docs/decisions/003-five-causes.md) |

```bash
git clone https://github.com/wpalswpa/kids-art-museum-serving-evidence.git
cd kids-art-museum-serving-evidence
python -m unittest discover -s tests -v
```

Python 3.10 이상, 표준 라이브러리만 씁니다. 규칙 코드는 [fallback.py](fallback.py), 검사는 [tests/test_fallback.py](tests/test_fallback.py), 원본 프로젝트에서 실제로 돌려 본 기록은 [evidence/README.md](evidence/README.md)에 있습니다.

## 이 저장소가 보장하지 않는 것

- 검사는 처리 규칙만 확인합니다. 모델이 좋은 결과를 만드는지는 확인하지 않습니다.
- 원본 프로젝트에서 움직이는 그림은 팀이 만든 단순한 그림에서도 크게 일그러졌고, 품질 평가는 그림 수가 적어 끝나지 않았습니다([기록](evidence/README.md)).
- 실제 가족이 쓰는 모습과 만족은 관찰하지 않았습니다.

화면의 회랑 배경은 Touzania18의 사진(CC BY-SA 4.0)을 3D 면으로 펴서 자른 것이고, 견본 그림은 팀이 그렸습니다.
