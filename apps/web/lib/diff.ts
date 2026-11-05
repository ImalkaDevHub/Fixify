/** Line diff (longest common subsequence). Inputs are bounded excerpts (≤ ~400 lines). */

export type DiffRow =
  | { type: "equal"; oldNo: number; newNo: number; text: string }
  | { type: "remove"; oldNo: number; text: string }
  | { type: "add"; newNo: number; text: string };

export type SplitRow = {
  left: { no: number; text: string; kind: "equal" | "remove" } | null;
  right: { no: number; text: string; kind: "equal" | "add" } | null;
};

function lines(text: string): string[] {
  const result = text.split("\n");
  if (result.length > 1 && result[result.length - 1] === "") result.pop();
  return result;
}

export function diffLines(before: string, after: string, startLine = 1): DiffRow[] {
  const a = lines(before);
  const b = lines(after);
  const n = a.length;
  const m = b.length;
  // lcs[i][j] = length of LCS of a[i..] and b[j..]
  const lcs: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) {
      rows.push({ type: "equal", oldNo: startLine + i, newNo: startLine + j, text: a[i] });
      i++;
      j++;
    } else if (j < m && (i >= n || lcs[i][j + 1] >= lcs[i + 1][j])) {
      rows.push({ type: "add", newNo: startLine + j, text: b[j] });
      j++;
    } else {
      rows.push({ type: "remove", oldNo: startLine + i, text: a[i] });
      i++;
    }
  }
  return rows;
}

/** Pair removals with additions so a changed line sits next to its replacement. */
export function toSplit(rows: DiffRow[]): SplitRow[] {
  const result: SplitRow[] = [];
  let index = 0;
  while (index < rows.length) {
    const row = rows[index];
    if (row.type === "equal") {
      result.push({ left: { no: row.oldNo, text: row.text, kind: "equal" }, right: { no: row.newNo, text: row.text, kind: "equal" } });
      index++;
      continue;
    }
    const removed: { no: number; text: string }[] = [];
    const added: { no: number; text: string }[] = [];
    while (index < rows.length && rows[index].type !== "equal") {
      const current = rows[index];
      if (current.type === "remove") removed.push({ no: current.oldNo, text: current.text });
      else if (current.type === "add") added.push({ no: current.newNo, text: current.text });
      index++;
    }
    for (let k = 0; k < Math.max(removed.length, added.length); k++) {
      result.push({
        left: removed[k] ? { ...removed[k], kind: "remove" } : null,
        right: added[k] ? { ...added[k], kind: "add" } : null,
      });
    }
  }
  return result;
}

export function diffStats(rows: DiffRow[]): { added: number; removed: number } {
  return { added: rows.filter((r) => r.type === "add").length, removed: rows.filter((r) => r.type === "remove").length };
}
