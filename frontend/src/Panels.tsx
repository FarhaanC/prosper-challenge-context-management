// The side panel. With a stage selected it edits that stage; otherwise it edits the agent's
// own settings (name, persona, always-available tools...).

import { useState } from "react";
import type { Agent, Arrow, Stage, Tool } from "./api";
import { toggle } from "./edits";

// The AI models offered (decision 68 compares the larger and the smaller one). A list, so a
// typo can't break every call.
const MODELS = ["gpt-4o", "gpt-4o-mini"];

type StageProps = {
  agent: Agent;
  stage: Stage;
  tools: Tool[];
  placeholders: Record<string, string>;
  onChange: (change: Partial<Stage>) => void;
  /** Rename the stage. Returns false if it couldn't (App says why). */
  onRename: (newName: string) => boolean;
  onMakeStart: () => void;
  onDelete: () => void;
};

export function StagePanel({ agent, stage, tools, placeholders, onChange, onRename, onMakeStart, onDelete }: StageProps) {
  // The name is typed into a draft and applied on Enter or when leaving the field, so the box
  // isn't renamed (and its arrows rewired) on every key press. (The panel starts afresh for
  // each stage: App gives it the stage's name as its key.)
  const [draftName, setDraftName] = useState(stage.name);
  const commitName = () => {
    const name = draftName.trim();
    if (!name || name === stage.name || !onRename(name)) setDraftName(stage.name); // the field shows the real name
  };

  const globals = agent.global_tools ?? [];
  const stageNames = agent.nodes.map((s) => s.name);
  const messages = stage.task_messages?.length ? stage.task_messages : [{ role: "developer", content: "" }];
  const arrows = stage.edges ?? [];
  const setArrow = (i: number, change: Partial<Arrow>) =>
    onChange({ edges: arrows.map((a, j) => (j === i ? { ...a, ...change } : a)) });
  // Tools whose code moves the call to this stage by its name: renaming it would break them.
  const neededBy = tools.filter((t) => t.moves_to.includes(stage.name)).map((t) => t.name);

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
      {neededBy.length > 0 && (
        <p className="muted">
          The code of {neededBy.join(", ")} moves the call to this stage by its name, so keep the name.
        </p>
      )}

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
      {stage.role_message && (
        <p className="muted">This stage has its own role, which replaces the agent's persona here.</p>
      )}
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
        const listed = (stage.tools ?? []).includes(tool.name);
        return (
          <label key={tool.name} className="check tool" title={tool.description}>
            {/* An always-available tool is ticked and fixed here, unless this stage lists it too
                (Save refuses that): then the tick works, so it can be taken out of this stage. */}
            <input
              type="checkbox"
              disabled={global && !listed}
              checked={global || listed}
              onChange={() => onChange({ tools: toggle(stage.tools, tool.name) })}
            />
            <span>
              <strong>{tool.name}</strong>
              {global ? " (always available)" : ""}
              {tool.moves_to.length ? ` → ${tool.moves_to.join(", ")}` : " (stays)"}
              <br />
              <span className="muted">{tool.description}</span>
              {tool.fields.length > 0 && (
                <>
                  <br />
                  <span className="muted fields">
                    Takes: {tool.fields.map((f) => (tool.required.includes(f) ? `${f} (needed)` : f)).join(", ")}
                  </span>
                </>
              )}
            </span>
          </label>
        );
      })}

      <h3>Arrows out (moves the AI chooses)</h3>
      {arrows.length === 0 && <p className="muted">None. Drag from this box to another to add one.</p>}
      {arrows.map((arrow, i) => (
        <div key={i} className="arrow">
          <label>
            Tool name (letters, digits, _ and - only)
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

type AgentProps = {
  agent: Agent;
  tools: Tool[];
  onChange: (change: Partial<Agent>) => void;
};

export function AgentPanel({ agent, tools, onChange }: AgentProps) {
  const model = agent.model ?? MODELS[0];
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
        <select value={model} onChange={(e) => onChange({ model: e.target.value })}>
          {/* A model already in the file but not in the list stays visible, so it isn't changed by accident. */}
          {!MODELS.includes(model) && <option value={model}>{model}</option>}
          {MODELS.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
      </label>
      <label>
        Voice id (ElevenLabs)
        <input value={agent.voice_id ?? ""} onChange={(e) => onChange({ voice_id: e.target.value })} />
      </label>
      <p className="muted">A wrong voice id leaves calls silent: copy it from ElevenLabs.</p>
      <h3>Persona (applies in every stage without its own role)</h3>
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
