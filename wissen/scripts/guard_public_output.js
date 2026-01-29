#!/usr/bin/env node
"use strict";

/**
 * PATH: wissen/scripts/guard_public_output.js
 * Version: 2026-01-29 21:00 CET
 *
 * Guard script for Hugo public output.
 * Fixes:
 *  - Resolve relative nav hrefs against current page URL path (supports Hugo relref-style links).
 *  - Harden URL scheme checks to also reject data: and vbscript: in addition to javascript:.
 */

const fs = require("fs");
const path = require("path");
const cheerio = require("cheerio");

const ROOT = process.env.GUARD_ROOT
  ? path.resolve(process.env.GUARD_ROOT)
  : path.resolve(__dirname, "..", "public");

const MAX_FILES = Number.parseInt(process.env.GUARD_MAX_FILES || "", 10);
const REDUNDANT_STRATEGY = (process.env.GUARD_REDUNDANT_URL_STRATEGY || "redirect")
  .trim()
  .toLowerCase();

const NAV_GUARD_REL_PATHS = new Set([
  "de/index.html",
  "de/shop/index.html",
  "de/faq/index.html",
  "de/produkte/index.html",
  "de/lookbook/index.html",
  "en/index.html",
  "en/shop/index.html",
  "en/faq/index.html",
  "en/products/index.html",
  "en/lookbook/index.html",
]);

const FORBIDDEN_PATTERNS = [
  "/wissen/de/de/",
  "/wissen/en/en/",
  "/produkte/produkte/",
  "/products/products/",
];

const REDUNDANT_URL_PATTERNS = [
  "/wissen/de/de/",
  "/wissen/en/en/",
  "/wissen/de/produkte/produkte/",
  "/wissen/en/products/products/",
  "/wissen/de/oeffentlich/oeffentlich/",
  "/wissen/en/public/public/",
];

const NAV_TARGETS = {
  de: [
    "/wissen/de/shop/",
    "/wissen/de/faq/",
    "/wissen/de/produkte/",
    "/wissen/de/lookbook/",
  ],
  en: [
    "/wissen/en/shop/",
    "/wissen/en/faq/",
    "/wissen/en/products/",
    "/wissen/en/lookbook/",
  ],
};

const LEGAL_TARGETS = {
  de: [
    "/wissen/de/impressum/",
    "/wissen/de/datenschutz/",
    "/wissen/de/agb/",
    "/wissen/de/widerruf/",
    "/wissen/de/kontakt/",
  ],
  en: [
    "/wissen/en/imprint/",
    "/wissen/en/privacy/",
    "/wissen/en/terms/",
    "/wissen/en/withdrawal/",
    "/wissen/en/contact/",
  ],
};

const LANG_PREFIXES = {
  de: "/wissen/de/",
  en: "/wissen/en/",
};

const DEBUG = ["1", "true", "yes", "on"].includes(
  (process.env.GUARD_DEBUG || "").toLowerCase()
);

function normalizeHref(href, baseUrlPath = "/") {
  if (!href) {
    return null;
  }

  const raw = String(href).trim();
  if (!raw) {
    return null;
  }

  // Keep anchors as-is (the guard handles "#" explicitly as invalid).
  if (raw.startsWith("#")) {
    return raw;
  }

  let pathValue = raw;

  // Detect scheme (e.g., http:, https:, mailto:, javascript:).
  const schemeMatch = raw.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/);
  const scheme = schemeMatch ? schemeMatch[1].toLowerCase() : null;

  try {
    if (scheme === "http" || scheme === "https") {
      const url = new URL(raw);
      pathValue = url.pathname;
    } else if (!scheme) {
      // Resolve relative paths against the current page URL path.
      if (raw.startsWith("/")) {
        pathValue = raw;
      } else {
        const base = new URL(
          `https://example.com${
            baseUrlPath.endsWith("/") ? baseUrlPath : baseUrlPath + "/"
          }`
        );
        const resolved = new URL(raw, base);
        pathValue = resolved.pathname;
      }
    }
  } catch (error) {
    pathValue = raw;
  }

  if (!pathValue.startsWith("/")) {
    pathValue = `/${pathValue}`;
  }
  if (!pathValue.endsWith("/")) {
    pathValue = `${pathValue}/`;
  }

  return pathValue;
}

function debugLog(...messages) {
  if (DEBUG) {
    console.log(...messages);
  }
}

function shouldRunNavGuards(relPath) {
  const normalized = relPath.replace(/\\/g, "/");
  return NAV_GUARD_REL_PATHS.has(normalized);
}

function collectHtmlFiles(root) {
  const results = [];
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (entry.isFile() && entry.name.endsWith(".html")) {
        results.push(full);
      }
    }
  }
  return results.sort();
}

function normalizeUrlPath(filePath) {
  const rel = path.relative(ROOT, filePath).split(path.sep).join("/");
  let rawPath = "/";
  if (rel !== "index.html") {
    if (rel.endsWith("/index.html")) {
      rawPath = `/${rel.slice(0, -"/index.html".length)}/`;
    } else {
      rawPath = `/${rel}`;
    }
  }

  if (rawPath.startsWith("/wissen/")) {
    return rawPath;
  }
  const combined = `/wissen${rawPath}`;
  return combined.replace(/\/+/g, "/");
}

function getLang(urlPath) {
  for (const [lang, prefix] of Object.entries(LANG_PREFIXES)) {
    if (urlPath.startsWith(prefix)) {
      return lang;
    }
  }
  return null;
}

function hasNoindex($) {
  const robots = $("meta[name='robots']").attr("content") || "";
  return robots.toLowerCase().includes("noindex");
}

function isAliasLanding($) {
  return (
    $("meta[http-equiv]")
      .toArray()
      .some((el) => {
        const value = ($(el).attr("http-equiv") || "").toLowerCase();
        return value === "refresh";
      })
  );
}

function extractPathFromUrl(href) {
  if (!href) {
    return null;
  }
  try {
    const url = new URL(href, "https://example.com");
    return url.pathname;
  } catch {
    return null;
  }
}

function ensureCanonical($, filePath, urlPath, lang, errors, enforcePath) {
  const canonicals = $("link[rel='canonical']");
  if (canonicals.length !== 1) {
    errors.push(
      `${filePath}: expected exactly 1 canonical, found ${canonicals.length}`
    );
    return;
  }

  const canonicalHref = canonicals.first().attr("href") || "";
  if (!/^https?:\/\//i.test(canonicalHref)) {
    errors.push(`${filePath}: canonical must be absolute URL: ${canonicalHref}`);
    return;
  }

  const canonicalPath = extractPathFromUrl(canonicalHref);
  if (!canonicalPath) {
    errors.push(`${filePath}: canonical could not be parsed: ${canonicalHref}`);
    return;
  }

  for (const pattern of FORBIDDEN_PATTERNS) {
    if (canonicalPath.includes(pattern)) {
      errors.push(
        `${filePath}: canonical contains forbidden pattern "${pattern}": ${canonicalHref}`
      );
    }
  }

  if (enforcePath) {
    if (!canonicalPath.startsWith(LANG_PREFIXES[lang])) {
      errors.push(
        `${filePath}: canonical does not start with expected lang prefix ${LANG_PREFIXES[lang]}: ${canonicalHref}`
      );
    }

    const expectedPath = urlPath.replace(/\/+/g, "/");
    if (canonicalPath.replace(/\/+/g, "/") !== expectedPath) {
      errors.push(
        `${filePath}: canonical path mismatch. expected ${expectedPath}, got ${canonicalPath}`
      );
    }
  }
}

function checkForbiddenPatterns($, filePath, errors) {
  const targets = [
    { selector: "a[href]", attr: "href" },
    { selector: "link[rel='canonical'][href]", attr: "href" },
    { selector: "img[src]", attr: "src" },
  ];

  for (const { selector, attr } of targets) {
    $(selector)
      .toArray()
      .forEach((el) => {
        const value = $(el).attr(attr) || "";
        for (const pattern of FORBIDDEN_PATTERNS) {
          if (value.includes(pattern)) {
            errors.push(
              `${filePath}: forbidden pattern '${pattern}' found in ${selector} ${attr}="${value}"`
            );
          }
        }
      });
  }
}

function isRedundantUrlPath(urlPath) {
  return REDUNDANT_URL_PATTERNS.some((pattern) => urlPath.includes(pattern));
}

function ensureRedundantStrategy(noindex, filePath, urlPath, errors) {
  if (!isRedundantUrlPath(urlPath)) {
    return;
  }

  if (REDUNDANT_STRATEGY === "redirect") {
    errors.push(
      `${filePath}: redundant URL detected (${urlPath}); redirect strategy requires removing redundant output`
    );
    return;
  }

  if (REDUNDANT_STRATEGY !== "noindex") {
    errors.push(
      `${filePath}: invalid GUARD_REDUNDANT_URL_STRATEGY "${REDUNDANT_STRATEGY}" (expected "redirect" or "noindex")`
    );
    return;
  }

  if (!noindex) {
    errors.push(
      `${filePath}: redundant URL detected (${urlPath}); expected meta robots to include noindex`
    );
  }
}

function checkPrimaryNav($, filePath, urlPath, lang, errors) {
  const container = $("[data-testid='primary-nav']");
  if (!container.length) {
    debugLog(`${filePath}: primary nav container not found`);
    errors.push(`${filePath}: primary nav container not found`);
    return;
  }

  const rawHrefs = container
    .find("a")
    .toArray()
    .map((el) => {
      const href = $(el).attr("href");
      return href ? href.trim() : "";
    });

  const normalizedHrefs = rawHrefs
    .map((href) => normalizeHref(href, urlPath))
    .filter(Boolean);

  debugLog(
    `${filePath}: primary nav container found (${container.length})`,
    JSON.stringify({
      rawHrefs,
      normalizedHrefs,
    })
  );

  rawHrefs.forEach((href) => {
    const raw = (href || "").toString();
    const value = raw.trim();
    const lower = value.toLowerCase();

    const m = lower.match(/^([a-z][a-z0-9+.-]*):/);
    const scheme = m ? m[1] : null;
    const isBadScheme =
      scheme && (scheme === "javascript" || scheme === "data" || scheme === "vbscript");

    if (!value || value === "#" || isBadScheme) {
      errors.push(`${filePath}: invalid primary nav href "${raw}"`);
    }
  });

  const expected = NAV_TARGETS[lang].map((href) => normalizeHref(href, urlPath));
  const expectedSet = new Set(expected);

  const targetHrefs = normalizedHrefs.filter((href) =>
    href.startsWith(LANG_PREFIXES[lang])
  );

  const extra = targetHrefs.filter((href) => !expectedSet.has(href));
  if (extra.length) {
    errors.push(
      `${filePath}: primary nav contains unexpected ${LANG_PREFIXES[lang]} links: ${extra.join(", ")}`
    );
  }

  const missing = expected.filter((href) => !targetHrefs.includes(href));
  if (missing.length) {
    errors.push(
      `${filePath}: primary nav missing required links: ${missing.join(", ")}`
    );
  }

  for (const href of expected) {
    const count = targetHrefs.filter((value) => value === href).length;
    if (count > 1) {
      errors.push(`${filePath}: primary nav has duplicate link ${href}`);
    }
  }
}

function checkNavDrawer($, filePath, urlPath, lang, errors) {
  const container = $("[data-testid='nav-drawer']");
  if (!container.length) {
    debugLog(`${filePath}: nav drawer container not found`);
    errors.push(`${filePath}: nav drawer container not found`);
    return;
  }

  const rawHrefs = container
    .find("a[href]")
    .toArray()
    .map((el) => ($(el).attr("href") || "").trim());

  const normalizedHrefs = rawHrefs
    .map((href) => normalizeHref(href, urlPath))
    .filter(Boolean);

  debugLog(
    `${filePath}: nav drawer container found (${container.length})`,
    JSON.stringify({
      rawHrefs,
      normalizedHrefs,
    })
  );

  const expected = NAV_TARGETS[lang].map((href) => normalizeHref(href, urlPath));
  const missing = expected.filter((href) => !normalizedHrefs.includes(href));
  if (missing.length) {
    errors.push(
      `${filePath}: nav drawer missing required links: ${missing.join(", ")}`
    );
  }

  const legalTargets = LEGAL_TARGETS[lang].map((href) => normalizeHref(href, urlPath));
  const hasLegal = normalizedHrefs.some((href) =>
    legalTargets.some((target) => href.startsWith(target))
  );
  if (!hasLegal) {
    errors.push(`${filePath}: nav drawer missing a legal/footer link`);
  }
}

function main() {
  if (!fs.existsSync(ROOT)) {
    console.error(`Guard failed: root path not found: ${ROOT}`);
    return 1;
  }

  let files = collectHtmlFiles(ROOT);
  if (Number.isFinite(MAX_FILES) && MAX_FILES > 0) {
    files = files.slice(0, MAX_FILES);
  }

  const errors = [];

  for (const filePath of files) {
    const rel = path.relative(ROOT, filePath).split(path.sep).join("/");
    if (rel.endsWith("/404.html") || rel === "404.html") {
      continue;
    }

    const urlPath = normalizeUrlPath(filePath);
    const lang = getLang(urlPath);
    if (!lang) {
      continue;
    }

    const html = fs.readFileSync(filePath, "utf8");
    const $ = cheerio.load(html);

    if (isAliasLanding($)) {
      continue;
    }

    const noindex = hasNoindex($);

    ensureRedundantStrategy(noindex, filePath, urlPath, errors);

    if (noindex) {
      ensureCanonical($, filePath, urlPath, lang, errors, false);
    } else {
      ensureCanonical($, filePath, urlPath, lang, errors, true);
    }

    checkForbiddenPatterns($, filePath, errors);
    if (shouldRunNavGuards(rel)) {
      checkPrimaryNav($, filePath, urlPath, lang, errors);
      checkNavDrawer($, filePath, urlPath, lang, errors);
    }
  }

  if (errors.length) {
    console.error("Guard violations:");
    errors.forEach((error) => console.error(` - ${error}`));
    return 1;
  }

  console.log(`Guard OK. Checked ${files.length} HTML files.`);
  return 0;
}

process.exit(main());
