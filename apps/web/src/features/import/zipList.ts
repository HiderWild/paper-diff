/** List entry paths from a zip without full inflate (central directory). */

function u16(v: DataView, o: number) {
  return v.getUint16(o, true);
}
function u32(v: DataView, o: number) {
  return v.getUint32(o, true);
}

export async function listZipEntryPaths(file: File): Promise<string[]> {
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  const view = new DataView(buf);
  // Find EOCD signature 0x06054b50 from the end
  let eocd = -1;
  const maxBack = Math.min(bytes.length, 0xffff + 22);
  for (let i = bytes.length - 22; i >= bytes.length - maxBack; i--) {
    if (i < 0) break;
    if (
      bytes[i] === 0x50 &&
      bytes[i + 1] === 0x4b &&
      bytes[i + 2] === 0x05 &&
      bytes[i + 3] === 0x06
    ) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) {
    // fallback: scan local headers (incomplete but useful)
    return listLocalHeaders(view, bytes.length);
  }
  const total = u16(view, eocd + 10);
  let offset = u32(view, eocd + 16);
  const paths: string[] = [];
  const decoder = new TextDecoder("utf-8");
  for (let n = 0; n < total; n++) {
    if (offset + 46 > bytes.length) break;
    if (u32(view, offset) !== 0x02014b50) break;
    const nameLen = u16(view, offset + 28);
    const extraLen = u16(view, offset + 30);
    const commentLen = u16(view, offset + 32);
    const nameStart = offset + 46;
    const nameBytes = bytes.subarray(nameStart, nameStart + nameLen);
    let name = decoder.decode(nameBytes).replace(/\\/g, "/");
    // skip directory markers only
    if (name && !name.endsWith("/")) paths.push(name.replace(/^\//, ""));
    offset = nameStart + nameLen + extraLen + commentLen;
  }
  return paths;
}

function listLocalHeaders(view: DataView, len: number): string[] {
  const paths: string[] = [];
  const decoder = new TextDecoder("utf-8");
  let o = 0;
  while (o + 30 < len) {
    if (view.getUint32(o, true) !== 0x04034b50) break;
    const nameLen = view.getUint16(o + 26, true);
    const extraLen = view.getUint16(o + 28, true);
    const compSize = view.getUint32(o + 18, true);
    const nameStart = o + 30;
    const nameBytes = new Uint8Array(
      view.buffer,
      view.byteOffset + nameStart,
      nameLen
    );
    const name = decoder.decode(nameBytes).replace(/\\/g, "/");
    if (name && !name.endsWith("/")) paths.push(name.replace(/^\//, ""));
    o = nameStart + nameLen + extraLen + compSize;
  }
  return paths;
}

export function defaultImportName(d = new Date()): string {
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  const date = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
  const time = `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  // 14 digits with hyphen between date and time: YYYYMMDD-HHMMSS
  return `${date}-${time}`;
}

export type LocalPreview = {
  paths: string[];
  method: "zip" | "folder" | "files";
  zipCount?: number;
};

export function pathsFromFileList(
  list: FileList | File[],
  method: "folder" | "files"
): string[] {
  const files = Array.from(list);
  return files.map(
    (f) =>
      (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
  );
}
