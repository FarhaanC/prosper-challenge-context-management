// The side panel. With a stage selected it edits that stage; otherwise it edits the agent's
// own settings (name, persona, always-available tools...).

import { useEffect, useState } from "react";
import type { Agent, Arrow, Stage, Tool } from "./api";
import { toggle } from "./edits";

type StageProps = {
  agent: Agent;
  stage: Stage;
  tools: Tool[];
  placeholders: Record<string, string>;
  onChange: (change: Partial<Stage>) => void;
  onRename: (newName: string) => void;
  onMakeStart: () => void;
  onDelete: () => void;
};

export function StagePanel({ agent, stage, tools, placeholders, onChange, onRename, onMakeStart, onDelete }: StageProps) {
  // The name is typed into a draft and applied on Enter or when leaving the field, so the box
  // isn't renamed (and its arrows rewired) on every key press.
  const [draftName, setDraftName] = useState(stage.name);
  useEffect(() => setDraftName(stage.name), [stage.name]);
  const commitName = () => {
    const name = draftName.trim();
    if (name && name !== stage.name) onRename(name);
    else setDraftName(stage.name);
  };

  const globals = agent.global_tools ?? [];
  const stageNames = agent.nodes.map((s) => s.name);
  const messages = stage.task_messages.length ? stage.task_messages : [{ role: "developer", content: "" }];
  const arrows = stage.edges ?? [];
  const setArrow = (i: number, change: Partial<Arrow>) =>
    onChange({ edges: arrows.map((a, j) => (j === i ? { ...a, ...change } : a)) });

  return (
    <div className="panel">
      <h2>Stage</h2>

      <label>
        Name
        <input
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => e.key === "Enter" && commitName()}
        />
      </label>

      <div className="row">
        <label className="check">
          <input type="radio" checked={agent.initial_node === stage.name} onChange={onMakeStart} />
          Calls start here
        </label>
        <label className="check">
          <input type="checkbox" checked={!!stage.end} onChange={(e) => onChange({ end: e.target.checked })} />
          Ends the call
        </label>
      </div>

      <h3>Instructions</h3>
      {messages.map((m, i) => (
        <textarea
          key={i}
          rows={12}
          value={m.content}
          onChange={(e) =>
            onChange({ task_messages: messages.map((msg, j) => (j === i ? { ...msg, content: e.target.value } : msg)) })
          }
        />
      ))}
      <details className="hint">
        <summary>Placeholders you can use</summary>
        <p>The code fills these in when the stage starts:</p>
        <ul>
          {Object.entries(placeholders).map(([name, meaning]) => (
            <li key={name}>
              <code>{`{${name}}`}</code> {meaning}
            </li>
          ))}
        </ul>
      </details>

      <h3>Tools in this stage</h3>
      <p className="muted">Dashed arrows show where each tool's code can move the call.</p>
      {tools.map((tool) => {
        const global = globals.includes(tool.name);
        return (
          <label key={tool.name} className="check tool" title={tool.description}>
            <input
              type="checkbox"
              disabled={global}
              checked={global || (stage.tools ?? []).includes(tool.name)}
              onChange={() => onChange({ tools: toggle(stage.tools, tool.name) })}
            />
            <span>
              <strong>{tool.name}</strong>
              {global ? " (always available)" : ""}
              {tool.moves_to.length ? ` → ${tool.moves_to.join(", ")}` : " (stays)"}
              <br />
              <span className="muted">{tool.description}</span>
            </span>
          </label>
        );
      })}

      <h3>Arrows out (moves the AI chooses)</h3>
      {arrows.length === 0 && <p className="muted">None. Drag from this box to another to add one.</p>}
      {arrows.map((arrow, i) => (
        <div key={i} className="arrow">
          <label>
            Tool name
            <input value={arrow.function} onChange={(e) => setArrow(i, { function: e.target.value })} />
          </label>
          <label>
            When to use it
            <input value={arrow.description} onChange={(e) => setArrow(i, { description: e.target.value })} />
          </label>
          <label>
            Goes to
            <select value={arrow.target} onChange={(e) => setArrow(i, { target: e.target.value })}>
              {!stageNames.includes(arrow.target) && <option value={arrow.target}>{arrow.target} (missing)</option>}
              {stageNames.map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <button className="link" onClick={() => onChange({ edges: arrows.filter((_, j) => j !== i) })}>
            Remove arrow
          </button>
        </div>
      ))}

      <button className="danger" onClick={onDelete}>
        Delete this stage
      </button>
    </div>
  );
}

type AgentProps = { agent: Agent; tools: Tool[]; onChange: (change: Partial<Agent>) => void };

export function AgentPanel({ agent, tools, onChange }: AgentProps) {
  return (
    <div className="panel">
      <h2>Agent</h2>
      <p className="muted">Click a stage to edit it. Drag from one box to another to add an arrow.</p>
      <label>
        Name
        <input value={agent.name} onChange={(e) => onChange({ name: e.target.value })} />
      </label>
      <label>
        AI model
        <input value={agent.model ?? ""} onChange={(e) => onChange({ model: e.target.value })} />
      </label>
      <label>
        Voice id (ElevenLabs)
        <input value={agent.voice_id ?? ""} onChange={(e) => onChange({ voice_id: e.target.value })} />
      </label>
      <h3>Persona (applies in every stage)</h3>
      <textarea rows={8} value={agent.persona ?? ""} onChange={(e) => onChange({ persona: e.target.value })} />
      <h3>Always-available tools</h3>
      {tools.map((tool) => (
        <label key={tool.name} className="check tool" title={tool.description}>
          <input
            type="checkbox"
            checked={(agent.global_tools ?? []).includes(tool.name)}
            onChange={() => onChange({ global_tools: toggle(agent.global_tools, tool.name) })}
          />
          <span>
            <strong>{tool.name}</strong>
            {tool.moves_to.length ? ` → ${tool.moves_to.join(", ")}` : " (stays)"}
          </span>
        </label>
      ))}
    </div>
  );
}
