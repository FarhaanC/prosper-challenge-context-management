// Everything the editor asks the server, and the shapes of what comes back.
// The server is backend/editor_api.py. The agent's shape matches backend/agent_builder/schema.py:
// the server refuses keys it doesn't know, so the editor never adds its own (box positions live
// in the browser instead, see graph.ts).

export type Message = { role: string; content: string };

/** A solid arrow: a move the AI chooses (a tool that only moves the call to `target`). */
export type Arrow = {
  function: string;
  description: string;
  target: string;
  properties?: Record<string, unknown>;
  required?: string[];
};

/** One stage of the call ("node" in the agent file). */
export type Stage = {
  name: string;
  task_messages: Message[];
  role_message?: string | null;
  edges?: Arrow[];
  tools?: string[];
  pre_actions?: unknown[];
  post_actions?: unknown[];
  end?: boolean;
  respond_immediately?: boolean;
};

export type Agent = {
  name: string;
  initial_node: string;
  nodes: Stage[];
  persona?: string;
  voice_id?: string;
  model?: string;
  global_tools?: string[];
  history?: string;
  parallel_tool_calls?: boolean;
};

/** A tool from the registry (backend/call/tools.py). Its code decides where it moves the call. */
export type Tool = { name: string; description: string; moves_to: string[]; fields: string[]; required: string[] };

export type CallEvent = { at: string; event: string; [key: string]: unknown };

export type Card = {
  caller: string;
  new_patient: boolean | null;
  wants: string;
  visit: string;
  doctor: string;
  place: string;
  time: string;
  status: string;
  options_on_offer: string[];
};

export type LatestCall = { file: string | null; events: CallEvent[]; card: Card | null };

export type SaveResult = { ok: true } | { ok: false; problems: string[] };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`);
  return response.json();
}

export const loadAgent = () => getJson<Agent>("/api/editor/agent");
export const loadTools = () => getJson<Tool[]>("/api/editor/tools");
export const loadPlaceholders = () => getJson<Record<string, string>>("/api/editor/placeholders");
export const loadLatestCall = () => getJson<LatestCall>("/api/editor/calls/latest");

/** Save the agent. The server checks it first; if it has problems, nothing is saved. */
export async function saveAgent(agent: Agent): Promise<SaveResult> {
  const response = await fetch("/api/editor/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(agent),
  });
  if (response.ok || response.status === 422) return response.json();
  throw new Error(`Saving failed: ${response.status} ${response.statusText}`);
}
