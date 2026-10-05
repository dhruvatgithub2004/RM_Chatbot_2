export const fmtAed = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : "AED " + Math.round(n).toLocaleString("en-US");

export const fmtNum = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : Math.round(n).toLocaleString("en-US");

export const fmtAsOf = (iso?: string) => {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
};
