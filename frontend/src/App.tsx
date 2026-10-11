// The editor's main screen: a top bar (Save, Test call), the canvas in the middle, the side
// panel on the right, and the call inspector at the bottom.
//
// The agent being edited lives in one piece of state (`agent`). Every edit makes a new copy
// (see edits.ts) and React redraws. `savedJson` is the agent as last loaded or saved, so we can
// tell whether there are unsaved changes.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from "@xyflow/react";
import { loadAgent, loadPlaceholders, loadTools, saveAgent, type Agent, type Stage, type Tool } from "./api";
import { boxTypes } from "./Boxes";
import { addArrow, addStage, deleteStage, updateStage } from "./edits";
import { ALWAYS, buildEdges, buildNodes, loadPositions, savePositions, type Positions } from "./graph";
import { Inspector } from "./Inspector";
import { AgentPanel, StagePanel } from "./Panels";

// The call page is Pipecat's own. Served by the agent itself it's on the same address; while
// developing with `npm run dev` the editor is on another port, so we point at the agent directly.
const CALL_PAGE = import.meta.env.DEV ? "http://localhost:7860/client/" : "/client/";

/** What the last Save said: nothing yet, saved, or the problems it found (kept on screen while
 *  the person fixes them, until the next Save), or an error reaching the server. */
type SaveOutcome = { kind: "none" } | { kind: "saved" } | { kind: "problems"; problems: string[] } | { kind: "error"; message: string };

export default function App() {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [savedJson, setSavedJson] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const [placeholders, setPlaceholders] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null); // a stage name, or null for agent settings
  const [outcome, setOutcome] = useState<SaveOutcome>({ kind: "none" });
  const [saving, setSaving] = useState(false);
  const [renameProblem, setRenameProblem] = useState(""); // shown under its own heading, not as a Save problem
  const [loadError, setLoadError] = useState("");
  const [showCall, setShowCall] = useState(false);
  const [positions, setPositions] = useState<Positions>(loadPositions);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null);

  // Load everything once when the page opens.
  useEffect(() => {
    Promise.all([loadAgent(), loadTools(), loadPlaceholders()])
      .then(([a, t, p]) => {
        setAgent(a);
        setSavedJson(JSON.stringify(a));
        setTools(t);
        setPlaceholders(p);
      })
      .catch((e) => setLoadError(`Couldn't load the agent: ${e}`));
  }, []);

  // Boxes: rebuilt from the agent whenever it (or the selection) changes, keeping what React
  // Flow measured about each box, which it needs to draw the arrows.
  useEffect(() => {
    if (!agent) return;
    setNodes((previous) => {
      const before = new Map(previous.map((n) => [n.id, n]));
      return buildNodes(agent, positions, selected).map((n) => {
        const old = before.get(n.id);
        return old ? { ...old, data: n.data, position: n.position, selected: n.selected } : n;
      });
    });
  }, [agent, positions, selected]);

  const edges = useMemo(() => (agent ? buildEdges(agent, tools) : []), [agent, tools]);

  // Which box is highlighted is decided by `selected` alone (the stage in the side panel), so
  // React Flow's own selection changes are left out.
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((ns) => applyNodeChanges(changes.filter((c) => c.type !== "select"), ns)),
    [],
  );

  // When a box is dropped after dragging, remember where (in this browser only).
  const onNodeDragStop = useCallback((_: unknown, node: Node) => {
    setPositions((p) => {
      const next = { ...p, [node.id]: node.position };
      savePositions(next);
      return next;
    });
  }, []);

  // Show every box again when a stage is added or removed, or the call panel opens or closes.
  const stageCount = agent?.nodes.length ?? 0;
  useEffect(() => {
    const timer = setTimeout(() => flow?.fitView({ duration: 200 }), 50); // after the boxes are drawn
    return () => clearTimeout(timer);
  }, [flow, stageCount, showCall]);

  if (!agent) {
    return <div className="loading">{loadError || "Loading the agent…"}</div>;
  }

  const edit = (next: Agent) => {
    setAgent(next);
    setRenameProblem("");
    if (outcome.kind === "saved") setOutcome({ kind: "none" });
  };
  const stage = agent.nodes.find((s) => s.name === selected);
  const dirty = JSON.stringify(agent) !== savedJson;

  const save = async () => {
    setSaving(true);
    try {
      const result = await saveAgent(agent);
      if (result.ok) {
        setSavedJson(JSON.stringify(agent));
        setOutcome({ kind: "saved" });
      } else {
        setOutcome({ kind: "problems", problems: result.problems });
      }
    } catch (e) {
      setOutcome({ kind: "error", message: String(e) });
    } finally {
      setSaving(false);
    }
  };

  const renameStage = (oldName: string, newName: string): boolean => {
    if (agent.nodes.some((s) => s.name === newName)) {
      setRenameProblem(`There's already a stage called '${newName}', so '${oldName}' keeps its name.`);
      return false;
    }
    edit(updateStage(agent, oldName, { name: newName }));
    setSelected(newName);
    if (positions[oldName]) {
      const { [oldName]: place, ...rest } = positions;
      const next = { ...rest, [newName]: place };
      setPositions(next);
      savePositions(next);
    }
    return true;
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>{agent.name}</h1>
        <button
          onClick={() => {
            const added = addStage(agent);
            edit(added.agent);
            setSelected(added.name);
          }}
        >
          + Stage
        </button>
        <button className="primary" disabled={!dirty || saving} onClick={save}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={() => setShowCall((v) => !v)}>{showCall ? "Close call" : "Test call"}</button>
        <span className="status">
          {outcome.kind === "saved" && !dirty && "Saved. The next call uses it."}
          {outcome.kind === "error" && <span className="error-text">{outcome.message}</span>}
          {dirty && "Unsaved changes"}
        </span>
      </header>

      {renameProblem && (
        <div className="problems">
          <strong>Can't rename the stage:</strong> {renameProblem}
        </div>
      )}

      {outcome.kind === "problems" && (
        <div className="problems">
          <strong>Not saved. Fix these, then Save again{dirty ? " (this list is from the last Save)" : ""}:</strong>
          <ul>
            {outcome.problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <main className="middle">
        <div className="canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={boxTypes}
            onInit={setFlow}
            onNodesChange={onNodesChange}
            onNodeDragStop={onNodeDragStop}
            onNodeClick={(_, n) => setSelected(n.id === ALWAYS ? null : n.id)}
            onPaneClick={() => setSelected(null)}
            onConnect={(c: Connection) => edit(addArrow(agent, c.source, c.target, tools))}
            fitView
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
          <div className="legend">
            <span>── the AI's own move</span>
            <span>- - - a tool's code moves the call</span>
          </div>
        </div>

        <aside className="side">
          {stage ? (
            <StagePanel
              key={stage.name}
              agent={agent}
              stage={stage}
              tools={tools}
              placeholders={placeholders}
              onChange={(change: Partial<Stage>) => edit(updateStage(agent, stage.name, change))}
              onRename={(newName) => renameStage(stage.name, newName)}
              onMakeStart={() => edit({ ...agent, initial_node: stage.name })}
              onDelete={() => {
                edit(deleteStage(agent, stage.name));
                setSelected(null);
              }}
            />
          ) : (
            <AgentPanel agent={agent} tools={tools} onChange={(change) => edit({ ...agent, ...change })} />
          )}
        </aside>

        {showCall && (
          <aside className="call">
            <div className="call-head">
              Test call <a href={CALL_PAGE} target="_blank" rel="noreferrer">open in a new tab</a>
            </div>
            {dirty && <p className="warning">You have unsaved changes: this call uses the last saved version.</p>}
            <iframe src={CALL_PAGE} title="Test call" allow="microphone; autoplay" />
          </aside>
        )}
      </main>

      <Inspector />
    </div>
  );
}
