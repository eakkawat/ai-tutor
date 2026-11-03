export type CheckStatus = "ready" | "missing" | "invalid" | "unreachable";
export type Check = {
  id: "llm" | "ffmpeg" | "ffprobe" | "whisper"; label: string; purpose: string; required: boolean;
  status: CheckStatus; fix: string | null; detail: string | null;
};
export type SetupStatus = { checks: Check[]; can_continue: boolean; media_enabled: boolean; media_note: string | null };
export type HomeState = "empty_library" | "no_active_skill" | "active_skill" | "reviews_due";
export type Home = { state: HomeState; books: number; active_skill: { id: number; name: string; session_id: number | null } | null; reviews_due: number };

export type LlmIn = { base_url: string; model: string; api_key: string };

export type Principle = { id: number; principle: string; test: string; chunk_id: number; citation: string | null };
export type Skill = {
  id: number; domain: string; name: string; description: string; practice_type: string | null; status: "active" | "pending" | "archived";
  merge_into: number | null; merge_note: string | null; learning_status: string; hours: number;
  principles: Principle[]; sources: { source_id: number; title: string; pages: [number, number] }[];
  concepts: { id: number; name: string; required_level: string; is_foundation: boolean }[];
  prerequisites: { id: number; name: string }[];
  merge?: { target: { id: number; name: string; principles: number }; adds: string[]; text: string };
};
export type SkillMap = { domains: { domain: string; skills: Skill[] }[]; pending: number };

export type Project = { id: number; name: string; description: string; good_enough: string; minutes_per_session: number; active: boolean; skills_practised: number };
export type ProjectIn = { name: string; description: string; good_enough: string; minutes_per_session: number };
export type PickCard = {
  id: number; name: string; description: string; practice_type: string | null; domain: string; learning_status: string; hours: number;
  why: string | null; recommended: boolean; needs: { id: number; name: string }[]; minutes: number;
  principles: { principle: string; citation: string | null; chunk_id: number }[];
};
export type Shortlist = { project: Project; skills: PickCard[]; ranked_by: "tutor" | "similarity"; note: string | null; all_passed: boolean; total_available: number };
export type ActiveSkill = { id: number; name: string; hours: number; attempt_next: number; session_id: number | null; phase: string | null };

export type SessionPhase = "diagnose" | "learn" | "check" | "practice" | "feedback" | "revise" | "pass";
export type Msg = {
  id: number; role: "tutor" | "user"; kind: string | null; phase: SessionPhase | null; content: string;
  citations: { citation: string; chunk_id: number }[]; meta: Record<string, unknown>; at: string;
};
export type TaskExtras = { template?: string[]; worked_example?: string; hint?: string; split_steps?: string[]; smaller_scope?: string; constraint?: string; higher_standard?: string; combine?: string };
export type PracticeTask = { title: string; instructions: string; support: string | null; template: string[]; minutes: number; attempt: number; extras?: TaskExtras; base_minutes?: number };
export type FlowRating = {
  id: number; rating: "too_easy" | "just_right" | "too_hard"; tapped: string | null; inferred: boolean; classification: string; lever: string | null; lever_label: string | null;
  level_before: number; level_after: number; message: string; verdict: string;
};
export type FlowView = {
  level: number; supports: string[]; constraints: string[]; hours: number; early: boolean; success_rate: number | null; target: [number, number];
  can_rate: boolean; rating: FlowRating | null;
};
export type Gate = { unlocked: boolean; done: number; total: number; message: string | null; missing: { id: number; name: string; level: string }[]; concepts: { id: number; name: string; level: string }[] };
export type SessionView = {
  id: number; phase: SessionPhase; ended: boolean; attempt: number; next_attempt: number;
  skill: { id: number; name: string; description: string; principles: Principle[]; concepts: { id: number; name: string }[] };
  project: { id: number; name: string; minutes_per_session: number };
  difficulty: number; hours: number; task: PracticeTask | null; draft: string;
  timer: { limit_s: number; elapsed_s: number; running: boolean; left_s: number | null; overtime_s: number };
  diagnosis: { can_do: string; gap: string; level: number; meets_all: boolean } | null;
  gate: Gate; messages: Msg[]; allowed: string[];
  check: { current: CheckQuestion | null; remaining_minutes: number; budget_left: number; all_done: boolean } | null;
  assets: Asset[]; flow: FlowView; feedback_pending: boolean; feedback_error: string | null; route: "pass" | "reteach" | "revise" | null; route_concepts: string[];
};
export type Asset = {
  id: number; kind: "image" | "video"; filename: string; status: "processing" | "ready" | "error"; error: string | null; duration_s: number | null;
  size_bytes: number; steps: { cuts?: StepState; frames?: StepState; transcript?: StepState } | null; notes: string[]; width: number | null; height: number | null;
  downscaled: boolean; thumb: string | null; attached: boolean;
};
export type StepState = { status: "waiting" | "running" | "done" | "skipped"; count?: number; done?: number; total?: number; lines?: number; note?: string };
export type Evidence = {
  kind: "image" | "video"; n: number; asset_id: number; filename: string; locator: string;
  region?: number[] | null; start_s?: number; end_s?: number; frames?: { id: number; idx: number; t: number }[];
};
export type CheckQuestion = { concept: string; concept_id: number; level: "define" | "spot"; prompt: string; options: string[]; attempts: number; hint_shown: boolean };
export type FbResult = { n: number; principle: string; result: "followed" | "partly" | "not"; comment: string; quote: string; locator: string | null; evidence?: Evidence | null; citation: string | null; chunk_id: number };
export type FbFix = { n: number; fix: string; example: string; citation: string | null; chunk_id: number; principle: string };
export type FbMeta = {
  version: number; passed: boolean; summary: string; results: FbResult[]; fixes: FbFix[]; since: string;
  mistakes: { n: number; kind: "concept" | "execution"; concept: string | null; tag: string; count?: number }[];
  diff: { principles: { n: number; before: string | null; after: string; change: "improved" | "same" | "worse" }[]; lines_added: number; lines_removed: number } | null;
};
export type Compare = { a: { version: number; text: string }; b: { version: number; text: string }; lines: { op: " " | "+" | "-"; text: string }[] };

export type ProfileNote = { id: number; text: string; section: "understand" | "flow"; topic: string | null; evidence: string | null; source: "auto" | "user"; edited: boolean; updated_at: string };
export type ProfileSection = { key: "understand" | "flow"; title: string; notes: ProfileNote[] };
export type ProgressData = {
  totals: { practice_hours: number; skills_passed: number; just_right: [number, number]; reviews_right: [number, number] };
  skills: { id: number; name: string; status: string; status_text: string; hours: number; target: number; bar: number; over: number; success_rate: number | null }[];
  mistakes: { tag: string; kind: string; count: number; last_seen: string; skill: string; fixed: boolean }[];
  flow_history: { id: number; task: string; skill: string | null; felt: string; inferred: boolean; changed: string; at: string }[];
  target: number;
};

export type Triage = { book_type: string; domain?: string; practicable: boolean; likely_skills: string[]; reason: string };
export type SourceStatus = "processing" | "ready" | "reference_only" | "needs_ocr" | "error" | "cancelled" | "new";
export type Source = {
  id: number; title: string; author: string | null; kind: "single" | "chapters"; pages: number; status: SourceStatus;
  stage: "extracting" | "chunking" | "embedding" | "triage" | null; progress: number; message: string | null; estimate_s: number | null;
  triage: Triage | null; chunks: number; files: number; pages_without_text: string[]; skills: number; pending_skills: number;
};
export type Passage = {
  id: number; source_id: number; source_title: string; author: string | null; label: string | null; title: string | null;
  page_start: number; page_end: number; citation: string; text: string; before: string | null; after: string | null;
  prev_id: number | null; next_id: number | null;
};

export class ApiError extends Error {
  constructor(message: string, public field?: string, public retryable = false) { super(message); }
}

async function upload({ files, title, author }: { files: File[]; title?: string; author?: string }): Promise<{ id: number; skipped: string[] }> {
  const fd = new FormData();
  if (title?.trim()) fd.append("title", title.trim());
  if (author?.trim()) fd.append("author", author.trim());
  files.forEach((f) => fd.append("files", f));
  const r = await fetch("/api/library/upload", { method: "POST", body: fd });      // no JSON header: the browser sets the boundary
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))).detail;
    throw new ApiError(typeof d === "string" ? d : d?.message ?? `Upload failed (${r.status})`, d?.field);
  }
  return r.json();
}

async function uploadAsset(sessionId: number, file: File): Promise<Asset> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/api/sessions/${sessionId}/assets`, { method: "POST", body: fd });       // no JSON header: the browser sets the boundary
  if (!r.ok) {
    const d = (await r.json().catch(() => ({}))).detail;
    throw new ApiError(typeof d === "string" ? d : d?.message ?? `Upload failed (${r.status})`, d?.code);
  }
  return r.json();
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const d = body.detail;
    throw new ApiError(typeof d === "string" ? d : d?.message ?? `Request failed (${r.status})`, d?.field ?? d?.code, d?.retryable === true);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

export const api = {
  setupStatus: (verify = false) => call<SetupStatus>(`/api/setup/status?verify=${verify}`),
  saveLlm: (b: LlmIn) => call<SetupStatus>("/api/setup/llm", { method: "POST", body: JSON.stringify(b) }),
  home: () => call<Home>("/api/home"),
  library: () => call<{ sources: Source[] }>("/api/library"),
  upload,
  cancel: (id: number) => call<{ ok: true }>(`/api/library/${id}/cancel`, { method: "POST" }),
  retry: (id: number) => call<{ ok: true }>(`/api/library/${id}/retry`, { method: "POST" }),
  remove: (id: number) => call<{ ok: true }>(`/api/library/${id}`, { method: "DELETE" }),
  findSkills: (id: number) => call<{ ok: true }>(`/api/library/${id}/find-skills`, { method: "POST" }),
  skillMap: () => call<SkillMap>("/api/skills"),
  pendingSkills: () => call<{ skills: Skill[] }>("/api/skills/pending"),
  patchSkill: (id: number, body: Partial<Pick<Skill, "name" | "description" | "practice_type">>) => call<Skill>(`/api/skills/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  setPrinciples: (id: number, items: { principle: string; test: string; chunk_id: number }[]) =>
    call<Skill>(`/api/skills/${id}/principles`, { method: "PUT", body: JSON.stringify(items) }),
  deleteSkill: (id: number) => call<{ outcome: "deleted" | "archived" | "discarded" }>(`/api/skills/${id}`, { method: "DELETE" }),
  splitSkill: (id: number, body: { name: string; principle_ids: number[] }) => call<{ new_skill: Skill; skill: Skill }>(`/api/skills/${id}/split`, { method: "POST", body: JSON.stringify(body) }),
  mergeSkill: (id: number, into: number) => call<{ outcome: string; skill: Skill }>(`/api/skills/${id}/merge`, { method: "POST", body: JSON.stringify({ into }) }),
  acceptSkill: (id: number) => call<Record<string, number>>(`/api/skills/${id}/accept`, { method: "POST" }),
  acceptAsNew: (id: number) => call<Record<string, number>>(`/api/skills/${id}/accept-as-new`, { method: "POST" }),
  skillMode: () => call<{ mode: "auto" | "manual" }>("/api/settings/skill-mode"),
  setSkillMode: (mode: "auto" | "manual") => call<{ mode: string }>("/api/settings/skill-mode", { method: "PUT", body: JSON.stringify({ mode }) }),
  projects: () => call<{ projects: Project[]; active: Project | null }>("/api/projects"),
  createProject: (b: ProjectIn) => call<Project>("/api/projects", { method: "POST", body: JSON.stringify(b) }),
  activateProject: (id: number) => call<Project>(`/api/projects/${id}/activate`, { method: "POST" }),
  shortlist: (projectId: number) => call<Shortlist>(`/api/projects/${projectId}/shortlist`, { method: "POST" }),
  activeSkill: () => call<{ active: ActiveSkill | null }>("/api/active-skill"),
  startSkill: (skillId: number, projectId: number, pause = false) =>
    call<{ session_id: number; skill_id: number; phase: string }>(`/api/skills/${skillId}/start`, { method: "POST", body: JSON.stringify({ project_id: projectId, pause_current: pause }) }),
  session: (id: number) => call<SessionView>(`/api/sessions/${id}`),
  act: (id: number, action: string, text = "") => call<SessionView>(`/api/sessions/${id}/act`, { method: "POST", body: JSON.stringify({ action, text }) }),
  saveDraft: (id: number, text: string) => call<{ ok: true }>(`/api/sessions/${id}/draft`, { method: "PUT", body: JSON.stringify({ text }) }),
  compare: (id: number, a: number, b: number) => call<Compare>(`/api/sessions/${id}/compare?a=${a}&b=${b}`),
  rate: (id: number, rating: string, cantStart = false) =>
    call<SessionView>(`/api/sessions/${id}/rating`, { method: "POST", body: JSON.stringify({ rating, cant_start: cantStart }) }),
  profile: () => call<{ sections: ProfileSection[] }>("/api/profile"),
  addNote: (text: string, section: string) => call<ProfileNote>("/api/profile/notes", { method: "POST", body: JSON.stringify({ text, section }) }),
  editNote: (id: number, text: string) => call<ProfileNote>(`/api/profile/notes/${id}`, { method: "PATCH", body: JSON.stringify({ text }) }),
  removeNote: (id: number) => call<{ ok: true }>(`/api/profile/notes/${id}`, { method: "DELETE" }),
  progress: () => call<ProgressData>("/api/progress"),
  uploadAsset,
  removeAsset: (id: number) => call<{ ok: true }>(`/api/assets/${id}`, { method: "DELETE" }),
  retryAsset: (id: number) => call<{ ok: true }>(`/api/assets/${id}/retry`, { method: "POST" }),
  vision: () => call<{ vision: boolean | null }>("/api/setup/vision"),
  nextSkill: (id: number) => call<{ next: PickCard | null; note: string | null; all_passed: boolean }>(`/api/sessions/${id}/next`),
  feltWrong: (messageId: number, note: string) => call<{ ok: true }>(`/api/messages/${messageId}/felt-wrong`, { method: "POST", body: JSON.stringify({ note }) }),
  passage: (id: number) => call<Passage>(`/api/chunks/${id}`),
};
