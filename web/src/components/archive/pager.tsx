import Link from "next/link";

/**
 * Keyset pagination has no page numbers by construction — you can only step
 * forward from a cursor. The cursors already visited are carried in the URL so
 * "back" is a pop rather than a re-query from the start.
 */
export function Pager({
  baseParams,
  stack,
  nextCursor,
  shown,
}: {
  baseParams: URLSearchParams;
  stack: string[];
  nextCursor: string | null;
  shown: number;
}) {
  const href = (cursors: string[]) => {
    const params = new URLSearchParams(baseParams);
    params.delete("c");
    if (cursors.length) params.set("c", cursors.join(","));
    const qs = params.toString();
    return `/archive${qs ? `?${qs}` : ""}`;
  };

  return (
    <div className="rule-t flex flex-wrap items-center justify-between gap-4 px-4 py-4">
      <p className="num text-[10px] uppercase tracking-placard text-chalk/30">
        Page {stack.length + 1} · {shown} row{shown === 1 ? "" : "s"}
      </p>
      <div className="flex gap-3">
        {stack.length > 0 && (
          <Link href={href(stack.slice(0, -1))} className="btn-ghost no-underline">
            Back
          </Link>
        )}
        {nextCursor ? (
          <Link href={href([...stack, nextCursor])} className="btn-ghost no-underline">
            Next
          </Link>
        ) : (
          <span className="btn border-chalk/10 text-chalk/25">End of record</span>
        )}
      </div>
    </div>
  );
}
