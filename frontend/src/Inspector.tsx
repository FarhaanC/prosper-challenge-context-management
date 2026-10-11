// The call inspector. About once a second it asks the server for the newest call log
// (backend/call_logs) and shows: the stage the call is in, the booking card, and every event
// in order, including the input and output tokens of each AI reply (decision 45).

import { useEffect, useRef, useState } from "react";
import { loadLatestCall, type CallEvent, type LatestCall } from "./api";

const POLL_MS = 1000;
const SHORT = 140; // characters of a tool's reply shown on its line; the rest is one click away

export function Inspector() {
  const [call, setCall] = useState<LatestCall | null>(null);
  const [error, setError] = useState("");
  const [live, setLive] = useState(true);
  const list = useRef<HTMLOListElement>(null);
  const atBottom = useRef(true);

  // Ask, wait for the answer, wait a second, ask again. Waiting for each answer means a slow
  // server can't pile up requests, and answers can't arrive out of order.
  useEffect(() => {
    if (!live) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
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
      if (!stopped) timer = setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      stopped = true; // paused or closed: stop asking
      clearTimeout(timer);
    };
  }, [live]);

  // New events scroll into view, unless the person has scrolled up to read something.
  const count = call?.events.length ?? 0;
  useEffect(() => {
    if (list.current && atBottom.current) list.current.scrollTop = list.current.scrollHeight;
  }, [count]);
  const onScroll = () => {
    const el = list.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  };

  const events = call?.events ?? [];
  const stage = [...events].reverse().find((e) => e.event === "stage")?.stage as string | undefined;
  const turns = events.filter((e) => e.event === "ai_turn");
  const total = (key: string) => turns.reduce((sum, e) => sum + Number(e[key] ?? 0), 0);
  const card = call?.card;
  const finished = card && card.status !== "in_progress";

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
        <span title="An AI reply the caller talks over is cut off before the AI service reports its tokens, so it isn't counted.">
          AI replies: {turns.length} · tokens in {total("input_tokens").toLocaleString()} · out{" "}
          {total("output_tokens").toLocaleString()} <span className="muted">(replies cut off by the caller aren't counted)</span>
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
              <dt>{finished ? "Last offered" : "On offer"}</dt>
              <dd>
                {card.options_on_offer.length ? (
                  <ul className={finished ? "muted" : ""}>
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
        <ol className="events" ref={list} onScroll={onScroll}>
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

/** A tool's reply in one short line: why it wasn't done, or what came back. */
function shortResult(event: CallEvent): string {
  if (event.error) return String(event.error); // the tool's code failed (a bug, not a refusal)
  const result = { ...((event.result ?? {}) as Record<string, unknown>) };
  // The reasons a tool gives, in the order a person would want them.
  for (const key of ["error", "say", "reasons", "problems", "which_one", "noted"]) {
    if (result[key] !== undefined) return clip(text(result[key]));
  }
  delete result.ok;
  return Object.keys(result).length ? clip(text(result)) : "";
}

function text(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) return value.join(" ");
  return JSON.stringify(value);
}

function clip(s: string): string {
  return s.length > SHORT ? `${s.slice(0, SHORT)}…` : s;
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
            <pre>{((e.instructions as string[]) ?? []).join("\n\n")}</pre>
          </details>
        </li>
      );
    case "tool": {
      const ok = (e.result as Record<string, unknown> | undefined)?.ok === true;
      const detail = shortResult(e);
      return (
        <li className={`ev tool${ok ? "" : " refused"}`}>
          {t} tool <strong>{String(e.tool)}</strong> <code>{JSON.stringify(e.args)}</code> → {ok ? "ok" : "not done"}
          {e.next_stage ? ` → ${String(e.next_stage)}` : ""}
          {detail && <span className="detail"> {detail}</span>}
          {e.said ? <div className="said">code said: “{String(e.said)}”</div> : null}
          <details>
            <summary>full reply</summary>
            <pre>{JSON.stringify(e.result ?? e.error, null, 2)}</pre>
          </details>
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
