# buildlog

Engineering notebook for AI-assisted development. Capture your work as publishable content. Include the fuckups.

This is the npm wrapper for [buildlog](https://github.com/Peleke/buildlog-template). It lets you use buildlog via `npx`/`bunx` in TypeScript and JavaScript projects.

## Quick start

```bash
npx @peleke.s/buildlog init
npx @peleke.s/buildlog new my-feature
npx @peleke.s/buildlog commit -m "feat: add auth"
npx @peleke.s/buildlog skills
npx @peleke.s/buildlog gauntlet loop src/
```

## Install

```bash
# One-off (no install needed)
npx @peleke.s/buildlog init

# Pin as dev dependency
npm install -D buildlog
# or
bun add -D buildlog
```

## Requirements

Python 3.10+ must be available. The npm package is a thin wrapper that invokes the Python CLI.

If `buildlog` isn't already installed, the wrapper will try `uvx buildlog` (auto-downloads from PyPI) or `python -m buildlog` as fallbacks.

To install the Python CLI directly:

```bash
pip install buildlog
# or
uv tool install buildlog
```

## How it works

The npm package ships a single bin shim that:

1. Looks for `buildlog` on PATH
2. Falls back to `uvx buildlog` (zero-install via uv)
3. Falls back to `python3 -m buildlog`
4. Passes through all arguments and stdio transparently

Every command works identically to the Python CLI. See the [full documentation](https://github.com/Peleke/buildlog-template) for details.

## package.json scripts

```json
{
  "scripts": {
    "gauntlet": "buildlog gauntlet loop src/",
    "buildlog:commit": "buildlog commit"
  }
}
```

## License

MIT
