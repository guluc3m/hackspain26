import PouchDB from 'pouchdb';
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import readline from 'node:readline';

// Resident bridge: one request per stdin line, one response line per request.
// Python holds the cross-process lock (pouchdb.lock) through each exchange, and
// the LevelDB directory is opened for the exchange and closed before the
// response line: LevelDB locks that directory exclusively for as long as a
// process keeps it open, so a handle held between requests would starve the
// second process (CLI vs UI) that the lock file exists to serialise. Staying
// resident removes the ~200 ms node cold start from every operation; an
// exchange costs ~6 ms.
const root = process.argv[2];
const fail = (message) => { throw new Error(message); };
let db = null;
let viewsReady = false;
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
  if (viewsReady) return;
  await immutable({
    _id: '_design/trace-v1',
    views: {
      by_file: { map: 'function(doc) { if (doc.file_id && doc.kind) emit([doc.file_id, doc.kind, doc.timestamp || 0, doc._id], null); }' },
      by_invoice: { map: 'function(doc) { if (doc.invoice_id && doc.kind) emit([doc.invoice_id, doc.kind, doc.timestamp || 0, doc._id], null); }' },
    },
  });
  viewsReady = true;
}

// ---------------------------------------------------------------------------
// Selective replication gate.
//
// The selection is computed here, inside the same locked operation as the
// replication itself, from the current documents. Python cannot compute it
// beforehand: an invoice may gain a new scan / ESCALAR decision between the
// Python read and the replication, which would leak its evidence.
//
// An invoice is withheld while its latest scan has no decision (newly seen or
// in-progress reprocess), while its latest decision is ESCALAR without a
// covering resolution, while a review marker has no commit, or while any of its
// documents carries an unresolved revision conflict. NO_PAGAR is definitive and
// PAGAR is a clean pass: neither is ever withheld.
// ---------------------------------------------------------------------------

function reviewState(bucket) {
  const scans = bucket.scans
    .slice()
    .sort((a, c) => (a.timestamp - c.timestamp) || (a._id < c._id ? -1 : a._id > c._id ? 1 : 0));
  if (!scans.length) return 'pending';
  const latestScan = scans[scans.length - 1];
  const decisions = [];
  for (const scan of scans) {
    const decision = bucket.decisions.find((d) => d.scan_id === scan.scan_id);
    if (decision) decisions.push(decision);
  }
  const latestDecision = decisions.length ? decisions[decisions.length - 1] : null;
  // A newer scan without a decision (newly seen or in-progress reprocess) is
  // pending even when an older decision was PAGAR.
  if (!latestDecision || latestDecision.scan_id !== latestScan.scan_id) return 'pending';
  const committed = new Set(bucket.resolutions.map((r) => r._id.slice('resolution:'.length)));
  for (const marker of bucket.reviews) {
    if (committed.has(marker._id.slice('review:'.length))) continue;
    // A marker only blocks while it still covers the current state: the reviewed
    // decision, or the transaction's planned decision. A marker left behind by a
    // concurrent reprocess is stale and must not lock the invoice forever.
    const transaction = marker.transaction ? `decision:${marker.transaction}` : null;
    if (latestDecision._id === marker.reviewed_decision_id || latestDecision._id === transaction) {
      return 'pending';
    }
  }
  const covered = bucket.resolutions.some(
    (r) => r.resolved_decision_id === latestDecision._id || r.reviewed_decision_id === latestDecision._id,
  );
  // Offloaded decisions keep the result at the top level (routing metadata).
  const result = latestDecision.decision?.result ?? latestDecision.result;
  if (result !== 'ESCALAR') return covered ? 'resolved' : 'not_required';
  return covered ? 'resolved' : 'pending';
}

function jobIdOf(doc) {
  if (doc.job_id) return doc.job_id;
  const id = doc._id;
  if (id.startsWith('job:')) return id.slice(4);
  if (id.startsWith('job_event:')) return id.slice(10).split(':')[0];
  if (id.startsWith('job_item:')) return id.slice(9).split(':')[0];
  if (id.startsWith('job_result:')) return id.slice(11);
  return null;
}

function batchIdOf(doc) {
  if (doc.batch_id) return doc.batch_id;
  const id = doc._id;
  if (id.startsWith('batch:')) return id.slice(6);
  if (id.startsWith('batch_result:')) return id.slice(13);
  if (id.startsWith('artifact:batch-')) return id.slice(15).split(':')[0];
  return null;
}

async function latestDecisionId(fileKey) {
  const response = await db.allDocs({
    startkey: `scan:${fileKey}:`, endkey: `scan:${fileKey}:\uffff`,
    include_docs: true, conflicts: true,
  });
  const scans = response.rows
    .map((row) => row.doc)
    .filter(Boolean)
    .sort((a, c) => (a.timestamp - c.timestamp) || (a._id < c._id ? -1 : a._id > c._id ? 1 : 0));
  if (!scans.length) return null;
  const latest = scans[scans.length - 1];
  try {
    const decision = await db.get(`decision:${latest.scan_id}`, { conflicts: true });
    return decision._id;
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function selection() {
  const response = await db.allDocs({ include_docs: true, conflicts: true });
  const docs = [];
  for (const row of response.rows) if (row.doc) docs.push(row.doc);

  const buckets = new Map();
  const bucket = (key) => {
    let value = buckets.get(key);
    if (!value) {
      value = { scans: [], decisions: [], resolutions: [], reviews: [] };
      buckets.set(key, value);
    }
    return value;
  };
  const emptyBucket = () => ({ scans: [], decisions: [], resolutions: [], reviews: [] });
  const files = [];
  const decisionById = new Map();
  const fileIdKeys = new Map();
  const fileKeyByContent = new Map();
  for (const doc of docs) {
    const id = doc._id;
    if (id.startsWith('file:')) {
      files.push(doc);
      if (!fileIdKeys.has(doc.file_id)) fileIdKeys.set(doc.file_id, new Set());
      fileIdKeys.get(doc.file_id).add(doc.file_key);
      fileKeyByContent.set(`${doc.file_id}\u0000${doc.sha256}`, doc.file_key);
      continue;
    }
    if (id.startsWith('decision:')) decisionById.set(id, doc);
    if (!doc.file_key) continue;
    const value = bucket(doc.file_key);
    if (id.startsWith('scan:')) value.scans.push(doc);
    else if (id.startsWith('decision:')) value.decisions.push(doc);
    else if (id.startsWith('resolution:')) value.resolutions.push(doc);
    else if (id.startsWith('review:')) value.reviews.push(doc);
  }

  const states = {};
  const withheld = new Set();
  for (const file of files) {
    const state = reviewState(buckets.get(file.file_key) || emptyBucket());
    states[file.file_key] = state;
    if (state === 'pending') withheld.add(file.file_key);
  }
  for (const doc of docs) {
    if (doc._conflicts?.length && doc.file_key) {
      withheld.add(doc.file_key);
      states[doc.file_key] = 'pending';
    }
  }

  // --- reference closure -------------------------------------------------
  // A document is withheld when it carries a withheld identity or references a
  // withheld document (payload_ref, job/batch parent, cache scan). Envelopes
  // are withheld unless every referenced input is eligible. Blobs are withheld
  // unless a published artifact references them (fail-closed for orphans).
  const withheldIds = new Set();
  const withheldScanIds = new Set();
  const withheldJobIds = new Set();
  const withheldBatchIds = new Set();
  const knownJobIds = new Set();
  const knownBatchIds = new Set();
  for (const doc of docs) {
    if (doc._id.startsWith('job:')) knownJobIds.add(jobIdOf(doc));
    if (doc._id.startsWith('batch:')) knownBatchIds.add(batchIdOf(doc));
  }

  for (const doc of docs) {
    if (doc.file_key && withheld.has(doc.file_key)) withheldIds.add(doc._id);
  }

  // Cache docs are shared and anonymous: publish only when every invoice that
  // produced the page is eligible; otherwise never export the raw cache. An
  // anonymous feature (no known file key) proves nothing and is ignored.
  const pageOwners = new Map();
  for (const doc of docs) {
    if (!doc._id.startsWith('feature:')) continue;
    const sha = doc.feature?.sha256;
    if (!sha || !doc.file_key || !(doc.file_key in states)) continue;
    if (!pageOwners.has(sha)) pageOwners.set(sha, new Set());
    pageOwners.get(sha).add(doc.file_key);
  }
  for (const doc of docs) {
    if (!doc._id.startsWith('cache:')) continue;
    const owners = pageOwners.get(doc.page_sha256);
    const eligible = owners && owners.size && [...owners].every((owner) => !withheld.has(owner));
    if (!eligible) {
      withheldIds.add(doc._id);
      if (doc.key) withheldScanIds.add(`cache-${doc.key}`);
    }
  }

  const jobEligible = (doc) => {
    for (const entry of doc.expected || []) {
      if (!entry || typeof entry !== 'object') return false;
      const key = fileKeyByContent.get(`${entry.file_id}\u0000${entry.sha256}`);
      if (!key || withheld.has(key)) return false;
    }
    return true;
  };
  const batchEligible = (doc) => {
    for (const entry of doc.expected || []) {
      const fileId = entry && typeof entry === 'object' ? entry.file_id : entry;
      const keys = fileIdKeys.get(fileId);
      if (!keys || !keys.size) return false;
      for (const key of keys) if (withheld.has(key)) return false;
    }
    for (const decisionId of doc.decisions || []) {
      const decision = decisionById.get(decisionId);
      if (!decision || withheld.has(decision.file_key)) return false;
    }
    return true;
  };
  for (const doc of docs) {
    const id = doc._id;
    if (id.startsWith('job:')) {
      if (!jobEligible(doc)) {
        withheldIds.add(id);
        withheldJobIds.add(jobIdOf(doc));
      }
    } else if (id.startsWith('batch:') || id.startsWith('batch_result:')) {
      if (!batchEligible(doc)) {
        withheldIds.add(id);
        withheldBatchIds.add(batchIdOf(doc));
      }
    }
  }

  let changed = true;
  while (changed) {
    changed = false;
    for (const doc of docs) {
      if (withheldIds.has(doc._id)) {
        // A withheld document also withholds the artifact it offloads to, even
        // when that artifact carries no identity of its own.
        if (doc.payload_ref && !withheldIds.has(doc.payload_ref)) {
          withheldIds.add(doc.payload_ref);
          changed = true;
        }
        continue;
      }
      let hit = false;
      if (doc.payload_ref && withheldIds.has(doc.payload_ref)) {
        hit = true;
      } else if (doc.scan_id && withheldScanIds.has(doc.scan_id)) {
        hit = true;
      } else {
        const jobId = jobIdOf(doc);
        const batchId = batchIdOf(doc);
        if (jobId && (!knownJobIds.has(jobId) || withheldJobIds.has(jobId))) hit = true;
        else if (batchId && (!knownBatchIds.has(batchId) || withheldBatchIds.has(batchId))) hit = true;
      }
      if (hit) {
        withheldIds.add(doc._id);
        changed = true;
      }
    }
  }

  const publishedChunks = new Set();
  for (const doc of docs) {
    if (!doc._id.startsWith('artifact:') || withheldIds.has(doc._id)) continue;
    for (const chunk of doc.chunks || []) publishedChunks.add(chunk);
  }
  const blobs = [];
  for (const doc of docs) {
    if (doc._id.startsWith('blob:') && !publishedChunks.has(doc._id)) blobs.push(doc._id);
  }
  blobs.sort();

  const withheldFileKeys = [...withheld].sort();
  const withheldDocIds = [...withheldIds].sort();
  const gate = createHash('sha256')
    .update(JSON.stringify([withheldFileKeys, withheldDocIds, blobs]))
    .digest('hex');
  return { states, withheld_file_keys: withheldFileKeys, doc_ids: withheldDocIds, blobs, gate };
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
    const withheld = await selection();
    const withheldFileKeys = new Set(withheld.withheld_file_keys);
    const withheldDocIds = new Set(withheld.doc_ids);
    const withheldBlobs = new Set(withheld.blobs);
    const filter = (doc) => !doc._id.startsWith('_')
      && !withheldDocIds.has(doc._id)
      && !withheldBlobs.has(doc._id)
      && !withheldFileKeys.has(doc.file_key);
    replication = db.sync(remote, {
      live: false, retry: false, timeout: 30000,
      batch_size: 16, batches_limit: 1,
      filter,
      // The gate changes exactly when the withheld selection changes, so the
      // native replication id changes and a fresh scan re-emits documents that
      // earlier checkpoints had skipped (e.g. a newly resolved invoice).
      query_params: { gate: withheld.gate },
    });
    replication.on('denied', () => { denied = true; replication.cancel(); });
    deadline = setTimeout(() => { timedOut = true; replication.cancel(); }, 90000);
    const result = await replication;
    if (denied || timedOut || !result.push.ok || !result.pull.ok || result.push.errors?.length || result.pull.errors?.length) {
      fail('CouchDB replication incomplete or denied');
    }
    // Native replication retains revision branches. Never report success while
    // readers would silently see an arbitrary winning conflicting revision.
    // Withheld documents are not replicated, so their conflicts cannot reach
    // the remote and must not block the rest of the exchange.
    let startkey;
    while (true) {
      const page = await db.allDocs({ startkey, skip: startkey ? 1 : 0, limit: 128, include_docs: true, conflicts: true });
      for (const row of page.rows) {
        if (withheldDocIds.has(row.id) || withheldBlobs.has(row.id)) continue;
        if (row.doc && withheldFileKeys.has(row.doc.file_key)) continue;
        checked(row.doc);
      }
      if (page.rows.length < 128) break;
      startkey = page.rows.at(-1).id;
    }
    // Capture the completed sequence inside the same locked operation so a
    // concurrent write after this point stays pending, never marked synced.
    const info = await db.info();
    return { ok: true, pushed: result.push.docs_written, pulled: result.pull.docs_written, seq: info.update_seq, withheld: withheld.withheld_file_keys.length };
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
async function run(request) {
  if (request.op === 'batch') {
    const results = [];
    for (const part of request.requests) results.push(await run(part));
    return results;
  }
  if (request.op === 'ping') return { pid: process.pid };
  let result;
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
  } else if (request.op === 'blobs') {
    const data = [];
    for (const id of request.ids) {
      checked(await db.get(id, { conflicts: true }));
      data.push((await db.getAttachment(id, 'data')).toString('base64'));
    }
    result = data;
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
  } else if (request.op === 'selection') {
    result = await selection();
  } else if (request.op === 'put_conditional') {
    const latest = await latestDecisionId(request.file_key);
    if (latest !== request.expected_decision_id) {
      fail('La factura cambió durante la resolución; recargue la revisión');
    }
    result = await immutable(request.doc);
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
  return result;
}

// A `query` materialises its index in a sibling leveldb directory that PouchDB
// keeps locked for the life of the process. Its own cleanup on close misses it:
// the prefix it filters dependent stores by ("_pouch_" + db name) is not the one
// those stores are registered under, so db.close() leaves the lock held. A
// resident bridge would then starve a second process (CLI vs UI) on the same
// root, which the lock file exists to serialise; close the views explicitly.
async function releaseViews(db) {
  for (const pending of Object.values(db._cachedViews || {})) {
    try {
      await (await pending).db.close();
    } catch { /* a view that never opened holds nothing */ }
  }
}

// One exchange: open, answer, close, one response line. stdin EOF ends the
// process, so a dead Python parent never leaves a bridge behind. Nothing else
// may write to stdout; diagnostics belong on stderr.
const input = readline.createInterface({ input: process.stdin, terminal: false });
for await (const line of input) {
  if (!line.trim()) continue;
  let response;
  try {
    const request = JSON.parse(line);
    db = new PouchDB(root, { adapter: 'leveldb' });
    viewsReady = false;
    response = { ok: true, result: await run(request) };
  } catch (error) {
    response = { ok: false, error: error.message };
  } finally {
    const handle = db;
    db = null;
    if (handle) {
      await releaseViews(handle);
      await handle.close().catch(() => {});
    }
  }
  process.stdout.write(JSON.stringify(response) + '\n');
}
