#!/usr/bin/env node

/**
 * validate-templates.mjs - Validates template files are generic (not project-specific)
 *
 * Checks:
 * 1. Templates don't contain VE-specific or other project-specific terms
 * 2. Templates use {{DOMAIN}} placeholders for customization points
 * 3. Templates follow naming conventions
 */

import { readFileSync, existsSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const TEMPLATES_DIR = join(ROOT, 'templates');

// Parse --project <dir> --domain <DOMAIN> arguments
const projectIdx = process.argv.indexOf('--project');
const domainIdx = process.argv.indexOf('--domain');
const PROJECT_DIR = projectIdx !== -1 ? process.argv[projectIdx + 1] : null;
const PROJECT_DOMAIN = domainIdx !== -1 ? process.argv[domainIdx + 1] : null;

const errors = [];
const warnings = [];

function error(msg) {
  errors.push(`ERROR: ${msg}`);
}

function warn(msg) {
  warnings.push(`WARN: ${msg}`);
}

// Project-specific terms that should NOT appear in generic templates
// Add terms here as projects are detected to have leaked into templates
const PROJECT_SPECIFIC_TERMS = [
  // VE (Value Engine) specific terms
  { term: 'entity_graph', project: 'VE' },
  { term: 'VE_TASKS', project: 'VE' },
  { term: 'VE_CONFIG_SPEC', project: 'VE' },
  { term: 'VE_DSL_SPEC', project: 'VE' },
  { term: 'VE Code Patterns', project: 'VE' },
  { term: 'VE Review', project: 'VE' },
  { term: 'INV-CALC', project: 'VE' },
  { term: 'NEB75', project: 'VE' },
  { term: 'ConfigPanel', project: 'VE' },
  { term: 'taxRules', project: 'VE' },
  { term: 'retirementRules', project: 'VE' },
  { term: 'feeRanges', project: 'VE' },
  { term: 'depreciationRules', project: 'VE' },
  { term: 'Johns graph', project: 'VE' },
  { term: 'manco', project: 'VE' },
  { term: 'scorp', project: 'VE' },
  { term: 'asset_portfolio', project: 'VE' },

  // React Flow specific (too implementation-specific for generic template)
  { term: 'useNodesState', project: 'React Flow' },
  { term: 'useEdgesState', project: 'React Flow' },
  { term: 'reactflow', project: 'React Flow' },
  { term: 'React Flow', project: 'React Flow' },
  { term: 'getBezierPath', project: 'React Flow' },
  { term: 'EdgeLabelRenderer', project: 'React Flow' },

  // Domain-specific financial terms (should be in FGT_DOMAIN_*.md, not templates)
  { term: 'IRS_LIMIT', project: 'Financial Domain' },
  { term: 'federal_brackets', project: 'Financial Domain' },
  { term: 'married_filing_jointly', project: 'Financial Domain' },
  { term: 'cap rate', project: 'Financial Domain' },
  { term: 'debt service', project: 'Financial Domain' },

  // Nakano Watch Crawler specific terms
  { term: 'nakano-crawler', project: 'Nakano' },
  { term: 'nakano watch', project: 'Nakano' },
  { term: 'Nakano Watch', project: 'Nakano' },
  { term: 'eBay', project: 'Nakano' },
  { term: 'Rolex', project: 'Nakano' },

  // doc2txt (formerly pdf2txt) specific terms
  { term: 'pdf2txt', project: 'doc2txt' },
  { term: 'doc2txt', project: 'doc2txt' },
  { term: 'page_needs_ocr', project: 'doc2txt' },

  // AV226 / RE Dev Model specific terms
  { term: 'alta_vista', project: 'AV226' },
  { term: 'Alta Vista', project: 'AV226' },
  { term: 'cfg_PadRent', project: 'AV226' },
  { term: 'MHC', project: 'AV226' },
  { term: 'manufactured home', project: 'AV226' },
  { term: 'pad rent', project: 'AV226' },
  { term: 'waterfall', project: 'AV226' },
  { term: 'Class A', project: 'AV226' },
  { term: 'Class B', project: 'AV226' },
];

// Template naming conventions
const VALID_TEMPLATE_PATTERNS = [
  /^[A-Z_]+_TEMPLATE\.md$/,  // e.g., PATTERNS_TEMPLATE.md
];

function validateTemplateContent(filePath, fileName) {
  const content = readFileSync(filePath, 'utf-8');

  // Check for project-specific terms
  for (const { term, project } of PROJECT_SPECIFIC_TERMS) {
    if (content.includes(term)) {
      error(`${fileName} contains ${project}-specific term: "${term}"`);
    }
  }

  // Check that templates have placeholder documentation
  const hasPlaceholderDoc = content.includes('{{') || content.includes('placeholder');
  if (!hasPlaceholderDoc) {
    warn(`${fileName} has no placeholder documentation - templates should indicate customization points`);
  }
}

function validateTemplateNaming(fileName) {
  const isValidName = VALID_TEMPLATE_PATTERNS.some(pattern => pattern.test(fileName));
  if (!isValidName) {
    warn(`${fileName} doesn't follow template naming convention (*_TEMPLATE.md)`);
  }
}

function getAllFiles(dir, ext) {
  const results = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...getAllFiles(full, ext));
    } else if (entry.name.endsWith(ext)) {
      results.push(full);
    }
  }
  return results;
}

function validateTemplatesDirectory() {
  if (!existsSync(TEMPLATES_DIR)) {
    error('templates/ directory not found');
    return;
  }

  const files = readdirSync(TEMPLATES_DIR);
  const mdFiles = files.filter(f => f.endsWith('.md'));

  if (mdFiles.length === 0) {
    error('No markdown template files found in templates/');
    return;
  }

  for (const file of mdFiles) {
    const filePath = join(TEMPLATES_DIR, file);
    validateTemplateNaming(file);
    validateTemplateContent(filePath, file);
  }

  // Also validate scaffold templates (.tmpl files)
  const scaffoldDir = join(TEMPLATES_DIR, 'scaffold');
  const tmplFiles = getAllFiles(scaffoldDir, '.tmpl');
  for (const tmplPath of tmplFiles) {
    const relativeName = tmplPath.replace(TEMPLATES_DIR + '/', '');
    validateTemplateContent(tmplPath, relativeName);
  }
  if (tmplFiles.length > 0) {
    console.log(`  Scanned ${tmplFiles.length} scaffold template(s)`);
  }
}

// --- Project-level cargo-cult detection (when --project and --domain are provided) ---

// Language signal detection for cross-domain cargo-cult detection
const LANGUAGE_SIGNALS = {
  python: {
    positive: ['def ', 'import ', 'class ', '.py', 'pytest', 'dataclass', '__init__', 'pydantic'],
    negative: ['React', 'useState', 'TypeScript', 'tsx', 'jsx', 'const ', 'npm run', 'useEffect'],
  },
  javascript: {
    positive: ['const ', 'function ', 'import {', 'require(', '.tsx', '.jsx', 'npm ', 'node '],
    negative: ['def ', 'import os', 'pytest', '__init__', 'pydantic', 'dataclass'],
  },
};

function validateProjectFile(filePath, fileName, domain) {
  if (!existsSync(filePath)) return;
  const content = readFileSync(filePath, 'utf-8');

  // Check for terms from OTHER projects (skip terms matching this domain)
  const domainLower = domain.toLowerCase();
  for (const { term, project } of PROJECT_SPECIFIC_TERMS) {
    const projectLower = project.toLowerCase();
    // Skip terms that belong to the current project's domain
    if (domainLower.includes(projectLower) || projectLower.includes(domainLower)) continue;
    if (content.includes(term)) {
      error(`${fileName} contains ${project}-specific term: "${term}"`);
    }
  }

  // Detect language mismatch by counting signals
  for (const [lang, signals] of Object.entries(LANGUAGE_SIGNALS)) {
    const positiveCount = signals.positive.filter(s => content.includes(s)).length;
    const negativeCount = signals.negative.filter(s => content.includes(s)).length;
    if (negativeCount >= 3 && negativeCount > positiveCount) {
      warn(`${fileName} appears to contain ${lang === 'python' ? 'JavaScript/TypeScript' : 'Python'} content — possible cargo-cult from another project`);
    }
  }
}

function validateProjectFiles(projectDir, domain) {
  if (!existsSync(projectDir)) {
    error(`Project directory not found: ${projectDir}`);
    return;
  }

  console.log(`Validating project files for domain: ${domain}\n`);

  const filesToCheck = [
    `PATTERNS_${domain}.md`,
    `REVIEWS_${domain}.md`,
    `FGT_DOMAIN_${domain}.md`,
    `BUG_PATTERNS_${domain}.md`,
  ];

  for (const fileName of filesToCheck) {
    const filePath = join(projectDir, fileName);
    if (existsSync(filePath)) {
      validateProjectFile(filePath, fileName, domain);
    }
  }
}

// Run validation
console.log('Validating template files for generic content...\n');

validateTemplatesDirectory();

if (PROJECT_DIR && PROJECT_DOMAIN) {
  validateProjectFiles(PROJECT_DIR, PROJECT_DOMAIN);
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
  console.log(`Template validation failed with ${errors.length} error(s)`);
  process.exit(1);
}

console.log('Template validation passed - all templates are generic');
