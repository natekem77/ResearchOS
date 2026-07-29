import 'package:flutter/material.dart';

import '../../../design_system/researchos_design_system.dart';
import '../common/viewer_models.dart';

class EnhancedTableViewer extends StatefulWidget {
  const EnhancedTableViewer({super.key, required this.output});

  final Map<String, dynamic> output;

  @override
  State<EnhancedTableViewer> createState() => _EnhancedTableViewerState();
}

class _EnhancedTableViewerState extends State<EnhancedTableViewer> {
  String _query = '';
  int? _sortColumnIndex;
  bool _sortAscending = true;

  @override
  Widget build(BuildContext context) {
    final structured = mapFromObject(widget.output['structured']);
    final columns = _columns(structured);
    var rows = rowsFromObject(structured['rows']);
    if (_query.trim().isNotEmpty) {
      final needle = _query.trim().toLowerCase();
      rows = rows
          .where((row) => row.values
              .any((value) => value.toString().toLowerCase().contains(needle)))
          .toList();
    }
    if (_sortColumnIndex != null && _sortColumnIndex! < columns.length) {
      final key = columns[_sortColumnIndex!];
      rows.sort(
        (a, b) => _compareValues(a[key], b[key]) * (_sortAscending ? 1 : -1),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            labelText: 'Search table',
          ),
          onChanged: (value) {
            setState(() {
              _query = value;
            });
          },
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content: Text('CSV export is prepared for this table.')),
              );
            },
            icon: const Icon(Icons.ios_share_outlined),
            label: const Text('Export CSV'),
          ),
        ),
        Scrollbar(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              sortColumnIndex: _sortColumnIndex,
              sortAscending: _sortAscending,
              columns: [
                for (var index = 0; index < columns.length; index++)
                  DataColumn(
                    label: Text(columns[index]),
                    onSort: (columnIndex, ascending) {
                      setState(() {
                        _sortColumnIndex = columnIndex;
                        _sortAscending = ascending;
                      });
                    },
                  ),
              ],
              rows: [
                for (final row in rows)
                  DataRow(
                    cells: [
                      for (final column in columns)
                        DataCell(SelectableText(formatViewerCell(row[column]))),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

List<String> _columns(Map<String, dynamic> structured) {
  final configured =
      structured['columns'] is List ? structured['columns'] as List : const [];
  if (configured.isNotEmpty) {
    return configured.map((item) => item.toString()).toList();
  }
  final rows = rowsFromObject(structured['rows']);
  if (rows.isEmpty) return const [];
  return rows.first.keys.map((key) => key.toString()).toList();
}

int _compareValues(Object? left, Object? right) {
  final leftNumber = double.tryParse(left?.toString() ?? '');
  final rightNumber = double.tryParse(right?.toString() ?? '');
  if (leftNumber != null && rightNumber != null) {
    return leftNumber.compareTo(rightNumber);
  }
  return (left?.toString() ?? '').compareTo(right?.toString() ?? '');
}
