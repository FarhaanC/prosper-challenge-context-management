// The call inspector. Once a second it asks the server for the newest call log
// (backend/call_logs) and shows: the stage the call is in, the booking card, and every event
// in order, including the input and output tokens of each AI reply (decision 45).

import { useEffect, useRef, useState } from "react";
import { loadLatestCall, type CallEvent, type LatestCall } from "./api";

const POLL_MS = 1000;

export function Inspector() {
  const [call, setCall] = useState<LatestCall | null>(null);
  const [error, setError] = useState("");
  const [live, setLive] = useState(true);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (!live) return;
    let stopped = false;
    const poll = async () => {
      try {
        const latest = await loadLatestCall();
        if (!stopped) {
          setCall(latest);
          setError("");
        }
      } catch (e) {
        if (!stopped) setError(String(e));
      }
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      stopped = true; // the inspector was paused or closed: stop asking
      clearInterval(timer);
    };
  }, [live]);

  // Keep the newest event in view when new ones arrive.
  const count = call?.events.length ?? 0;
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [count]);

  const events = call?.events ?? [];
  const stage = [...events].reverse().find((e) => e.event === "stage")?.stage as string | undefined;
  const turns = events.filter((e) => e.event === "ai_turn");
  const total = (key: string) => turns.reduce((sum, e) => sum + Number(e[key] ?? 0), 0);
  const card = call?.card;

  return (
    <div className="inspector">
      <div className="inspector-head">
        <strong>Call inspector</strong>
        <span className="muted">{call?.file ?? "no calls yet"}</span>
        {stage && (
          <span>
            Stage: <span className="badge start">{stage}</span>
          </span>
        )}
        <span>
          AI replies: {turns.length} · tokens in {total("input_tokens").toLocaleString()} · out{" "}
          {total("output_tokens").toLocaleString()}
        </span>
        <label className="check">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live
        </label>
        {error && <span className="error-text">{error}</span>}
      </div>
      <div className="inspector-body">
        <div className="card">
          <h3>Booking card</h3>
          {card ? (
            <dl>
              <dt>Caller</dt>
              <dd>{card.caller ? `${card.caller}${card.new_patient ? " (new)" : ""}` : "not identified yet"}</dd>
              <dt>Wants</dt>
              <dd>{card.visit || card.wants || "-"}</dd>
              <dt>Chosen</dt>
              <dd>{card.doctor ? `${card.doctor}, ${card.place}, ${card.time.replace("T", " ")}` : "-"}</dd>
              <dt>Status</dt>
              <dd>{card.status}</dd>
              <dt>On offer</dt>
              <dd>
                {card.options_on_offer.length ? (
                  <ul>
                    {card.options_on_offer.map((o) => (
                      <li key={o}>{o}</li>
                    ))}
                  </ul>
                ) : (
                  "-"
                )}
              </dd>
            </dl>
          ) : (
            <p className="muted">No call yet.</p>
          )}
        </div>
        <ol className="events" ref={list}>
          {events.map((e, i) => (
            <EventLine key={i} event={e} />
          ))}
        </ol>
      </div>
    </div>
  );
}

function time(e: CallEvent): string {
  return e.at.split("T")[1] ?? e.at;
}

/** One event from the call log, in a line a person can read. */
function EventLine({ event: e }: { event: CallEvent }) {
  const t = <span className="time">{time(e)}</span>;
  switch (e.event) {
    case "stage":
      return (
        <li className="ev stage">
          {t} → stage <strong>{String(e.stage)}</strong>
          <details>
            <summary>instructions the AI was given</summary>
            <pre>{(e.instructions as string[]).join("\n\n")}</pre>
          </details>
        </li>
      );
    case "tool": {
      const result = (e.result ?? {}) as Record<string, unknown>;
      const ok = result.ok === true;
      const detail = e.error ?? result.error ?? result.say ?? "";
      return (
        <li className={`ev tool${ok ? "" : " refused"}`}>
          {t} tool <strong>{String(e.tool)}</strong> <code>{JSON.stringify(e.args)}</code> → {ok ? "ok" : "not done"}
          {e.next_stage ? ` → ${String(e.next_stage)}` : ""}
          {detail ? <span className="muted"> {String(detail)}</span> : null}
          {e.said ? <div className="said">code said: “{String(e.said)}”</div> : null}
        </li>
      );
    }
    case "ai_turn":
      return (
        <li className="ev ai">
          {t} AI reply: {Number(e.input_tokens).toLocaleString()} tokens in, {Number(e.output_tokens).toLocaleString()} out
          {Number(e.cached_input_tokens) ? ` (${Number(e.cached_input_tokens).toLocaleString()} cached)` : ""}
        </li>
      );
    case "silence":
    case "time_limit":
      return (
        <li className="ev said">
          {t} {e.event === "silence" ? "silence" : "time limit"}: code said “{String(e.said)}”
          {e.hang_up ? " and hung up" : ""}
        </li>
      );
    default:
      return (
        <li className="ev">
          {t} {e.event}
        </li>
      );
  }
}
