M3 (deficit computation) — file bundle
=======================================

HOW TO APPLY
Copy everything under backend/ and frontend/ in this zip into the matching
paths in your project (C:\Users\khaled\Documents\delestage\...), overwriting
the files that already exist there.

NEW files (create):
  backend/app/models/deficit.py
  backend/app/schemas/deficit.py
  backend/app/services/deficit.py
  backend/app/modules/deficit/__init__.py
  backend/app/modules/deficit/router.py
  backend/migrations/versions/0004_user_scope_consistency.py   <- from the
      grill-me fixes a few turns back; included here because 0005 depends
      on it (down_revision = "0004"). Skip it ONLY if you already created
      it yourself and it matches.
  backend/migrations/versions/0005_deficit_computation.py
  backend/tests/test_deficit_pure.py
  backend/tests/test_deficit_db.py
  backend/tests/test_deficit_api.py
  frontend/src/pages/LoginPage.tsx
  frontend/src/pages/Dashboard.tsx
  frontend/src/components/RequireAuth.tsx
  frontend/src/features/dispatcher/DeficitPlanner.tsx

MODIFIED files (overwrite):
  backend/app/models/enums.py
  backend/app/models/__init__.py
  backend/app/main.py
  backend/app/modules/auth/router.py     <- /auth prefix fixed to /api/auth
  backend/app/core/deps.py               <- tokenUrl updated to match
  backend/tests/conftest.py              <- added the async `adb` fixture
  backend/pyproject.toml                 <- pytest-asyncio session-scoped
                                             event loop settings added
  frontend/src/App.tsx                   <- now the routing root
  frontend/src/api/client.ts             <- deficit API + types added
  frontend/src/App.css                   <- login/badge/planner styles added

ONE FILE TO DELETE (from the earlier grill-me fixes, not part of this zip):
  backend/app/core/health.py
  — main.py included here no longer imports or registers it. If you never
  did this deletion, do it now or main.py's import will simply be a no-op
  reference to a file that's fine to keep, but the router registration was
  already removed from main.py, so the duplicate endpoint just becomes dead
  code rather than breaking anything.

AFTER COPYING
  cd backend
  python -m alembic upgrade head
  python -m pytest tests/ -v          # expect 63 passed

  cd ../frontend
  npm install                          # react-router-dom etc. already in
                                        # package.json from earlier, this
                                        # just makes sure it's installed
  npm run dev                          # or docker compose up --build

Demo login: ahmed / delestage123 (Dispatcher) — then use "Charger le
scénario de démo" in the deficit planner to reproduce the documented
300/350/250/100/0 MW example end to end.
