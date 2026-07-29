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
        if (rows.length > 500)
          Expanded(
            child: _VirtualizedTable(
              columns: columns,
              rows: rows,
              sortColumnIndex: _sortColumnIndex,
              sortAscending: _sortAscending,
              onSort: (columnIndex, ascending) {
                setState(() {
                  _sortColumnIndex = columnIndex;
                  _sortAscending = ascending;
                });
              },
            ),
          )
        else
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
                          DataCell(
                              SelectableText(formatViewerCell(row[column]))),
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

class _VirtualizedTable extends StatelessWidget {
  const _VirtualizedTable({
    required this.columns,
    required this.rows,
    required this.sortColumnIndex,
    required this.sortAscending,
    required this.onSort,
  });

  final List<String> columns;
  final List<Map<String, dynamic>> rows;
  final int? sortColumnIndex;
  final bool sortAscending;
  final void Function(int columnIndex, bool ascending) onSort;

  @override
  Widget build(BuildContext context) {
    const cellWidth = 148.0;
    const rowHeight = 44.0;
    return Scrollbar(
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SizedBox(
          width: cellWidth * columns.length,
          child: Column(
            children: [
              SizedBox(
                height: rowHeight,
                child: Row(
                  children: [
                    for (var index = 0; index < columns.length; index++)
                      InkWell(
                        onTap: () => onSort(
                          index,
                          sortColumnIndex == index ? !sortAscending : true,
                        ),
                        child: Container(
                          width: cellWidth,
                          height: rowHeight,
                          alignment: Alignment.centerLeft,
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          decoration: BoxDecoration(
                            border: Border(
                              bottom: BorderSide(
                                color: Theme.of(context)
                                    .colorScheme
                                    .outlineVariant,
                              ),
                            ),
                          ),
                          child: Text(
                            '${columns[index]}'
                            '${sortColumnIndex == index ? (sortAscending ? ' ↑' : ' ↓') : ''}',
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.labelMedium,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                child: ListView.builder(
                  itemCount: rows.length,
                  itemExtent: rowHeight,
                  itemBuilder: (context, rowIndex) => Row(
                    children: [
                      for (final column in columns)
                        Container(
                          width: cellWidth,
                          alignment: Alignment.centerLeft,
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          decoration: BoxDecoration(
                            border: Border(
                              bottom: BorderSide(
                                color: Theme.of(context)
                                    .colorScheme
                                    .outlineVariant
                                    .withValues(alpha: 0.5),
                              ),
                            ),
                          ),
                          child: SelectableText(
                            formatViewerCell(rows[rowIndex][column]),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
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
