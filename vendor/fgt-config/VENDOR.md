# Vendored fgt-config (FGT structure validator)

Snapshot of `BAM-BAM-BAM/fgt-config` at commit
`4b3fa8125deae1294701d53bcf1ead3038b2b274` (2026-07-07), minimal set the
validator's self-checks require: `FGT.md`, `METHODOLOGY_LOG.md`,
`templates/`, `scripts/`.

Why vendored instead of the checklist §3 clone-at-SHA pattern: fgt-config
is a private repo and CI's `GITHUB_TOKEN` is scoped to this repo only, so
an anonymous clone fails. Vendoring keeps the CI step blocking and
hermetic while preserving the pattern's intent (pin to a SHA as
supply-chain defense).

Consumed by `.github/workflows/verify.yml` (fgt-validation job):

    node vendor/fgt-config/scripts/validate-fgt.mjs --project .

Re-vendor (deliberate validator upgrade only):

    SHA=$(git -C ~/projects/fgt-config rev-parse HEAD)
    rm -rf vendor/fgt-config/{FGT.md,METHODOLOGY_LOG.md,templates,scripts}
    cp ~/projects/fgt-config/{FGT.md,METHODOLOGY_LOG.md} vendor/fgt-config/
    cp -r ~/projects/fgt-config/{templates,scripts} vendor/fgt-config/
    # update the SHA above and in verify.yml's step comment

Do not edit files here — canonical source is `~/projects/fgt-config/`.
