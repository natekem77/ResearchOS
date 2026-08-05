import 'dart:convert';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/analysis/viewers/bar/bar_plot_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/common/viewer_factory.dart';
import 'package:researchos_mobile/analysis/viewers/dotplot/dot_plot_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/heatmap/heatmap_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/line/line_plot_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/scatter/scatter_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/table/enhanced_table_viewer.dart';
import 'package:researchos_mobile/analysis/viewers/violin/violin_plot_viewer.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/analysis_screen.dart';
import 'package:researchos_mobile/services/navigation_preferences_service.dart';

void main() {
  test('Analysis destination is discoverable but not in default five', () {
    expect(mundiDestinations.map((item) => item.id), contains('analysis'));
    expect(defaultNavigationDestinationIds, isNot(contains('analysis')));
  });

  testWidgets('analysis sections collapse expand and preserve state',
      (tester) async {
    final api = _mockAnalysisApi(<String>[]);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Public Datasets'), findsOneWidget);
    expect(find.text('Search GEO'), findsNothing);
    await tester.tap(find.text('Public Datasets'));
    await tester.pumpAndSettle();
    expect(find.text('Search GEO'), findsOneWidget);

    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    expect(find.text('Search GEO'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('dataset delete confirmation cancel does not delete',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);
    await tester.scrollUntilVisible(
      find.text('Bulk SAG GRKi'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byTooltip('Dataset actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(find.text('Delete dataset?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(
      calls
          .where((call) => call.startsWith('DELETE /mobile/analysis/datasets')),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('dataset and job deletion refresh after success', (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('Bulk SAG GRKi'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byTooltip('Dataset actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Bulk RNA-seq Dataset Validation/QC'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.byTooltip('Job actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Job actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete job only'));
    await tester.pumpAndSettle();

    expect(
      calls,
      contains('DELETE /mobile/analysis/datasets/analysis-dataset%3Atest'),
    );
    expect(
      calls,
      contains('DELETE /mobile/analysis/jobs/analysis-job%3Atest'),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('Analysis screen shows worker, datasets, jobs, and outputs',
      (tester) async {
    final calls = <String>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path == '/mobile/analysis/workers') {
          return _json({
            'workers': [
              {
                'worker_id': 'worker-1',
                'display_name': 'Lab Analysis Server',
                'status': 'ready',
                'cpu_count': 32,
                'ram_gb': 128,
                'running_job_count': 0,
                'maximum_concurrent_jobs': 1,
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/storage-locations') {
          return _json({
            'storage_locations': [
              {
                'id': 'analysis-storage:default',
                'display_name': 'Approved lab data root',
                'root_path': 'server-data',
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/demo-library') {
          return _json({
            'workspace': {'display_name': 'Demo Workspace'},
            'datasets': [
              {'display_name': 'PBMC 3k'},
              {'display_name': 'Small Retina Bulk'},
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/demo-workspace/install') {
          return _json({
            'workspace': {'display_name': 'Demo Workspace'},
            'installed_datasets': const [],
            'jobs': const [],
            'outputs': const [],
          });
        }
        if (request.url.path == '/mobile/analysis/public-datasets') {
          return _json({
            'datasets': [
              _publicDataset(),
            ],
          });
        }
        if (request.url.path ==
            '/mobile/analysis/public-datasets/GSE-MUNDI-RET-ORG-BULK/import') {
          return _json({
            'dataset': {
              'id': 'analysis-dataset:public',
              'display_name': 'Retinal organoid BMP4 response bulk RNA-seq',
            },
          });
        }
        if (request.url.path == '/mobile/analysis/datasets') {
          return _json({
            'datasets': [
              {
                'id': 'analysis-dataset:test',
                'display_name': 'Bulk SAG GRKi',
                'modality': 'bulk_rna_seq',
                'sample_count': 3,
                'features_count': 4,
                'metadata_summary': const {},
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/outputs') {
          return _json({
            'outputs': [
              _qcOutput(),
              _tableOutput(),
              _provenanceOutput(),
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/output-groups') {
          return _json({
            'groups': [
              {
                'dataset': {
                  'id': 'analysis-dataset:test',
                  'display_name': 'Bulk SAG GRKi',
                },
                'job': {
                  'id': 'analysis-job:test',
                  'workflow_id': 'bulk_rnaseq_validation_qc',
                  'status': 'complete',
                  'created_at': '2026-07-23T11:20:00Z',
                },
                'outputs': [
                  _qcOutput(),
                  _tableOutput(),
                  _provenanceOutput(),
                ],
              },
            ],
          });
        }
        if (request.url.path ==
            '/mobile/analysis/outputs/analysis-output%3Aqc') {
          return _json({
            'output': _qcOutput()
              ..addAll({
                'dataset': {
                  'display_name': 'Bulk SAG GRKi',
                },
                'job': {
                  'workflow_id': 'bulk_rnaseq_validation_qc',
                  'status': 'complete',
                },
                'references': const [],
              }),
          });
        }
        if (request.url.path ==
            '/mobile/analysis/outputs/analysis-output%3Atable') {
          return _json({
            'output': _tableOutput()
              ..addAll({
                'dataset': {
                  'display_name': 'Bulk SAG GRKi',
                },
                'job': {
                  'workflow_id': 'bulk_rnaseq_validation_qc',
                  'status': 'complete',
                },
                'references': const [],
              }),
          });
        }
        if (request.url.path ==
            '/mobile/analysis/outputs/analysis-output%3Aprovenance') {
          return _json({
            'output': _provenanceOutput()
              ..addAll({
                'dataset': {
                  'display_name': 'Bulk SAG GRKi',
                },
                'job': {
                  'workflow_id': 'bulk_rnaseq_validation_qc',
                  'status': 'complete',
                },
                'references': const [],
              }),
          });
        }
        if (request.url.path == '/mobile/analysis/notebook-references') {
          return _json({
            'reference': {
              'id': 'analysis-reference:test',
              'output_id': 'analysis-output:qc',
              'reference_type': 'linked',
            },
          });
        }
        if (request.url.path == '/mobile/analysis/workflows') {
          return _json({
            'workflows': [
              {
                'stable_key': 'bulk_rnaseq_validation_qc',
                'name': 'Bulk RNA-seq Dataset Validation/QC',
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/jobs') {
          if (request.method == 'POST') {
            return _json({
              'job': {
                'id': 'analysis-job:test',
                'dataset_id': 'analysis-dataset:test',
                'dataset_display_name': 'Bulk SAG GRKi',
                'workflow_id': 'bulk_rnaseq_validation_qc',
                'workflow_display_name': 'Bulk RNA-seq Dataset Validation/QC',
                'status': 'queued',
                'progress': 0,
                'current_stage': 'Queued',
                'created_at': '2026-07-23T11:19:00Z',
                'start_time': '2026-07-23T11:19:00Z',
                'elapsed_seconds': 0,
              }
            });
          }
          return _json({
            'jobs': [
              {
                'id': 'analysis-job:test',
                'dataset_id': 'analysis-dataset:test',
                'dataset_display_name': 'Bulk SAG GRKi',
                'workflow_id': 'bulk_rnaseq_validation_qc',
                'workflow_display_name': 'Bulk RNA-seq Dataset Validation/QC',
                'status': 'complete',
                'progress': 1,
                'current_stage': 'Complete',
                'created_at': '2026-07-23T11:20:00Z',
                'start_time': '2026-07-23T11:20:00Z',
                'elapsed_seconds': 42,
              }
            ],
          });
        }
        if (request.url.path ==
            '/mobile/analysis/jobs/analysis-job%3Atest/outputs') {
          return _json({
            'outputs': [
              _qcOutput(),
              _tableOutput(),
              _provenanceOutput(),
            ],
          });
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    expect(find.text('Analysis'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Lab Analysis Server'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Lab Analysis Server'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Demo Library'),
      -240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Demo Library'), findsOneWidget);
    await tester.tap(find.text('Install Demo Workspace'));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /mobile/analysis/demo-workspace/install'));
    await tester.scrollUntilVisible(
      find.text('Bulk SAG GRKi'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Bulk SAG GRKi'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Run QC'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('Run QC'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run QC'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Open Results'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('Open Results'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open Results'));
    await tester.pumpAndSettle();

    expect(find.text('Bulk RNA-seq QC Report'), findsWidgets);
    await tester.tap(
      find
          .descendant(
            of: find.byTooltip('Insert into Notebook').last,
            matching: find.byType(IconButton),
          )
          .first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Insert into Notebook'), findsOneWidget);
    await tester.tap(find.text('Insert').last);
    await tester.pumpAndSettle();
    expect(calls, contains('POST /mobile/analysis/notebook-references'));

    await tester.tap(
      find
          .ancestor(
            of: find.text('Bulk RNA-seq QC Report').last,
            matching: find.byType(ListTile),
          )
          .first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Validation checks'), findsOneWidget);
    expect(
        calls, contains('GET /mobile/analysis/outputs/analysis-output%3Aqc'));
    expect(calls, contains('POST /mobile/analysis/jobs'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Analysis output browser opens table outputs', (tester) async {
    final api = _mockAnalysisApi(<String>[]);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('Library Sizes'),
      600,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('Library Sizes'));
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('Library Sizes').last,
            matching: find.byType(ListTile),
          )
          .first,
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    expect(find.text('DMSO_1'), findsOneWidget);
    expect(find.text('library_size'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'queued DESeq2 job shows reason and dataset card fits narrow phone',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.url.path == '/mobile/analysis/workers') {
          return _json({
            'workers': [
              {
                'worker_id': 'worker-1',
                'display_name': 'Nathan Mac',
                'status': 'ready',
                'supported_workflows': ['bulk_rnaseq_validation_qc'],
                'running_job_count': 0,
                'maximum_concurrent_jobs': 1,
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/storage-locations') {
          return _json({'storage_locations': const []});
        }
        if (request.url.path == '/mobile/analysis/demo-library') {
          return _json({'datasets': const []});
        }
        if (request.url.path == '/mobile/analysis/public-datasets') {
          return _json({'datasets': const []});
        }
        if (request.url.path == '/mobile/analysis/datasets') {
          return _json({
            'datasets': [
              {
                'id': 'analysis-dataset:retina',
                'display_name':
                    'Small Retina Bulk With A Deliberately Long Display Name',
                'modality': 'bulk_rna_seq',
                'sample_count': 6,
                'features_count': 1200,
                'source_type': 'demo_server_folder',
                'metadata_summary': const {},
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/workflows') {
          return _json({
            'workflows': [
              {
                'stable_key': 'bulk_rnaseq_validation_qc',
                'name': 'Bulk RNA-seq Dataset Validation/QC',
                'status': 'installed',
                'readiness_reason': 'Ready',
              },
              {
                'stable_key': 'bulk_rnaseq_deseq2',
                'name': 'DESeq2 Differential Expression',
                'workflow_version': '1.0.0',
                'status': 'unavailable',
                'readiness_reason':
                    'No eligible worker with R/DESeq2 dependencies is connected.',
              },
              {
                'stable_key': 'single_cell_scanpy_standard',
                'name': 'Scanpy Standard Pipeline',
                'workflow_version': '1.0.0',
                'status': 'installed',
                'readiness_reason': 'Ready',
              },
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/jobs') {
          return _json({
            'jobs': [
              {
                'id': 'analysis-job:deseq2',
                'workflow_id': 'bulk_rnaseq_deseq2',
                'status': 'queued',
                'progress': 0,
                'current_stage': 'Queued',
                'queue_reason':
                    'Connected worker does not support bulk_rnaseq_deseq2. Missing R/DESeq2 dependencies.',
              }
            ],
          });
        }
        if (request.url.path == '/mobile/analysis/outputs' ||
            request.url.path == '/mobile/analysis/output-groups') {
          return _json({'outputs': const [], 'groups': const []});
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('Small Retina Bulk With A Deliberately Long Display Name'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text('Small Retina Bulk With A Deliberately Long Display Name'),
      findsOneWidget,
    );
    final deseq2Button = tester
        .widget<FilledButton>(find.widgetWithText(FilledButton, 'Run DESeq2'));
    expect(deseq2Button.onPressed, isNull);
    await tester.scrollUntilVisible(
      find.textContaining('Missing R/DESeq2 dependencies'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('View Job'), findsOneWidget);
    expect(find.text('Open Results'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('volcano output opens graphical Plot tab with Data tab',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) =>
                ViewerFactory().build(context, output: _volcanoOutput()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Plot'), findsOneWidget);
    expect(find.text('Data'), findsOneWidget);
    expect(find.byType(ScatterViewer), findsOneWidget);
    expect(find.byType(ScatterChart), findsOneWidget);
    expect(find.text('Export PNG 300 dpi'), findsOneWidget);
    expect(find.text('upregulated: 1'), findsOneWidget);
    expect(find.text('significant total: 1'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, 'POU4F2');
    await tester.pumpAndSettle();

    await tester.tap(find.text('Data'));
    await tester.pumpAndSettle();
    expect(find.text('POU4F2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('public GEO datasets search and import from Analysis',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('Public Datasets').first,
      -300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Search GEO'), findsOneWidget);
    expect(find.text('Retinal organoid BMP4 response bulk RNA-seq'),
        findsOneWidget);
    await tester.enterText(
        find.widgetWithText(TextField, 'Search GEO'), 'BMP4');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Import').first);
    await tester.pumpAndSettle();

    expect(
      calls,
      contains(
        'POST /mobile/analysis/public-datasets/GSE-MUNDI-RET-ORG-BULK/import',
      ),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('CPM public dataset queues QC only and shows failed job error',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.enterText(
        find.widgetWithText(TextField, 'Search GEO'), 'GSE229682');
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Import + QC only'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('Import + QC only'));
    await tester.pumpAndSettle();
    expect(find.text('Import + QC only'), findsOneWidget);
    await tester.tap(find.text('Import + QC only'));
    await tester.pumpAndSettle();

    expect(
      calls,
      contains('POST /mobile/analysis/public-datasets/GSE229682/import'),
    );
    expect(
        calls.where((call) => call == 'POST /mobile/analysis/jobs').length, 1);

    await tester.scrollUntilVisible(
      find.text('View Job'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(find.text('View Job').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('View Job').last);
    await tester.pumpAndSettle();
    expect(find.text('Error'), findsOneWidget);
    expect(find.text('DESeq2 requires raw integer counts.'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('slow public datasets endpoint does not block other sections',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(
      calls,
      publicDatasetsDelay: const Duration(seconds: 7),
    );
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pump();
    await tester.tap(find.text('Expand all'));
    await tester.pump();

    for (var i = 0; i < 20; i += 1) {
      await tester.pump(const Duration(milliseconds: 250));
      if (find
          .text('Lab Analysis Server', skipOffstage: false)
          .evaluate()
          .isNotEmpty) {
        break;
      }
    }

    expect(calls, contains('GET /mobile/analysis/workers'));
    expect(calls, contains('GET /mobile/analysis/demo-library'));
    await tester.scrollUntilVisible(
      find.text('Lab Analysis Server'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Lab Analysis Server'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Bulk SAG GRKi'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Bulk SAG GRKi'), findsOneWidget);
    await tester.pump(const Duration(seconds: 7));
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.drag(find.byType(Scrollable).first, const Offset(0, 500));
      await tester.pump();
    }
    expect(
        find.textContaining(
          'Timed out while loading this section',
          skipOffstage: false,
        ),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('DESeq2 dialog uses imported condition defaults and validation',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('Imported retinal GEO counts'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.scrollUntilVisible(
      find.widgetWithText(FilledButton, 'Run DESeq2').last,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester
        .ensureVisible(find.widgetWithText(FilledButton, 'Run DESeq2').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Run DESeq2').last);
    await tester.pumpAndSettle();

    expect(
        find.text('condition: D060, D070, D090, D120, D200'), findsOneWidget);
    expect(
      find.text('Condition levels: D060, D070, D090, D120, D200'),
      findsOneWidget,
    );
    expect(find.text('D200'), findsWidgets);
    expect(find.text('D060'), findsWidgets);
    expect(find.text('Zero-count samples: none'), findsOneWidget);
    expect(find.text('Duplicated genes: 0'), findsOneWidget);
    await tester.tap(find.text('Submit DESeq2'));
    await tester.pumpAndSettle();
    expect(
      calls.any((call) =>
          call.startsWith('BODY ') &&
          call.contains('"numerator_level":"D200"') &&
          call.contains('"denominator_level":"D060"')),
      isTrue,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('viewer factory routes scientific outputs to typed viewers',
      (tester) async {
    final cases = [
      (_maOutput(), ScatterViewer, ScatterChart),
      (_pcaOutput(), ScatterViewer, ScatterChart),
      (_umapOutput(), ScatterViewer, ScatterChart),
      (_featurePlotOutput(), ScatterViewer, ScatterChart),
      (_sampleDistanceHeatmapOutput(), HeatmapViewer, null),
      (_topGeneHeatmapOutput(), HeatmapViewer, null),
      (_markerDotPlotOutput(), DotPlotViewer, null),
      (_violinOutput(), ViolinPlotViewer, null),
      (_dispersionOutput(), LinePlotViewer, LineChart),
      (_librarySizePlotOutput(), BarPlotViewer, BarChart),
      (_tableOutput(), EnhancedTableViewer, null),
    ];

    for (final (output, viewerType, chartType) in cases) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) =>
                  ViewerFactory().build(context, output: output),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(viewerType), findsOneWidget);
      if (chartType != null) expect(find.byType(chartType), findsOneWidget);
      if (output['output_type'] != 'table') {
        expect(find.text('Plot'), findsOneWidget);
        expect(find.text('Data'), findsOneWidget);
        expect(find.text('Export PNG 300 dpi'), findsOneWidget);
      }
      if (output['id'] == 'analysis-output:ma') {
        expect(find.textContaining('log10 baseMean'), findsWidgets);
      }
      if (output['id'] == 'analysis-output:pca') {
        expect(find.text('DMSO'), findsOneWidget);
        expect(find.text('SAG'), findsOneWidget);
      }
      if (output['id'] == 'analysis-output:top-genes') {
        expect(find.text('Row-wise Z-score of VST values'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('single-cell dataset opens Scanpy configuration and submits job',
      (tester) async {
    final calls = <String>[];
    final api = _mockAnalysisApi(calls);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();
    await _expandAllAnalysisSections(tester);

    await tester.scrollUntilVisible(
      find.text('PBMC 3k (10x public)'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.scrollUntilVisible(
      find.widgetWithText(FilledButton, 'Run Scanpy'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    final runScanpyButton = find.widgetWithText(FilledButton, 'Run Scanpy');
    await tester.ensureVisible(runScanpyButton);
    await tester.pumpAndSettle();
    await tester.tap(runScanpyButton);
    await tester.pumpAndSettle();

    expect(find.text('QC Filtering'), findsOneWidget);
    expect(find.text('Normalization and Features'), findsOneWidget);
    expect(find.text('Dimensionality Reduction'), findsOneWidget);
    expect(find.text('Clustering and Markers'), findsOneWidget);
    await tester.tap(find.text('Submit Scanpy'));
    await tester.pumpAndSettle();

    expect(
      calls.any((call) =>
          call.startsWith('BODY ') &&
          call.contains('"workflow_key":"single_cell_scanpy_standard"') &&
          call.contains('"leiden_resolution":0.5')),
      isTrue,
    );
    expect(find.text('Scanpy job queued.'), findsOneWidget);
    expect(find.text('Scanpy Standard Pipeline'), findsWidgets);
    expect(find.text('Queued'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}

ResearchOsApi _mockAnalysisApi(
  List<String> calls, {
  Duration publicDatasetsDelay = Duration.zero,
}) {
  return ResearchOsApi(
    baseUrl: 'http://example.test',
    client: MockClient((request) async {
      calls.add('${request.method} ${request.url.path}');
      if (request.method == 'POST' &&
          request.url.path == '/mobile/analysis/jobs') {
        calls.add('BODY ${request.body}');
      }
      if (request.method == 'DELETE' &&
          request.url.path.startsWith('/mobile/analysis/datasets/')) {
        return _json({
          'deleted': true,
          'jobs': 1,
          'outputs': 3,
          'files_removed': true,
        });
      }
      if (request.method == 'DELETE' &&
          request.url.path.startsWith('/mobile/analysis/jobs/')) {
        return _json({
          'deleted': true,
          'outputs': 3,
          'outputs_deleted':
              request.url.queryParameters['delete_outputs'] == 'true',
        });
      }
      if (request.url.path == '/mobile/analysis/workers') {
        return _json({
          'workers': [
            {
              'worker_id': 'worker-1',
              'display_name': 'Lab Analysis Server',
              'status': 'ready',
              'cpu_count': 32,
              'ram_gb': 128,
              'running_job_count': 0,
              'maximum_concurrent_jobs': 1,
            }
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/storage-locations') {
        return _json({
          'storage_locations': [
            {
              'id': 'analysis-storage:default',
              'display_name': 'Approved lab data root',
              'root_path': 'server-data',
            }
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/demo-library') {
        return _json({
          'workspace': {'display_name': 'Demo Workspace'},
          'datasets': [
            {'display_name': 'PBMC 3k'},
            {'display_name': 'Small Retina Bulk'},
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/public-datasets') {
        if (publicDatasetsDelay > Duration.zero) {
          await Future<void>.delayed(publicDatasetsDelay);
        }
        return _json({
          'datasets': [
            _publicDataset(),
            _exploratoryPublicDataset(),
          ],
        });
      }
      if (request.url.path ==
          '/mobile/analysis/public-datasets/GSE-MUNDI-RET-ORG-BULK/import') {
        return _json({
          'dataset': {
            'id': 'analysis-dataset:public',
            'display_name': 'Retinal organoid BMP4 response bulk RNA-seq',
          },
        });
      }
      if (request.url.path ==
          '/mobile/analysis/public-datasets/GSE229682/import') {
        return _json({
          'dataset': {
            'id': 'analysis-dataset:cpm',
            'display_name': 'GSE229682 CPM-only retinal organoids',
            'exploratory_only': true,
            'source_data_kind': 'normalized_cpm',
          },
        });
      }
      if (request.url.path == '/mobile/analysis/datasets') {
        return _json({
          'datasets': [
            {
              'id': 'analysis-dataset:test',
              'display_name': 'Bulk SAG GRKi',
              'modality': 'bulk_rna_seq',
              'sample_count': 3,
              'features_count': 4,
              'metadata_summary': const {},
            },
            _geoDataset(),
            _singleCellDataset(),
            {
              'id': 'analysis-dataset:cpm',
              'display_name': 'GSE229682 CPM-only retinal organoids',
              'modality': 'bulk_rna_seq',
              'sample_count': 15,
              'features_count': 59618,
              'source_data_kind': 'normalized_cpm',
              'exploratory_only': true,
              'metadata_summary': {
                'exploratory_only': true,
                'source_data_kind': 'normalized_cpm',
              },
            },
          ],
        });
      }
      if (request.url.path ==
          '/mobile/analysis/datasets/analysis-dataset:geo') {
        return _json({'dataset': _geoDataset()});
      }
      if (request.url.path == '/mobile/analysis/outputs') {
        return _json({
          'outputs': [
            _qcOutput(),
            _tableOutput(),
            _provenanceOutput(),
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/output-groups') {
        return _json({
          'groups': [
            {
              'dataset': {
                'id': 'analysis-dataset:test',
                'display_name': 'Bulk SAG GRKi',
              },
              'job': {
                'id': 'analysis-job:test',
                'workflow_id': 'bulk_rnaseq_validation_qc',
                'status': 'complete',
                'created_at': '2026-07-23T11:20:00Z',
              },
              'outputs': [
                _qcOutput(),
                _tableOutput(),
                _provenanceOutput(),
              ],
            },
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/workflows') {
        return _json({
          'workflows': [
            {
              'stable_key': 'bulk_rnaseq_validation_qc',
              'name': 'Bulk RNA-seq Dataset Validation/QC',
            },
            {
              'stable_key': 'bulk_rnaseq_deseq2',
              'name': 'DESeq2 Differential Expression',
              'status': 'installed',
              'readiness_reason': 'Ready',
            },
            {
              'stable_key': 'single_cell_scanpy_standard',
              'name': 'Scanpy Standard Pipeline',
              'status': 'installed',
              'readiness_reason': 'Ready',
            },
          ],
        });
      }
      if (request.url.path == '/mobile/analysis/jobs') {
        if (request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          final workflowId = body['workflow_id']?.toString() ?? '';
          final datasetId = body['dataset_id']?.toString() ?? '';
          final datasetName = datasetId == 'analysis-dataset:single-cell'
              ? 'PBMC 3k (10x public)'
              : datasetId == 'analysis-dataset:geo'
                  ? 'GSE229682 retinal organoid raw counts'
                  : 'Bulk SAG GRKi';
          final workflowName = workflowId == 'single_cell_scanpy_standard'
              ? 'Scanpy Standard Pipeline'
              : workflowId == 'bulk_rnaseq_deseq2'
                  ? 'DESeq2 Differential Expression'
                  : 'Bulk RNA-seq Dataset Validation/QC';
          return _json({
            'job': {
              'id': 'analysis-job:queued',
              'dataset_id': datasetId,
              'dataset_display_name': datasetName,
              'workflow_id': workflowId,
              'workflow_display_name': workflowName,
              'status': 'queued',
              'progress': 0,
              'current_stage': 'Queued',
              'created_at': '2026-08-04T12:01:00Z',
              'queued_at': '2026-08-04T12:01:00Z',
              'start_time': '2026-08-04T12:01:00Z',
              'elapsed_seconds': 0,
            }
          });
        }
        return _json({
          'jobs': [
            {
              'id': 'analysis-job:test',
              'dataset_id': 'analysis-dataset:test',
              'dataset_display_name': 'Bulk SAG GRKi',
              'workflow_id': 'bulk_rnaseq_validation_qc',
              'workflow_display_name': 'Bulk RNA-seq Dataset Validation/QC',
              'status': 'complete',
              'progress': 1,
              'current_stage': 'Complete',
              'created_at': '2026-07-23T11:20:00Z',
              'start_time': '2026-07-23T11:20:00Z',
              'elapsed_seconds': 42,
            },
            {
              'id': 'analysis-job:failed',
              'dataset_id': 'analysis-dataset:geo',
              'dataset_display_name': 'GSE229682 retinal organoid raw counts',
              'workflow_id': 'bulk_rnaseq_deseq2',
              'workflow_display_name': 'DESeq2 Differential Expression',
              'status': 'failed',
              'progress': 1,
              'current_stage': 'Failed',
              'created_at': '2026-07-23T11:21:00Z',
              'start_time': '2026-07-23T11:21:00Z',
              'elapsed_seconds': 8,
              'error_summary': 'DESeq2 requires raw integer counts.',
            },
          ],
        });
      }
      if (request.url.path ==
          '/mobile/analysis/jobs/analysis-job%3Afailed/outputs') {
        return _json({'outputs': const []});
      }
      if (request.url.path ==
          '/mobile/analysis/outputs/analysis-output%3Atable') {
        return _json({
          'output': _tableOutput()
            ..addAll({
              'dataset': {
                'display_name': 'Bulk SAG GRKi',
              },
              'job': {
                'workflow_id': 'bulk_rnaseq_validation_qc',
                'status': 'complete',
              },
              'references': const [],
            }),
        });
      }
      return http.Response('not found', 404);
    }),
  );
}

Future<void> _expandAllAnalysisSections(WidgetTester tester) async {
  final button = find.text('Expand all');
  if (button.evaluate().isEmpty) return;
  await tester.tap(button);
  await tester.pumpAndSettle();
}

Map<String, dynamic> _qcOutput() {
  return {
    'id': 'analysis-output:qc',
    'display_name': 'Bulk RNA-seq QC Report',
    'output_type': 'qc_report',
    'job_id': 'analysis-job:test',
    'dataset_id': 'analysis-dataset:test',
    'created_at': '2026-07-23T11:20:00Z',
    'structured': {
      'summary': {
        'sample_count': 3,
        'feature_count': 4,
        'integer_counts_valid': true,
        'sample_names_match': true,
        'duplicate_gene_count': 0,
        'library_size_min': 115,
        'library_size_median': 159,
        'library_size_max': 165,
        'metadata_rows': 3,
      },
      'flags': const [],
      'group_sizes': {'DMSO': 1, 'SAG': 2},
    },
    'provenance': {
      'workflow_stable_key': 'bulk_rnaseq_validation_qc',
      'workflow_version': '1.0.0',
      'worker_id': 'worker-1',
    },
  };
}

Map<String, dynamic> _tableOutput() {
  return {
    'id': 'analysis-output:table',
    'display_name': 'Library Sizes',
    'output_type': 'table',
    'job_id': 'analysis-job:test',
    'dataset_id': 'analysis-dataset:test',
    'structured': {
      'columns': ['sample', 'library_size', 'detected_genes'],
      'rows': [
        {'sample': 'DMSO_1', 'library_size': 115, 'detected_genes': 4},
        {'sample': 'SAG_1', 'library_size': 159, 'detected_genes': 4},
      ],
    },
  };
}

Map<String, dynamic> _provenanceOutput() {
  return {
    'id': 'analysis-output:provenance',
    'display_name': 'Reproducibility Manifest',
    'output_type': 'provenance',
    'job_id': 'analysis-job:test',
    'dataset_id': 'analysis-dataset:test',
    'structured': {
      'workflow_stable_key': 'bulk_rnaseq_validation_qc',
      'workflow_version': '1.0.0',
      'worker_id': 'worker-1',
      'parameters': {'sample_id_column': 'sample'},
      'dataset_checksum': 'abc123',
      'outputs': const [],
    },
  };
}

Map<String, dynamic> _publicDataset() {
  return {
    'accession': 'GSE-MUNDI-RET-ORG-BULK',
    'title': 'Retinal organoid BMP4 response bulk RNA-seq',
    'organism': 'Homo sapiens',
    'sample_count': 6,
    'platform': 'Illumina NovaSeq 6000',
    'summary': 'Curated retinal organoid public GEO import fixture.',
  };
}

Map<String, dynamic> _geoDataset() {
  return {
    'id': 'analysis-dataset:geo',
    'display_name': 'Imported retinal GEO counts',
    'modality': 'bulk_rna_seq',
    'sample_count': 15,
    'features_count': 59618,
    'source_data_kind': 'raw_counts',
    'exploratory_only': false,
    'metadata_summary': {
      'suggested_deseq2': {
        'sample_id_column': 'sample',
        'design_factors': ['condition'],
        'contrast_factor': 'condition',
        'denominator_level': 'D060',
        'numerator_level': 'D200',
      },
      'validation': {
        'sample_count': 15,
        'duplicate_gene_count': 0,
        'duplicate_sample_count': 0,
        'zero_count_samples': const [],
        'missing_metadata_samples': const [],
        'metadata_without_counts': const [],
        'conditions': ['D060', 'D070', 'D090', 'D120', 'D200'],
        'condition_levels_by_factor': {
          'condition': ['D060', 'D070', 'D090', 'D120', 'D200'],
        },
        'count_matrix_dimensions': {
          'genes': 59618,
          'samples': 15,
        },
      },
    },
  };
}

Map<String, dynamic> _singleCellDataset() {
  return {
    'id': 'analysis-dataset:pbmc3k',
    'display_name': 'PBMC 3k (10x public)',
    'modality': 'single_cell_rna_seq',
    'source_type': 'public_geo',
    'cell_count': 30,
    'features_count': 12,
    'source_type': 'server_folder',
    'metadata_summary': {
      'dataset_type': 'single_cell_rna_seq',
      'matrix_format': '10x_mtx',
      'sparse': true,
      'metadata_columns': ['barcode', 'leiden', 'sample'],
      'validation': {
        'cells': 30,
        'genes': 12,
        'median_genes_per_cell': 8,
        'median_counts_per_cell': 54,
        'zero_count_cells': const [],
        'duplicate_barcodes': const [],
        'duplicate_genes': const [],
        'mitochondrial_gene_prefix': 'MT-',
        'warnings': const [],
        'errors': const [],
      },
    },
  };
}

Map<String, dynamic> _exploratoryPublicDataset() {
  return {
    'accession': 'GSE229682',
    'title': 'GSE229682 CPM-only retinal organoids',
    'organism': 'Homo sapiens',
    'tissue': 'Human retinal organoids',
    'sample_count': 15,
    'platform': 'GPL16791 Illumina HiSeq 2500',
    'experimental_groups': ['D060', 'D070', 'D090', 'D120', 'D200'],
    'source_data_kind': 'normalized_cpm',
    'exploratory_only': true,
    'summary': 'Processed CPM table for exploratory visualization.',
    'import_warning':
        'GEO provides CPM values, not raw counts. Mundi imports this dataset as exploratory-only and will not run DESeq2 on rounded CPM values.',
  };
}

Map<String, dynamic> _volcanoOutput() {
  return {
    'id': 'analysis-output:volcano',
    'display_name': 'Volcano Plot',
    'output_type': 'interactive_plot',
    'job_id': 'analysis-job:deseq2',
    'dataset_id': 'analysis-dataset:test',
    'viewer_config': {'plot_subtype': 'volcano'},
    'structured': {
      'plot_type': 'volcano',
      'thresholds': {'alpha': 0.05, 'lfc': 1.0},
      'summary_counts': {
        'upregulated': 1,
        'downregulated': 0,
        'significant total': 1,
      },
      'auto_labels': ['POU4F2'],
      'points': [
        {
          'gene_id': 'POU4F2',
          'x': 1.8,
          'y': 2.0,
          'log2FoldChange': 1.8,
          'neg_log10_padj': 2.0,
          'padj': 0.01,
          'baseMean': 30,
          'significance': 'significant',
          'direction': 'up',
        },
        {
          'gene_id': 'RBPMS',
          'x': 1.2,
          'y': 1.3,
          'log2FoldChange': 1.2,
          'neg_log10_padj': 1.3,
          'padj': 0.05,
          'baseMean': 24,
          'significance': 'not_significant',
          'direction': 'none',
        },
      ],
    },
  };
}

Map<String, dynamic> _maOutput() {
  return {
    'id': 'analysis-output:ma',
    'display_name': 'MA Plot',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'ma',
      'x_scale': 'log10',
      'points': [
        {
          'gene_id': 'POU4F2',
          'x': 1.477,
          'baseMean': 30,
          'y': 1.8,
          'log2FoldChange': 1.8,
          'padj': 0.01,
          'significance': 'significant',
          'direction': 'up',
        },
        {
          'gene_id': 'RBPMS',
          'x': 1.38,
          'baseMean': 24,
          'y': 1.2,
          'log2FoldChange': 1.2,
          'padj': 0.05,
          'significance': 'not significant',
          'direction': 'none',
        },
      ],
    },
  };
}

Map<String, dynamic> _pcaOutput() {
  return {
    'id': 'analysis-output:pca',
    'display_name': 'PCA',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'pca',
      'variance_explained': {'PC1': 0.7, 'PC2': 0.2},
      'color_by': 'condition',
      'condition_levels': ['DMSO', 'SAG'],
      'points': [
        {
          'sample': 'DMSO_1',
          'condition': 'DMSO',
          'PC1': -1.0,
          'PC2': 0.2,
          'metadata': {'condition': 'DMSO'},
        },
        {
          'sample': 'SAG_1',
          'condition': 'SAG',
          'PC1': 1.0,
          'PC2': -0.2,
          'metadata': {'condition': 'SAG'},
        },
      ],
    },
  };
}

Map<String, dynamic> _umapOutput() {
  return {
    'id': 'analysis-output:umap',
    'display_name': 'UMAP Leiden Clusters',
    'output_type': 'embedding',
    'viewer_config': {'plot_subtype': 'umap'},
    'structured': {
      'plot_type': 'umap',
      'x_axis': 'UMAP1',
      'y_axis': 'UMAP2',
      'color_by': 'leiden',
      'condition_levels': ['0', '1'],
      'points': [
        {
          'barcode': 'AAAC-1',
          'cell_id': 'AAAC-1',
          'UMAP1': -1.0,
          'UMAP2': 0.2,
          'leiden': '0',
          'metadata': {'leiden': '0', 'sample': 'PBMC'},
        },
        {
          'barcode': 'TTTG-1',
          'cell_id': 'TTTG-1',
          'UMAP1': 1.1,
          'UMAP2': -0.4,
          'leiden': '1',
          'metadata': {'leiden': '1', 'sample': 'PBMC'},
        },
      ],
    },
  };
}

Map<String, dynamic> _featurePlotOutput() {
  return {
    'id': 'analysis-output:feature-plot',
    'display_name': 'Feature Plot MS4A1',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'feature_plot',
      'x': 'UMAP1',
      'y': 'UMAP2',
      'selected_feature': 'MS4A1',
      'feature_expression': {
        'MS4A1': {'AAAC-1': 2.1, 'TTTG-1': 0.2},
      },
      'points': [
        {
          'barcode': 'AAAC-1',
          'cell_id': 'AAAC-1',
          'x': -1.0,
          'y': 0.2,
          'UMAP1': -1.0,
          'UMAP2': 0.2,
          'leiden': '0',
          'metadata': {'leiden': '0'},
        },
        {
          'barcode': 'TTTG-1',
          'cell_id': 'TTTG-1',
          'x': 1.1,
          'y': -0.4,
          'UMAP1': 1.1,
          'UMAP2': -0.4,
          'leiden': '1',
          'metadata': {'leiden': '1'},
        },
      ],
    },
  };
}

Map<String, dynamic> _sampleDistanceHeatmapOutput() {
  return {
    'id': 'analysis-output:sample-distance',
    'display_name': 'Sample Distance Heatmap',
    'output_type': 'heatmap',
    'structured': {
      'plot_type': 'sample_distance_heatmap',
      'columns': ['sample', 'DMSO_1', 'SAG_1'],
      'clustered': true,
      'transformation': 'Euclidean distance on transformed expression values',
      'rows': [
        {'sample': 'DMSO_1', 'DMSO_1': 0.0, 'SAG_1': 2.195},
        {'sample': 'SAG_1', 'DMSO_1': 2.195, 'SAG_1': 0.0},
      ],
      'row_labels': ['DMSO_1', 'SAG_1'],
      'column_labels': ['DMSO_1', 'SAG_1'],
      'matrix': [
        [0.0, 2.195],
        [2.195, 0.0],
      ],
    },
  };
}

Map<String, dynamic> _topGeneHeatmapOutput() {
  return {
    'id': 'analysis-output:top-genes',
    'display_name': 'Top Gene Heatmap',
    'output_type': 'heatmap',
    'structured': {
      'plot_type': 'top_gene_heatmap',
      'columns': ['gene_id', 'DMSO_1', 'SAG_1'],
      'clustered': true,
      'default_scale': 'row_z_score',
      'transformation': 'Row-wise Z-score of VST values',
      'rows': [
        {'gene_id': 'POU4F2', 'DMSO_1': -1.0, 'SAG_1': 1.0},
        {'gene_id': 'RBPMS', 'DMSO_1': -1.0, 'SAG_1': 1.0},
      ],
      'row_labels': ['POU4F2', 'RBPMS'],
      'column_labels': ['DMSO_1', 'SAG_1'],
      'matrix': [
        [-1.0, 1.0],
        [-1.0, 1.0],
      ],
    },
  };
}

Map<String, dynamic> _markerDotPlotOutput() {
  return {
    'id': 'analysis-output:marker-dotplot',
    'display_name': 'Marker Dot Plot',
    'output_type': 'dot_plot',
    'structured': {
      'plot_type': 'marker_dotplot',
      'clusters': ['0', '1'],
      'genes': ['MS4A1', 'CD3D'],
      'points': [
        {
          'cluster': '0',
          'gene': 'MS4A1',
          'percent_expressing': 0.82,
          'average_scaled_expression': 1.4,
        },
        {
          'cluster': '0',
          'gene': 'CD3D',
          'percent_expressing': 0.18,
          'average_scaled_expression': -0.6,
        },
        {
          'cluster': '1',
          'gene': 'MS4A1',
          'percent_expressing': 0.22,
          'average_scaled_expression': -0.4,
        },
        {
          'cluster': '1',
          'gene': 'CD3D',
          'percent_expressing': 0.78,
          'average_scaled_expression': 1.2,
        },
      ],
      'columns': [
        'cluster',
        'gene',
        'percent_expressing',
        'average_scaled_expression'
      ],
      'rows': [
        {
          'cluster': '0',
          'gene': 'MS4A1',
          'percent_expressing': 0.82,
          'average_scaled_expression': 1.4,
        },
        {
          'cluster': '1',
          'gene': 'CD3D',
          'percent_expressing': 0.78,
          'average_scaled_expression': 1.2,
        },
      ],
    },
  };
}

Map<String, dynamic> _violinOutput() {
  return {
    'id': 'analysis-output:violin',
    'display_name': 'Genes per Cell Violin',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'violin',
      'x': 'leiden',
      'y': 'detected_genes',
      'rows': [
        {
          'group': '0',
          'n': 10,
          'min': 200,
          'q1': 450,
          'median': 700,
          'q3': 900,
          'max': 1200,
        },
        {
          'group': '1',
          'n': 10,
          'min': 180,
          'q1': 420,
          'median': 680,
          'q3': 940,
          'max': 1300,
        },
      ],
    },
  };
}

Map<String, dynamic> _dispersionOutput() {
  return {
    'id': 'analysis-output:dispersion',
    'display_name': 'Dispersion Plot',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'dispersion_plot',
      'x_scale': 'log10',
      'gene_wise': [
        {'x': 1.0, 'mean': 10, 'y': 0.4, 'dispersion': 0.4},
        {'x': 1.3, 'mean': 20, 'y': 0.2, 'dispersion': 0.2},
      ],
      'fitted': [
        {'x': 1.0, 'mean': 10, 'y': 0.32, 'dispersion': 0.32},
        {'x': 1.3, 'mean': 20, 'y': 0.24, 'dispersion': 0.24},
      ],
      'final': [
        {'x': 1.0, 'mean': 10, 'y': 0.36, 'dispersion': 0.36},
        {'x': 1.3, 'mean': 20, 'y': 0.22, 'dispersion': 0.22},
      ],
    },
  };
}

Map<String, dynamic> _librarySizePlotOutput() {
  return {
    'id': 'analysis-output:library-size-plot',
    'display_name': 'Library Size Plot',
    'output_type': 'interactive_plot',
    'structured': {
      'plot_type': 'library_size_plot',
      'columns': ['sample', 'library_size'],
      'rows': [
        {'sample': 'DMSO_1', 'library_size': 115},
        {'sample': 'SAG_1', 'library_size': 159},
      ],
    },
  };
}

http.Response _json(Map<String, dynamic> body) {
  return http.Response(jsonEncode(body), 200, headers: {
    'content-type': 'application/json',
  });
}
