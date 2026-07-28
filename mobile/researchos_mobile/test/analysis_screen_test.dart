import 'dart:convert';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/analysis/viewers/volcano_plot_viewer.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/analysis_screen.dart';
import 'package:researchos_mobile/services/navigation_preferences_service.dart';

void main() {
  test('Analysis destination is discoverable but not in default five', () {
    expect(mundiDestinations.map((item) => item.id), contains('analysis'));
    expect(defaultNavigationDestinationIds, isNot(contains('analysis')));
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
                'status': 'queued',
                'progress': 0,
              }
            });
          }
          return _json({
            'jobs': [
              {
                'id': 'analysis-job:test',
                'workflow_id': 'bulk_rnaseq_validation_qc',
                'status': 'complete',
                'progress': 1,
                'current_stage': 'Complete',
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
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.url.path == '/mobile/analysis/workers') {
          return _json({'workers': const []});
        }
        if (request.url.path == '/mobile/analysis/storage-locations') {
          return _json({'storage_locations': const []});
        }
        if (request.url.path == '/mobile/analysis/demo-library') {
          return _json({'datasets': const []});
        }
        if (request.url.path == '/mobile/analysis/datasets') {
          return _json({'datasets': const []});
        }
        if (request.url.path == '/mobile/analysis/workflows') {
          return _json({'workflows': const []});
        }
        if (request.url.path == '/mobile/analysis/jobs') {
          return _json({'jobs': const []});
        }
        if (request.url.path == '/mobile/analysis/outputs') {
          return _json({
            'outputs': [_volcanoOutput()],
          });
        }
        if (request.url.path == '/mobile/analysis/output-groups') {
          return _json({
            'groups': [
              {
                'dataset': {'display_name': 'Small Retina Bulk'},
                'job': {
                  'id': 'analysis-job:deseq2',
                  'workflow_id': 'bulk_rnaseq_deseq2',
                  'status': 'complete',
                },
                'outputs': [_volcanoOutput()],
              }
            ],
          });
        }
        if (request.url.path ==
            '/mobile/analysis/outputs/analysis-output%3Avolcano') {
          return _json({'output': _volcanoOutput()});
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AnalysisScreen(api: api))),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Volcano Plot'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(
      find
          .ancestor(
              of: find.text('Volcano Plot').last,
              matching: find.byType(ListTile))
          .first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Plot'), findsOneWidget);
    expect(find.text('Data'), findsOneWidget);
    expect(find.byType(VolcanoPlotViewer), findsOneWidget);
    expect(find.byType(ScatterChart), findsOneWidget);
    expect(find.textContaining('points'), findsOneWidget);
    expect(find.text('Export Current View'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, 'POU4F2');
    await tester.pumpAndSettle();
    expect(find.text('1 points'), findsOneWidget);

    await tester.tap(find.text('Data'));
    await tester.pumpAndSettle();
    expect(find.text('POU4F2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

ResearchOsApi _mockAnalysisApi(List<String> calls) {
  return ResearchOsApi(
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
        return _json({
          'jobs': [
            {
              'id': 'analysis-job:test',
              'workflow_id': 'bulk_rnaseq_validation_qc',
              'status': 'complete',
              'progress': 1,
              'current_stage': 'Complete',
            }
          ],
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
      return http.Response('not found', 404);
    }),
  );
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

http.Response _json(Map<String, dynamic> body) {
  return http.Response(jsonEncode(body), 200, headers: {
    'content-type': 'application/json',
  });
}
