"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { Icon } from "./Icon";

/**
 * Sharp document preview: the PDF LibreOffice produced, drawn with pdf.js at the
 * screen's pixel density. Text stays crisp at any zoom and page breaks match Word.
 * Pages render lazily as they scroll into view.
 */
export function PdfView({ url, changed }: { url: string; changed?: Set<number> }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [ratio, setRatio] = useState(1.414);
  const [width, setWidth] = useState(780);
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setState("loading");
    setDoc(null);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
        const task = pdfjs.getDocument({ url, withCredentials: true });
        loaded = await task.promise;
        if (cancelled) { loaded.destroy(); return; }
        const first = await loaded.getPage(1);
        const vp = first.getViewport({ scale: 1 });
        setRatio(vp.height / vp.width);
        setDoc(loaded);
        setState("ready");
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => { cancelled = true; loaded?.destroy(); };
  }, [url]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const base = Math.min(900, Math.max(260, width - 48));
  const w = Math.round(fit ? base : base * zoom);

  return (
    <div ref={wrap} className="pageview">
      <div className="pv-zoom">
        <button className="icon-btn sm" aria-label="Zoom out" onClick={() => { setFit(false); setZoom((z) => Math.max(0.4, (fit ? 1 : z) - 0.15)); }}>−</button>
        <button className="btn text sm" title="Fit to width" onClick={() => { setFit(true); setZoom(1); }}>{fit ? "Fit" : `${Math.round(zoom * 100)}%`}</button>
        <button className="icon-btn sm" aria-label="Zoom in" onClick={() => { setFit(false); setZoom((z) => Math.min(3, (fit ? 1 : z) + 0.15)); }}>+</button>
      </div>
      {state === "loading" ? <div className="pv-loading"><Icon name="spinner" /><span className="muted">Preparing the document…</span></div> : null}
      {state === "error" ? <div className="empty"><span className="empty-ic"><Icon name="warning" /></span><h3>Preview unavailable</h3>Download the file to open it in Word.</div> : null}
      {doc ? (
        <div className="pv-pages">
          {Array.from({ length: doc.numPages }, (_, i) => i + 1).map((n) => (
            <PdfPage key={`${url}-${n}`} doc={doc} n={n} width={w} height={Math.round(w * ratio)} changed={changed?.has(n)} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PdfPage({ doc, n, width, height, changed }: { doc: PDFDocumentProxy; n: number; width: number; height: number; changed?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(n <= 2);

  useEffect(() => {
    const el = box.current;
    if (!el || visible) return;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) setVisible(true); }, { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible || !canvas.current) return;
    let task: { cancel: () => void; promise: Promise<void> } | null = null;
    let alive = true;
    (async () => {
      const page = await doc.getPage(n);
      if (!alive || !canvas.current) return;
      const base = page.getViewport({ scale: 1 });
      const dpr = Math.min(3, window.devicePixelRatio || 1);
      const vp = page.getViewport({ scale: (width / base.width) * dpr });
      const c = canvas.current;
      c.width = Math.floor(vp.width);
      c.height = Math.floor(vp.height);
      const ctx = c.getContext("2d");
      if (!ctx) return;
      task = page.render({ canvasContext: ctx, viewport: vp });
      try { await task.promise; } catch { /* cancelled */ }
    })();
    return () => { alive = false; task?.cancel(); };
  }, [visible, doc, n, width]);

  return (
    <div ref={box} className={`pv-page ${changed ? "changed" : ""}`} style={{ width, height }}>
      <canvas ref={canvas} style={{ width, height, display: "block" }} aria-label={`Page ${n}`} />
      <span className="pv-num">{n}{changed ? " · changed" : ""}</span>
    </div>
  );
}
