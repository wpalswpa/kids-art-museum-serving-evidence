"""작품 한 점의 처리 규칙: 원본 먼저 전시, 품질 미달은 낮춤, 장애는 재시도.

원본 프로젝트(팀, 비공개)의 설계 규칙을 공개 가능한 최소 형태로 다시 쓴 것이다.
팀 코드의 사본이 아니며, 모델을 부르지 않는다. 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 결과 종류와 낮춤 순서. 원본 액자는 모델이 필요 없어서 항상 만들 수 있다.
CHAIN = {"animated": "relief", "sculpture": "relief", "relief": "frame"}
MODEL_FREE = "frame"

# 워커가 돌려주는 응답 분류
OK = "ok"
QUALITY_BELOW = "quality_below"
INFRA_ERRORS = {"engine_down", "timeout", "storage", "db", "model_not_ready"}

MAX_ATTEMPTS = 3  # 첫 시도 포함

# 결과 원인 5분류. 서로 섞지 않는다.
GUARDIAN_CHOICE = "guardian_choice"      # 보호자가 처음부터 액자·입체를 고름
MODEL_DOWNGRADE = "model_downgrade"      # 품질 미달로 한 단계 낮춤
GUARDIAN_SWITCH = "guardian_switch"      # 결과 확인 때 보호자가 낮은 결과로 바꿈
INFRA_FAILURE = "infra_failure"          # 장애로 재시도 중이거나 소진
NOT_DELIVERED = "not_delivered"          # 재시도 소진으로 결과를 만들지 못함


@dataclass
class Artwork:
    """보호자가 올린 작품 한 점. 올린 순간 원본 액자로 전시된다."""
    wanted: str                          # 보호자가 고른 결과 종류
    on_wall: str = MODEL_FREE            # 지금 미술관 벽에 걸린 것
    target: str = ""                     # 지금 만들고 있는 결과 종류
    attempts: int = 0
    result: str | None = None            # 만들어진 결과(확인 대기)
    causes: list[str] = field(default_factory=list)
    log: list[tuple[str, str, int]] = field(default_factory=list)  # (단계, 응답, 시도)

    def __post_init__(self) -> None:
        self.target = self.wanted
        if self.wanted in (MODEL_FREE, "relief"):
            self.causes.append(GUARDIAN_CHOICE)

    @property
    def closed(self) -> bool:
        return self.result is not None or NOT_DELIVERED in self.causes


def upload(wanted: str) -> Artwork:
    """올리기: 모델 결과를 기다리지 않고 원본 액자부터 건다."""
    art = Artwork(wanted=wanted)
    if wanted == MODEL_FREE:
        art.result = MODEL_FREE
    return art


def apply(art: Artwork, response: str) -> Artwork:
    """결과를 만드는 단계의 응답 하나를 반영한다."""
    if art.closed:
        raise ValueError("이미 끝난 작품에는 응답을 반영하지 않는다")
    art.attempts += 1
    art.log.append((art.target, response, art.attempts))

    if response == OK:
        art.result = art.target
    elif response == QUALITY_BELOW:
        # 품질 미달은 재시도하지 않고 한 단계 낮춘다. 시도 횟수는 새 단계에서 다시 센다.
        art.causes.append(MODEL_DOWNGRADE)
        art.target = CHAIN.get(art.target, MODEL_FREE)
        art.attempts = 0
        if art.target == MODEL_FREE:
            art.result = MODEL_FREE
    elif response in INFRA_ERRORS:
        # 장애는 낮춤이 아니다. 같은 단계를 다시 시도하고, 소진되면 결과 미도달.
        if INFRA_FAILURE not in art.causes:
            art.causes.append(INFRA_FAILURE)
        if art.attempts >= MAX_ATTEMPTS:
            art.causes.append(NOT_DELIVERED)
    else:
        raise ValueError(f"모르는 응답 분류: {response}")
    return art


def confirm(art: Artwork, choice: str) -> Artwork:
    """결과 확인: 보호자가 [좋아요]를 누르면 바꿔 건다. 낮은 결과를 고르면 보호자 전환."""
    if art.result is None and NOT_DELIVERED not in art.causes:
        raise ValueError("확인할 결과가 아직 없다")
    if NOT_DELIVERED in art.causes:
        # 소진 뒤 원본 액자로 걸어도 원인은 장애로 남는다. 보호자 전환으로 세지 않는다.
        if choice != MODEL_FREE:
            raise ValueError("결과를 만들지 못한 작품은 원본 액자만 고를 수 있다")
        art.on_wall = MODEL_FREE
        return art
    if choice != art.result:
        art.causes.append(GUARDIAN_SWITCH)
    art.on_wall = choice
    return art


def counts_in_first_approval(art: Artwork) -> bool:
    """첫 결과 승인율의 분모에 넣는가. 결과를 받지 못한 작품은 뺀다."""
    return NOT_DELIVERED not in art.causes
