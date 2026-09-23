# National Intelligent Load Shedding Management Platform
### *Plateforme Nationale Intelligente de Gestion du Délestage Manuel Tournant*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6.x-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An intelligent, equity-aware decision-support platform designed for electrical transmission and distribution system operators (client context: **STEG - Société Tunisienne de l'Électricité et du Gaz**). The system optimizes, coordinates, executes, and evaluates manual rotating load shedding (*délestage tournant*) across national power grids in real time while guaranteeing critical infrastructure protection, fair regional rotation, and transparent public communication.

---

## 📌 Table of Contents

- [Overview & Objectives](#-overview--objectives)
- [System Architecture & Hierarchy](#-system-architecture--hierarchy)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Repository Structure](#-repository-structure)
- [Quickstart with Docker](#-quickstart-with-docker)
- [Local Development Setup](#-local-development-setup)
- [Pre-configured Demo Accounts](#-pre-configured-demo-accounts)
- [End-to-End Workflow Walkthrough](#-end-to-end-workflow-walkthrough)
- [API Reference](#-api-reference)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Roadmap & Future Evolutions](#-roadmap--future-evolutions)

---

## ⚡ Overview & Objectives

During severe supply-demand imbalances (unexpected generator outages, transmission line bottlenecks, or extreme heatwave peaks), electrical network integrity requires rapid, controlled reduction of demand to prevent cascading frequency collapse and total blackout.

This platform bridges high-level national dispatching strategies with ground-level distribution switching operations:

1. **Ensures Equity & Fair Rotation**: Balances load-shedding burdens across regions and administrative districts using historical rotation metrics and Gini index evaluation.
2. **Protects Critical Infrastructure**: Enforces strict priority classifications ($P_0$ to $P_5$); vital installations (hospitals, water pumping stations, military sites) are strictly non-délestable ($P_0$).
3. **Hard Duration Limits**: Strictly enforces configurable maximum outage durations (e.g., 45 minutes) with real-time 80% warnings and 100% threshold alarms.
4. **Closed-Loop Traceability**: Every order, validation, and physical switch event is cryptographically hash-chained in an immutable, tamper-proof audit trail.
5. **Citizen Transparency**: Dedicated public portal providing zone-level outage statuses, scheduled time slots, and estimated restoration times.

---

## 🏗️ System Architecture & Hierarchy

The platform models the multi-tier operational structure of the national electrical grid:

```mermaid
flowchart TD
    DN["National Dispatching (DN)<br/>Deficit Planning & National Orders"]
    
    CRCN["CRC Nord (67% Share)"]
    CRCS["CRC Sud (33% Share)"]
    
    BCC1["BCC Tunis (420 MW)"]
    BCC2["BCC Nabeul (360 MW)"]
    BCC3["BCC Sousse (240 MW)"]
    BCC4["BCC Bizerte (180 MW)"]
    BCC5["BCC Sfax (310 MW)"]
    BCC6["BCC Gabès (190 MW)"]
    BCC7["BCC Gafsa (130 MW)"]
    
    DN -->|Proportional Allocation| CRCN
    DN -->|Proportional Allocation| CRCS
    
    CRCN -->|Largest Remainder Quota| BCC1
    CRCN -->|Largest Remainder Quota| BCC2
    CRCN -->|Largest Remainder Quota| BCC3
    CRCN -->|Largest Remainder Quota| BCC4
    
    CRCS -->|Largest Remainder Quota| BCC5
    CRCS -->|Largest Remainder Quota| BCC6
    CRCS -->|Largest Remainder Quota| BCC7

    BCC1 -.-> F1["Substations & Medium Voltage Feeders (P0-P5)"]
    BCC5 -.-> F5["Substations & Medium Voltage Feeders (P0-P5)"]
```

### Allocation & Selection Algorithms
* **Deficit Formulation**:
  $$P_{\text{deficit}} = P_{\text{demand}} - P_{\text{generation}} - P_{\text{interconnections}} - P_{\text{margin}}$$
* **Proportional Regional Quota (Largest Remainder Method)**:
  Guarantees exact integer/fractional dispatching quotas such that:
  $$\sum P_{\text{BCC}} = P_{\text{CRC}} \quad \text{and} \quad \sum P_{\text{CRC}} = P_{\text{National}}$$
* **Feeder Selection & Rotation Engine**:
  Prioritizes feeders using a multi-criteria score incorporating feeder priority ($P_1 > P_2 > \dots > P_5$), cumulative historical shed time, rest-time since last shed event, and minimum switching penalties.

---

## 🚀 Key Features

### 1. Deficit Calculation & Planning (National Dispatcher)
* Compute deficits per 15 or 30-minute time slot.
* CSV bulk import for daily forecast profiles.
* Pre-built 300 MW demonstration scenarios for live evaluations.

### 2. Hierarchical Order Allocation & Dispatching
* Automated breakdown of national MW targets into CRC and BCC sub-quotas.
* Validation workflow: National Dispatcher initiates $\rightarrow$ Regional Control Centers review $\rightarrow$ BCC operators confirm.

### 3. BCC Operator Execution Console
* Automated candidate feeder recommendation based on constraint satisfaction.
* Manual override capabilities with mandatory operator justification logging.
* One-click execution confirmation with automated timers.

### 4. Real-Time Telemetry & Monitoring Dashboard
* Live telemetry engine streaming active shed MW vs. target quota.
* Gap analysis and feeder operational states (Closed, Opening Requested, Opened).
* 80% time warning (amber) and 100% maximum duration breach alarm (red).

### 5. SCADA & Grid Simulator
* Integrated test simulator to replay electrical load fluctuations, manual switch operations, and network disturbances without impacting physical SCADA assets.

### 6. Post-Event Analysis & KPI Evaluation
* Real-time calculation of **Energy Not Supplied (ENS / Énergie Non Distribuée)**:
  $$\text{ENS} = \int P_{\text{shed}}(t) \, dt \quad [\text{MWh}]$$
* Regional equity reporting via **Gini Coefficient** computation on cumulative outage minutes.
* Outage duration compliance audits.

### 7. Tamper-Proof Audit Trail
* Cryptographically linked SHA-256 hash-chain storing every operational action.
* PostgreSQL triggers prohibiting `UPDATE` or `DELETE` operations at the database engine level.

### 8. Public Citizen Transparency Portal & Map
* Searchable interface for citizens to check outage schedules by governorate, delegation, or postal code.
* Interactive map displaying affected sectors and estimated time to restoration.

---

## 💻 Tech Stack

| Layer | Technology | Description |
|---|---|---|
| **Backend Framework** | Python 3.12 / FastAPI | High-performance asynchronous REST API & WebSockets |
| **Database & ORM** | PostgreSQL 16 / SQLAlchemy 2.0 / Alembic | Relational integrity, asyncpg driver, automated migrations |
| **Frontend Framework** | React 19 / TypeScript / Vite | Single Page Application with component-driven architecture |
| **State & Data Fetching**| TanStack Query (React Query) / Axios | Optimized caching and server state synchronisation |
| **Real-Time Layer** | WebSockets + Live Telemetry Engine | Low-latency state push to operator dashboards |
| **Containerization** | Docker & Docker Compose | Uniform development and deployment environments |
| **Testing** | Pytest, pytest-asyncio, HTTPX | Comprehensive pure algorithm and database integration tests |

---

## 📂 Repository Structure

```
delestage/
├── docker-compose.yml          # Container configuration (Postgres, API, Web)
├── .env.example                # Sample environment variables
│
├── backend/
│   ├── app/
│   │   ├── core/               # App configuration, async DB engine, security, JWT
│   │   ├── engine/             # Core algorithms: allocator, rules, rotation logic
│   │   ├── models/             # SQLAlchemy ORM models (hierarchy, orders, audit, etc.)
│   │   ├── schemas/            # Pydantic validation and serialization models
│   │   ├── services/           # Business services (telemetry, deficit, execution, etc.)
│   │   ├── modules/            # Domain-driven API routers:
│   │   │   ├── auth/           # OAuth2 JWT login & token management
│   │   │   ├── deficit/        # Deficit calculation & scenario import
│   │   │   ├── orders/         # Order creation & multi-tier allocation
│   │   │   ├── execution/      # Feeder switching & rotation execution
│   │   │   ├── monitoring/     # Live telemetry metrics & active alarms
│   │   │   ├── simulator/      # Grid & SCADA event simulator
│   │   │   ├── evaluation/     # Post-mortem ENS & Gini equity analytics
│   │   │   ├── citizen/public/ # Unauthenticated citizen lookup endpoints
│   │   │   └── admin/          # Feeder attributes & platform parameter controls
│   │   └── main.py             # FastAPI entrypoint & router registration
│   ├── migrations/             # Alembic migration revisions (0001 to 0007)
│   ├── seed/                   # Deterministic national synthetic grid generator
│   ├── tests/                  # Pytest test suite (pure unit & DB integration tests)
│   ├── pyproject.toml          # Python package specifications and dependencies
│   └── Dockerfile              # Backend container build specification
│
└── frontend/
    ├── src/
    │   ├── api/                # Axios API client & typed backend interfaces
    │   ├── components/         # Reusable UI elements (Layout, RequireAuth, etc.)
    │   ├── contexts/           # Authentication state context
    │   ├── features/           # Modular operator feature interfaces:
    │   │   ├── dispatcher/     # Deficit planning & allocation tree
    │   │   ├── execution/      # BCC feeder switching & rotation views
    │   │   └── monitoring/     # Telemetry charts & feeder status table
    │   ├── pages/              # Role-specific application views:
    │   │   ├── LoginPage.tsx
    │   │   ├── DeficitPage.tsx
    │   │   ├── OrdersPage.tsx
    │   │   ├── OrderDetailPage.tsx
    │   │   ├── MonitoringPage.tsx
    │   │   ├── BccPage.tsx
    │   │   ├── SimulatorPage.tsx
    │   │   ├── EvaluationPage.tsx
    │   │   ├── CitizenPage.tsx
    │   │   └── AdminPage.tsx
    │   ├── App.tsx             # Routing & React Query provider
    │   └── main.tsx            # React application entrypoint
    ├── package.json            # Node.js dependencies & scripts
    └── Dockerfile              # Frontend container build specification
```

---

## 🐳 Quickstart with Docker

The fastest way to boot the complete ecosystem (Database, FastAPI, and React Frontend):

### 1. Clone the repository
```bash
git clone https://github.com/khaled214566/delestage.git
cd delestage
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```

### 3. Launch with Docker Compose
```bash
docker compose up --build
```

### 4. Run Migrations & Seed the Grid
In a separate terminal, apply database migrations and populate the synthetic grid:
```bash
# Run database migrations
docker compose exec api python -m alembic upgrade head

# Generate deterministic national grid topology (CRCs, BCCs, Substations, Feeders)
docker compose exec api python -m seed.generate
```

### 5. Access the Platform
* **Operator Frontend**: [http://localhost:5173](http://localhost:5173)
* **Citizen Transparency Portal**: [http://localhost:5173/citizen](http://localhost:5173/citizen)
* **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc API Explorer**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🛠️ Local Development Setup

If you prefer to run services natively without Docker:

### Prerequisites
* **Python 3.12+**
* **Node.js 20+** & **npm**
* **PostgreSQL 16+** running on `localhost:5432`

---

### Backend Setup

1. **Navigate to the backend directory and create a virtual environment**:
   ```bash
   cd backend
   python -m venv .venv
   
   # On Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Configure local environment**:
   Set `DATABASE_URL` in `.env` (or environment variables):
   ```env
   DATABASE_URL=postgresql+asyncpg://delestage:delestage_dev@localhost:5432/delestage
   DATABASE_URL_SYNC=postgresql://delestage:delestage_dev@localhost:5432/delestage
   SECRET_KEY=change-me-in-production-use-openssl-rand-hex-32
   CORS_ORIGINS=["http://localhost:5173"]
   ```

4. **Run migrations and populate seed data**:
   ```bash
   python -m alembic upgrade head
   python -m seed.generate
   ```

5. **Start the FastAPI development server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

### Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd ../frontend
   ```

2. **Install Node modules**:
   ```bash
   npm install
   ```

3. **Start the Vite development server**:
   ```bash
   npm run dev
   ```
   The UI will be accessible at `http://localhost:5173`.

---

## 👥 Pre-configured Demo Accounts

All pre-seeded demo accounts share the password: `delestage123`

| Username | Password | Role | Operational Scope | Primary Capabilities |
|---|---|---|---|---|
| `admin` | `delestage123` | **ADMIN** | National | Manage users, adjust system parameters, toggle feeder sheddability |
| `ahmed` | `delestage123` | **DISPATCHER** | National | Compute national deficit, generate shedding orders, run simulations |
| `crc_n` | `delestage123` | **CRC_OPERATOR** | Regional (CRC Nord) | Inspect regional quotas, monitor BCC allocation distribution |
| `sana` | `delestage123` | **BCC_OPERATOR** | District (BCC Tunis) | Validate candidate feeder lists, confirm physical cutoffs, execute rotations |
| *Public* | *None* | **CITIZEN** | National | Open lookup by zone, view restoration estimates & outage calendar |

---

## 🔄 End-to-End Workflow Walkthrough

Experience a complete operational cycle in 5 steps:

```
[1. Forecast & Deficit] ──> [2. Hierarchical Order] ──> [3. BCC Feeder Selection]
                                                                  │
[5. Evaluation & ENS]   <── [4. Real-time Telemetry & Rotation] <─┘
```

1. **Calculate Deficit**:
   * Log in as **Dispatcher** (`ahmed`).
   * Navigate to **Deficit Planner**. Click **"Charger le scénario de démo"** to load a standard 300 MW peak deficit.
2. **Issue Shedding Order**:
   * Click **"Créer l'ordre de délestage"**.
   * The backend's largest remainder allocator computes regional shares:
     * **CRC Nord (67%)**: ~200 MW distributed across Tunis, Nabeul, Sousse, Bizerte.
     * **CRC Sud (33%)**: ~100 MW distributed across Sfax, Gabès, Gafsa.
3. **Execute & Confirm at BCC**:
   * Log in as BCC Operator **Sana** (`sana`) or switch to the **BCC Execution** screen.
   * Review automatically suggested feeders (ensuring $P_0$ lines are excluded and rotation rest-times are respected).
   * Confirm the opening command to trigger execution status.
4. **Monitor Real-Time Alarms & Telemetry**:
   * Access the **Live Monitoring** dashboard.
   * Observe active shed load vs. target deficit and live countdown timers.
   * If an outage approaches 80% of maximum duration (36 min), an amber warning sounds. At 100% (45 min), a critical alarm instructs an immediate feeder rotation.
5. **Evaluate Impact**:
   * Open the **Post-Mortem Evaluation** page.
   * Inspect computed **Energy Not Supplied (MWh)** and the **Gini equity index** showing regional fairness distribution.

---

## 📡 API Reference

The backend exposes a fully typed REST and WebSocket interface:

| Prefix | Description | Auth Required |
|---|---|:---:|
| `POST /api/auth/token` | OAuth2 password flow login (returns JWT Bearer token) | ❌ |
| `GET /api/health` | System health check, DB connection state & sheddable MW count | ❌ |
| `GET /api/public/schedule` | Public citizen search for power outage schedules by zone | ❌ |
| `GET/POST /api/deficit/slots` | Slot-based deficit calculation and CSV import | ✅ (Dispatcher) |
| `GET/POST /api/orders` | Order creation, listing, and hierarchical allocation tree | ✅ (Dispatcher/CRC) |
| `GET/POST /api/execution/*` | Feeder switching commands and BCC execution logging | ✅ (BCC Operator) |
| `GET /api/rotation/candidates` | Automated candidate feeder selection & equity scoring | ✅ (BCC Operator) |
| `GET /api/monitoring/live` | Real-time active shed power, gap analysis, and active alarms | ✅ |
| `POST /api/simulator/step` | Advance grid simulator clock and inject load disturbances | ✅ (Dispatcher/Admin) |
| `GET /api/evaluation/kpis` | Post-event audit metrics (ENS in MWh, Gini fairness coefficient) | ✅ |
| `GET /api/admin/audit-log` | Verification of cryptographically hash-chained audit records | ✅ (Admin) |

---

## 🧪 Testing & Quality Assurance

The codebase includes an automated test suite verifying business invariants, allocation arithmetic, and database integrity.

```bash
# Run all tests inside backend directory
cd backend
pytest tests/ -v
```

### Test Highlights:
* `test_allocation_pure.py`: Verifies the Largest Remainder algorithm guarantees $\sum P_{\text{sub}} = P_{\text{target}}$ without rounding drift.
* `test_deficit_pure.py`: Tests power balance deficit equations under varied generation/import edge cases.
* `test_rotation_pure.py`: Ensures $P_0$ infrastructure is never selected and maximum outage duration limits trigger rotation warnings.
* `test_schema_db.py`: Validates PostgreSQL foreign key constraints and the immutable audit log trigger.

---

## 🗺️ Roadmap & Future Evolutions

- [ ] **SCADA / EMS Adapter Layer**: Integration with industrial protocols (ICCP / TASE.2, OPC UA, IEC 60870-5-104) to replace manual BCC entry.
- [ ] **AI-Powered Short-Term Load Forecasting**: Integration of weather, temperature, and historical consumption machine learning models.
- [ ] **Decentralized Renewable Integration**: Accounting for distributed rooftop PV and wind variability in real-time feeder net load.
- [ ] **Demand-Side Response (DSR)**: Automated commercial and industrial load shedding contracts before residential feeder tripping.
- [ ] **Mobile Citizen Application**: Dedicated iOS/Android mobile apps with push notification alerts before scheduled rotations.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Developed for Track 2: **National Intelligent Load Shedding Management Platform** (STEG).
