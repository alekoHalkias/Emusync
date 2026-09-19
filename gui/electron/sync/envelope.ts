// Transfer envelope (#478) — mirrors server/sync_client.py's
// _pack_envelope/_unpack_envelope exactly (same magic bytes, same format
// codes) so a blob written by either side is read the same way by the other.
// Replaces the old "write to a temp file, then probe it with `tar -tf`'s exit
// code" detection this file's push.ts/memcard.ts used to do independently of
// (and slightly differently from) the Python side.
const MAGIC = Buffer.from("ES1\0", "latin1"); // 4 bytes
export const FMT_RAW = 0;
export const FMT_TAR = 1;
export const FMT_TARGZ = 2;

export function packEnvelope(fmt: number, payload: Buffer): Buffer {
  return Buffer.concat([MAGIC, Buffer.from([fmt]), payload]);
}

// fmt is null when *data* has no envelope header — a blob that predates
// #478 (already-stored saves/history/console_saves). Callers should fall
// back to their old sniff-by-parsing logic in that case.
export function unpackEnvelope(data: Buffer): { fmt: number | null; payload: Buffer } {
  if (data.length >= 5 && data.subarray(0, 4).equals(MAGIC)) {
    return { fmt: data[4], payload: data.subarray(5) };
  }
  return { fmt: null, payload: data };
}
