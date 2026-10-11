// Turns the agent into the boxes and arrows React Flow draws. Nothing here changes the agent.
//
// - One box per stage, plus one "Always available" box for the global tools.
// - Solid arrows: the stage's own moves (edges in the agent file), which the AI chooses.
// - Dashed arrows: moves decided by code. A tool's code (backend/call/tools.py) can move the
//   call to the stages in its `moves_to`; we draw one arrow per stage it can reach, labelled
//   with the tools that lead there.

import type { ReactNode } from "react";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { Agent, Tool } from "./api";

export const ALWAYS = "__always__"; // id of the "Always available" box

export type Positions = Record<string, { x: number; y: number }>;

export type StageBoxData = { name: string; tools: string[]; isStart: boolean; ends: boolean };
export type AlwaysBoxData = { tools: string[] };

const GAP_X = 300; // between stages, left to right
const STEP_Y = 170; // every other stage sits lower, so an arrow that skips a stage passes beside it, not behind it

/** Where a box goes when it has no saved position: stages left to right in a zig-zag, the
 *  "Always available" box under the first one, so its arrows fan out to the right. */
function defaultPosition(index: number): { x: number; y: number } {
  if (index < 0) return { x: 0, y: 2.4 * STEP_Y };
  return { x: index * GAP_X, y: index % 2 ? STEP_Y : 0 };
}

/** An arrow's label: one tool name per line, so labels of arrows side by side don't overlap. */
function toolLabel(names: string[]): ReactNode {
  if (names.length === 1) return names[0];
  return names.map((name, i) => (
    // The first line is lifted by half the extra lines, so the block stays centred on the arrow.
    <tspan key={name} x={0} dy={i === 0 ? `${-(names.length - 1) * 0.6}em` : "1.2em"}>
      {name}
    </tspan>
  ));
}

/** The boxes. `selected` is the stage open in the side panel: its box is the highlighted one. */
export function buildNodes(agent: Agent, positions: Positions, selected: string | null): Node[] {
  const stages: Node[] = agent.nodes.map((stage, i) => ({
    id: stage.name,
    type: "stage",
    selected: stage.name === selected,
    position: positions[stage.name] ?? defaultPosition(i),
    data: {
      name: stage.name,
      tools: stage.tools ?? [],
      isStart: agent.initial_node === stage.name,
      ends: !!stage.end,
    } satisfies StageBoxData,
  }));
  const always: Node = {
    id: ALWAYS,
    type: "always",
    selected: false,
    position: positions[ALWAYS] ?? defaultPosition(-1),
    data: { tools: agent.global_tools ?? [] } satisfies AlwaysBoxData,
  };
  return [...stages, always];
}

export function buildEdges(agent: Agent, tools: Tool[]): Edge[] {
  const registry = new Map(tools.map((t) => [t.name, t]));
  const stageNames = new Set(agent.nodes.map((s) => s.name));
  const edges: Edge[] = [];

  // Solid: the AI's own moves.
  for (const stage of agent.nodes) {
    (stage.edges ?? []).forEach((arrow, i) => {
      if (!stageNames.has(arrow.target)) return; // a broken arrow: Save lists it as a problem
      edges.push({
        id: `move:${stage.name}:${i}`,
        source: stage.name,
        target: arrow.target,
        label: arrow.function,
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    });
  }

  // Dashed: where each tool's code can move the call. Tools leading the same way share one arrow.
  const dashed = (from: string, toolNames: string[]) => {
    const byTarget = new Map<string, string[]>();
    for (const name of toolNames) {
      for (const target of registry.get(name)?.moves_to ?? []) {
        if (target === from || !stageNames.has(target)) continue; // no arrow back to itself
        byTarget.set(target, [...(byTarget.get(target) ?? []), name]);
      }
    }
    for (const [target, names] of byTarget) {
      edges.push({
        id: `code:${from}:${target}`,
        source: from,
        target,
        label: toolLabel(names),
        className: "code-decided",
        style: { strokeDasharray: "6 4" },
        markerEnd: { type: MarkerType.ArrowClosed },
      });
    }
  };
  for (const stage of agent.nodes) dashed(stage.name, stage.tools ?? []);
  dashed(ALWAYS, agent.global_tools ?? []);
  return edges;
}

const STORAGE_KEY = "agent-editor-positions";

export function loadPositions(): Positions {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {}; // private window or blocked storage: boxes just use their default places
  }
}

export function savePositions(positions: Positions): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
  } catch {
    // not saved; the boxes go back to their default places next time
  }
}
