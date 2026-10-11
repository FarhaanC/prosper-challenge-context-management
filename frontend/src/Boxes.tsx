// The two kinds of box on the canvas. The small dots (Handles) are where arrows attach:
// arrows come in on the left and leave on the right.

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { AlwaysBoxData, StageBoxData } from "./graph";

export function StageBox({ data, selected }: NodeProps<Node<StageBoxData>>) {
  return (
    <div className={`box stage${selected ? " selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="box-title">
        {data.name}
        {data.isStart && <span className="badge start">start</span>}
        {data.ends && <span className="badge end">ends call</span>}
      </div>
      <ul className="box-tools">
        {data.tools.length ? data.tools.map((t) => <li key={t}>{t}</li>) : <li className="muted">no tools</li>}
      </ul>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export function AlwaysBox({ data, selected }: NodeProps<Node<AlwaysBoxData>>) {
  return (
    <div className={`box always${selected ? " selected" : ""}`}>
      <div className="box-title">Always available</div>
      <ul className="box-tools">
        {data.tools.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      {/* Arrows only leave this box: you can't move "to" the global tools. */}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

export const boxTypes = { stage: StageBox, always: AlwaysBox };
