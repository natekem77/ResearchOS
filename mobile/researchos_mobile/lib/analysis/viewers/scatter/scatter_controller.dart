import 'package:flutter/material.dart';

import '../common/viewer_models.dart';

class ScatterController extends ChangeNotifier {
  String _query = '';
  String? _selectedId;
  bool _showLabels = false;
  bool _hideUnselectedCategories = false;

  String get query => _query;
  String? get selectedId => _selectedId;
  bool get showLabels => _showLabels;
  bool get hideUnselectedCategories => _hideUnselectedCategories;

  set query(String value) {
    _query = value;
    if (value.trim().isNotEmpty) _selectedId = value.trim();
    notifyListeners();
  }

  void select(ScatterPointModel point) {
    _selectedId = point.id;
    notifyListeners();
  }

  void setShowLabels(bool value) {
    _showLabels = value;
    notifyListeners();
  }

  void setHideUnselectedCategories(bool value) {
    _hideUnselectedCategories = value;
    notifyListeners();
  }

  void reset() {
    _query = '';
    _selectedId = null;
    _showLabels = false;
    _hideUnselectedCategories = false;
    notifyListeners();
  }
}
