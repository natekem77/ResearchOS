import 'package:flutter/material.dart';

class HeatmapController extends ChangeNotifier {
  bool _showValues = true;
  String? _selectedCellLabel;

  bool get showValues => _showValues;
  String? get selectedCellLabel => _selectedCellLabel;

  void setShowValues(bool value) {
    _showValues = value;
    notifyListeners();
  }

  void selectCell(String label) {
    _selectedCellLabel = label;
    notifyListeners();
  }
}
