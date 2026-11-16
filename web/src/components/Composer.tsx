// The composer: the only text field in the app (DESIGN.md rule 3).
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

  // Grow with the text, up to eight lines; then the field scrolls.
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
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

  return (
    <>
      {error ? (
        <p className="composer-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="composer">
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
            className="icon-button"
            aria-label={listening ? "Stop listening" : "Speak"}
            aria-pressed={listening}
            onClick={toggleSpeech}
          >
            {listening ? <MicOff size={16} aria-hidden="true" /> : <Mic size={16} aria-hidden="true" />}
          </button>
        ) : null}
        <button
          type="button"
          className="icon-button send"
          aria-label="Send"
          disabled={!text.trim() || busy || !ready}
          onClick={() => void submit()}
        >
          <ArrowUp size={16} aria-hidden="true" />
        </button>
      </div>
    </>
  );
}
