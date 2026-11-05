"use client";

import { FileCode2 } from "lucide-react";
import { Highlight, themes, type Token } from "prism-react-renderer";
import { useMemo, useState, type ReactNode } from "react";
import type { FileChange } from "@/lib/api";
import { diffLines, diffStats, toSplit } from "@/lib/diff";
import { cn } from "@/lib/utils";
import { Segmented } from "@/components/ui/primitives";

const PRISM_LANGUAGE: Record<string, string> = {
  javascript: "javascript", jsx: "jsx", typescript: "typescript", tsx: "tsx", html: "markup", vue: "markup", svelte: "markup", xml: "markup",
  astro: "markup", css: "css", scss: "css", less: "css", json: "json", python: "python", markdown: "markdown", yaml: "yaml", go: "go",
};

const theme = {
  ...themes.oneDark,
  plain: { ...themes.oneDark.plain, backgroundColor: "transparent", color: "#E2E8F0" },
};

function Code({ code, language, children }: { code: string; language: string; children: (lines: Token[][], getTokenProps: (input: { token: Token }) => { className?: string; style?: React.CSSProperties; children?: ReactNode }) => ReactNode }) {
  return (
    <Highlight theme={theme} code={code} language={PRISM_LANGUAGE[language] ?? "markup"}>
      {({ tokens, getTokenProps }) => <>{children(tokens, getTokenProps)}</>}
    </Highlight>
  );
}

function LineContent({ tokens, getTokenProps, fallback }: { tokens?: Token[]; getTokenProps: (input: { token: Token }) => { className?: string; style?: React.CSSProperties; children?: ReactNode }; fallback: string }) {
  if (!tokens) return <>{fallback || " "}</>;
  return (
    <>
      {tokens.map((token, index) => {
        const props = getTokenProps({ token });
        return <span key={index} className={props.className} style={props.style}>{props.children}</span>;
      })}
      {tokens.length === 0 && " "}
    </>
  );
}

const ROW_TONE = {
  equal: "",
  remove: "bg-critical/[0.09]",
  add: "bg-success/[0.09]",
};
const GUTTER_TONE = { equal: "text-subtle", remove: "text-critical/80 bg-critical/[0.07]", add: "text-success/80 bg-success/[0.07]" };

export function DiffViewer({ change }: { change: FileChange }) {
  const [mode, setMode] = useState<"split" | "unified">("split");
  const rows = useMemo(() => diffLines(change.original, change.proposed, change.start_line), [change]);
  const split = useMemo(() => toSplit(rows), [rows]);
  const stats = diffStats(rows);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-[#0B1120]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft bg-panel/80 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-[13px]">
          <FileCode2 className="h-4 w-4 shrink-0 text-cyan" aria-hidden />
          <span className="truncate font-mono text-ink/90">{change.path}</span>
          <span className="shrink-0 text-[12px] text-success">+{stats.added}</span>
          <span className="shrink-0 text-[12px] text-critical">−{stats.removed}</span>
        </div>
        <Segmented label={`diff-mode-${change.path}`} value={mode} onChange={setMode} options={[{ value: "split", label: "Side by side" }, { value: "unified", label: "Unified" }]} />
      </div>
      <Code code={change.original} language={change.language}>
        {(oldTokens, getTokenProps) => (
          <Code code={change.proposed} language={change.language}>
            {(newTokens) => {
              const oldLine = (no: number) => oldTokens[no - change.start_line];
              const newLine = (no: number) => newTokens[no - change.start_line];
              return mode === "unified" ? (
                <div className="overflow-x-auto scrollbar-thin" role="table" aria-label={`Unified diff of ${change.path}`}>
                  <table className="code-font w-full border-collapse">
                    <tbody>
                      {rows.map((row, index) => (
                        <tr key={index} className={ROW_TONE[row.type]}>
                          <td className={cn("w-12 select-none px-2 text-right align-top", GUTTER_TONE[row.type])}>{row.type !== "add" ? row.oldNo : ""}</td>
                          <td className={cn("w-12 select-none px-2 text-right align-top", GUTTER_TONE[row.type])}>{row.type !== "remove" ? row.newNo : ""}</td>
                          <td className={cn("w-5 select-none text-center align-top", row.type === "add" ? "text-success" : row.type === "remove" ? "text-critical" : "text-subtle")}>
                            {row.type === "add" ? "+" : row.type === "remove" ? "−" : ""}
                          </td>
                          <td className="whitespace-pre pr-4">
                            <LineContent
                              tokens={row.type === "add" ? newLine(row.newNo) : row.type === "remove" ? oldLine(row.oldNo) : oldLine(row.oldNo)}
                              getTokenProps={getTokenProps}
                              fallback={row.text}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2" role="table" aria-label={`Side-by-side diff of ${change.path}`}>
                  {(["left", "right"] as const).map((side) => (
                    <div key={side} className={cn("overflow-x-auto scrollbar-thin", side === "right" && "border-t border-line-soft md:border-l md:border-t-0")}>
                      <div className="border-b border-line-soft px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-subtle">{side === "left" ? "Original" : "Proposed"}</div>
                      <table className="code-font w-full border-collapse">
                        <tbody>
                          {split.map((row, index) => {
                            const cell = row[side];
                            const kind = cell?.kind ?? "equal";
                            return (
                              <tr key={index} className={cell ? ROW_TONE[kind] : "bg-elevated/20"}>
                                <td className={cn("w-12 select-none px-2 text-right align-top", cell ? GUTTER_TONE[kind] : "")}>{cell?.no ?? ""}</td>
                                <td className="whitespace-pre pr-4">
                                  {cell ? (
                                    <LineContent tokens={side === "left" ? oldLine(cell.no) : newLine(cell.no)} getTokenProps={getTokenProps} fallback={cell.text} />
                                  ) : (
                                    " "
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              );
            }}
          </Code>
        )}
      </Code>
    </div>
  );
}
