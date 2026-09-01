import { timingSafeEqual } from "node:crypto";
import { revalidatePath, revalidateTag } from "next/cache";
import { NextResponse, type NextRequest } from "next/server";

import {
  ALL_CACHE_TAGS,
  CACHE_TAGS,
  REVALIDATABLE_PATHS,
  type CacheTag,
} from "@/lib/cache";

/**
 * The publish handshake's frontend half (§2.3, §5). The pipeline writes the
 * slate and flips model_runs.status to 'success' in one transaction, then
 * curls this endpoint; nothing here polls and nothing holds a socket open.
 *
 * POST only — a GET revalidate endpoint is triggerable by any third-party
 * <img> tag, and the secret would then travel in referrer logs.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs"; // timingSafeEqual

const VALID_TAGS = new Set<string>(ALL_CACHE_TAGS);

/** Constant-time compare that also refuses to leak the secret's length. */
function secretMatches(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) {
    // Still burn a comparison so a wrong length is not measurably faster.
    timingSafeEqual(b, b);
    return false;
  }
  return timingSafeEqual(a, b);
}

export async function POST(request: NextRequest) {
  const expected = process.env.REVALIDATE_SECRET ?? "";
  if (expected.length === 0) {
    return NextResponse.json(
      { revalidated: false, error: "REVALIDATE_SECRET is not set on this deployment." },
      { status: 503 },
    );
  }

  const provided = request.headers.get("x-revalidate-secret") ?? "";
  if (!secretMatches(provided, expected)) {
    return NextResponse.json({ revalidated: false }, { status: 401 });
  }

  // An empty or absent body means "a slate published" — the common case, and
  // the one the pipeline's curl step sends.
  const body = await readBody(request);
  const tags: CacheTag[] =
    body.tags && body.tags.length > 0
      ? body.tags.filter((t): t is CacheTag => VALID_TAGS.has(t))
      : [CACHE_TAGS.slate, CACHE_TAGS.archive];

  if (body.tags && tags.length === 0) {
    return NextResponse.json(
      { revalidated: false, error: `Unknown tag. Valid tags: ${ALL_CACHE_TAGS.join(", ")}` },
      { status: 400 },
    );
  }

  for (const tag of tags) revalidateTag(tag);
  for (const path of REVALIDATABLE_PATHS) revalidatePath(path);

  return NextResponse.json({
    revalidated: true,
    tags,
    paths: REVALIDATABLE_PATHS,
    now: new Date().toISOString(),
  });
}

async function readBody(request: NextRequest): Promise<{ tags?: string[] }> {
  try {
    const raw: unknown = await request.json();
    if (raw && typeof raw === "object" && "tags" in raw) {
      const tags = (raw as { tags: unknown }).tags;
      if (Array.isArray(tags)) {
        return { tags: tags.filter((t): t is string => typeof t === "string") };
      }
    }
  } catch {
    // No body, or not JSON. Both mean "revalidate the slate".
  }
  return {};
}
