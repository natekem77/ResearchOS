import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
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
              {
                'id': 'analysis-output:test',
                'display_name': 'Bulk RNA-seq QC Report',
                'output_type': 'qc_report',
                'structured': {
                  'summary': {'sample_count': 3, 'feature_count': 4},
                },
              }
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
    expect(find.text('Lab Analysis Server'), findsOneWidget);
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
    await tester.tap(find.text('Run QC'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Open Results'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Open Results'));
    await tester.pumpAndSettle();

    expect(find.text('Bulk RNA-seq QC Report'), findsOneWidget);
    expect(calls, contains('POST /mobile/analysis/jobs'));
    expect(tester.takeException(), isNull);
  });
}

http.Response _json(Map<String, dynamic> body) {
  return http.Response(jsonEncode(body), 200, headers: {
    'content-type': 'application/json',
  });
}
