import PouchDB from 'pouchdb';
import { createHash, randomUUID } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';

// One finite operation. Python holds the cross-process lock through db.close().
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
const db = new PouchDB(process.argv[2], { adapter: 'leveldb' });
const fail = (message) => { throw new Error(message); };
function checked(doc) {
  if (doc._conflicts?.length) fail(`Unresolved revision conflicts: ${doc._id}`);
  return doc;
}
function body(doc) {
  const { _rev, _conflicts, ...rest } = doc;
  return rest;
}
async function immutable(doc) {
  if (doc._rev || doc._deleted) fail('Immutable documents cannot supply revisions or tombstones');
  if (doc.kind === 'decision' && !['PAGAR', 'NO_PAGAR', 'ESCALAR'].includes(doc.decision?.result ?? doc.result)) {
    fail('Invalid decision result');
  }
  try {
    return await db.put(doc);
  } catch (error) {
    if (error.status !== 409) throw error;
    const old = checked(await db.get(doc._id, { conflicts: true, attachments: true }));
    const incoming = structuredClone(doc);
    for (const attachment of Object.values(incoming._attachments || {})) {
      if (Buffer.isBuffer(attachment.data) || attachment.data instanceof Uint8Array) {
        attachment.data = Buffer.from(attachment.data).toString('base64');
      }
    }
    // PouchDB adds digest/revpos/length metadata; compare actual bytes and MIME.
    for (const attachment of Object.values(old._attachments || {})) {
      delete attachment.digest;
      delete attachment.revpos;
      delete attachment.length;
    }
    if (!isDeepStrictEqual(body(old), incoming)) fail(`Immutable document collision: ${doc._id}`);
    return { ok: true, id: old._id, rev: old._rev };
  }
}
async function views() {
  await immutable({
    _id: '_design/trace-v1',
    views: {
      by_file: { map: 'function(doc) { if (doc.file_id && doc.kind) emit([doc.file_id, doc.kind, doc.timestamp || 0, doc._id], null); }' },
      by_invoice: { map: 'function(doc) { if (doc.invoice_id && doc.kind) emit([doc.invoice_id, doc.kind, doc.timestamp || 0, doc._id], null); }' },
    },
  });
}
let result;
try {
  if (request.op === 'put') {
    result = await immutable(request.doc);
  } else if (request.op === 'blob') {
    const data = Buffer.from(request.data, 'base64');
    if (data.length > 1024 * 1024) fail('Blob exceeds 1 MiB');
    const sha = createHash('sha256').update(data).digest('hex');
    if (sha !== request.sha256) fail('Blob checksum mismatch');
    result = await immutable({
      _id: `blob:${sha}`, kind: 'blob',
      _attachments: { data: { content_type: 'application/octet-stream', data } },
    });
  } else if (request.op === 'get' || request.op === 'get_full') {
    try { result = checked(await db.get(request.id, { conflicts: true, attachments: request.op === 'get_full' })); }
    catch (error) { if (error.status === 404) result = null; else throw error; }
  } else if (request.op === 'attachment') {
    checked(await db.get(request.id, { conflicts: true }));
    result = (await db.getAttachment(request.id, 'data')).toString('base64');
  } else if (request.op === 'list') {
    const response = await db.allDocs({
      startkey: request.prefix, endkey: `${request.prefix}\uffff`,
      include_docs: true, conflicts: true,
    });
    result = response.rows.map(row => checked(row.doc));
  } else if (request.op === 'query') {
    await views();
    const response = await db.query(`trace-v1/${request.index}`, {
      startkey: request.key, endkey: [...request.key, {}],
      include_docs: true, conflicts: true, reduce: false,
    });
    result = response.rows.map(row => checked(row.doc));
  } else if (request.op === 'info') {
    const info = await db.info();
    let instanceId = '';
    try {
      const idDoc = await db.get('_local/db_identity');
      instanceId = idDoc.uuid;
    } catch (err) {
      if (err.status !== 404) throw err;
      instanceId = randomUUID();
      await db.put({ _id: '_local/db_identity', uuid: instanceId });
    }
    result = { ...info, instance_id: instanceId };
  } else if (request.op === 'local_get') {
    const id = request.id.startsWith('_local/') ? request.id : `_local/${request.id}`;
    try {
      const doc = await db.get(id);
      const { _id, _rev, ...payload } = doc;
      result = payload;
    } catch (error) {
      if (error.status === 404) result = null;
      else throw error;
    }
  } else if (request.op === 'local_put') {
    const id = request.id.startsWith('_local/') ? request.id : `_local/${request.id}`;
    const rawPayload = request.payload || {};
    if (Object.keys(rawPayload).some(k => k.startsWith('_'))) fail('Reserved local payload key');
    const payload = rawPayload;
    let saved = false;
    for (let attempt = 0; attempt < 10; attempt++) {
      let rev = undefined;
      try {
        const cur = await db.get(id);
        rev = cur._rev;
      } catch (err) {
        if (err.status !== 404) throw err;
      }
      const doc = { ...payload, _id: id };
      if (rev) doc._rev = rev;
      try {
        await db.put(doc);
        saved = true;
        break;
      } catch (err) {
        if (err.status === 409) continue;
        throw err;
      }
    }
    if (!saved) fail(`CAS conflict updating local doc: ${id}`);
    result = { ok: true };
  } else if (request.op === 'changes') {
    const since = Number(request.since || 0);
    const limit = Math.max(1, Math.min(Number(request.limit || 100), 500));
    const ch = await db.changes({
      since,
      limit,
      include_docs: true,
      attachments: false,
      conflicts: true,
    });
    const docs = [];
    let last = since;
    let size = 0;
    for (const r of ch.results) {
      if (r.deleted) fail('Deleted documents cannot be synchronized');
      if (r.id.startsWith('_')) { last = r.seq; continue; }
      let doc = checked(r.doc);
      if (r.id.startsWith('blob:')) {
        doc = { _id: r.id, kind: 'blob' };
      } else if (doc._attachments) {
        doc = checked(await db.get(r.id, { conflicts: true, attachments: true }));
      }
      const bytes = Buffer.byteLength(JSON.stringify(doc));
      if (bytes > 2 * 1024 * 1024 - 4096) fail('Document exceeds sync limit; use artifacts');
      if (size + bytes > 2 * 1024 * 1024 - 4096 && docs.length) break;
      docs.push(doc);
      size += bytes;
      last = r.seq;
    }
    result = { last_seq: ch.results.length ? last : ch.last_seq, results: docs };
  } else if (request.op === 'sync_put') {
    if (typeof request.doc?._id !== 'string' || request.doc._id.startsWith('_')) fail('Reserved sync document ID');
    if (Object.keys(request.doc).some(k => k.startsWith('_') && !['_id', '_attachments'].includes(k))) fail('Reserved sync document key');
    const dependencies = request.doc.kind === 'artifact' ? [...(request.doc.chunks || [])] : [];
    if (request.doc.payload_ref) dependencies.push(request.doc.payload_ref);
    for (const id of dependencies) checked(await db.get(id, { conflicts: true }));
    result = await immutable(request.doc);
  } else {
    fail('Unknown operation');
  }
  await db.close();
  process.stdout.write(JSON.stringify({ ok: true, result }));
} catch (error) {
  await db.close().catch(() => {});
  process.stdout.write(JSON.stringify({ ok: false, error: error.message }));
  process.exitCode = 1;
}
