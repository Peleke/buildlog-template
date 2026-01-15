# buildlog

Engineering notebook for AI-assisted development. Capture your work as publishable content.

## Install

```bash
pipx run copier copy gh:Peleke/buildlog-template .
```

That's it. You get:

```
buildlog/
├── BUILDLOG_SYSTEM.md    # How the system works
└── _TEMPLATE.md          # Copy this for each entry
```

Plus auto-injection into `CLAUDE.md` if you have one.

## Use

```bash
cp buildlog/_TEMPLATE.md buildlog/$(date +%Y-%m-%d)-my-feature.md
```

Fill it in as you work. Include the fuckups.

## Update

```bash
pipx run copier update
```

## Philosophy

1. **Write fast, not pretty** - Refrigerator to-do list energy
2. **Never delete mistakes** - Most valuable teaching content
3. **Include the journey** - Wrong turns > polished outcomes
4. **AI reflection required** - Meta-commentary on the collaboration

## Quality Bar

Each entry should be publishable as a $500+ tutorial (Envato Tuts+, Manning, O'Reilly).

## License

MIT
