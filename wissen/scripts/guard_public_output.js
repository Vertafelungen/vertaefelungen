#!/usr/bin/env node
"use strict";

/**
 * guard_public_output.js
 * Version: 2026-01-29 21:00 CET
 *
 * Fixes:
 * - Resolve relative hrefs against current page URL path so nav guards work with relref/relative links.
 * - Extend dangerous scheme detection to include data: and vbscript: (in addition to javascript:).
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

const LANGS = ["de", "en"];

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

  // Keep anchors as-is; the nav guards treat "#" as invalid explicitly.
  if (raw.startsWith("#")) {
    return raw;
  }

  let pathValue = raw;

  try {
    // Absolute URL: use pathname
    if (/^https?:\/\//i.test(raw)) {
      const url = new URL(raw);
      pathValue = url.pathname;
    } else {
      // Relative or absolute-path URL: resolve against the current page URL path
      // Example: "../shop/" on "/wissen/de/faq/" resolves to "/wissen/de/shop/".
      const base = new URL(
        `https://example.com${
          baseUrlPath.endsWith("/") ? baseUrlPath : baseUrlPath + "/"
        }`
      );
      const resolved = new URL(raw, base);
      pathValue = resolved.pathname;
    }
  } catch (error) {
    // Fallback: keep raw as-is; best-effort normalization below
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
  return $("meta[http-equiv]")
    .toArray()
    .some((el) => {
      const value = ($(el).attr("http-equiv") || "").toLowerCase();
      return value === "refresh";
    });
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
  const html = $.html();
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (html.includes(pattern)) {
      errors.push(`
