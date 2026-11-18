import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import { FormattedText } from "./FormattedText";

export function DocumentPreview({ episode, file, onClose }: {
  episode: string; file: string; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setText(null);
    setError("");
    void (async () => {
      try {
        const response = await fetch(api.fileUrl(episode, file), { signal: controller.signal });
        if (!response.ok) throw new Error(response.status === 404 ? "This file could not be found." : "This file could not be opened.");
        const content = await response.text();
        if (!controller.signal.aborted) setText(content);
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "This file could not be opened.");
      }
    })();
    return () => controller.abort();
  }, [episode, file]);

  return createPortal(
    <dialog ref={dialog} className="document-preview" aria-label={`Read ${file}`} onCancel={onClose} onKeyDown={(event) => event.stopPropagation()}>
      <header className="document-preview-head">
        <div><strong>{file}</strong><p className="meta">Reading only. Close this view to review the approval.</p></div>
        <button type="button" onClick={onClose} autoFocus>Close</button>
      </header>
      <div className="document-preview-content" tabIndex={0}>
        {error ? <p role="alert">{error}</p> : text === null ? <p role="status">Opening file…</p> :
          /\.(md|markdown)$/i.test(file) ? <FormattedText text={text || "This file is empty."} /> :
            <pre className="document-preview-text">{text || "This file is empty."}</pre>}
      </div>
    </dialog>, document.body,
  );
}
