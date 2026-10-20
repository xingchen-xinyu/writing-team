import path from 'node:path';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import process from 'node:process';

import {
  CdpConnection,
  findChromeExecutable as findChromeExecutableBase,
  findExistingChromeDebugPort,
  gracefulKillChrome,
  getFreePort,
  launchChrome as launchChromeBase,
  openPageSession,
  waitForChromeDebugPort,
  type PlatformCandidates,
} from 'baoyu-chrome-cdp';

import { Endpoint, Model } from '../constants.js';
import { logger } from './logger.js';
import {
  extract_json_from_response,
  get_nested_value,
} from './parsing.js';
import { upload_file, parse_file_name } from './upload-file.js';
import { resolveGeminiWebChromeProfileDir, resolveGeminiWebCookiePath } from './paths.js';

const GEMINI_APP_URL = 'https://gemini.google.com/app';

const CHROME_CANDIDATES_FULL: PlatformCandidates = {
  darwin: [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ],
  win32: [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ],
  default: [
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
  ],
};

// ── Model header resolution (mirrors main.ts resolveModel) ──

function resolveModel(id: string): Model {
  const k = id.trim();
  if (k === 'gemini-3-pro' || k === 'gemini-3.0-pro') return Model.G_3_0_PRO;
  if (k === 'gemini-3-flash' || k === 'gemini-3.0-flash') return Model.G_3_0_FLASH;
  if (k === 'gemini-3-flash-thinking' || k === 'gemini-3.0-flash-thinking') return Model.G_3_0_FLASH_THINKING;
  if (k === 'gemini-3.1-pro-preview') return Model.G_3_1_PRO_PREVIEW;
  return Model.from_name(k);
}

// ── Token extraction via HTTP (mirrors get_access_token in get-access-token.ts) ──

function buildCookieHeader(cookies: Record<string, string>): string {
  return Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');
}

async function getAccessTokenViaHttp(cookies: Record<string, string>): Promise<string> {
  const resp = await fetch(GEMINI_APP_URL, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Cookie': buildCookieHeader(cookies),
    },
    signal: AbortSignal.timeout(30_000),
  });
  if (!resp.ok) throw new Error(`Init request failed: HTTP ${resp.status}`);
  const text = await resp.text();
  const m = text.match(/"SNlM0e":"(.*?)"/);
  if (!m) throw new Error('SNlM0e token not found in response — cookies may be expired');
  return m[1];
}

// ── Chrome lifecycle ──

function findChromeExecutable(): string | null {
  return findChromeExecutableBase({
    candidates: CHROME_CANDIDATES_FULL,
    envNames: ['GEMINI_WEB_CHROME_PATH'],
  }) ?? null;
}

async function launchOrReuseChrome(profileDir: string) {
  const existingPort = await findExistingChromeDebugPort({ profileDir });
  const reusing = existingPort !== null;
  const port = existingPort ?? await getFreePort();

  let chrome: any = null;
  if (!reusing) {
    const chromePath = findChromeExecutable();
    if (!chromePath) throw new Error('Chrome executable not found.');
    chrome = await launchChromeBase({
      chromePath,
      profileDir,
      port,
      url: GEMINI_APP_URL,
      extraArgs: ['--disable-popup-blocking'],
    });
  }

  const wsUrl = await waitForChromeDebugPort(port, 30_000, { includeLastError: true });
  const cdp = await CdpConnection.connect(wsUrl, 15_000);

  return { cdp, chrome, port, reusing };
}

// ── Response parsing (extracted from GeminiClient.generate_content) ──

const GENERATED_IMAGE_URL_PREFIX = 'https://lh3.googleusercontent.com/gg-dl/';

function collectGeneratedImageUrls(responseJson: unknown[]): string[] {
  const urls: string[] = [];
  const seen = new Set<string>();
  const stack: unknown[] = [responseJson];

  while (stack.length > 0 && urls.length < 4) {
    const v = stack.pop();
    if (typeof v === 'string') {
      if (v.startsWith(GENERATED_IMAGE_URL_PREFIX) && !seen.has(v)) {
        seen.add(v);
        urls.push(v);
      }
      // Try to parse as JSON — image URLs are often embedded inside
      // nested JSON strings (e.g. the [2] payload of wrb.fr fragments).
      if (v.startsWith('[') || v.startsWith('{')) {
        try { stack.push(JSON.parse(v)); } catch {}
      }
      continue;
    }
    if (Array.isArray(v)) {
      for (let i = 0; i < v.length; i++) stack.push(v[i]);
      continue;
    }
    if (v && typeof v === 'object') {
      for (const val of Object.values(v as Record<string, unknown>)) stack.push(val);
    }
  }

  return urls;
}

function parseGenerateResponse(responseText: string): string[] {
  const responseJson = extract_json_from_response(responseText);
  if (!Array.isArray(responseJson)) {
    throw new Error('Invalid response JSON structure');
  }

  // Find body with candidate data. Prefer the LAST matching part —
  // later streaming fragments contain the completed image URLs while
  // earlier ones may still be in "Creating your image" state.
  let bodyJson: unknown[] | null = null;
  for (let partIndex = 0; partIndex < responseJson.length; partIndex++) {
    const part = responseJson[partIndex];
    if (!Array.isArray(part)) continue;
    const partBody = get_nested_value<string | null>(part, [2], null);
    if (!partBody) continue;
    try {
      const parsed = JSON.parse(partBody) as unknown[];
      if (get_nested_value(parsed, [4], null)) {
        bodyJson = parsed;
        // Don't break — keep scanning for later (more complete) parts
      }
    } catch {}
  }

  if (!bodyJson) {
    const snippet = responseText.length > 500 ? responseText.slice(0, 500) + '...' : responseText;
    logger.info('   CDP response (first 500 chars):', snippet);
    throw new Error('No candidate data found in response');
  }

  const imageUrls = collectGeneratedImageUrls(responseJson);
  if (imageUrls.length === 0) {
    // Fallback: scan candidate list for generated images
    const candidateList = get_nested_value<unknown[]>(bodyJson, [4], []);
    for (let ci = 0; ci < candidateList.length; ci++) {
      const candidate = candidateList[ci];
      if (!Array.isArray(candidate)) continue;
      const gen = get_nested_value<unknown[]>(candidate, [12, 7, 0], []);
      for (const g of gen) {
        if (!Array.isArray(g)) continue;
        const url = get_nested_value<string | null>(g, [0, 3, 3], null);
        if (url) imageUrls.push(url);
      }
    }
  }

  if (imageUrls.length === 0) {
    const snippet = responseText.length > 300 ? responseText.slice(0, 300) + '...' : responseText;
    logger.info('   CDP response dump:', snippet);
    throw new Error('No generated image URL found in response');
  }

  return imageUrls;
}

// ── Image download (via injected JS fetch → returns base64) ──

async function downloadImageViaCdp(
  cdp: CdpConnection,
  sessionId: string,
  imageUrl: string,
  outputPath: string,
  cookies: Record<string, string>,
): Promise<void> {
  // Download via Bun HTTP with cookies (matches GeneratedImage.save() behavior).
  // JS fetch() from gemini.google.com to lh3.googleusercontent.com is blocked
  // by CORS; Bun's HTTP client has no such restriction and we can send cookies.
  const downloadUrl = imageUrl + '=s2048';
  const cookieHeader = Object.entries(cookies)
    .filter(([, v]) => typeof v === 'string' && v.length > 0)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');

  let resp: Response | null = null;
  let url = downloadUrl;
  for (let i = 0; i < 10; i++) {
    resp = await fetch(url, {
      method: 'GET',
      headers: {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://gemini.google.com/',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Cookie': cookieHeader,
      },
      redirect: 'manual',
      signal: AbortSignal.timeout(30_000),
    });

    if (resp.status >= 300 && resp.status < 400) {
      const loc = resp.headers.get('location');
      if (!loc) break;
      url = new URL(loc, url).toString();
      continue;
    }

    break;
  }

  if (!resp) throw new Error('Image download failed: no response');
  if (!resp.ok) throw new Error(`Image download HTTP ${resp.status}`);

  const buf = Buffer.from(await resp.arrayBuffer());
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, buf);
}

// ── Main entry point ──

type CdpTask = {
  prompt: string;
  image: string;
};

type CdpBatchInput = {
  model: string;
  tasks: CdpTask[];
};

type CdpBatchResultItem = {
  index: number;
  image: string;
  success: boolean;
  error?: string;
};

export async function generateViaCdp(batchPath: string): Promise<void> {
  const raw = await readFile(batchPath, 'utf8');
  const input: CdpBatchInput = JSON.parse(raw);

  if (!input.tasks || input.tasks.length === 0) {
    throw new Error('Batch file contains no tasks.');
  }

  const model = resolveModel(input.model || 'gemini-3.0-flash');
  const profileDir = process.env.GEMINI_WEB_CHROME_PROFILE_DIR?.trim() || resolveGeminiWebChromeProfileDir();

  logger.info(`🚀 CDP: launching Chrome (profile: ${path.basename(profileDir)})...`);
  const { cdp, chrome, port, reusing } = await launchOrReuseChrome(profileDir);
  logger.info(reusing
    ? `   Reusing Chrome on port ${port}`
    : `   Chrome launched on port ${port}`);

  let sessionId: string | null = null;
  let targetId: string | null = null;
  let createdTarget = false;
  const results: CdpBatchResultItem[] = [];

  try {
    // Step 1: Read cookies from cookies.json
    const cookiePath = resolveGeminiWebCookiePath();
    const cookieRaw = await readFile(cookiePath, 'utf8');
    const cookieData = JSON.parse(cookieRaw);
    const cookies: Record<string, string> = cookieData?.cookieMap || cookieData?.cookies || {};
    if (!cookies['__Secure-1PSID']) {
      throw new Error('No __Secure-1PSID cookie found. Run --gemini-web-login first.');
    }

    // Step 2: Open Gemini page (needed for same-origin cookie domain context)
    logger.info('📄 Opening Gemini page...');
    const page = await openPageSession({
      cdp,
      reusing,
      url: GEMINI_APP_URL,
      matchTarget: (t) => t.type === 'page' && t.url.includes('gemini.google.com'),
      enableNetwork: true,
      enableRuntime: true,
    });
    sessionId = page.sessionId;
    targetId = page.targetId;
    createdTarget = page.createdTarget;

    // Step 3: Inject cookies while on gemini.google.com origin
    // Set cookies individually in Chrome's store for page login (needed for
    // SNlM0e token extraction from page) AND via setExtraHTTPHeaders for API
    // calls (Origin/Referer are forbidden in browser fetch()).
    logger.info('🍪 Injecting cookies...');
    await cdp.send('Network.clearBrowserCookies', {}, { sessionId, timeoutMs: 5_000 }).catch(() => {});

    for (const [name, value] of Object.entries(cookies)) {
      if (typeof value !== 'string') continue;
      await cdp.send<any>('Network.setCookie', {
        name,
        value,
        url: GEMINI_APP_URL,
        domain: '.google.com',
        path: '/',
        secure: true,
        httpOnly: name.startsWith('__Secure-'),
        sameSite: 'Lax',
      }, { sessionId, timeoutMs: 5_000 }).catch(() => {});
    }

    // Inject Origin + Referer via CDP (forbidden in browser fetch()).
    // Cookie is NOT injected here to avoid conflict with Chrome's cookie store.
    await cdp.send('Network.setExtraHTTPHeaders', {
      headers: {
        'Origin': 'https://gemini.google.com',
        'Referer': 'https://gemini.google.com/',
      },
    }, { sessionId, timeoutMs: 5_000 });

    // Reload to log in the page with injected cookies
    await cdp.send('Page.reload', {}, { sessionId, timeoutMs: 30_000 });
    await new Promise(r => setTimeout(r, 5000));

    // Extract SNlM0e token from the logged-in page (or fall back to HTTP)
    logger.info('🔑 Extracting access token...');
    const tokenResult = await cdp.send<{ result: { value: string } }>(
      'Runtime.evaluate',
      {
        expression: '(function(){var m=document.documentElement.innerText.match(/"SNlM0e":"(.*?)"/);return m?m[1]:null;})()',
        returnByValue: true,
      },
      { sessionId, timeoutMs: 15_000 },
    );
    let accessToken = tokenResult?.result?.value;
    if (!accessToken) {
      accessToken = await getAccessTokenViaHttp(cookies);
      logger.info('   ✅ Token obtained via HTTP fallback');
    } else {
      logger.info('   ✅ Token obtained from page');
    }

    // Process each task
    for (let i = 0; i < input.tasks.length; i++) {
      const task = input.tasks[i];
      const label = `[${i + 1}/${input.tasks.length}]`;

      try {
        // Build Gemini API request body (same structure as GeminiClient)
        let first: unknown[] = [task.prompt];
        const refs = task.reference && task.reference.length > 0 ? task.reference : null;
        if (refs) {
          const uploaded = await Promise.all(
            refs.map(async (p) => [[await upload_file(p, null)], parse_file_name(p)] as [string[], string])
          );
          first = [task.prompt, 0, null, uploaded];
        }
        const inner: unknown[] = [first, null, null];
        const fReq = JSON.stringify([null, JSON.stringify(inner)]);
        const body = new URLSearchParams({ at: accessToken, 'f.req': fReq }).toString();

        // JS fetch headers — Origin/Referer/Cookie injected at CDP level via
        // Network.setExtraHTTPHeaders. Only set headers Chrome's fetch() allows.
        const fetchHeaders: Record<string, string> = {
          'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
          'X-Same-Domain': '1',
          ...model.model_header,
        };
        const headersJson = JSON.stringify(fetchHeaders);

        // Inject JS fetch to call Gemini API (runs inside Chrome, same-origin)
        // Use Endpoint.GENERATE (StreamGenerate), same as GeminiClient.generate_content().
        // Endpoint.BATCH_EXEC expects a different RPC-serialized body format that
        // triggers HTTP 400 ("af.httprm") when sent the GENERATE-style body.
        logger.info(`🎨 ${label} Generating via CDP...`);
        const endpointUrl = JSON.stringify(Endpoint.GENERATE);
        const jsFetch = `
          (async () => {
            try {
              const resp = await fetch(${endpointUrl}, {
                method: 'POST',
                headers: ${headersJson},
                body: ${JSON.stringify(body)},
              });
              if (!resp.ok) {
                const errBody = await resp.text().catch(() => '(no body)');
                return JSON.stringify({ error: 'HTTP ' + resp.status, status: resp.status, body: errBody.slice(0, 300) });
              }
              return await resp.text();
            } catch (e) {
              return JSON.stringify({ error: e.message || String(e) });
            }
          })()
        `;

        const fetchResult = await cdp.send<{ result: { value: string } }>(
          'Runtime.evaluate',
          { expression: jsFetch, returnByValue: true, awaitPromise: true },
          { sessionId, timeoutMs: 180_000 },
        );

        const responseText = fetchResult?.result?.value ?? '';

        // Check for JS-level errors
        if (responseText.startsWith('{"error"')) {
          let errObj: any;
          try { errObj = JSON.parse(responseText); } catch { errObj = { error: responseText }; }
          if (errObj.status === 401 || errObj.status === 403) {
            throw new Error(`Auth failed (${errObj.status}). Session may have expired.`);
          }
          const detail = errObj.body ? ` — ${errObj.body}` : '';
          throw new Error(`${errObj.error}${detail}`);
        }

        if (!responseText || responseText.length < 100) {
          throw new Error(`Empty or short response (${responseText.length} chars)`);
        }

        // Parse response and extract image URLs
        const imageUrls = parseGenerateResponse(responseText);
        if (imageUrls.length === 0) {
          throw new Error('No images in response');
        }

        // Download the first generated image
        const outputPath = path.resolve(task.image);
        const ext = path.extname(outputPath);
        const finalPath = ext ? outputPath : outputPath + '.png';
        await downloadImageViaCdp(cdp, sessionId, imageUrls[0], finalPath, cookies);

        console.log(`${label} ✅ ${path.basename(task.image)}`);
        results.push({ index: i, image: task.image, success: true });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        console.log(`${label} ❌ ${path.basename(task.image)}: ${msg}`);
        results.push({ index: i, image: task.image, success: false, error: msg });
      }
    }
  } finally {
    // Cleanup
    if (cdp && createdTarget && targetId) {
      try { await cdp.send('Target.closeTarget', { targetId }, { timeoutMs: 5_000 }); } catch {}
    }
    if (cdp) cdp.close();
    if (chrome) await gracefulKillChrome(chrome, port);
  }

  // Write results
  const resultPath = path.join(path.dirname(batchPath), '_batch_result_cdp.json');
  await writeFile(resultPath, JSON.stringify(results, null, 2), 'utf8');

  const failed = results.filter(r => !r.success).length;
  if (failed > 0) {
    throw new Error(`${failed}/${results.length} tasks failed. See ${resultPath}`);
  }
}
