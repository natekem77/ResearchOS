# Research Resources

Research Resources are reusable laboratory materials and scientific entities that can be referenced across experiments instead of duplicated inside each experiment record.

## Supported Resource Types

- Compound
- Antibody
- Marker
- Gene
- Protein
- Cell line
- Organoid line
- Media
- Growth factor
- Small molecule
- Reagent
- Primer
- Vector
- Plasmid
- Consumable
- Equipment
- Other

## Resource Fields

Each resource can store:

- Name
- Aliases
- Vendor
- Catalog number
- Lot number
- RRID
- Storage location
- Concentration
- Units
- Expiration
- Notes

Resources also carry metadata so future providers can attach custom fields without schema changes.

## Usage Tracking

`ResourceUsage` records connect resources to:

- Experiments
- Protocols
- Sessions
- Notebook entries
- GraphPad assets
- Statistics
- Microscopy
- Literature

This lets ResearchOS answer questions such as:

- Which experiments used this antibody lot?
- Which protocols used this growth factor?
- Which microscopy assets came from this marker/resource?
- What papers mention this reagent?

## API

List resources:

```bash
curl http://127.0.0.1:8001/resources
```

Create a resource:

```bash
curl -X POST http://127.0.0.1:8001/resources \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type":"compound",
    "name":"SAG",
    "aliases":["Smoothened agonist"],
    "vendor":"Demo Vendor",
    "catalog_number":"SAG-001",
    "lot_number":"LOT-82",
    "storage_location":"-20C box A",
    "concentration":"100",
    "units":"nM",
    "notes":"Demo resource"
  }'
```

Get one resource:

```bash
curl http://127.0.0.1:8001/resources/resource:...
```

Filter by type:

```bash
curl http://127.0.0.1:8001/resources/type/compound
```

Update a resource:

```bash
curl -X PUT http://127.0.0.1:8001/resources/resource:... \
  -H "Content-Type: application/json" \
  -d '{"resource_type":"compound","name":"SAG","aliases":["Smoothened agonist"],"notes":"Updated"}'
```

## Knowledge Graph

Resources are first-class Knowledge Graph objects. Resource names and aliases are indexed as graph entities.

For example, a SAG compound resource appears in:

```bash
curl http://127.0.0.1:8001/knowledgegraph/entity/SAG
```

The entity payload includes related resources plus experiments, notebook entries, literature, assets, and statistics that reference the same entity.

## Experiment Workspace

Experiment workspaces show resources connected through:

- shared Knowledge Graph entities
- explicit `ResourceUsage` links
- experiment compounds, markers, genes, proteins, and cell-line metadata

## Flutter

The mobile app includes a Resources page for:

- searching resources
- filtering by type
- creating resource records
- seeing aliases, vendor/catalog/lot, storage location, and usage count

## Design Rule

Resources should be reusable across many experiments. Do not copy vendor/catalog/lot metadata into every experiment when a resource record can represent it once.
