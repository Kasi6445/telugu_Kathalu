#!/usr/bin/env node
// Bumps the ?v=N version in all HTML files that reference static/style.css.
// Run this after changing style.css, before committing.

const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');

// Find all HTML files containing the versioned CSS link
const files = execSync('git ls-files "*.html"', { cwd: ROOT })
  .toString().trim().split('\n').filter(Boolean);

const versionPattern = /style\.css\?v=(\d+)/;
let currentVersion = null;

// Detect current version from any file
for (const file of files) {
  const content = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const match = content.match(versionPattern);
  if (match) { currentVersion = parseInt(match[1], 10); break; }
}

if (currentVersion === null) {
  console.error('Could not find ?v=N in any HTML file.');
  process.exit(1);
}

const nextVersion = currentVersion + 1;
let updated = 0;

for (const file of files) {
  const fullPath = path.join(ROOT, file);
  const content  = fs.readFileSync(fullPath, 'utf8');
  if (!versionPattern.test(content)) continue;
  const newContent = content.replace(
    new RegExp(`style\\.css\\?v=${currentVersion}`, 'g'),
    `style.css?v=${nextVersion}`
  );
  if (newContent !== content) {
    fs.writeFileSync(fullPath, newContent, 'utf8');
    updated++;
  }
}

console.log(`Bumped CSS version: v=${currentVersion} → v=${nextVersion} (${updated} files updated)`);

// Also update the version recorded in CLAUDE.md
const claudeMdPath = path.join(ROOT, 'CLAUDE.md');
if (fs.existsSync(claudeMdPath)) {
  const md = fs.readFileSync(claudeMdPath, 'utf8');
  fs.writeFileSync(claudeMdPath, md.replace(/`v=\d+`/, `\`v=${nextVersion}\``), 'utf8');
}

// Keep CSS_VERSION in lib/seo_writer.py in sync so promote.py generates correct links.
const seoWriterPath = path.join(ROOT, 'lib', 'seo_writer.py');
if (fs.existsSync(seoWriterPath)) {
  const py = fs.readFileSync(seoWriterPath, 'utf8');
  const updated_py = py.replace(/^CSS_VERSION\s*=\s*\d+/m, `CSS_VERSION  = ${nextVersion}`);
  if (updated_py !== py) {
    fs.writeFileSync(seoWriterPath, updated_py, 'utf8');
    console.log(`Updated CSS_VERSION in lib/seo_writer.py to ${nextVersion}`);
  } else {
    console.warn('Warning: CSS_VERSION not found in lib/seo_writer.py — update it manually.');
  }
}
