# Extension SDK

ResearchOS extensions are the official path for adding scientific integrations without coupling new providers directly into the core application.

The current SDK is in-memory scaffolding for built-in and future installable extensions. Existing provider endpoints continue to work unchanged while ResearchOS migrates toward extension-first integration.

## Core Concepts

The SDK defines:

- `ExtensionManifest`
- `Extension`
- `ExtensionRegistry`
- `ExtensionManager`

Extensions can contribute:

- providers
- agents
- commands
- pages
- importers
- exporters
- background jobs
- widgets

## Manifest

Every extension declares:

- `extension_id`
- `name`
- `version`
- `author`
- `dependencies`
- `capabilities`
- `required_permissions`
- `description`

Example:

```python
from app.extensions import ExtensionManifest

manifest = ExtensionManifest(
    extension_id="example.pubmed",
    name="PubMed Extension",
    version="0.1.0",
    author="Example Lab",
    dependencies=[],
    capabilities=["provider", "importer", "page"],
    required_permissions=["network:pubmed"],
    description="Imports PubMed literature metadata.",
)
```

## Registration API

Extensions register through `ExtensionManager`:

```python
from app.extensions import ExtensionManager

manager = ExtensionManager()
manager.register_extension(manifest)
manager.register_provider("example.pubmed", "pubmed", title="PubMed")
manager.register_importer("example.pubmed", "import_pubmed_query", endpoint="/providers/pubmed/import")
manager.register_page("example.pubmed", "pubmed", route="#/literature")
manager.register_command("example.pubmed", "search_pubmed", title="Search PubMed")
```

Supported methods:

- `register_provider()`
- `register_agent()`
- `register_command()`
- `register_page()`
- `register_importer()`
- `register_exporter()`
- `register_background_job()`
- `register_widget()`

## Built-In Extensions

ResearchOS currently registers built-in extensions for:

- OneNote
- Markdown demo notes
- GraphPad
- Microscopy
- Spreadsheets
- Literature

These wrap current provider modules without changing their behavior.

## API

List installed extensions:

```bash
curl http://127.0.0.1:8001/extensions
```

Get one extension:

```bash
curl http://127.0.0.1:8001/extensions/builtin.graphpad
```

Enable or disable:

```bash
curl -X POST http://127.0.0.1:8001/extensions/builtin.graphpad/disable
curl -X POST http://127.0.0.1:8001/extensions/builtin.graphpad/enable
```

Disabling an extension currently changes registry status only. It does not disable existing built-in provider endpoints yet.

## Dependency Rules

The registry rejects an extension when:

- its `extension_id` is already installed
- a declared dependency has not been installed
- it registers a duplicate contribution ID under the same extension

Future versions may support semantic version constraints.

## Marketplace Placeholder

The UI includes a future marketplace placeholder. A future marketplace should support:

- extension discovery
- trust and signing metadata
- compatibility checks
- permission review
- lab/workspace-specific enablement
- update/rollback

## Future Provider Migration

Future integrations should be built as extensions:

- GraphPad
- PubMed
- Benchling
- ImageJ
- CellProfiler
- OneNote
- sequencing pipelines
- flow cytometry
- microscopy analysis

Providers should contribute metadata and events through the Extension SDK instead of hardcoding cross-service coupling.
