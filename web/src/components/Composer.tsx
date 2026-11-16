// The composer: the one text field for sentences (DESIGN.md rule 3). A floating capsule with material (rule 18).
// Enter sends, Shift+Enter starts a new line, Ctrl/Cmd+Enter is left to "accept the open card".
import { ArrowUp, Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { messageOf, send } from "../store/actions";
import { useUi } from "../store/store";

interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}

type RecognitionCtor = new () => Recognition;

function speechCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const LINE = 23;
const MAX_LINES = 6;
const BARS = 5;

/**
 * Five small strokes that follow the microphone level while the browser listens. They write straight to the DOM,
 * so the composer does not re-render 60 times a second. Without microphone access they stay still.
 */
function useLevel(active: boolean) {
  const bars = useRef<Array<HTMLElement | null>>([]);
  useEffect(() => {
    if (!active || typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return;
    const Ctx =
      (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    let stopped = false;
    let frame = 0;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        if (stopped) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        ctx = new Ctx();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        ctx.createMediaStreamSource(s).connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          analyser.getByteFrequencyData(data);
          const band = Math.floor(data.length / (BARS * 2));
          for (let i = 0; i < BARS; i += 1) {
            let sum = 0;
            for (let j = 0; j < band; j += 1) sum += data[i * band + j] ?? 0;
            const level = Math.min(1, sum / band / 160);
            const el = bars.current[i];
            if (el) el.style.transform = `scaleY(${(0.25 + level * 0.75).toFixed(2)})`;
          }
          frame = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch(() => undefined);
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close();
      for (const el of bars.current) if (el) el.style.transform = "";
    };
  }, [active]);
  return bars;
}

export function Composer() {
  const onboarding = useUi((s) => s.state !== null && !s.state.app.onboarded);
  const ready = useUi((s) => s.boot === "ready");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const recognition = useRef<Recognition | null>(null);
  const base = useRef("");
  const Speech = speechCtor();
  const bars = useLevel(listening);

  // Grow with the text, up to six lines; then the field scrolls inside.
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, LINE * MAX_LINES)}px`;
  }, [text]);

  useEffect(() => () => recognition.current?.stop(), []);

  async function submit() {
    const value = text.trim();
    if (!value || busy || !ready) return;
    recognition.current?.stop();
    setBusy(true);
    setError(null);
    try {
      await send(value);
      setText("");
    } catch (e) {
      setError(`Couldn't send. ${messageOf(e)}`);
    } finally {
      setBusy(false);
      area.current?.focus();
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
    if (e.ctrlKey || e.metaKey) return; // accepts the open card (handled by the app)
    if (e.shiftKey) return; // new line
    e.preventDefault();
    void submit();
  }

  function toggleSpeech() {
    if (!Speech) return;
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const r = new Speech();
    r.lang = navigator.language || "en-US";
    r.continuous = true;
    r.interimResults = true;
    base.current = text ? `${text.trimEnd()} ` : "";
    r.onresult = (e) => {
      let said = "";
      for (let i = 0; i < e.results.length; i += 1) said += e.results[i]?.[0]?.transcript ?? "";
      setText(base.current + said.trimStart());
    };
    r.onend = () => setListening(false);
    r.onerror = (e) => {
      setListening(false);
      if (e.error === "not-allowed") setError("The browser blocked the microphone. Allow it for this page, or type.");
    };
    recognition.current = r;
    setError(null);
    r.start();
    setListening(true);
  }

  const placeholder = onboarding ? "Paste your links." : "Say what you want…";
  const hasText = text.trim().length > 0;

  return (
    <>
      {error ? (
        <p className="composer-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className={listening ? "composer listening" : "composer"}>
        {listening ? (
          <span className="level" aria-hidden="true">
            {Array.from({ length: BARS }, (_, i) => (
              <i
                key={i}
                ref={(el) => {
                  bars.current[i] = el;
                }}
              />
            ))}
          </span>
        ) : null}
        <label htmlFor="composer" className="sr-only">
          Message
        </label>
        <textarea
          id="composer"
          ref={area}
          rows={1}
          value={text}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          enterKeyHint="send"
        />
        {Speech ? (
          <button
            type="button"
            className={listening ? "icon-button mic on" : "icon-button mic"}
            aria-label={listening ? "Stop listening" : "Speak"}
            aria-pressed={listening}
            onClick={toggleSpeech}
          >
            {listening ? <MicOff size={16} aria-hidden="true" /> : <Mic size={16} aria-hidden="true" />}
          </button>
        ) : null}
        <button
          type="button"
          className={hasText ? "send ready" : "send"}
          aria-label="Send"
          disabled={!hasText || busy || !ready}
          onClick={() => void submit()}
        >
          <ArrowUp size={16} aria-hidden="true" />
        </button>
      </div>
    </>
  );
}
