# 우리 아이 미술관

보호자가 아이 그림 사진을 올리면 가족만의 미술관에 전시하고, AI 모델이 움직이는 그림이나 입체 그림을 제안하는 서비스입니다. 이 저장소는 그 서비스의 **모델 서빙 상태 규칙**을 담았습니다.
모델은 느리고 자주 실패합니다. 그래서 **원본 액자를 먼저 걸고**, 품질이 모자라면 **한 단계 낮추고**, 장애는 **같은 단계를 다시 시도**하며, 결과가 어디서 왔는지 **다섯 가지 원인으로 나눠 기록**합니다.

원본은 MLOps 과정의 팀 프로젝트(비공개)입니다. 여기 있는 코드는 팀 코드의 사본이 아니라 상태 규칙만 최소 형태로 다시 쓴 것입니다.

## 맡은 범위

| 구분 | 내용 |
|---|---|
| 맡은 일(팀 역할 분담 기준) | API 서버, 작업 DB와 큐, 낮춤 체인, 재시도와 원인 분류, 작품 삭제, 운영 지표, 외부에 여는 모델 기능 |
| 팀이 함께 정한 것 | 이 저장소의 규칙. 팀 결정 기록과 설계서에서 확정했다 |
| 다른 팀원이 맡은 것 | 모델 어댑터와 워커, 모델 평가, 보호자 화면 |

## 문제 해결을 먼저 읽기

| 문제 | 선택 | 확인 방법 |
|---|---|---|
| 움직이는 그림 한 장에 수십 초에서 몇 분이 걸려 보호자가 빈 화면을 기다린다 | 올리는 즉시 모델 없이 만들 수 있는 원본 액자를 건다. 새 결과는 보호자가 확인해야 바꿔 건다 | [원본 먼저 전시](docs/decisions/001-original-first.md) |
| 품질 미달과 서버 장애를 같은 "실패"로 다루면 재시도가 품질을 고치지 못하고, 장애가 품질 문제로 보인다 | 품질 미달은 재시도 없이 한 단계 낮추고(움직임 → 입체 → 액자), 장애는 같은 단계를 최대 3번 시도한다 | [낮춤과 재시도를 나눈 이유](docs/decisions/002-downgrade-vs-retry.md) |
| 결과의 원인이 섞이면 운영 지표가 거짓말을 한다 | 보호자 선택 · 모델 낮춤 · 보호자 전환 · 인프라 실패 · 결과 미도달을 섞지 않는다 | [원인 5분류](docs/decisions/003-five-causes.md) |

## 바로 실행

```bash
git clone https://github.com/wpalswpa/kids-art-museum-serving-evidence.git
cd kids-art-museum-serving-evidence
python -m unittest discover -s tests -v
```

Python 3.10 이상. 표준 라이브러리만 쓰므로 모델도 GPU도 네트워크도 필요 없습니다.

## 검사 이름이 곧 규칙입니다

```
original_frame_is_on_the_wall_right_after_upload        올리면 원본 액자가 바로 걸린다
new_result_replaces_frame_only_after_guardian_confirms  새 결과는 보호자 확인 뒤에만 바꿔 건다
quality_below_goes_one_step_down_without_retry          품질 미달은 재시도 없이 한 단계 낮춘다
infra_error_is_not_a_downgrade                          장애는 낮춤이 아니다
same_stage_is_tried_at_most_three_times_including_first 같은 단계는 첫 시도 포함 최대 3번
frame_after_exhausted_retries_stays_infra_not_switch    소진 뒤 액자로 걸어도 원인은 장애로 남는다
not_delivered_work_is_excluded_from_first_approval_rate 결과를 못 받은 작품은 첫 결과 승인율에서 뺀다
```

## 무엇을 보면 되나

| 궁금한 것 | 파일 |
|---|---|
| 규칙 코드 | [fallback.py](fallback.py) |
| 깨지면 안 되는 것 | [tests/test_fallback.py](tests/test_fallback.py) |
| 원본 프로젝트에서 실제로 돌려 본 기록 | [evidence/README.md](evidence/README.md) |
| 공개 서버의 견본 미술관 화면 | [evidence/sample-museum.jpg](evidence/sample-museum.jpg) |

## 이 저장소가 보장하지 않는 것

- 검사는 상태 규칙만 확인합니다. 모델이 좋은 결과를 만드는지는 확인하지 않습니다.
- 원본 프로젝트에서 움직이는 그림은 팀이 만든 단순한 그림에서도 크게 일그러졌습니다. 품질 평가는 그림 수가 적어 끝나지 않았습니다([기록](evidence/README.md)).
- 실제 가족이 쓰는 모습과 만족은 관찰하지 않았습니다.
