#!/usr/bin/env node
"use strict";

/**
 * guard_public_output.js
 * Version: 2026-01-29 21:00 CET
 *
 * Change: Harden primary-nav href scheme validation to also reject data: and vbscript:
 * (keeps existing behavior for empty/#/javascript:; adds trimming to avoid false negatives).
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
const LANG_PREFIXES = {
  de: "/wissen/de/",
  en: "/wissen/en/",
};

const NAV_TARGETS = {
  de: ["/wissen/de/shop/", "/wissen/de/faq/", "/wissen/de/produkte/", "/wissen/de/lookbook/"],
  en: ["/wissen/en/shop/", "/wissen/en/faq/", "/wissen/en/products/", "/wissen/en/lookbook/"],
};

const debugLog = (...args) => {
  if (process.env.GUARD_DEBUG === "1") {
    // eslint-disable-next-line no-console
    console.log("[guard]", ...args);
  }
};

const isHtmlFile = (filePath) => filePath.toLowerCase().endsWith(".html");

const walkDir = (dir, results = []) => {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkDir(full, results);
    } else if (entry.isFile()) {
      results.push(full);
    }
  }
  return results;
};

const relFromRoot = (absPath) => path.relative(ROOT, absPath).replaceAll("\\", "/");

const normalizeHref = (href) => {
  if (!href) return null;
  const raw = String(href).trim();
  if (!raw) return null;

  if (raw.startsWith("#")) return "#";

  // Allow absolute URLs (external) but normalize casing for scheme
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) {
    return raw;
  }

  // Normalize relative/absolute internal URLs
  const withoutQuery = raw.split("?")[0].split("#")[0];

  // Ensure leading slash for internal paths
  if (withoutQuery.startsWith("/")) return withoutQuery;
  return `/${withoutQuery}`;
};

const ensureExpectedLangPrefix = (href, lang) => {
  if (!href) return false;
  return href.startsWith(LANG_PREFIXES[lang]);
};

const findPrimaryNavContainer = ($) => {
  // Heuristics:
  // Prefer nav element, then header, else first element with role navigation
  const nav = $("nav").first();
  if (nav.length) return nav;

  const roleNav = $('[role="navigation"]').first();
  if (roleNav.length) return roleNav;

  const header = $("header").first();
  if (header.length) return header;

  return null;
};

const extractHrefs = ($, container) => {
  const hrefs = [];
  container.find("a").each((_, el) => {
    const href = $(el).attr("href");
    hrefs.push(href);
  });
  return hrefs;
};

const checkForbiddenPatterns = (filePath, html) => {
  const errors = [];
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (html.includes(pattern)) {
      errors.push(`${filePath}: forbidden pattern present "${pattern}"`);
    }
  }
  return errors;
};

const checkRedundantUrlStrategy = (filePath, html) => {
  const errors = [];
  if (REDUNDANT_STRATEGY !== "redirect" && REDUNDANT_STRATEGY !== "error") {
    errors.push(
      `${filePath}: invalid GUARD_REDUNDANT_URL_STRATEGY="${REDUNDANT_STRATEGY}" (expected redirect|error)`
    );
    return errors;
  }

  const hits = [];
  for (const pattern of REDUNDANT_URL_PATTERNS) {
    if (html.includes(pattern)) hits.push(pattern);
  }

  if (!hits.length) return errors;

  if (REDUNDANT_STRATEGY === "error") {
    errors.push(`${filePath}: redundant URL patterns present: ${hits.join(", ")}`);
  } else {
    debugLog(`${filePath}: redundant URL patterns present (allowed due to redirect strategy)`, hits);
  }

  return errors;
};

const detectLangFromPath = (relPath) => {
  const parts = relPath.split("/");
  const lang = parts[0];
  if (LANGS.includes(lang)) return lang;
  return null;
};

const guardPrimaryNav = (filePath, relPath, html) => {
  const errors = [];
  const lang = detectLangFromPath(relPath);

  if (!lang) return errors;
  if (!NAV_GUARD_REL_PATHS.has(relPath)) return errors;

  const $ = cheerio.load(html);
  const container = findPrimaryNavContainer($);

  if (!container || !container.length) {
    errors.push(`${filePath}: primary nav container not found`);
    return errors;
  }

  const rawHrefs = extractHrefs($, container);
  const normalizedHrefs = rawHrefs
    .map((href) => normalizeHref(href))
    .filter(Boolean);

  debugLog(
    `${filePath}: primary nav container found (${container.length})`,
    JSON.stringify({
      rawHrefs,
      normalizedHrefs,
    })
  );

  rawHrefs.forEach((href) => {
    const raw = href == null ? "" : String(href);
    const value = raw.trim();
    const lower = value.toLowerCase();

    if (
      !value ||
      value === "#" ||
      lower.startsWith("javascript:") ||
      lower.startsWith("data:") ||
      lower.startsWith("vbscript:")
    ) {
      errors.push(`${filePath}: invalid primary nav href "${raw}"`);
    }
  });

  const expected = NAV_TARGETS[lang].map((href) => normalizeHref(href));
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
    if (!ensureExpectedLangPrefix(href, lang)) {
      errors.push(`${filePath}: expected nav target does not have lang prefix: "${href}"`);
    }
  }

  return errors;
};

const checkFile = (absPath) => {
  const relPath = relFromRoot(absPath);
  const html = fs.readFileSync(absPath, "utf8");

  const errors = [];
  errors.push(...checkForbiddenPatterns(absPath, html));
  errors.push(...checkRedundantUrlStrategy(absPath, html));
  errors.push(...guardPrimaryNav(absPath, relPath, html));
  return errors;
};

const main = () => {
  if (!fs.existsSync(ROOT)) {
    // eslint-disable-next-line no-console
    console.error(`ERROR: ROOT directory not found: ${ROOT}`);
    process.exit(2);
  }

  const allFiles = walkDir(ROOT).filter(isHtmlFile);

  const files = Number.isFinite(MAX_FILES) && MAX_FILES > 0 ? allFiles.slice(0, MAX_FILES) : allFiles;

  debugLog(`Scanning ROOT=${ROOT} files=${files.length} totalHtml=${allFiles.length}`);

  const allErrors = [];
  for (const file of files) {
    try {
      const errs = checkFile(file);
      allErrors.push(...errs);
    } catch (err) {
      allErrors.push(`${file}: exception while scanning: ${err && err.message ? err.message : String(err)}`);
    }
  }

  if (allErrors.length) {
    // eslint-disable-next-line no-console
    console.error(allErrors.join("\n"));
    process.exit(2);
  }

  // eslint-disable-next-line no-console
  console.log(`OK: guard_public_output passed (${files.length} HTML files scanned)`);
};

main();
