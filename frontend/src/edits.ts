// Every change the editor can make to the agent. Each function takes the agent and returns a
// new, changed copy (React redraws when it gets a new object; the old one is never modified).

import type { Agent, Stage, Tool } from "./api";

/** Change some fields of one stage. Renaming also updates the arrows and the start stage. */
export function updateStage(agent: Agent, name: string, change: Partial<Stage>): Agent {
  const newName = change.name ?? name;
  return {
    ...agent,
    initial_node: agent.initial_node === name ? newName : agent.initial_node,
    nodes: agent.nodes.map((stage) => {
      const updated = stage.name === name ? { ...stage, ...change } : stage;
      if (newName === name || !updated.edges) return updated;
      return { ...updated, edges: updated.edges.map((a) => (a.target === name ? { ...a, target: newName } : a)) };
    }),
  };
}

export function addStage(agent: Agent): { agent: Agent; name: string } {
  const taken = new Set(agent.nodes.map((s) => s.name));
  let n = 1;
  while (taken.has(`new_stage_${n}`)) n++;
  const name = `new_stage_${n}`;
  const stage: Stage = { name, task_messages: [{ role: "developer", content: "" }], tools: [] };
  return { agent: { ...agent, nodes: [...agent.nodes, stage] }, name };
}

/** Remove a stage. Arrows into it and tools that move there are kept as they are, so Save
 *  lists them as problems: nothing the person wrote disappears without them seeing it. */
export function deleteStage(agent: Agent, name: string): Agent {
  return { ...agent, nodes: agent.nodes.filter((s) => s.name !== name) };
}

/** A new solid arrow, from dragging one box onto another. The AI calls an arrow like a tool,
 *  so its name may only use letters, digits, _ and -, and must be new in this stage. The name
 *  and wording can be changed in the side panel. */
export function addArrow(agent: Agent, from: string, to: string, tools: Tool[]): Agent {
  const stage = agent.nodes.find((s) => s.name === from);
  if (!stage) return agent;
  const taken = new Set([...(stage.edges ?? []).map((a) => a.function), ...tools.map((t) => t.name)]);
  const base = `go_to_${to.replace(/[^A-Za-z0-9_-]+/g, "_")}`.slice(0, 60);
  let name = base;
  for (let n = 2; taken.has(name); n++) name = `${base}_${n}`;
  const arrow = { function: name, description: `Call this to move the conversation to ${to}.`, target: to };
  return updateStage(agent, from, { edges: [...(stage.edges ?? []), arrow] });
}

/** Add or remove one tool name in a list (a stage's tools, or the always-available ones). */
export function toggle(list: string[] | undefined, name: string): string[] {
  const current = list ?? [];
  return current.includes(name) ? current.filter((n) => n !== name) : [...current, name];
}
