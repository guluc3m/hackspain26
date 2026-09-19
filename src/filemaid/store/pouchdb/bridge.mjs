import PouchDB from 'pouchdb';
import { createHash } from 'node:crypto';
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
  const refs = [];
  if (doc.kind === 'artifact') {
    if (!Array.isArray(doc.chunks) || doc.chunks.some(id => typeof id !== 'string' || !id.startsWith('blob:'))) fail('Invalid artifact chunks');
    refs.push(...doc.chunks);
  }
  if (doc.payload_ref !== undefined) {
    if (typeof doc.payload_ref !== 'string' || !doc.payload_ref.startsWith('artifact:')) fail('Invalid payload reference');
    refs.push(doc.payload_ref);
  }
  for (const id of refs) {
    if (id === doc._id) fail('Cyclic dependency');
    checked(await db.get(id, { conflicts: true }));
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

async function replicate(url, credentials) {
  const target = new URL(url);
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password || target.search || target.hash || !target.pathname.replaceAll('/', '')) {
    fail('CouchDB requires an HTTP(S) database URL without credentials');
  }
  const remote = new PouchDB(url, {
    skip_setup: true,
    auth: credentials.user ? { username: credentials.user, password: credentials.password } : undefined,
    fetch: (address, options = {}) => {
      const headers = new Headers(options.headers);
      if (credentials.token) headers.set('Authorization', `Bearer ${credentials.token}`);
      return PouchDB.fetch(address, { ...options, headers, redirect: 'error' });
    },
  });
  let replication;
  let deadline;
  let denied = false;
  let timedOut = false;
  try {
    await remote.info(); // The configured database must already exist.
    replication = db.sync(remote, {
      live: false, retry: false, timeout: 30000,
      batch_size: 16, batches_limit: 1,
      filter: doc => !doc._id.startsWith('_'),
    });
    replication.on('denied', () => { denied = true; replication.cancel(); });
    deadline = setTimeout(() => { timedOut = true; replication.cancel(); }, 90000);
    const result = await replication;
    if (denied || timedOut || !result.push.ok || !result.pull.ok || result.push.errors?.length || result.pull.errors?.length) {
      fail('CouchDB replication incomplete or denied');
    }
    // Native replication retains revision branches. Never report success while
    // readers would silently see an arbitrary winning conflicting revision.
    let startkey;
    while (true) {
      const page = await db.allDocs({ startkey, skip: startkey ? 1 : 0, limit: 128, include_docs: true, conflicts: true });
      for (const row of page.rows) checked(row.doc);
      if (page.rows.length < 128) break;
      startkey = page.rows.at(-1).id;
    }
    // Capture the completed sequence inside the same locked operation so a
    // concurrent write after this point stays pending, never marked synced.
    const info = await db.info();
    return { ok: true, pushed: result.push.docs_written, pulled: result.pull.docs_written, seq: info.update_seq };
  } catch (error) {
    if (error.message?.startsWith('Unresolved revision conflicts:')) throw error;
    const status = Number.isInteger(error.status) ? ` (HTTP ${error.status})` : '';
    fail(`CouchDB replication failed${status}; check endpoint, credentials and database permissions`);
  } finally {
    clearTimeout(deadline);
    replication?.cancel();
    await remote.close();
  }
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
    result = await db.info();
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
  } else if (request.op === 'sync') {
    result = await replicate(request.url, request.credentials || {});
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
