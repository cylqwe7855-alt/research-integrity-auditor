#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');

const skillName = 'paper-fraud-auditor';
const packageRoot = path.resolve(__dirname, '..');

function usage() {
  console.log(`Research Integrity Auditor skill installer

Usage:
  research-integrity-auditor [options]

Options:
  --project          Install into ./.claude/skills/${skillName}
  --skills-dir DIR   Install into DIR/${skillName}
  --target DIR       Install directly into DIR
  --help             Show this help

Default target:
  ~/.claude/skills/${skillName}`);
}

function parseArgs(argv) {
  const options = { project: false, skillsDir: null, target: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--project') {
      options.project = true;
    } else if (arg === '--skills-dir') {
      options.skillsDir = argv[++i];
    } else if (arg === '--target') {
      options.target = argv[++i];
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }
  return options;
}

function targetDir(options) {
  if (options.target) {
    return path.resolve(options.target);
  }
  if (options.project) {
    return path.resolve(process.cwd(), '.claude', 'skills', skillName);
  }
  const skillsDir = options.skillsDir
    ? path.resolve(options.skillsDir)
    : path.join(os.homedir(), '.claude', 'skills');
  return path.join(skillsDir, skillName);
}

function copyItem(relativePath, target) {
  const source = path.join(packageRoot, relativePath);
  if (!fs.existsSync(source)) {
    return;
  }
  const destination = path.join(target, relativePath);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.cpSync(source, destination, {
    recursive: true,
    force: true,
    errorOnExist: false,
    dereference: false,
    filter: (item) => !item.includes(`${path.sep}__pycache__${path.sep}`) && !item.endsWith('.pyc'),
  });
}

function install(target) {
  fs.mkdirSync(target, { recursive: true });
  for (const item of ['SKILL.md', 'agents', 'references', 'scripts', 'README.md', 'LICENSE']) {
    copyItem(item, target);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    usage();
    return;
  }
  const target = targetDir(options);
  install(target);
  console.log(`Installed ${skillName} to ${target}`);
  console.log('Restart Claude Code if the skill does not appear immediately.');
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
