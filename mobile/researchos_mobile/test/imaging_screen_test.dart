import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:researchos_mobile/api/researchos_api.dart';
import 'package:researchos_mobile/screens/imaging_screen.dart';

void main() {
  testWidgets('Imaging Hub displays assets, worker status, and queues workflow',
      (tester) async {
    final calls = <String>[];
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path == '/mobile/imaging/assets') {
          return _json({
            'assets': [
              {
                'id': 'imaging-asset:test',
                'original_filename': 'cells.ome.tif',
                'format': 'OME.TIF',
                'size_bytes': 2048,
                'metadata': {
                  'metadata_status': 'unavailable',
                  'channels': 2,
                  'z_slices': 10,
                },
              }
            ],
          });
        }
        if (request.url.path == '/mobile/imaging/jobs') {
          if (request.method == 'POST') {
            return _json({
              'job': {
                'id': 'imaging-job:new',
                'status': 'queued',
                'progress': 0,
              },
            });
          }
          return _json({
            'jobs': [
              {
                'id': 'imaging-job:done',
                'workflow_id': 'generate_preview',
                'status': 'complete',
                'progress': 1,
              }
            ],
          });
        }
        if (request.url.path == '/mobile/imaging/workflows') {
          return _json({
            'workflows': [
              {
                'stable_key': 'generate_preview',
                'name': 'Generate Preview',
                'description': 'Create a visualization PNG.',
              }
            ],
          });
        }
        if (request.url.path == '/mobile/imaging/worker-status') {
          return _json({
            'worker': {
              'status': 'ready',
              'connected': true,
              'fiji_version': 'ImageJ 2.x',
            },
          });
        }
        return _json({});
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: ImagingScreen(api: api))),
    );
    await tester.pumpAndSettle();

    expect(find.text('Imaging Hub'), findsOneWidget);
    expect(find.text('Upload Image'), findsOneWidget);
    expect(find.text('cells.ome.tif'), findsOneWidget);
    expect(find.text('Imaging Worker'), findsOneWidget);
    expect(find.textContaining('Connected / Ready'), findsOneWidget);
    expect(find.text('Search imaging datasets'), findsOneWidget);

    await tester.tap(find.text('cells.ome.tif'));
    await tester.pumpAndSettle();
    expect(find.text('Display'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Run analysis').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Generate Preview'));
    await tester.pumpAndSettle();

    expect(calls, contains('POST /mobile/imaging/jobs'));
    expect(find.textContaining('Could not queue imaging job'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('queued jobs show waiting state when worker is unavailable',
      (tester) async {
    final api = ResearchOsApi(
      baseUrl: 'http://example.test',
      client: MockClient((request) async {
        if (request.url.path == '/mobile/imaging/assets') {
          return _json({'assets': const []});
        }
        if (request.url.path == '/mobile/imaging/jobs') {
          return _json({
            'jobs': [
              {
                'id': 'imaging-job:queued',
                'workflow_id': 'generate_preview',
                'status': 'queued',
                'progress': 0.0,
              }
            ],
          });
        }
        if (request.url.path == '/mobile/imaging/workflows') {
          return _json({'workflows': const []});
        }
        if (request.url.path == '/mobile/imaging/worker-status') {
          return _json({
            'worker': {
              'status': 'unavailable',
              'connected': false,
            },
          });
        }
        return _json({});
      }),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: ImagingScreen(api: api))),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Unavailable'), findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(find.textContaining('Waiting for imaging worker'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

http.Response _json(Map<String, Object?> body) => http.Response(
      jsonEncode(body),
      200,
      headers: {'content-type': 'application/json'},
    );
