# 5-Minute Platform Demonstration Plan & Script
### *National Intelligent Load Shedding Management Platform (STEG)*

---

## ⏱️ Video Structure & Timing Overview

| Timestamp | Duration | Section | Screen / URL | Core Focus |
|---|:---:|---|---|---|
| **0:00 – 0:40** | 40s | **1. Introduction & Context** | Login / Dashboard | The grid challenge, mission, and architecture overview |
| **0:40 – 1:30** | 50s | **2. Deficit Planning & Formulation** | `Calcul du déficit` (`/`) | Load demo scenario (300 MW), deficit formula, order creation |
| **1:30 – 2:30** | 60s | **3. Hierarchical Order Allocation** | `Ordres de délestage` (`/orders/:id`) | National → CRC → BCC → Départs, Largest Remainder algorithm, $P_0$ protection |
| **2:30 – 3:20** | 50s | **4. BCC Execution & Feeder Rotation** | `Postes de délestage` (`/bcc`) | Local dispatch, multi-criteria recommendation engine, execution |
| **3:20 – 4:10** | 50s | **5. Live Telemetry & Post-Event KPIs** | `Monitoring` & `Indicateurs` | Real-time MW tracking, 80%/100% duration alarms, ENS & Gini equity index |
| **4:10 – 4:45** | 35s | **6. Citizen Transparency & Audit Trail** | `Portail Citoyen` & `Administration` | Public outage map/search, SHA-256 immutable cryptographic audit log |
| **4:45 – 5:00** | 15s | **7. Conclusion** | Overview / Summary | High-level wrap-up |

---

## 📋 Pre-Recording Setup Checklist

1. **Browser Setup**: Open Google Chrome / Edge at 100% zoom with clean bookmarks.
2. **Pre-open Tabs** (for seamless, instant tab switches):
   - **Tab 1**: Operator UI (`http://localhost:5173`) logged in as **Ahmed** (Dispatcher: `ahmed` / `delestage123`).
   - **Tab 2**: Operator UI logged in as **Sana** (BCC Operator: `sana` / `delestage123`) on `/bcc`.
   - **Tab 3**: Public Citizen Portal (`http://localhost:5173/citizen`).
   - **Tab 4**: Admin Audit Trail (`http://localhost:5173/admin`).
3. **Resolution & Audio**: 1080p (1920×1080), microphone tested, operating system notifications silenced.

---

## 🎙️ Word-for-Word Video Script

---

### [00:00 – 00:40] Part 1: Introduction & The Grid Challenge

> **🖥️ [Screen Action]**: *Start on the top navigation bar showing the STEG logo and platform title ("Plateforme Nationale de Conduite du Délestage"). Slowly hover over the sidebar navigation items.*

**🗣️ [Voiceover]**:
> "Welcome. During extreme summer heatwaves or sudden generation loss, electrical power grids face severe supply-demand deficits that risk cascading frequency collapse and nationwide blackouts.
> 
> To prevent this, grid operators must perform **manual rotating load shedding**. Historically, this process was manual, prone to regional imbalances, and lacked operational visibility.
> 
> This platform—designed for the Tunisian national grid operator STEG—is an **intelligent, equity-aware decision-support system**. It automates the entire lifecycle: from national deficit forecasting and hierarchical quota distribution down to medium-voltage feeder switching, real-time telemetry, and public transparency."

---

### [00:40 – 01:30] Part 2: Deficit Planning & Formulation

> **🖥️ [Screen Action]**: *Click on **"Calcul du déficit"** in the sidebar. Point the cursor to the mode selection (Planifié J-1 / Temps Réel J). Click the button **"Charger le scénario de démo (300 MW)"**.*

**🗣️ [Voiceover]**:
> "Let’s start in the role of the **National Dispatcher**.
> 
> Under **Calcul du déficit**, the dispatcher plans emergency shedding across discrete 15- or 30-minute time slots. The system computes the required shedding target using the physical balance equation:
> 
> $$\text{Deficit} = \text{Demand} - \text{Generation} - \text{Interconnections} - \text{Operating Margin}$$
> 
> Operators can upload daily forecast CSV files or load pre-configured emergency scenarios. Here, we load our 300-megawatt peak deficit scenario.
> 
> Every slot is clearly itemized with its generation shortfall. Once reviewed, the dispatcher clicks **'Créer l'ordre de délestage'** to initiate the national shedding order."

---

### [01:30 – 02:30] Part 3: Hierarchical Order Allocation & Priority Protection

> **🖥️ [Screen Action]**: *Navigate to **"Ordres de délestage"**, open the newly created order, and expand the **Allocation Tree** (click "Tout déplier" or expand CRC Nord → BCC1).*

**🗣️ [Voiceover]**:
> "Here in the **Order Detail** screen, our mathematical allocation engine distributes the national target through the grid’s operational hierarchy:
> 
> - First, down to the Regional Control Centers: **CRC Nord** receives 67% and **CRC Sud** 33%, proportional to their regional baseload.
> - Next, down to the 7 district **BCCs** using the **Largest Remainder algorithm (Hamilton's method)**, guaranteeing exact megawatt allocations without rounding errors.
> - Finally, down to the individual **medium-voltage feeders (Départs)**.
> 
> Notice the strict priority tagging: vital infrastructure like hospitals, water pumping stations, and security installations are classified as **$P_0$** and are strictly protected from shedding. Sheddable feeders are prioritized from **$P_1$ to $P_5$**.
> 
> The dispatcher can review the exact achieved MW against the quota, inspect each assigned feeder, or manually add and remove specific feeders when field constraints dictate."

---

### [02:30 – 03:20] Part 4: BCC Operator Execution & Automated Feeder Rotation

> **🖥️ [Screen Action]**: *Switch to Tab 2 or click **"Postes de délestage (BCC)"**. Select **BCC1 - Tunis**. Highlight the recommended candidate feeders and click to confirm feeder opening/switching.*

**🗣️ [Voiceover]**:
> "Now let's switch hats to the **BCC District Operator** in Tunis.
> 
> Local operators don’t have to manually calculate which lines to trip. The platform features an **automated Feeder Selection Engine**. 
> 
> The algorithm evaluates three core criteria:
> 1. Feeder priority—shedding non-critical industrial or commercial lines ($P_5$) before residential lines.
> 2. Cumulative outage history—ensuring neighbourhoods that were shed earlier in the week are not repeatedly targeted.
> 3. Minimum rest-time—guaranteeing feeders have had sufficient cool-down time before being shed again.
> 
> The operator simply reviews the automated recommendations, verifies the MW contribution matches their BCC quota, and confirms the switching order with a single click."

---

### [03:20 – 04:10] Part 5: Real-Time Telemetry, Duration Alarms & Equity Evaluation

> **🖥️ [Screen Action]**: *Click on **"Monitoring"** in the sidebar. Show the live gauge/telemetry stream and duration countdown timers. Then click on **"Indicateurs & Performance"** (`/evaluation`).*

**🗣️ [Voiceover]**:
> "Once switches are opened, the **Live Monitoring Dashboard** streams real-time SCADA telemetry.
> 
> Operators track active shed megawatts against target quotas in real time. Crucially, the platform enforces a **hard 45-minute maximum outage ceiling**:
> - At 80% duration—around 36 minutes—an amber warning notifies the operator to prepare a rotation.
> - At 100%, an alarm sounds, requiring an immediate switchover to a fresh feeder to restore power to affected citizens.
> 
> When the event concludes, we navigate to **Indicateurs & Performance**. Here, the platform calculates **Energy Not Supplied (ENS in MWh)** and evaluates regional fairness through a computed **Gini Equity Index**, proving that the burden was shared equitably across all governorates."

---

### [04:10 – 04:45] Part 6: Public Citizen Transparency & Immutable Audit Trail

> **🖥️ [Screen Action]**: *Switch to Tab 3 (**Portail public citoyen**), type a delegation or click a zone on the map. Then switch to Tab 4 (**Administration**), scroll down to the Cryptographic Audit Log.*

**🗣️ [Voiceover]**:
> "Transparency and accountability are central to this platform:
> 
> For the public, the **Citizen Transparency Portal** offers an interactive map and search tool. Citizens can look up their governorate or delegation to check real-time power status, scheduled rotation slots, and estimated restoration times.
> 
> For institutional governance, the **Administration** console features an **immutable, cryptographically linked SHA-256 audit trail**. Every single login, allocation calculation, override, and switch command is permanently hash-chained, preventing retrospective tampering."

---

### [04:45 – 05:00] Part 7: Conclusion & Wrap-Up

> **🖥️ [Screen Action]**: *Return to the main overview or order detail screen, cursor steady.*

**🗣️ [Voiceover]**:
> "In summary, this platform transforms emergency load shedding from a chaotic, manual procedure into a coordinated, algorithmically optimized, and equitable operation. It protects national grid stability, safeguards critical infrastructure, and keeps citizens informed.
> 
> Thank you for watching."

---

## 💡 Practical Recording Advice

- **Cursor Discipline**: Keep your cursor still when speaking. Only move it deliberately to point to the feature being described.
- **Pacing**: Aim for an average delivery speed of ~130 words per minute. Leave a brief 1-second silence before and after switching tabs to facilitate video editing.
- **Non-destructive Mistakes**: If you stumble on a phrase, pause for 2 seconds and re-say that specific sentence cleanly. You can cut the dead space effortlessly during video editing.
