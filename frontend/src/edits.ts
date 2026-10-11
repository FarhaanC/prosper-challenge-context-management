// Every change the editor can make to the agent. Each function takes the agent and returns a
// new, changed copy (React redraws when it gets a new object; the old one is never modified).

import type { Agent, Stage } from "./api";

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

/** Remove a stage and the solid arrows into it. Tools that can still move there are left for
 *  Save's checks to report, so nothing is changed silently. */
export function deleteStage(agent: Agent, name: string): Agent {
  return {
    ...agent,
    nodes: agent.nodes
      .filter((s) => s.name !== name)
      .map((s) => (s.edges ? { ...s, edges: s.edges.filter((a) => a.target !== name) } : s)),
  };
}

/** A new solid arrow, from dragging one box onto another. Its name and wording are editable. */
export function addArrow(agent: Agent, from: string, to: string): Agent {
  const stage = agent.nodes.find((s) => s.name === from);
  if (!stage) return agent;
  const arrow = { function: `go_to_${to}`, description: `Call this to move the conversation to ${to}.`, target: to };
  return updateStage(agent, from, { edges: [...(stage.edges ?? []), arrow] });
}

/** Add or remove one tool name in a list (a stage's tools, or the always-available ones). */
export function toggle(list: string[] | undefined, name: string): string[] {
  const current = list ?? [];
  return current.includes(name) ? current.filter((n) => n !== name) : [...current, name];
}
