# Repository guidance

## Start here

- Product: 知营, a Chinese, multi-tenant education-institution operations system. One person may hold several jobs; institutions can also employ many people.
- Current source baseline: `0.4.0-rc2`, database head `0006_deepseek`.
- Read `README.md`, `docs/GPT_HANDOFF.txt` and `UPGRADE_0.4.0-rc2.txt` before changing business behavior.
- Directories: `backend/app` (FastAPI), `frontend/src` (React/TypeScript), `publisher` (isolated browser/MCP gateway), `backend/migrations` (Alembic), `docs` (contracts and evidence).

## Business and permission boundaries

- Enforce institution isolation and per-operation role/ownership checks in APIs, workers, exports, attachments and events. Platform admin status alone does not grant institution business access.
- Positions: owner, admissions, teacher, scheduler, academic_admin, revenue_viewer, finance, content_ops; users can combine positions. Teachers and admissions retain their scoped data when combined with unrelated roles.
- New registrations directly capture amount, discount and purchased lessons. Historical course packages remain retained; do not reintroduce course-package dependency.
- Teacher feedback is a completion KPI per lesson, not a content editor or automatic parent messaging feature.
- Financial amounts are integer fen. Payments, refunds, lesson accounting and commissions remain deterministic backend services. AI produces drafts or explanations and cannot bypass validation or approval.
- Preserve append-only journals, historical membership/attendance snapshots, idempotency and refund snapshots.
- Web/WeCom consultation, social comment and private-message auto replies remain paused. Digital-human live streaming is not integrated and its navigation is hidden.

## Models and publishing

- DeepSeek is the selectable text provider. Aliyun remains responsible for image/video/TTS generation, embeddings, visual scoring and independent review.
- Owner manages integration credentials and AI settings. Keep credentials tenant-encrypted and never return plaintext stored keys.
- Funding is explicit (platform or institution BYOK); do not fall back to another key when quota or credentials are missing.
- Queued model tasks preserve provider/model/rate snapshots. Unknown paid results retain reservations and must not be blindly resubmitted.
- Matrix plans freeze explicit account targets; accounts have separate credentials and publishing locks. A publish requires a verifiable external ID and URL before reporting success.
- Blind prediction uses the final content version and never reads that work's performance. Preserve immutable predictions and independent rule review.
- Real external calls and publishing require the user's authorized integration scope, configured credentials and relevant switches. Mocks, demo records and protocol tests are not real account acceptance.

## Local development and checks

- Python >=3.12, Node 24; production Docker pins its runtimes. Use checked-in dependency locks.
- `python scripts/configure.py` creates a local secret without printing it and preserves existing configuration.
- Install with `python -m pip install -r backend/requirements.lock`, `python -m pip install --no-deps -e ./backend`, and `npm ci --prefix frontend` in the selected virtual environment.
- `python -m pytest backend/tests/test_deepseek.py -q` tests the provider with a mocked HTTP transport.
- `python -m pytest backend/tests -q` runs backend regression on isolated temporary databases.
- `npm run build --prefix frontend` checks TypeScript and builds the frontend.
- Windows browser tests: `./scripts/test-browser.ps1 -Grep DeepSeek` creates isolated demo data. Do not run arbitrary browser fixtures against a user's working database.
- `node frontend/test-deepseek-migration.mjs` tests PostgreSQL syntax and isolation in PGlite WASM; it is not native PostgreSQL acceptance.
- Production migration uses Alembic and migration credentials. Never run the full offline schema SQL over an existing business database.

## Evidence and secrets

- See `docs/release-0.4.0-rc2.json` and `docs/deepseek-acceptance.json`. Reports have their original timestamps; state what this run actually verified.
- Recorded baseline: backend 172 passed; provider 16 passed; provider browser 3 passed. Full browser suite also records two old tests expecting the hidden digital-human menu and three demo-specific skipped cases.
- Real provider/account tests, native PostgreSQL and Docker/cloud acceptance remain separate gates. Do not mark them passed without evidence.
- Never commit `.env*` except the empty example templates, `.local`, user uploads, databases, cookies, private keys, logs, test traces or dependency directories.
- Keep vendor revisions and third-party notices; don't overwrite or relicense upstream components as project-owned code.
