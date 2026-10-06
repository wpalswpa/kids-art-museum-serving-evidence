// 보호자 화면. 응답 타입은 contracts/openapi.yaml의 스키마 이름을 따른다.
type Kind = "animated" | "sculpture" | "relief" | "frame";
type Status = "queued" | "running" | "done" | "not_delivered";
type Cause = "guardian_choice" | "model_downgrade" | "guardian_switch" | "infra_failure" | "not_delivered";

interface Artwork {
  id: number;
  title: string;
  wanted: Kind;
  on_wall: Kind;
  target: Kind;
  status: Status;
  result: Kind | null;
  causes: Cause[];
  attempts: { stage: Kind; classification: string; attempt: number; latency_ms: number }[];
}

interface ApiError {
  error: "not_found" | "invalid_request" | "not_ready" | "db_unavailable";
  detail?: string;
  request_id: string;
}

const KIND_LABEL: Record<Kind, string> = { animated: "움직이는 그림", sculpture: "조각", relief: "입체", frame: "원본 액자" };
const CAUSE_LABEL: Record<Cause, string> = {
  guardian_choice: "보호자가 처음부터 고름",
  model_downgrade: "품질이 모자라 한 단계 낮춤",
  guardian_switch: "보호자가 다른 결과로 바꿈",
  infra_failure: "서버 장애로 다시 시도함",
  not_delivered: "결과를 만들지 못함",
};

const $ = <T extends HTMLElement>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`화면 요소 없음: ${selector}`);
  return el;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = await res.json();
  if (!res.ok) {
    const err = body as ApiError;
    throw new Error(`${err.error} (${err.request_id})`);
  }
  return body as T;
}

function render(art: Artwork): void {
  $("#artwork").hidden = false;
  $('[data-testid="on-wall"]').textContent = KIND_LABEL[art.on_wall];
  const status = $('[data-testid="status"]');
  const notice = $('[data-testid="notice"]');
  const hang = $<HTMLButtonElement>('[data-testid="hang-result"]');
  const keep = $<HTMLButtonElement>('[data-testid="keep-frame"]');
  notice.hidden = true;
  if (art.status === "queued" || art.status === "running") {
    status.textContent = `${KIND_LABEL[art.target]} 만드는 중`;
  } else if (art.status === "done") {
    status.textContent = `결과가 나왔어요: ${KIND_LABEL[art.result ?? "frame"]}`;
  } else {
    status.textContent = "결과를 만들지 못했어요";
    notice.hidden = false;
    notice.textContent = "서버 문제로 결과를 만들지 못했어요. 작품은 원본 액자로 걸려 있어요.";
  }
  $('[data-testid="causes"]').textContent = art.causes.map((c) => CAUSE_LABEL[c]).join(" · ");
  // 결과 확인 전에는 바꿔 걸지 않는다. 결과가 없으면 원본 액자만 고를 수 있다.
  hang.disabled = !(art.status === "done" && art.result !== null && art.result !== art.on_wall);
  keep.disabled = art.status === "queued" || art.status === "running";
  hang.onclick = () => void confirmChoice(art.id, art.result ?? "frame");
  keep.onclick = () => void confirmChoice(art.id, "frame");
}

async function confirmChoice(id: number, choice: Kind): Promise<void> {
  render(await call<Artwork>(`/artworks/${id}/confirm`, { method: "POST", body: JSON.stringify({ choice }) }));
}

async function poll(id: number): Promise<void> {
  const art = await call<Artwork>(`/artworks/${id}`);
  render(art);
  if (art.status === "queued" || art.status === "running") setTimeout(() => void poll(id), 1000);
}

$<HTMLFormElement>("#upload").addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = $<HTMLInputElement>("#title").value;
  const wanted = $<HTMLSelectElement>("#wanted").value as Kind;
  const art = await call<Artwork>("/artworks", { method: "POST", body: JSON.stringify({ wanted, title }) });
  render(art);
  void poll(art.id);
});

export {};
