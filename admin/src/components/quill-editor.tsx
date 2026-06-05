import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import Quill from "quill";
import "quill/dist/quill.snow.css";

export interface QuillHandle {
  /** Replace the whole document with plain text (used for streaming). */
  setText: (text: string) => void;
  /** Replace the whole document with HTML. */
  setHTML: (html: string) => void;
  getText: () => string;
}

/**
 * Thin React wrapper around vanilla Quill (avoids react-quill's React-18
 * findDOMNode issues). Uncontrolled: `initialHTML` seeds the editor once, then
 * `onChange` streams the current HTML + plain text out. Imperative `setText` /
 * `setHTML` let callers push content in (e.g. LLM token streaming).
 */
export const QuillEditor = forwardRef<QuillHandle, {
  initialHTML?: string;
  placeholder?: string;
  onChange?: (html: string, text: string) => void;
  minHeight?: number;
}>(function QuillEditor({ initialHTML = "", placeholder, onChange, minHeight = 260 }, ref) {
  const hostRef = useRef<HTMLDivElement>(null);
  const quillRef = useRef<Quill | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useImperativeHandle(ref, () => ({
    setText: (text: string) => {
      const q = quillRef.current;
      if (!q) return;
      q.setText(text);
      q.setSelection(q.getLength(), 0);
    },
    setHTML: (html: string) => {
      const q = quillRef.current;
      if (!q) return;
      q.setText("");
      q.clipboard.dangerouslyPasteHTML(html);
    },
    getText: () => quillRef.current?.getText() ?? "",
  }), []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || quillRef.current) return;

    const editorEl = document.createElement("div");
    host.appendChild(editorEl);

    const q = new Quill(editorEl, {
      theme: "snow",
      placeholder,
      modules: {
        toolbar: [
          [{ header: [2, 3, false] }],
          ["bold", "italic", "underline"],
          [{ list: "ordered" }, { list: "bullet" }],
          ["link"],
          ["clean"],
        ],
      },
    });
    quillRef.current = q;

    if (initialHTML) q.clipboard.dangerouslyPasteHTML(initialHTML);
    onChangeRef.current?.(q.root.innerHTML, q.getText());

    q.on("text-change", () => {
      onChangeRef.current?.(q.root.innerHTML, q.getText());
    });

    return () => {
      quillRef.current = null;
      host.innerHTML = "";
    };
    // mount once — editor is uncontrolled thereafter
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="jf-quill" style={{ background: "#fff", borderRadius: 12, overflow: "hidden", border: "1px solid var(--card-border)" }}>
      <div ref={hostRef} style={{ ["--ql-min" as string]: `${minHeight}px` }} />
    </div>
  );
});

export default QuillEditor;
