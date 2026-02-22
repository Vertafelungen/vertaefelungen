#!/usr/bin/env node
"use strict";

/**
 * PATH: wissen/scripts/guard_public_output.js
 * Version: 2026-02-22 18:45 CET
 *
 * Changes:
 * - Harden primary-nav href scheme validation (block javascript:, data:, vbscript:)
 * - Accept Shop legal SSOT links in nav drawer (Imprint/Terms/Privacy/Withdrawal) in addition to Wissen stubs.
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
  de: ["/wissen/de/shop/", "/wissen/de/faq/", "/wissen/de/produkte/", "/wissen/de/lookbook/"],
  en: ["/wissen/en/shop/", "/wissen/en/faq/", "/wissen/en/products/", "/wissen/en/lookbook/"],
};

// Drawer/footer links are considered valid if they point to either:
// 1) the canonical legal pages in the Shop (preferred SSOT), or
// 2) legacy Wissen stub pages (kept as an acceptable fallback).
const LEGAL_TARGETS = {
  de: [
    // Shop SSOT (preferred)
    "/de/content/2-impressum",
    "/de/content/3-allgemeine-geschaeftsbedingungen",
    "/de/content/7-datenschutzerklaerung",
    "/de/content/8-widerrufsbelehrung",
    // Wissen stubs (fallback)
    "/wissen/de/impressum/",
    "/wissen/de/datenschutz/",
    "/wissen/de/agb/",
    "/wissen/de/widerruf/",
    "/wissen/de/kontakt/",
  ],
  en: [
    // Shop SSOT (preferred)
    "/en/content/2-Imprint",
    "/en/content/3-allgemeine-geschaeftsbedingungen",
    "/en/content/7-datenschutzerklaerung",
    "/en/content/8-widerrufsbelehrung",
    // Wissen stubs (fallback)
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

function normalizeHref(href) {
  if (!href) {
    return null;
  }

  let pathValue = href;

  try {
    if (/^https?:\/\//i.test(href)) {
      const url = new URL(href);
      pathValue = url.pathname;
    }
  } catch (error) {
    pathValue = href;
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
  for (const lang of LANGS) {
    if (urlPath.startsWith(LANG_PREFIXES[lang])) {
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
      `${filePath}: expected exactly 1 canonical link, found ${canonicals.length}`
    );
    return;
  }
  const href = canonicals.attr("href") || "";
  if (!href.trim()) {
    errors.push(`${filePath}: canonical href is empty`);
    return;
  }
  if (!/^https?:\/\//i.test(href.trim())) {
    errors.push(`${filePath}: canonical href must be absolute (found: ${href})`);
    return;
  }
  const canonicalPath = extractPathFromUrl(href);
  if (!canonicalPath) {
    errors.push(`${filePath}: canonical href is invalid (found: ${href})`);
    return;
  }
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (canonicalPath.includes(pattern)) {
      errors.push(
        `${filePath}: canonical href contains redundant pattern '${pattern}' (found: ${href})`
      );
    }
  }
  if (enforcePath) {
    if (!canonicalPath || !canonicalPath.startsWith(LANG_PREFIXES[lang])) {
      errors.push(
        `${filePath}: canonical href must resolve under ${LANG_PREFIXES[lang]} (found: ${href})`
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
      .forEach((element) => {
        const value = ($(element).attr(attr) || "").trim();
        if (!value) {
          return;
        }
        for (const pattern of FORBIDDEN_PATTERNS) {
          if (value.includes(pattern)) {
            errors.push(
              `${filePath}: contains forbidden pattern '${pattern}' in ${selector} (${attr}='${value}')`
            );
          }
        }
        for (const pattern of REDUNDANT_URL_PATTERNS) {
          if (value.includes(pattern)) {
            errors.push(
              `${filePath}: contains redundant pattern '${pattern}' in ${selector} (${attr}='${value}')`
            );
          }
        }
      });
  }

  // Block unsafe URI schemes in primary navigation.
  const primaryNav = $("[data-testid='primary-nav']");
  if (primaryNav.length) {
    primaryNav
      .find("a[href]")
      .toArray()
      .forEach((element) => {
        const href = ($(element).attr("href") || "").trim();
        if (!href) {
          return;
        }
        const lowered = href.toLowerCase();
        if (
          lowered.startsWith("javascript:") ||
          lowered.startsWith("data:") ||
          lowered.startsWith("vbscript:")
        ) {
          errors.push(`${filePath}: primary nav contains unsafe href scheme: ${href}`);
        }
      });
  }
}

function ensureRedundantStrategy(noindex, filePath, urlPath, errors) {
  if (REDUNDANT_STRATEGY === "noindex") {
    if (!noindex) {
      for (const pattern of REDUNDANT_URL_PATTERNS) {
        if (urlPath.includes(pattern)) {
          errors.push(`${filePath}: redundant URL must be noindex (found indexable)`);
        }
      }
    }
  } else if (REDUNDANT_STRATEGY === "redirect") {
    // enforce canonical under lang prefix via ensureCanonical(... enforcePath=true)
  }
}

function checkPrimaryNav($, filePath, lang, errors) {
  const container = $("[data-testid='primary-nav']");
  if (!container.length) {
    errors.push(`${filePath}: primary nav container not found`);
    return;
  }

  const rawHrefs = container
    .find("a[href]")
    .toArray()
    .map((el) => ($(el).attr("href") || "").trim());

  const normalizedHrefs = rawHrefs
    .map((href) => normalizeHref(href))
    .filter(Boolean);

  const expected = NAV_TARGETS[lang].map((href) => normalizeHref(href));
  const missing = expected.filter((href) => !normalizedHrefs.includes(href));
  if (missing.length) {
    errors.push(`${filePath}: primary nav missing required links: ${missing.join(", ")}`);
  }

  const unexpected = normalizedHrefs.filter(
    (href) => href && href.startsWith(LANG_PREFIXES[lang]) && !expected.includes(href)
  );
  if (unexpected.length) {
    errors.push(
      `${filePath}: primary nav contains unexpected ${LANG_PREFIXES[lang]} links: ${unexpected.join(", ")}`
    );
  }

  for (const href of expected) {
    const count = normalizedHrefs.filter((value) => value === href).length;
    if (count > 1) {
      errors.push(`${filePath}: primary nav has duplicate link ${href}`);
    }
  }
}

function checkNavDrawer($, filePath, lang, errors) {
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
    .map((href) => normalizeHref(href))
    .filter(Boolean);

  debugLog(
    `${filePath}: nav drawer container found (${container.length})`,
    JSON.stringify({
      rawHrefs,
      normalizedHrefs,
    })
  );

  const expected = NAV_TARGETS[lang].map((href) => normalizeHref(href));
  const missing = expected.filter((href) => !normalizedHrefs.includes(href));
  if (missing.length) {
    errors.push(`${filePath}: nav drawer missing required links: ${missing.join(", ")}`);
  }

  const legalTargets = LEGAL_TARGETS[lang].map((href) => normalizeHref(href));
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
      checkPrimaryNav($, filePath, lang, errors);
      checkNavDrawer($, filePath, lang, errors);
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
