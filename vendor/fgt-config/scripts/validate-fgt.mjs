#!/usr/bin/env node

/**
 * validate-fgt.mjs - Validates FGT repository structure
 *
 * Checks:
 * 1. FGT.md exists with required sections
 * 2. templates/ directory exists with required files
 * 3. Markdown links in FGT.md are not broken
 */

import { readFileSync, existsSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

// Parse --project <dir> argument
const projectIdx = process.argv.indexOf('--project');
const PROJECT_DIR = projectIdx !== -1 ? process.argv[projectIdx + 1] : null;

const errors = [];
const warnings = [];

function error(msg) {
  errors.push(`ERROR: ${msg}`);
}

function warn(msg) {
  warnings.push(`WARN: ${msg}`);
}

function checkFileExists(filePath, description) {
  const fullPath = join(ROOT, filePath);
  if (!existsSync(fullPath)) {
    error(`${description} not found: ${filePath}`);
    return false;
  }
  return true;
}

function checkFgtMd() {
  const fgtPath = join(ROOT, 'FGT.md');
  if (!existsSync(fgtPath)) {
    error('FGT.md not found in repository root');
    return;
  }

  const content = readFileSync(fgtPath, 'utf-8');

  // Required sections
  const requiredSections = [
    'Bug Abstraction Protocol',
    'Prevention Principles',
    'Test Categories',
    'Enforcement Planes',
    'CI Enforcement',
  ];

  for (const section of requiredSections) {
    if (!content.includes(section)) {
      error(`FGT.md missing required section: ${section}`);
    }
  }

  // Check for VE-specific content that shouldn't be in generic FGT
  const veSpecificTerms = [
    'entity_graph',
    'VE_',
    'VE-',
    'INV-CALC',
    'DSL Parsing',
    'React Flow',
    'ConfigPanel',
    'NEB75',
    'alta_vista',
    'Alta Vista',
    'cfg_PadRent',
    'MHC',
    'pad rent',
  ];

  for (const term of veSpecificTerms) {
    if (content.includes(term)) {
      warn(`FGT.md contains VE-specific term: "${term}"`);
    }
  }
}

function checkTemplatesDirectory() {
  const templatesDir = join(ROOT, 'templates');
  if (!existsSync(templatesDir)) {
    error('templates/ directory not found');
    return;
  }

  const requiredTemplates = [
    'PATTERNS_TEMPLATE.md',
    'REVIEWS_TEMPLATE.md',
    'BUG_PATTERNS_TEMPLATE.md',
    'FGT_DOMAIN_TEMPLATE.md',
  ];

  for (const template of requiredTemplates) {
    const templatePath = join(templatesDir, template);
    if (!existsSync(templatePath)) {
      error(`Required template not found: templates/${template}`);
    }
  }

  const recommendedTemplates = [
    'CLAUDE_MD_TEMPLATE.md',
    'CLAUDE_HOOKS_TEMPLATE.md',
    'EXPERT_REVIEWERS_TEMPLATE.md',
    'BACKLOG_TEMPLATE.md',
    'REVALIDATION_TEMPLATE.md',
    'CONFIG_TEMPLATE.md',
    'ENTITY_RESOLUTION_TEMPLATE.md',
  ];

  for (const template of recommendedTemplates) {
    const templatePath = join(templatesDir, template);
    if (!existsSync(templatePath)) {
      warn(`Recommended template not found: templates/${template}`);
    }
  }
}

function checkScriptsDirectory() {
  const scriptsDir = join(ROOT, 'scripts');
  if (!existsSync(scriptsDir)) {
    error('scripts/ directory not found');
    return;
  }

  const recommendedScripts = [
    'new-project.sh',
  ];

  for (const script of recommendedScripts) {
    const scriptPath = join(scriptsDir, script);
    if (!existsSync(scriptPath)) {
      warn(`Recommended script not found: scripts/${script}`);
    }
  }
}

function checkMarkdownLinks() {
  const fgtPath = join(ROOT, 'FGT.md');
  if (!existsSync(fgtPath)) return;

  const content = readFileSync(fgtPath, 'utf-8');

  // Find relative markdown links: [text](path.md) or [text](./path.md)
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let match;

  while ((match = linkRegex.exec(content)) !== null) {
    const linkPath = match[2];

    // Skip external links and anchors
    if (linkPath.startsWith('http') || linkPath.startsWith('#')) {
      continue;
    }

    // Resolve relative to FGT.md location (root)
    const fullPath = join(ROOT, linkPath.split('#')[0]);
    if (!existsSync(fullPath)) {
      error(`Broken link in FGT.md: ${linkPath}`);
    }
  }
}

// --- CI-workflow security checks (apply to fgt-config itself and to projects) ---

/**
 * Flag `continue-on-error: true` on any workflow step that is not explicitly
 * advisory.
 *
 * This is av226 BUG-029: a CI check configured to tolerate failure provides no
 * defense at all (33-day hollow defense before it was discovered).
 *
 * Precision rule: a step whose `run:` body already contains `|| true` (shell
 * swallow) is explicitly advisory — the author's stated intent is reporting,
 * not gating. The `continue-on-error: true` is redundant belt-and-suspenders,
 * not a silenced defense. Skip those. Bare `continue-on-error: true` on a step
 * that would otherwise fail is the real BUG-029 pattern and stays ERROR.
 */
function checkWorkflowContinueOnError(baseDir, label) {
  const workflowsDir = join(baseDir, '.github', 'workflows');
  if (!existsSync(workflowsDir)) return;
  const stepStart = /^\s+-\s+(name|uses|run):/;
  const files = readdirSync(workflowsDir).filter(
    f => f.endsWith('.yml') || f.endsWith('.yaml')
  );
  for (const f of files) {
    const content = readFileSync(join(workflowsDir, f), 'utf-8');
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (!/^\s*continue-on-error\s*:\s*true\b/.test(lines[i])) continue;
      // Walk back to the current step's first line.
      let stepStartIdx = 0;
      for (let j = i - 1; j >= 0; j--) {
        if (stepStart.test(lines[j])) { stepStartIdx = j; break; }
      }
      // If the step's body already neutralises failures at the shell level,
      // treat the redundant continue-on-error as intentional advisory.
      let advisory = false;
      for (let j = stepStartIdx; j < i; j++) {
        if (/\|\|\s*true\b/.test(lines[j])) { advisory = true; break; }
      }
      if (advisory) continue;
      error(
        `${label}.github/workflows/${f}:${i + 1}: \`continue-on-error: true\`` +
        ` (BUG-029: CI step tolerates failure — defense is hollow)`
      );
    }
  }
}

/**
 * Flag `git clone` of an external HTTPS/SSH URL that is not pinned to a commit
 * SHA within the surrounding 10 lines.
 *
 * "Pinned" means one of:
 *   (a) a 40-char hex SHA literal appears in the window, or
 *   (b) a `*_SHA` env-var reference (e.g. `$FGT_SHA`, `${ACTIONS_SHA}`) appears.
 *
 * Rationale: unpinned clone + run in CI = account-takeover on the upstream
 * org gets arbitrary code execution in this job, with access to its secrets.
 * Reported as WARN because heuristics can have false-positives (e.g. internal
 * repos with other access controls).
 */
function checkWorkflowGitClonePinned(baseDir, label) {
  const workflowsDir = join(baseDir, '.github', 'workflows');
  if (!existsSync(workflowsDir)) return;
  const files = readdirSync(workflowsDir).filter(
    f => f.endsWith('.yml') || f.endsWith('.yaml')
  );
  const cloneRegex = /\bgit\s+clone\b[^\n]*?\b(?:https?:\/\/|git@)/;
  const shaLiteral = /\b[0-9a-f]{40}\b/;
  const shaVar = /\$\{?[A-Za-z0-9_]*SHA[A-Za-z0-9_]*\}?/;
  for (const f of files) {
    const content = readFileSync(join(workflowsDir, f), 'utf-8');
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (!cloneRegex.test(lines[i])) continue;
      const windowText = lines.slice(i, Math.min(i + 11, lines.length)).join('\n');
      if (shaLiteral.test(windowText) || shaVar.test(windowText)) continue;
      warn(
        `${label}.github/workflows/${f}:${i + 1}: unpinned \`git clone\` — ` +
        `pin to a commit SHA (literal or via *_SHA env) to defend against ` +
        `upstream compromise`
      );
    }
  }
}

// --- Project-level checks (when --project is provided) ---

function checkProjectFgtLog(projectDir) {
  const fgtLogPath = join(projectDir, 'FGT_LOG.md');
  if (!existsSync(fgtLogPath)) {
    warn(`Project FGT_LOG.md not found: ${projectDir}`);
    return;
  }

  const content = readFileSync(fgtLogPath, 'utf-8');
  const lines = content.split('\n');
  // Count table rows (lines starting with | that aren't headers/separators/empty)
  const entryLines = lines.filter(line =>
    line.startsWith('|') &&
    !line.includes('---') &&
    !line.includes('Date') &&
    !line.includes('Task ID') &&
    !line.includes('Add entries') &&
    line.trim().length > 5
  );
  const entryCount = entryLines.length;

  let commitCount = 0;
  try {
    commitCount = parseInt(
      execSync(`git -C "${projectDir}" rev-list --count HEAD`, { encoding: 'utf-8' }).trim()
    );
  } catch {
    return; // Not a git repo or git unavailable
  }

  const expectedEntries = Math.floor(commitCount / 5);
  if (entryCount < expectedEntries && commitCount >= 10) {
    warn(`FGT_LOG.md has ${entryCount} entries for ${commitCount} commits (expected ~${expectedEntries}; guideline: 1 entry per 5 commits)`);
  }
}

function checkProjectRequiredFiles(projectDir) {
  const files = readdirSync(projectDir);
  const bugPatterns = files.find(f => f.startsWith('BUG_PATTERNS') && f.endsWith('.md'));
  if (!bugPatterns) {
    warn(`Project missing BUG_PATTERNS_*.md: ${projectDir}`);
  }

  if (!existsSync(join(projectDir, 'BACKLOG.md'))) {
    warn(`Project missing BACKLOG.md (required by Principle 9): ${projectDir}`);
  }
}

function checkProject(projectDir) {
  if (!existsSync(projectDir)) {
    error(`Project directory not found: ${projectDir}`);
    return;
  }
  console.log(`Validating project: ${projectDir}\n`);
  checkProjectFgtLog(projectDir);
  checkProjectRequiredFiles(projectDir);
  checkWorkflowContinueOnError(projectDir, `${projectDir}/`);
  checkWorkflowGitClonePinned(projectDir, `${projectDir}/`);
}

function checkPrincipleReferences() {
  // CONTRACT: Templates that reference principles by number must match FGT.md definitions.
  // Principles are now keyed by slug in tier tables (| `SLUG` | **Name** | ...);
  // numeric IDs map to slugs via the Legacy Numeric IDs table (| P5 | `SLUG` |).
  const fgtPath = join(ROOT, 'FGT.md');
  if (!existsSync(fgtPath)) return;

  const fgtContent = readFileSync(fgtPath, 'utf-8');

  // Extract slug → name from tier tables: "| `SLUG` | **Name** | meaning | violations |"
  const slugRowRegex = /^\|\s*`([A-Z][A-Z0-9-]+)`\s*\|\s*\*\*([^*]+)\*\*/gm;
  const slugToName = new Map();
  let match;
  while ((match = slugRowRegex.exec(fgtContent)) !== null) {
    slugToName.set(match[1], match[2].trim());
  }

  if (slugToName.size < 11) {
    warn(`Only found ${slugToName.size} principles in FGT.md tier tables (expected 11)`);
    return;
  }

  // Extract numeric → slug from the Legacy Numeric IDs table: "| P5 | `SLUG` |"
  const legacyRowRegex = /^\|\s*P(\d+)\s*\|\s*`([A-Z][A-Z0-9-]+)`\s*\|/gm;
  const numberToSlug = new Map();
  while ((match = legacyRowRegex.exec(fgtContent)) !== null) {
    numberToSlug.set(match[1], match[2]);
  }

  if (numberToSlug.size < 11) {
    warn(`Only found ${numberToSlug.size} entries in FGT.md Legacy Numeric IDs table (expected 11)`);
  }

  // Scan templates for "Principle N" references and verify the name still resolves
  const templatesDir = join(ROOT, 'templates');
  if (!existsSync(templatesDir)) return;

  const templateFiles = readdirSync(templatesDir).filter(f => f.endsWith('.md'));
  const principleRefRegex = /Principle\s+(\d+)\s*[:(]\s*([^)\n]+)/g;

  for (const file of templateFiles) {
    const content = readFileSync(join(templatesDir, file), 'utf-8');
    let refMatch;
    while ((refMatch = principleRefRegex.exec(content)) !== null) {
      const num = refMatch[1];
      const refName = refMatch[2].trim().replace(/\*\*/g, '');
      const slug = numberToSlug.get(num);
      const fgtName = slug ? slugToName.get(slug) : undefined;
      if (fgtName && !refName.toLowerCase().includes(fgtName.toLowerCase().split(' ')[0])) {
        // Only warn if the reference name doesn't start with the same word as the FGT definition
        warn(`${file}: references "Principle ${num}: ${refName}" but FGT.md defines Principle ${num} (${slug}) as "${fgtName}"`);
      }
    }
  }
}

// Run all checks
console.log('Validating FGT repository structure...\n');

checkFgtMd();
checkTemplatesDirectory();
checkScriptsDirectory();
checkMarkdownLinks();
checkPrincipleReferences();
// Also lint fgt-config's own workflows.
checkWorkflowContinueOnError(ROOT, '');
checkWorkflowGitClonePinned(ROOT, '');

if (PROJECT_DIR) {
  checkProject(PROJECT_DIR);
}

// Report results
if (warnings.length > 0) {
  console.log('Warnings:');
  for (const w of warnings) {
    console.log(`  ${w}`);
  }
  console.log();
}

if (errors.length > 0) {
  console.log('Errors:');
  for (const e of errors) {
    console.log(`  ${e}`);
  }
  console.log();
  console.log(`Validation failed with ${errors.length} error(s)`);
  process.exit(1);
}

console.log('FGT structure validation passed');
