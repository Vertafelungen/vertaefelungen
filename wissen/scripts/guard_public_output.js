#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const cheerio = require("cheerio");

const ROOT = process.env.GUARD_ROOT
  ? path.resolve(process.env.GUARD_ROOT)
  : path.resolve(__dirname, "..", "public");

const MAX_FILES = Number.parseInt(process.env.GUARD_MAX_FILES || "", 10);

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
      `${filePath}: expected exactly 1 canonical link, found ${canonicals.length}`
    );
    return;
  }
  const href = canonicals.attr("href") || "";
  if (!href.trim()) {
    errors.push(`${filePath}: canonical href is empty`);
    return;
  }
  if (enforcePath) {
    const canonicalPath = extractPathFromUrl(href);
    if (!canonicalPath || !canonicalPath.startsWith(LANG_PREFIXES[lang])) {
      errors.push(
        `${filePath}: canonical href must resolve under ${LANG_PREFIXES[lang]} (found: ${href})`
      );
    }
  }
}

function checkForbiddenPatterns($, filePath, noindex, errors) {
  if (noindex) {
    return;
  }
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

function checkPrimaryNav($, filePath, lang, errors) {
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
    if (!href || href === "#" || href.toLowerCase().startsWith("javascript:")) {
      errors.push(`${filePath}: invalid primary nav href "${href}"`);
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
    const count = targetHrefs.filter((value) => value === href).length;
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
    errors.push(
      `${filePath}: nav drawer missing required links: ${missing.join(", ")}`
    );
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

    if (noindex) {
      ensureCanonical($, filePath, urlPath, lang, errors, false);
      continue;
    }

    ensureCanonical($, filePath, urlPath, lang, errors, true);
    checkForbiddenPatterns($, filePath, noindex, errors);
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
