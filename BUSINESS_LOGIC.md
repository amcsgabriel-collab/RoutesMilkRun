# RoutesMilkRun - Business Logic & Solver Rules Documentation

## Executive Summary

This document explains the critical business logic and rules that govern how RoutesMilkRun optimizes delivery routes. It covers the fundamental assumptions, constraints, and algorithms used by the solver.

**Target Audience**: Business analysts, consultants, logistics managers, and non-technical stakeholders who need to understand what the system does and why it makes certain decisions.

---

## Table of Contents
1. [Fundamental Concepts](#fundamental-concepts)
2. [Route Structure & Organization](#route-structure--organization)
3. [Route Ordering & Stop Sequencing](#route-ordering--stop-sequencing)
4. [Route Combination Rules](#route-combination-rules)
5. [Roundtrip Formation](#roundtrip-formation)
6. [Tariff Assignment Logic](#tariff-assignment-logic)
7. [Hub Assignment Strategy](#hub-assignment-strategy)
8. [Transport Concepts (MR vs FTL)](#transport-concepts-mr-vs-ftl)
9. [Solver Optimization Objectives](#solver-optimization-objectives)
10. [Constraints & Limitations](#constraints--limitations)

---

## Fundamental Concepts

### What is a "Route"?

In RoutesMilkRun, a **route** is a complete journey from the distribution center (plant) to a group of shippers and back.

**Key Properties**:
- **Flow Direction**: Either "Parts" (outbound: plant → shippers) or "Empties" (return: shippers → plant)
- **Transport Concept**: 
  - **MR (Milk Run)**: Multiple stops (2-4 shippers per vehicle)
  - **FTL (Full Truck Load)**: Single dedicated delivery
- **Vehicle Assignment**: Every route uses exactly one vehicle type
- **Carrier Assignment**: All shippers in a route must belong to the same carrier group
- **Frequency**: How many times per week the route operates (1-5 times typical)

### What is a "Trip"?

A **trip** is a pairing of outbound and return journeys.

**Trip Types**:
- **Roundtrip** (R): Both parts and empties (e.g., leave Monday with goods, return Monday empty)
- **Single Trip** (S): Only parts OR empties (e.g., goods only, no return)
- **Not Determined** (N/D): Placeholder (should not appear in final solution)

**Roundtrip Example**:
```
Parts Route: Plant → Shipper A → Shipper B → Plant (Monday)
Empties Route: Plant → Shipper A → Shipper B → Plant (Monday return)
Combined Trip: Operates Monday morning out, Monday evening/next morning back
```

### Flow Directions

RoutesMilkRun always tracks **two separate flows**:

1. **Parts Flow** (Outbound)
   - Direction: Plant → Shippers
   - Purpose: Deliver goods TO customers
   - Demand Unit: Weight, Volume, Loading Meters
   - Frequency: X times per week

2. **Empties Flow** (Return)
   - Direction: Shippers → Plant
   - Purpose: Retrieve empty pallets/containers
   - Demand Unit: Weight, Volume, Loading Meters
   - Frequency: X times per week
   - **Key Rule**: Empties frequency = Parts frequency (for roundtrips)

**Why Two Flows?**
- Realistic milk runs include return legs
- Enables cost calculation (return cost is cheaper than outbound)
- Allows "hub" consolidation at intermediate points

---

## Route Structure & Organization

### Direct Routes (Milk Run - MR)

A direct route connects the plant directly to 1-4 shippers **without intermediate consolidation**.

**Rules**:
- **Minimum stops**: 1 (single shipper = FTL)
- **Maximum stops**: 4 shippers (business constraint)
- **Carrier constraint**: All shippers must share same carrier group
- **Vehicle constraint**: Assigned to one specific vehicle type (truck size)
- **Stops order**: Optimized using nearest-neighbor algorithm (see below)

**Cost Model**:
```
Total Cost = Base Cost + (Stop Count - 1) × Stop Cost + Deviation Adjustment

Example:
Base Cost: €800 per truck
Stop Cost: €120 per additional stop
3 stops in route: €800 + (3-1) × €120 = €1,040
```

### Hub-Based Routes (Two-Leg Model)

Hub consolidation uses a **two-leg approach**:

1. **First-Leg Route** (Shipper → Hub)
   - Carrier: LTL (Less Than Truck Load)
   - Type: Individual shipments
   - Each shipper gets own first-leg (no stops)
   - Frequency: Matches shipper demand frequency

2. **Linehaul Route** (Hub → Plant)
   - Carrier: FTL or LTL depending on volume
   - Type: Consolidated shipment from hub
   - Multiple first-leg shipments combined
   - Frequency: Matches hub consolidation pattern

**When Hub Makes Sense**:
- Shipper too small for direct route
- Shipper scattered geographically
- Shipper on different carrier network
- Multiple small shippers serve single hub

---

## Route Ordering & Stop Sequencing

### Nearest-Neighbor Greedy Algorithm

When a route pattern is created, **shippers are automatically ordered** using a greedy nearest-neighbor approach:

**Algorithm**:
1. Start from the shipper **farthest from the plant**
2. From current location, visit nearest unvisited shipper
3. After all shippers, return to plant
4. Record distance for each leg

**Why Farthest First?**
- Minimizes backtracking
- Reduces total route distance/time
- Improves vehicle utilization

**Example**:
```
Plant at (0, 0)
Shippers:
  - A at (100, 100) - distance 141 km
  - B at (50, 50)   - distance 71 km
  - C at (60, 40)   - distance 72 km

Chosen start: A (farthest = 141 km)
From A, nearest neighbor: C (72 km from A)
From C, nearest neighbor: B (50 km from C)
From B, return to plant

Final sequence: A → C → B → Plant
```

### Deviation Calculation

**Deviation** measures how much longer the route is compared to direct transport.

```
Deviation (km) = (Total Distance - Direct Distance) / (Stops - 1)

Direct Distance = Shipper A coordinates to Plant
Total Distance = A → B → C → ... → Plant

Example:
Direct: A to Plant = 141 km
Total: A → C → B → Plant = 141 + 72 + 50 + 72 = 335 km
Deviation = (335 - 141) / 2 = 97 km per stop
```

**Deviation Brackets** (used for tariff selection):
- **Small (0-30 km)**: Local urban routes
- **Low (30-50 km)**: Regional routes
- **Medium (50-100 km)**: Extended regional
- **High (100-150 km)**: Long distance
- **Very High (>150 km)**: Very long routes

**Business Impact**:
- Higher deviation → Higher cost per stop
- Impacts carrier tariff selection
- Helps identify inefficient route combinations

---

## Route Combination Rules

### Shipper Allocation Percentages

A shipper can be **split across multiple routes** with percentage allocations.

**Example Scenario**:
```
Shipper: Amazon
Total parts demand: 1,000 kg/week
Split across:
  - Route A: 60% (600 kg)
  - Route B: 40% (400 kg)

Business reason: Amazon too large for one truck, needs multiple carriers
```

**Allocation Rule**:
```
Sum of allocations per shipper per flow must = 100%

✓ Valid:   Route1=60% + Route2=40% = 100%
✗ Invalid: Route1=50% + Route2=50% = 100% ← Over-allocated if frequency differs
```

**Validation** (`verify_total_volume()`):
- Checks all shippers have 100% allocation
- Checks across both parts and empties flows separately
- Reports any misallocations before solver runs

### Same Shipper, Different Carriers

**Rule**: A shipper can ONLY appear once per route.

**But**: Same shipper can appear in multiple routes served by different carriers.

**Example**:
```
Shipper: MediaMarkt
Route A (DHL): 60% of demand
Route B (GLS): 40% of demand

Valid because:
- Different carriers
- Total = 100%
- Each route has shipper only once
```

### Carrier Group Homogeneity

**Rule**: All shippers in a single direct route must belong to the **same carrier group**.

**Definition**: Carrier Group = Business unit of carrier (e.g., "DHL_Nordic", "GLS_France")

**Why?**
- Simplifies logistics (one pickup point, one billing)
- Maintains network consistency
- Reduces operational complexity

**Example**:
```
✓ Valid:   DHL Nordic + DHL Nordic + DHL Nordic = Same group
✗ Invalid: DHL Nordic + GLS France = Different groups

Exception: Multiple carriers in SAME group can mix
✓ Valid: DHL_Nordic_Truck + DHL_Nordic_Van = Same group
```

---

## Roundtrip Formation

### Core Rule: Paired Parts + Empties

A **roundtrip** requires:
1. Exactly 1 parts route
2. Exactly 1 empties route
3. **Same shippers in both legs** (important!)
4. **Same frequency** (parts frequency = empties frequency)

**Example**:
```
Parts Route: Plant → A → B → C → Plant (3x/week)
Empties Route: Plant → A → B → C → Plant (3x/week)
Frequency: Both 3x/week

Creates Roundtrip with frequency = 3
```

### Why Roundtrips Save Costs

**Cost Calculation**:

For FTL (truck-based) tariffs:
```
Single Trip Cost = Base + (Stops - 1) × Stop Cost
Roundtrip Cost = RoundtripBase / 2 + (Stops - 1) × Stop Cost

Saving = (Base × 2) - RoundtripBase

Example:
Base: €800, RoundtripBase: €1,200, StopCost: €120
Single Trip (2 stops): €800 + €120 = €920
Roundtrip (2 stops each direction): €1,200/2 + €120 = €720
Saving per week: €200
Annual saving: €10,400 (52 weeks)
```

### Frequency Chunking

**Rule**: Break high frequencies into smaller chunks.

**Why?**
- Vehicle capacity limits
- Operational flexibility
- Realistic weekly schedules

**Algorithm**:
```
Max chunk per roundtrip = 5 journeys/week

Input: Roundtrip pair with frequency = 12x/week

Output:
  Roundtrip 1: frequency = 5
  Roundtrip 2: frequency = 5
  Roundtrip 3: frequency = 2
```

**Business Implication**: 12x/week delivery becomes 3 separate roundtrips to stay realistic.

### Validation: Matching Parts & Empties

**Critical Check** (in `TripRepository`):

Each roundtrip ID must have:
- ✓ Exactly 1 parts route entry
- ✓ Exactly 1 empties route entry
- ✓ Same roundtrip identifier

**Error Example**:
```
Roundtrip ID "RT001":
  Parts Route: "Route_A"
  Empties Route: "Route_A"
  Status: ✓ Valid

Roundtrip ID "RT002":
  Parts Route: "Route_B"
  Empties Route: "Route_B"
  Empties Route: "Route_C"  ← ERROR: 2 empties routes!
  Status: ✗ Invalid
```

---

## Tariff Assignment Logic

### Two Costing Models

RoutesMilkRun supports **two distinct pricing models**:

#### 1. Truck-Based Costing (Direct Routes)

Used for FTL and MR direct routes.

**Formula**:
```
Cost = Base Cost + (Stop Count - 1) × Stop Cost Multiplier

Stop Cost Multiplier = f(Deviation)

If Deviation > 150 km:
  Multiplier = Stop Cost × Deviation (km)
Else:
  Multiplier = Stop Cost × 1
```

**Variables**:
- **Base Cost**: Fixed cost per truck departure (€)
- **Stop Cost**: Cost per additional stop (€)
- **Roundtrip Base Cost**: Lower base for return routes (€)
- **Deviation**: Extra km beyond direct route

**Example**:
```
Base: €800, Stop: €50/km, Deviation: 120 km, Stops: 3

Cost = €800 + (3-1) × €50 × 1 = €900
(Deviation 120 < 150, so no km multiplier)

If Deviation was 200 km:
Cost = €800 + (3-1) × €50 × 200 = €20,800 (with multiplier)
```

#### 2. Weight-Based Costing (Hub Routes)

Used for LTL (Less Than Truckload) hub first-leg routes.

**Formula**:
```
Cost = f(Chargeable Weight, Tariff Bracket)

Chargeable Weight = MAX(Actual Weight, Volume × 250)
                    ↑
                    Conversion: 1 m³ = 250 kg equivalent

Select Tariff = Lookup(Carrier, Weight Bracket, Origin, Destination)
Cost = Tariff Price × Chargeable Weight
```

**Weight Brackets** (LTL):
```
≤200 kg    - Parcel rates
≤600 kg    - Small package
≤1,000 kg  - Medium package
≤2,000 kg  - Large package
≤4,000 kg  - Pallet level
≤10,000 kg - Multi-pallet
≤15,000 kg - Near-FTL
≤20,000 kg - Pre-FTL
≤25,000 kg - Full capacity
>25,000 kg - Over-weight surcharge
```

**Weight Brackets (Hub - Consolidated)**:
```
≤3,000 kg   - Hub rate 1
≤5,000 kg   - Hub rate 2
≤7,000 kg   - Hub rate 3
≤10,000 kg  - Hub rate 4
≤15,000 kg  - Hub rate 5
≤20,000 kg  - Hub rate 6
>20,000 kg  - Hub rate 7
```

**Hub brackets are CHEAPER** than LTL brackets for same weight (consolidation discount).

### Tariff Lookup Hierarchy

The system searches for matching tariffs in order:

```
For each route, try:

1. By ZIP Code + Destination COFOR
   (Most specific: exact ZIP, exact receiver)

2. By ZIP Code + Destination ZIP Range
   (Region specific: ZIP range for common areas)

3. By Country + Destination COFOR
   (Broader: entire country to specific shipper)

4. By Country + Destination ZIP Range
   (Broadest: entire country, ZIP range)

Use first match found
```

**Why Multiple Levels?**
- ZIP-level tariffs most accurate
- But not always available
- Falls back to country-level if ZIP unavailable
- Ensures all routes get priced

### Tariff Assignment Algorithm

For **Direct Routes**:
1. Calculate chargeable weight (per route)
2. Determine deviation bin (Small/Low/Medium/High/VH)
3. Build tariff bundle: (Carrier, Vehicle, Deviation)
4. Look up tariff for each bundle
5. Select matching tariff from LTL/FTL options
6. Assign to route

For **Hub Routes (First-Leg)**:
1. Calculate shipper chargeable weight (per shipper)
2. Determine weight bracket
3. Build tariff bundle: (Carrier, Weight Bracket, ZIP)
4. Look up tariff
5. Assign to route

For **Hub Routes (Linehaul)**:
1. Calculate total consolidated weight
2. If FTL concept: use truck-based model
3. If LTL concept: use both LTL and HUB brackets, pick cheaper
4. Assign to route

---

## Hub Assignment Strategy

### Automatic Hub Assignment

When a shipper is moved to hub distribution, the system automatically **assigns the best hub** based on location.

**Assignment Logic**:

```
1. Get shipper ZIP code (2-digit prefix)
2. Look up in hub-to-ZIP mapping:
   
   If ZIP mapping found → Assign that hub
   Else if country mapping found → Assign that hub
   Else → Cannot assign, shipper stays direct
   
3. Validate hub has required flow (parts/empties)
```

**Example**:
```
Shipper: Berlin retailer (ZIP: 10115)
Hub mappings:
  - ZIP 10 → Hub "Berlin_North"
  - Country "DE" → Hub "Frankfurt"

Assignment: Hub "Berlin_North" (ZIP match beats country)
```

### Hub Load Balancing

When multiple shippers are assigned to same hub, the system **generates all feasible first-leg + linehaul combinations**.

**Feasibility Rules**:
- First-leg route: One shipper per route (LTL consolidation)
- Linehaul route: Consolidates all first-legs
- Linehaul capacity: Cannot exceed truck capacity
- Linehaul frequency: Matches hub consolidation pattern

**Solver Decides**:
- Which first-leg + linehaul pairs to use
- Load per shipment
- Frequency of linehaul consolidation

---

## Transport Concepts (MR vs FTL)

### Milk Run (MR) - Multiple Stops

**Definition**: 2-4 shippers combined into single route.

**When Applied**:
```
Count of stops: 2, 3, or 4
Transport concept: "MR"
Pricing: Stop-based (truck + per-stop cost)
Frequency: Typically 1-3x/week
```

**Characteristics**:
- Consolidates smaller shipments
- Reduces vehicle utilization pressure
- More flexible scheduling
- Route ordering matters (deviation calculation)

**Example**:
```
Route: A → B → C → Plant
Stops: 3
Concept: MR
Base Cost: €800
Stop Costs: €120 + €100 = €220
Total: €1,020
```

### Full Truck Load (FTL) - Single Stop

**Definition**: Single shipper dedicated truck, or very large consolidated load.

**When Applied**:
```
Count of stops: 1
Transport concept: "FTL"
Pricing: Base cost only (no per-stop cost)
Frequency: Variable
```

**Characteristics**:
- Full vehicle dedicated
- No route ordering (only 1 stop)
- Lower per-unit cost for large shipments
- Higher utilization efficiency

**Example**:
```
Route: A only → Plant
Stops: 1
Concept: FTL
Base Cost: €800
Stop Costs: €0 (only 1 stop)
Total: €800
```

### Automatic Classification

```python
if count_of_stops > 1:
    transport_concept = "MR"
else:
    transport_concept = "FTL"
```

**No manual override** in current system.

---

## Solver Optimization Objectives

### Primary Objective: Minimize Total Cost

The solver aims to **minimize total weekly cost** across all routes.

```
Total Cost = Sum of:
  - All direct route costs (parts + empties)
  - All hub linehaul costs
  - All first-leg costs
```

### Cost Minimization Trade-offs

The solver balances competing pressures:

| Factor | Impact on Cost |
|--------|----------------|
| **More roundtrips** | Lower cost (splitting base) |
| **Longer routes** | Higher cost (more stops, deviation) |
| **Hub consolidation** | Lower cost for small shippers, higher coordination |
| **Lower frequency** | Lower cost (fewer departures) |
| **Better load utilization** | Lower cost per unit |

### Vehicle Utilization Penalties

If `overutilization` parameter is set, the solver can allow vehicles to exceed capacity with penalty:

```
Vehicle Capacity: 20 tons
Load: 24 tons (20% over)
Overutilization Rate: 10%

Penalty Cost = Base Cost × (1 + 0.10) = Base × 1.10
```

**Three Tiers**:
```
1-2 trucks: Overutilization rate A (e.g., 10%)
3-4 trucks: Overutilization rate B (e.g., 30%)
5+ trucks: Overutilization rate C (e.g., 50%)
```

**When Used**: Rare, only when needed to find feasible solution.

---

## Constraints & Limitations

### Hard Constraints (Must Not Violate)

| Constraint | Rule | Reason |
|-----------|------|--------|
| **Shipper allocation sum** | Each shipper 100% allocated per flow | Must fulfill all demand |
| **Carrier group homogeneity** | Same carrier group in one route | Operational simplicity |
| **Roundtrip parity** | Parts frequency = Empties frequency | Roundtrip economics |
| **Max stops per route** | ≤4 stops for MR | Vehicle capacity & maneuverability |
| **Vehicle assignment** | One vehicle per route | Cost model assumes vehicle type |
| **Frequency bounds** | 1-5x/week typical | Realistic operational range |

### Soft Constraints (Prefer Not to Violate)

| Constraint | Goal | Trade-off |
|-----------|------|-----------|
| **Lock routes** | Keep specific routes fixed | Limits optimization |
| **Block routes** | Prevent specific routes | Reduces solution space |
| **Hub availability** | Assign shippers to available hubs | May force direct if hub full |

### Physical Limitations

| Limitation | Value | Notes |
|-----------|-------|-------|
| **Max stops per MR route** | 4 | System design, vehicle maneuverability |
| **Min weight for hub** | 50 kg | Consolidation must be meaningful |
| **Max deviation for MR** | 200 km+ | Practical route length |
| **Frequency range** | 1-5x/week | Standard operational patterns |

### Data Quality Requirements

The solver will **fail if**:
- ✗ Shipper has no coordinates
- ✗ Shipper has missing demand (all zeros)
- ✗ Shippers have no assigned vehicle type
- ✗ No carrier network available
- ✗ Tariffs are missing for required brackets

---

## Example: End-to-End Routing Scenario

### Input Data
```
Shipper A: Berlin, 2,000 kg/week parts, 1,500 kg/week empties
Shipper B: Munich, 3,000 kg/week parts, 2,500 kg/week empties
Shipper C: Hamburg, 1,000 kg/week parts, 0 kg/week empties
Shipper D: Frankfurt, 1,500 kg/week parts, 1,200 kg/week empties

Plant: Hanover
Carrier: DHL (Group "Nordic")
Vehicle: 20-ton truck
```

### Processing Steps

**Step 1: Route Pattern Generation**
```
Generate all possible combinations:
- Single shipper routes: {A}, {B}, {C}, {D}
- Two-shipper: {A,B}, {A,C}, {A,D}, {B,C}, {B,D}, {C,D}
- Three-shipper: {A,B,C}, {A,B,D}, {A,C,D}, {B,C,D}
- Four-shipper: {A,B,C,D}

Filter by business rules:
- All must have same carrier group ✓ (all DHL Nordic)
- No more than 4 stops ✓
```

**Step 2: Sequence & Deviation**
```
For route {A, B, D}:
  Farthest from plant: A (Berlin)
  Nearest to A: D (Frankfurt)
  Nearest to D: B (Munich)
  
Sequence: A → D → B → Plant
Deviation: Calculated as shown earlier

Parts: 2,000 + 1,500 + 3,000 = 6,500 kg
Volume: [convert to kg]
Stops: 3 = MR (Milk Run)
```

**Step 3: Tariff Assignment**
```
Direct route {A,D,B} parts:
  Weight: 6,500 kg
  Stops: 3
  Deviation: 85 km (assumed "Medium")
  
Carrier: DHL Nordic
Vehicle: 20-ton truck
Deviation: Medium (50-100 km)
Tariff Bundle: (DHL, Truck-20T, Medium)
Look up tariff: Base €900, Stop Cost €150

Cost = €900 + (3-1) × €150 = €1,200/week parts
```

**Step 4: Roundtrip Optimization**
```
Can parts {A,D,B} pair with empties {A,D,B}?
  Parts frequency: 1x/week
  Empties frequency: 1x/week
  Same shippers: ✓
  
YES → Create roundtrip

Roundtrip saving:
  Two single trips: €1,200 × 2 = €2,400
  One roundtrip: €1,500 (roundtrip tariff)
  Saving: €900/week
```

**Step 5: Shipper C (Cannot combine)**
```
Shipper C: Only 1,000 kg parts, no empties demand

Cannot combine with others (would break allocation balance)
Create single-trip FTL route:
  Route: C → Plant
  Stops: 1 = FTL
  Cost: €750 (base cost, no stop multiplier)
```

**Step 6: Final Solution**
```
Route 1 (Roundtrip): A + D + B
  Parts: €1,200/week
  Empties: €1,200/week (paired)
  Frequency: 1x/week
  Shippers: 3 stops

Route 2 (Single Trip): C
  Parts: €750/week
  Empties: N/A
  Frequency: 1x/week
  Shippers: 1 stop

Total Weekly Cost: €3,150
Total Vehicles Needed: 2
```

---

## KPI Metrics Explained

The system tracks these performance indicators:

| KPI | Calculation | Business Meaning |
|-----|-----------|-----------------|
| **Total Cost** | Sum of all route costs | €/week expense |
| **Vehicles Used** | Count of distinct vehicle assignments | Fleet requirement |
| **Utilization** | Max(Weight%, Volume%, Meters%) | How full vehicle is (0-100%+) |
| **Cost/Vehicle** | Total Cost ÷ Vehicles | Efficiency per truck |
| **Cost/Volume** | Total Cost ÷ Total Volume | Cost per unit shipped |
| **Volume/Vehicle** | Total Volume ÷ Vehicles | Average load per truck |
| **Stops/Vehicle** | Total Stops ÷ Vehicles | How complex routes are |

---

## Common Questions & Answers

### Q: Why do some shippers split across multiple routes?

**A**: When shipper demand is too large for one vehicle or when different carrier networks serve different parts of their demand. The solver balances carrier efficiency with demand fulfillment.

### Q: Can I prevent a specific route combination?

**A**: Yes, use **"Block Route"** to exclude specific shipper combinations from being optimized. The solver will avoid that combination.

### Q: Why is the empties flow not being optimized?

**A**: Empties flow is always tied to parts flow in roundtrips. You cannot optimize them separately due to business model. If a shipper has no empties demand, only parts route is created.

### Q: What happens if a shipper has very high demand?

**A**: The system will either:
1. Split across multiple routes (allocation < 100%)
2. Create multiple frequency journeys
3. Move to hub consolidation if cost-effective

### Q: Can the solver change vehicle assignments?

**A**: Only if you set **"Solve Hubs"** option. The baseline solution uses predefined vehicle types from input data.

### Q: What if tariffs are missing for a route?

**A**: The solver will fail with an error. All shippers must have valid tariff mappings before optimization.

---

## Glossary

- **COFOR**: Shipper code/identifier
- **Deviation**: Extra km beyond direct route (for route complexity)
- **FTL**: Full Truck Load (1 shipper, full capacity)
- **LTL**: Less Than Truck Load (shared shipment, lower minimum)
- **MR**: Milk Run (2-4 shippers, consolidation)
- **Parts**: Outbound flow (plant to shippers)
- **Empties**: Return flow (shippers to plant)
- **Roundtrip**: Combined parts + empties journey same day
- **Tariff**: Pricing for transport based on weight, distance, carrier
- **Trip**: Pairing of parts and/or empties routes
- **Hub**: Consolidation point for geographic regions
- **First-Leg**: Route from shipper to hub
- **Linehaul**: Route from hub to plant
- **Chargeable Weight**: MAX(actual weight, volume × 250)
- **Utilization**: % of vehicle capacity used

---

## Feedback & Improvements

This document reflects the current business logic as of v0.1.3. As the system evolves, this documentation should be updated to reflect:
- New tariff models
- Additional constraints
- Enhanced optimization objectives
- Hub network expansions

**Last Updated**: 2026-05-13
