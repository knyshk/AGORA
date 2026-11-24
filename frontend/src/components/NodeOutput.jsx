import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders a Vega-Lite spec produced (and validated) by the backend chart agent.
export function VegaChart({ source }) {
  const ref = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let view;
    let spec;
    try {
      spec = JSON.parse(source);
    } catch (e) {
      setError(`Chart spec is not valid JSON: ${e.message}`);
      return undefined;
    }
    setError(null);
    import("vega-embed")
      .then(({ default: embed }) => embed(ref.current, spec, {
      actions: { export: true, source: true, compiled: false, editor: false },
      theme: "dark",
      config: { background: "transparent", range: { category: ["#f5ab3d", "#79d48b", "#7fb2ff", "#ff9187", "#c59cff"] } },
      }))
      .then((res) => { view = res.view; })
      .catch((e) => setError(`Could not render chart: ${e.message}`));
    return () => view && view.finalize();
  }, [source]);

  if (error) return <div style={{ color: "#ff9187" }}>{error}</div>;
  return <div ref={ref} style={{ width: "100%", minHeight: 280, margin: "12px 0" }} />;
}

const components = {
  code({ className, children, ...props }) {
    if (className === "language-vega-lite") {
      return <VegaChart source={String(children)} />;
    }
    return <code className={className} {...props}>{children}</code>;
  },
  pre({ children }) {
    // Avoid wrapping the chart in a <pre> block.
    const child = Array.isArray(children) ? children[0] : children;
    if (child?.props?.className === "language-vega-lite") return <>{children}</>;
    return <pre>{children}</pre>;
  },
};

export default function NodeOutput({ text }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>;
}
